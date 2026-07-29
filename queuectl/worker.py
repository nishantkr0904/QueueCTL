"""
worker.py — Worker execution engine for QueueCTL.

This module is responsible for:
  1. Running a single worker that claims and executes jobs.
  2. Registering and deregistering workers in the database.
  3. Handling graceful shutdown on SIGINT / SIGTERM.
  4. Retrying failed jobs with exponential backoff.
  5. Moving permanently failed jobs to the Dead Letter Queue (state='dead').

The worker does NOT implement its own claiming logic.  It delegates
all job claiming to claim_job() in storage.py, which uses
BEGIN IMMEDIATE for atomic, cross-process-safe claiming.

The worker does NOT implement heartbeat or continuous polling.
Those belong to later phases.
"""

import os
import signal
import subprocess
import time

from queuectl.models import (
    STATE_COMPLETED, STATE_DEAD, STATE_FAILED, STATE_PENDING, _now_utc,
)
from queuectl.storage import claim_job, update_job


# ---------------------------------------------------------------------------
# Backoff constant
# ---------------------------------------------------------------------------
# Default base for exponential backoff:  delay = base ^ attempts  seconds.
# With base=2:  first retry after 2s, second after 4s, third after 8s.
# This will become configurable via `config set backoff-base` in a later
# phase.  For now, we use the default value from INSTRUCTIONS.md.

DEFAULT_BACKOFF_BASE = 2


# ---------------------------------------------------------------------------
# Graceful shutdown flag
# ---------------------------------------------------------------------------
# When SIGINT or SIGTERM is received, this flag is set to True.
# The worker checks it between jobs and will NOT claim a new job
# if shutdown has been requested.  However, the currently executing
# job is always allowed to finish — we never kill a subprocess
# mid-execution.

_shutdown_requested = False


def _handle_shutdown_signal(signum, frame):
    """
    Signal handler for SIGINT (Ctrl+C) and SIGTERM.

    Sets the global shutdown flag so the worker loop exits gracefully
    after the current job finishes.  We do NOT raise an exception or
    call sys.exit() here because that would interrupt a running
    subprocess and leave the job in an inconsistent state.
    """
    global _shutdown_requested
    _shutdown_requested = True


# ---------------------------------------------------------------------------
# Crash Recovery
# ---------------------------------------------------------------------------

def perform_crash_recovery(connection):
    """
    Detect and recover orphaned jobs from crashed workers.

    Steps:
      1. Fetch all registered worker PIDs.
      2. Check if each PID is still alive. If not, remove its registration.
      3. Recover any jobs left in 'processing' by those stale workers.

    Args:
        connection: An open sqlite3.Connection.
    """
    from queuectl.storage import (
        get_all_worker_pids,
        remove_worker_registration,
        recover_orphaned_jobs,
    )

    # 1. Remove stale worker registrations
    active_pids = get_all_worker_pids(connection)
    for pid in active_pids:
        is_alive = True
        try:
            # os.kill(pid, 0) checks if the process exists
            os.kill(pid, 0)
        except OSError:
            is_alive = False
            
        if not is_alive:
            remove_worker_registration(connection, pid)
            
    # 2. Recover orphaned jobs
    # Now that stale workers are removed, any job in 'processing' whose worker_id
    # is not in the active workers table is an orphaned job.
    recover_orphaned_jobs(connection)



# ---------------------------------------------------------------------------
# Worker registration
# ---------------------------------------------------------------------------
# Workers register themselves in the 'workers' table when they start
# and remove their entry when they exit normally.  This lets other
# parts of the system (e.g., worker stop, crash recovery) know which
# workers are currently alive.

def register_worker(connection, pid):
    """
    Register a worker process in the database.

    Args:
        connection: An open sqlite3.Connection.
        pid:        The worker's OS process ID.

    Notes:
        The heartbeat_at column is set to the current time on
        registration.  Heartbeat updates are not implemented yet —
        that belongs to the crash recovery phase.
    """
    now = _now_utc()
    connection.execute(
        "INSERT OR REPLACE INTO workers (pid, started_at, heartbeat_at) "
        "VALUES (?, ?, ?)",
        (pid, now, now),
    )
    connection.commit()


def deregister_worker(connection, pid):
    """
    Remove a worker's registration from the database.

    Called when a worker exits normally (all jobs done or shutdown
    signal received).  If the worker is killed (SIGKILL), this
    never runs — crash recovery will clean up the stale row later.

    Args:
        connection: An open sqlite3.Connection.
        pid:        The worker's OS process ID.
    """
    connection.execute(
        "DELETE FROM workers WHERE pid = ?",
        (pid,),
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

def execute_job(connection, job):
    """
    Execute a claimed job's shell command and update its final state.

    This function runs the job's command using subprocess.run(),
    waits for it to finish, and then updates the job state based
    on the exit code:
      - exit code 0   → state = 'completed'
      - exit code ≠ 0 → state = 'failed', then retry logic applies

    Retry logic (on failure):
      1. Increment the attempts counter.
      2. If attempts <= max_retries, set state back to 'pending'
         so the job can be picked up again after its backoff delay.
      3. If attempts > max_retries, move the job to the Dead Letter
         Queue (state = 'dead').

    The command is executed via the operating system's shell
    (shell=True) because job commands are user-provided shell
    strings like "echo hello" or "sleep 2 && echo done".

    Args:
        connection: An open sqlite3.Connection.
        job:        A Job instance that has already been claimed
                    (state = 'processing').
    """
    # Run the shell command.  subprocess.run() blocks until the
    # command finishes, which is exactly what we want — simple,
    # synchronous execution.
    result = subprocess.run(
        job.command,
        shell=True,
        capture_output=True,
    )

    # Clear worker_id — this worker is done with the job.
    # (The worker_id was set during claiming; clearing it makes
    # the final state cleaner and avoids confusion later.)
    job.worker_id = None

    if result.returncode == 0:
        # --- Success ---
        job.state = STATE_COMPLETED
    else:
        # --- Failure: apply retry logic ---
        job.attempts += 1

        if job.attempts <= job.max_retries:
            # Retries remain — move the job back to 'pending'.
            # The updated_at timestamp (set by update_job below)
            # records WHEN this failure happened.  claim_job()
            # uses updated_at to enforce the backoff delay:
            # a pending job with attempts > 0 won't be claimed
            # until  updated_at + (base ^ attempts)  has passed.
            job.state = STATE_PENDING
        else:
            # All retries exhausted — move to the Dead Letter Queue.
            # The job stays in the same database row with state='dead'.
            # It can be re-enqueued later via `queuectl dlq retry`.
            job.state = STATE_DEAD

    # Persist the final state.  update_job() automatically
    # refreshes the updated_at timestamp.
    update_job(connection, job)


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def run_worker(connection):
    """
    Main worker loop: claim jobs and execute them until
    a shutdown signal is received.

    The loop continuously polls for work:
      1. Check if shutdown was requested → if yes, exit.
      2. Perform crash recovery to clean up any orphaned jobs.
      3. Try to claim the oldest pending job via claim_job().
      4. If no job was available → sleep briefly and try again.
      5. Execute the claimed job and update its state.
      6. Go back to step 1.

    Args:
        connection: An open sqlite3.Connection.
    """
    pid = os.getpid()

    while True:
        # --- Check for shutdown before claiming a new job ---
        # If SIGINT/SIGTERM was received during the last job's
        # execution, we stop here instead of claiming more work.
        if _shutdown_requested:
            break
            
        # --- Recover orphaned jobs ---
        # If any other worker crashed, this will reset their
        # processing jobs back to pending.
        perform_crash_recovery(connection)

        # --- Try to claim the next pending job ---
        # claim_job() handles all concurrency safety internally.
        # It returns a Job if one was claimed, or None if the
        # queue is empty (or another worker won the race).
        job = claim_job(connection, worker_id=pid)

        if job is None:
            # No pending jobs — wait briefly before polling again.
            time.sleep(0.5)
            continue

        # --- Execute the job ---
        # This runs the shell command synchronously and updates
        # the job state in the database when it finishes.
        execute_job(connection, job)
