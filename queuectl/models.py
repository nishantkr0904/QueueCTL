"""
models.py — Job data model for QueueCTL.

This module defines:
  1. State constants for the job lifecycle.
  2. The Job class — a plain Python object that represents a single job.
  3. Conversion helpers to move between Job objects and SQLite rows.

No database access happens here. This module only defines *what* a job
looks like; storage.py handles *where* it lives.
"""

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Job state constants
# ---------------------------------------------------------------------------
# These match the lifecycle defined in ARCHITECTURE.md (Section 4).
# Using constants avoids typos when comparing states across the codebase.

STATE_PENDING = "pending"          # Waiting to be picked up by a worker.
STATE_PROCESSING = "processing"    # A worker has claimed it and is running it.
STATE_COMPLETED = "completed"      # Command exited with code 0 — success.
STATE_FAILED = "failed"            # Command exited with non-zero code.
STATE_DEAD = "dead"                # All retries exhausted — in the DLQ.

# A tuple of every valid state, useful for validation.
VALID_STATES = (
    STATE_PENDING,
    STATE_PROCESSING,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_DEAD,
)

# Default maximum number of retries before a job moves to the DLQ.
DEFAULT_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------

def _now_utc():
    """
    Return the current UTC time as an ISO 8601 string.

    Example: '2025-11-04T10:30:00Z'

    This format matches the job specification in INSTRUCTIONS.md and is
    human-readable in both the database and JSON output.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------

class Job:
    """
    Represents a single background job in the queue.

    Every field maps directly to a column in the 'jobs' SQLite table.
    The class is intentionally simple — just a container for data with
    a couple of helper methods for conversion.

    Attributes:
        id          (str):  Unique identifier for the job.
        command     (str):  Shell command to execute.
        state       (str):  Current lifecycle state (see STATE_* constants).
        attempts    (int):  How many times execution has been attempted.
        max_retries (int):  Maximum retry count before moving to the DLQ.
        created_at  (str):  ISO 8601 timestamp — when the job was enqueued.
        updated_at  (str):  ISO 8601 timestamp — last state change.
        worker_id   (int):  PID of the worker currently processing this job,
                            or None if no worker has claimed it.
        started_at  (str):  ISO 8601 timestamp — when execution started,
                            or None if not yet started.
    """

    def __init__(self, id, command, state=STATE_PENDING, attempts=0,
                 max_retries=DEFAULT_MAX_RETRIES, created_at=None,
                 updated_at=None, worker_id=None, started_at=None):
        """
        Create a new Job instance.

        Args:
            id:          Unique job identifier (provided by the user).
            command:     Shell command the worker will execute.
            state:       Initial state (defaults to 'pending').
            attempts:    Number of execution attempts so far (defaults to 0).
            max_retries: Max retries before DLQ (defaults to 3).
            created_at:  Creation timestamp. Auto-generated if not provided.
            updated_at:  Last-update timestamp. Auto-generated if not provided.
            worker_id:   PID of the claiming worker (None until claimed).
            started_at:  When execution began (None until started).
        """
        self.id = id
        self.command = command
        self.state = state
        self.attempts = attempts
        self.max_retries = max_retries
        self.created_at = created_at or _now_utc()
        self.updated_at = updated_at or _now_utc()
        self.worker_id = worker_id
        self.started_at = started_at

    def to_dict(self):
        """
        Convert this Job to a plain dictionary.

        This is used for JSON serialisation — the `queuectl list --json`
        command needs to output job objects as JSON, and json.dumps()
        works with dicts but not custom objects.

        Returns:
            A dict with all job fields. Keys match the column names in
            the database and the field names in the assignment spec.
        """
        return {
            "id": self.id,
            "command": self.command,
            "state": self.state,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "worker_id": self.worker_id,
            "started_at": self.started_at,
        }

    @staticmethod
    def from_row(row):
        """
        Create a Job instance from a SQLite row (a tuple).

        The column order must match the order used in SELECT statements
        in storage.py. That order is:
            id, command, state, attempts, max_retries,
            created_at, updated_at, worker_id, started_at

        Args:
            row: A tuple of 9 values from a SQLite query.

        Returns:
            A Job instance populated with the row's data.
        """
        return Job(
            id=row[0],
            command=row[1],
            state=row[2],
            attempts=row[3],
            max_retries=row[4],
            created_at=row[5],
            updated_at=row[6],
            worker_id=row[7],
            started_at=row[8],
        )

    def __repr__(self):
        """
        Developer-friendly string representation for debugging.

        Example: Job(id='job1', state='pending', attempts=0)
        """
        return (
            f"Job(id={self.id!r}, state={self.state!r}, "
            f"attempts={self.attempts})"
        )
