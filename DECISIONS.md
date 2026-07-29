# Decisions

This document outlines the architectural decisions made during the development of QueueCTL.

### 1. Which exact line(s) prevent two workers from claiming the same job, and why is that operation atomic across separate OS processes?

In `queuectl/storage.py`, inside the `claim_job` function, the exact lines are:
```python
connection.execute("BEGIN IMMEDIATE")
# ... followed by ...
cursor = connection.execute(
    f"SELECT {_JOB_COLUMNS} FROM jobs WHERE state = 'pending' ... ORDER BY created_at ASC LIMIT 1"
)
# ... followed by ...
cursor = connection.execute(
    "UPDATE jobs SET state = 'processing', worker_id = ?, updated_at = ? WHERE id = ? AND state = 'pending'",
    (worker_pid, now, job.id),
)
```
**Why it's atomic:** `BEGIN IMMEDIATE` acquires a database-wide SQLite write lock instantly. No other process can begin a write transaction (or claim a job) until the current transaction commits or rolls back. This prevents race conditions globally across all separate OS processes interacting with the same SQLite file.

### 2. A worker is SIGKILLed halfway through a job. Walk through, step by step, what state the job is in and how it eventually runs again. What is the worst-case delay before recovery?

1. **State:** When a worker is forcefully terminated via `SIGKILL`, the job is left stuck in the `processing` state in the database, and the crashed worker's PID remains in the `workers` table (since no cleanup handler could run).
2. **Detection:** When the next worker starts up, it immediately runs the `perform_crash_recovery()` routine.
3. **Verification:** The new worker fetches all PIDs from the `workers` table and verifies their liveness using `os.kill(pid, 0)`. It detects the crashed worker's PID is no longer running and deletes its row from the `workers` table.
4. **Recovery:** The new worker queries the `jobs` table for any jobs in `processing` whose `worker_id` no longer exists in the active `workers` table. It resets these jobs back to `pending`.
5. **Worst-case delay:** The recovery executes instantly upon the next worker's startup sequence.

### 3. Does dlq retry reset attempts? Why is that the right call?

Yes, `queuectl dlq retry <id>` resets `attempts` to `0` (and `state` to `pending`). 
This is the right call because:
- dlq retry starts a new execution lifecycle.
- attempts is reset to 0 before the job is re-enqueued.
- This gives the job its full retry budget again.
- The previous failed lifecycle remains represented by the fact that the job previously reached the Dead Letter Queue.

### 4. What designs did you consider and reject for worker stop (cross-process signaling), and why?

- **Rejected:** Inter-Process Communication (IPC) pipes, TCP/UDP sockets, or a dedicated background daemon. These were rejected because they introduce massive architectural complexity and third-party dependencies, violating the constraint to keep the project beginner-friendly and reliant only on the Python standard library.
- **Rejected:** A "stop requested" database polling mechanism. This would introduce unnecessary I/O overhead as workers would need to constantly poll the DB while executing a shell command.
- **Chosen:** A simple OS-level signaling mechanism (`os.kill(pid, signal.SIGTERM)`). Since workers already write their PIDs to the `workers` table upon startup, the CLI can easily read the active PIDs and natively signal the OS to gracefully terminate the target processes.

### 5. If priorities were added tomorrow (high-priority jobs jump the queue), which parts of your design survive unchanged and which break?

**Survive Unchanged:**
- The worker execution loop (`run_worker`)
- The atomic locking mechanism (`BEGIN IMMEDIATE`)
- The retry and exponential backoff calculations
- Crash recovery and DLQ operations
- Job signaling and graceful shutdown

**Break / Require Modification:**
- **Database Schema:** The `jobs` table would need a new `priority` integer column.
- **`claim_job()` Query:** The `ORDER BY` clause in `storage.py` would need to change from `ORDER BY created_at ASC` to `ORDER BY priority DESC, created_at ASC` to ensure high-priority jobs are claimed first.
- **`enqueue` Command:** The CLI and `Job` model would need to accept and parse a new `--priority` flag.
