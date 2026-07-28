"""
storage.py — Job persistence layer for QueueCTL.

This module provides all database operations for jobs:
  1. Insert a new job.
  2. Fetch a single job by ID.
  3. List jobs (all, or filtered by state).
  4. Update a job's fields.
  5. Delete a job by ID.
  6. Atomically claim the next pending job for a worker.
  7. Enforce exponential backoff for retried jobs during claiming.

Every function takes a sqlite3.Connection as its first argument.
This module never opens or closes connections itself — that is
the responsibility of db.py.

Column order convention:
    All SELECT queries return columns in this order:
        id, command, state, attempts, max_retries,
        created_at, updated_at, worker_id, started_at
    This must match Job.from_row() in models.py.
"""

from queuectl.models import Job, _now_utc


# ---------------------------------------------------------------------------
# The column order used in every SELECT query. Defined once here so that
# if a column is added to the schema, there is exactly one place to update.
# ---------------------------------------------------------------------------
_JOB_COLUMNS = (
    "id, command, state, attempts, max_retries, "
    "created_at, updated_at, worker_id, started_at"
)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def insert_job(connection, job):
    """
    Insert a new job into the database.

    Args:
        connection: An open sqlite3.Connection.
        job:        A Job instance to persist.

    Raises:
        sqlite3.IntegrityError: If a job with the same ID already exists.
            The 'id' column is the primary key, so duplicates are rejected
            by SQLite automatically.

    Notes:
        The insert is committed immediately so the job is visible to
        other processes (e.g., workers polling for pending jobs) right away.
    """
    connection.execute(
        """
        INSERT INTO jobs (id, command, state, attempts, max_retries,
                          created_at, updated_at, worker_id, started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.id,
            job.command,
            job.state,
            job.attempts,
            job.max_retries,
            job.created_at,
            job.updated_at,
            job.worker_id,
            job.started_at,
        ),
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Read — single job
# ---------------------------------------------------------------------------

def get_job_by_id(connection, job_id):
    """
    Fetch a single job by its unique ID.

    Args:
        connection: An open sqlite3.Connection.
        job_id:     The job's unique identifier string.

    Returns:
        A Job instance if found, or None if no job with that ID exists.
    """
    cursor = connection.execute(
        f"SELECT {_JOB_COLUMNS} FROM jobs WHERE id = ?",
        (job_id,),
    )
    row = cursor.fetchone()

    # fetchone() returns None when no matching row is found.
    if row is None:
        return None

    return Job.from_row(row)


# ---------------------------------------------------------------------------
# Read — multiple jobs
# ---------------------------------------------------------------------------

def get_all_jobs(connection):
    """
    Fetch every job in the database.

    Args:
        connection: An open sqlite3.Connection.

    Returns:
        A list of Job instances. May be empty if no jobs exist yet.
    """
    cursor = connection.execute(
        f"SELECT {_JOB_COLUMNS} FROM jobs ORDER BY created_at"
    )
    rows = cursor.fetchall()

    return [Job.from_row(row) for row in rows]


def get_jobs_by_state(connection, state):
    """
    Fetch all jobs that are in a given state.

    Args:
        connection: An open sqlite3.Connection.
        state:      One of the STATE_* constants from models.py
                    (e.g., 'pending', 'failed', 'dead').

    Returns:
        A list of Job instances in the requested state. May be empty.
    """
    cursor = connection.execute(
        f"SELECT {_JOB_COLUMNS} FROM jobs WHERE state = ? ORDER BY created_at",
        (state,),
    )
    rows = cursor.fetchall()

    return [Job.from_row(row) for row in rows]


def count_jobs_by_state(connection):
    """
    Count how many jobs are in each state.

    This is used by the 'queuectl status' command to show a summary
    without loading every job into memory.

    Args:
        connection: An open sqlite3.Connection.

    Returns:
        A dict mapping state strings to counts.
        Example: {'pending': 5, 'processing': 2, 'completed': 10}
        States with zero jobs are not included in the dict.
    """
    cursor = connection.execute(
        "SELECT state, COUNT(*) FROM jobs GROUP BY state"
    )
    rows = cursor.fetchall()

    # Build a dict from the (state, count) pairs returned by GROUP BY.
    return {row[0]: row[1] for row in rows}


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_job(connection, job):
    """
    Update an existing job's fields in the database.

    This overwrites every column except 'id' (the primary key) and
    'created_at' (which should never change after insertion).

    The 'updated_at' timestamp is automatically set to the current
    UTC time so callers don't need to remember to do it.

    Args:
        connection: An open sqlite3.Connection.
        job:        A Job instance with the updated field values.
                    The job.id must match an existing row.

    Returns:
        True if a row was updated, False if no job with that ID exists.
    """
    # Always refresh updated_at when saving changes.
    job.updated_at = _now_utc()

    cursor = connection.execute(
        """
        UPDATE jobs
        SET command     = ?,
            state       = ?,
            attempts    = ?,
            max_retries = ?,
            updated_at  = ?,
            worker_id   = ?,
            started_at  = ?
        WHERE id = ?
        """,
        (
            job.command,
            job.state,
            job.attempts,
            job.max_retries,
            job.updated_at,
            job.worker_id,
            job.started_at,
            job.id,
        ),
    )
    connection.commit()

    # cursor.rowcount tells us how many rows were affected.
    # It will be 0 if no row with that ID exists.
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_job(connection, job_id):
    """
    Delete a job from the database by its ID.

    Args:
        connection: An open sqlite3.Connection.
        job_id:     The job's unique identifier string.

    Returns:
        True if a row was deleted, False if no job with that ID existed.
    """
    cursor = connection.execute(
        "DELETE FROM jobs WHERE id = ?",
        (job_id,),
    )
    connection.commit()

    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Claim — atomic job claiming
# ---------------------------------------------------------------------------

def claim_job(connection, worker_id):
    """
    Atomically claim the oldest pending job for a worker.

    This is the core concurrency-safety mechanism of QueueCTL.
    It ensures that no two workers — even across completely separate
    OS processes — can ever claim the same job.

    Args:
        connection: An open sqlite3.Connection.
        worker_id:  The PID of the worker claiming the job.

    Returns:
        A Job instance if a job was successfully claimed, or
        None if no pending jobs are available (or another worker
        won the race).

    Transaction design:
        The entire claim happens inside a single SQLite transaction
        using BEGIN IMMEDIATE.  This is critical for correctness:

        1. BEGIN IMMEDIATE acquires the database write lock *before*
           any reads.  A regular BEGIN (deferred) would only acquire
           the lock at write time, leaving a window where two workers
           could both SELECT the same pending job and then race on
           the UPDATE.  BEGIN IMMEDIATE closes that window.

        2. SELECT finds the oldest pending job (ORDER BY created_at
           ASC LIMIT 1).

        3. UPDATE transitions the job to 'processing', but includes
           AND state = 'pending' as a guard.  Even though we just
           selected a pending row, this guard protects against any
           edge case where the row's state changed between the
           SELECT and UPDATE (defence in depth).

        4. cursor.rowcount is checked — if it is 1, the claim
           succeeded and we COMMIT.  If it is 0, another worker
           won the race (or the job's state changed), so we
           ROLLBACK and return None.

        The transaction is intentionally very short: only a SELECT
        and an UPDATE.  Job execution (running the shell command)
        MUST happen OUTSIDE this transaction — never hold the
        database write lock while running a potentially long
        subprocess.

    Crash recovery preparation:
        After a successful claim the job row contains:
          - state      = 'processing'
          - worker_id  = the claiming worker's PID
          - updated_at = current UTC timestamp
        Later phases will use these fields to detect orphaned jobs
        when a worker crashes (SIGKILL) without cleaning up.
    """
    now = _now_utc()

    # --- Step 1: Begin an IMMEDIATE transaction ---
    # This acquires the SQLite write lock right away, preventing
    # any other process from starting a conflicting write
    # transaction until we COMMIT or ROLLBACK.
    connection.execute("BEGIN IMMEDIATE")

    try:
        # --- Step 2: Find the oldest ELIGIBLE pending job ---
        # A pending job is eligible if:
        #   a) It has never been attempted (attempts = 0) — fresh job,
        #      no backoff needed.
        #   b) It has been attempted before (attempts > 0) AND enough
        #      time has passed since its last failure.  The required
        #      delay is: backoff_base ^ attempts  seconds.
        #
        # We compute the eligibility cutoff using SQLite's datetime()
        # function:  updated_at + delay  must be <= the current time.
        # The '+N seconds' modifier adds the backoff delay directly
        # in the SQL query, so ineligible jobs are never even selected.
        #
        # Import here to avoid circular imports (worker → storage → worker).
        # This is a simple constant lookup, not heavy logic.
        from queuectl.worker import DEFAULT_BACKOFF_BASE

        cursor = connection.execute(
            f"SELECT {_JOB_COLUMNS} FROM jobs "
            "WHERE state = 'pending' "
            "  AND ("
            "        attempts = 0"
            "     OR datetime(updated_at, '+' || CAST(ROUND(POW(?, attempts)) AS INTEGER) || ' seconds') <= datetime(?)"
            "  ) "
            "ORDER BY created_at ASC "
            "LIMIT 1",
            (DEFAULT_BACKOFF_BASE, now),
        )
        row = cursor.fetchone()

        # No pending jobs available — nothing to claim.
        if row is None:
            connection.execute("ROLLBACK")
            return None

        job = Job.from_row(row)

        # --- Step 3: Guarded update — claim the job ---
        # The WHERE clause includes AND state = 'pending' as a
        # safety net.  If something unexpected changed the state
        # between our SELECT and this UPDATE, rowcount will be 0
        # and we know the claim failed.
        cursor = connection.execute(
            """
            UPDATE jobs
            SET state      = 'processing',
                worker_id  = ?,
                updated_at = ?
            WHERE id = ?
              AND state = 'pending'
            """,
            (worker_id, now, job.id),
        )

        # --- Step 4: Verify the claim ---
        if cursor.rowcount == 0:
            # Another worker claimed this job between our SELECT
            # and UPDATE (race lost).  Roll back and signal the
            # caller that no job was claimed.
            connection.execute("ROLLBACK")
            return None

        # --- Step 5: Commit — the job is now ours ---
        connection.execute("COMMIT")

        # Update the in-memory Job object to reflect the new state
        # so the caller sees the claimed job accurately.
        job.state = "processing"
        job.worker_id = worker_id
        job.updated_at = now

        return job

    except Exception:
        # If anything goes wrong, always release the write lock.
        connection.execute("ROLLBACK")
        raise
