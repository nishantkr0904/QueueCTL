# QueueCTL

QueueCTL is a minimal, production-grade CLI-based background job queue system built with Python and SQLite. It handles concurrent background tasks, automated exponential backoff retries, dead-letter queues, and crash recovery with no external daemons or heavy message brokers.

---

## Features

- **Enqueue:** Add background jobs via a simple JSON payload in the CLI.
- **Worker Execution:** Run background jobs automatically in separate foreground processes.
- **Retry:** Automatically retry failed jobs multiple times.
- **Exponential Backoff:** Wait progressively longer between each retry attempt.
- **Dead Letter Queue (DLQ):** Permanently failed jobs are stored for manual inspection and manual retry.
- **Crash Recovery:** Workers that are forcefully killed (`SIGKILL`) leave orphaned jobs. These jobs are detected and automatically recovered on the next worker startup.
- **Worker Stop:** Gracefully stop all running worker processes across terminals by sending `SIGTERM`.
- **Configuration Management:** Manage configuration like maximum retry limits and backoff timing persistently via the CLI.

---

## Architecture Overview

QueueCTL operates entirely through a shared SQLite database with the following flow:

**CLI** 
↓ (Validates and parses user commands)
**Storage** 
↓ (Translates CLI intents into safe database operations, including atomic job claims)
**SQLite** 
↓ (Persists jobs, configurations, and worker metadata safely via OS-level locking)
**Workers**
(Poll the DB, securely lock jobs, execute shell commands, and push the final state back)

---

## Project Structure

- **`queuectl/`**: The core application source code.
  - `main.py`: CLI entry point.
  - `cli.py`: Defines the Click-based command line interface and logic.
  - `models.py`: Defines the `Job` data model and state constants.
  - `storage.py`: Handles all database operations, including the atomic `claim_job` locking mechanism.
  - `worker.py`: Manages the worker polling loop, subprocess execution, and graceful shutdown signal handlers.
  - `db.py`: Bootstraps SQLite tables and connections.
- **`data/`**: Runtime storage for the local `jobs.db` database.
- **`docs/`**: Internal documentation for the architecture and roadmap.

---

## Requirements

- **Python:** 3.8+
- **SQLite:** 3.0+
- **Standard Library:** Heavily utilizes Python's built-in `sqlite3`, `subprocess`, and `os` modules.
- **Click:** The only third-party dependency for CLI framework (`pip install click`).

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/nishantkr0904/QueueCTL.git
cd QueueCTL

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install requirements
pip install -r requirements.txt

# 4. Initialize the database and test basic functionality
python3 -m queuectl.main status
```
*(Note: QueueCTL auto-initializes the database upon running any valid command for the first time.)*

---

## Usage Examples

**Add a new job to the queue:**
```bash
python -m queuectl.main enqueue '{"id": "job1", "command": "echo Hello World"}'
```

**Start a single foreground worker:**
```bash
python -m queuectl.main worker start
```

**Start multiple parallel workers (forks 4 processes):**
```bash
python -m queuectl.main worker start --count 4
```

**Gracefully stop all running workers from another terminal:**
```bash
python -m queuectl.main worker stop
```

**List all dead-lettered jobs:**
```bash
python -m queuectl.main dlq list
```

**Manually retry a dead-lettered job:**
```bash
python -m queuectl.main dlq retry job1
```

**Configure the default max retries for new jobs:**
```bash
python -m queuectl.main config set max-retries 5
```

**Configure the exponential backoff base delay:**
```bash
python -m queuectl.main config set backoff-base 3
```

---

## Job Lifecycle

A job traverses through the following states:

1. **pending** (Waiting for a worker)
   ↓
2. **processing** (Claimed by a worker and executing)
   ↓
3. **completed** (Exited with code 0)

*Or if it fails:*
3. **pending (retry)** (Exited with non-zero code, attempts incremented)
   ↓
4. **dead** (Exhausted all retries, moved to DLQ)
   ↓
5. **pending (manual retry)** (Engineer ran `dlq retry`, attempts reset to 0)

---

## Important Implementation Decisions

For a full breakdown, see `DECISIONS.md`.

- **Atomic Job Claiming:** Accomplished directly via SQL to prevent race conditions without needing a broker.
- **SQLite BEGIN IMMEDIATE:** Locks the database securely upfront during a transaction to ensure atomic reads/updates across independent OS processes.
- **State-Based Dead Letter Queue:** No separate tables were needed; DLQ simply leverages a specialized `dead` state string in the `jobs` table.
- **Crash Recovery:** Workers record their OS PID when starting. Subsequent worker boots use `os.kill(pid, 0)` to verify liveness and clear out orphaned `processing` jobs.
-- **Graceful Shutdown:** `SIGTERM` signals trip a global shutdown flag. The worker finishes its active subprocess without interruption before gracefully exiting.

---

---

## Demo Recording

Watch the complete project demonstration covering all required assignment scenarios:

**Video:** https://drive.google.com/file/d/1UGO5SulRsYoLBkPxmLuk7ABJUWaE117-/view?usp=sharing

> The demo includes:
> - Project overview and architecture
> - Basic job execution
> - Retry with exponential backoff
> - Dead Letter Queue (DLQ)
> - Multiple concurrent workers
> - SIGKILL crash recovery
> - SQLite persistence
> - Persistent configuration
> - JSON output validation
