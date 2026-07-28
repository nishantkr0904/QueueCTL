# QueueCTL — Project Roadmap

---

## Phase 1 — Project Setup

**Objective:** Establish the project foundation — scaffolding, directory structure, documentation, and development tooling.

**Features Completed:**
- Project scaffolding and directory structure
- Documentation (INSTRUCTIONS, ROADMAP, PROJECT_STRUCTURE, ARCHITECTURE, DEVELOPMENT_NOTES)
- `.gitignore`, `requirements.txt`, `pyproject.toml`
- Empty `queuectl/` package with `__init__.py`

**Expected Outcome:** A clean project skeleton ready for incremental development.

---

## Phase 2 — Database Setup

**Objective:** Set up the SQLite database layer — connection management and table creation.

**Features Completed:**
- SQLite connection with foreign key support enabled
- Helper functions to open and close a connection
- Table creation (jobs, config, workers) using `CREATE TABLE IF NOT EXISTS`

**Expected Outcome:** The database can be initialized and is ready for other modules to read and write data.

---

## Phase 3 — Job Model and Storage

**Objective:** Define the job data model and build the persistence layer for reading and writing jobs.

**Features Completed:**
- Job data model (id, command, state, attempts, max_retries, timestamps)
- Storage functions to insert, query, update, and delete jobs in the database
- Job serialization and deserialization

**Expected Outcome:** Jobs can be created, queried, updated, and deleted through the storage layer.

---

## Phase 4 — CLI Foundation

**Objective:** Build the CLI entry point and basic command routing.

**Features Completed:**
- Root CLI entry point (`main.py`) that invokes the Click command group
- Click command group and subgroup registration (`cli.py`)
- Command routing for all required commands: `enqueue`, `status`, `list`, `worker`, `dlq`, `config`
- Placeholder handlers for every command (no business logic)

**Expected Outcome:** A runnable CLI binary that recognises all commands and subcommands. Every command prints a placeholder message. No database access or business logic.

---

## Phase 5 — Enqueue Command Implementation

**Objective:** Allow users to submit jobs through the CLI.

**Features Completed:**
- `queuectl enqueue '<json>'` — add a new job to the queue
- JSON parsing with clear error message on malformed input
- Validation of required fields (`id` and `command`)
- Job creation using model defaults for state, attempts, max_retries, and timestamps
- Optional `max_retries` override from user input
- Duplicate job ID detection with user-friendly error
- Job persisted to SQLite via the existing storage layer

**Expected Outcome:** Users can enqueue jobs into persistent storage through the CLI. Invalid input is rejected with clear error messages. Duplicate IDs are prevented.

---

## Phase 6 — Worker Implementation

**Objective:** Build workers that pick up pending jobs and execute them, with support for multiple workers in parallel.

**Features Completed:**
- `queuectl worker start` — starts a single worker in the foreground
- `queuectl worker start --count N` — start N workers in the foreground
- Worker polls for pending jobs, claims them atomically, and executes the shell command
- Job state transitions: `pending → processing → completed` (on exit code 0) or `pending → processing → failed` (on non-zero exit code)
- Workers from separate OS processes can run concurrently
- Worker registration (tracking active workers)
- Graceful shutdown on SIGTERM/SIGINT — finish the in-flight job, then exit

**Expected Outcome:** Multiple workers across separate terminals process jobs in parallel. Every job runs exactly once. Graceful shutdown works correctly.

---

## Phase 7 — Retry with Exponential Backoff & Dead Letter Queue

**Objective:** Handle job failures with automatic retries and move permanently failed jobs to the DLQ.

**Features Completed:**
- Failed jobs retry automatically after a delay of `base ^ attempts` seconds
- Default backoff base is 2
- After `max_retries` exhausted, job moves to `dead` state (DLQ)
- `queuectl dlq list` — view all dead-lettered jobs
- `queuectl dlq retry <id>` — re-enqueue a dead job

**Expected Outcome:** Failing jobs are retried with increasing delays. Permanently failed jobs land in the DLQ and can be retried manually.

---

## Phase 8 — Crash Recovery

**Objective:** Ensure no job is permanently stuck in `processing` if a worker is killed (including SIGKILL).

**Features Completed:**
- Detection of orphaned jobs stuck in `processing` due to worker crashes
- Automatic recovery of orphaned jobs back to `pending`
- Worst-case recovery time under 60 seconds

**Expected Outcome:** After a SIGKILL, orphaned jobs are detected and re-queued automatically. No job is ever permanently stuck.

---

## Phase 9 — Worker Stop (Cross-Process Signaling)

**Objective:** Allow graceful worker shutdown from a separate terminal.

**Features Completed:**
- `queuectl worker stop` — signals all running workers to shut down from another terminal
- Workers finish their in-flight job before exiting

**Expected Outcome:** Running workers can be gracefully stopped from any terminal session.

---

## Phase 10 — Configuration Management

**Objective:** Make retry and backoff settings configurable and persistent.

**Features Completed:**
- `queuectl config set max-retries <N>` — set the maximum retry count
- `queuectl config set backoff-base <N>` — set the backoff base
- Configuration is persisted across restarts

**Expected Outcome:** Users can tune retry and backoff behavior via CLI. Settings are durable.

---

## Phase 11 — Documentation & Submission

**Objective:** Produce all required documentation and prepare the final submission.

**Features Completed:**
- `README.md` — setup instructions, usage examples, architecture overview, testing guide
- `DECISIONS.md` — answers to all five required design questions with specific line references
- CLI demo recording linked in README
- Incremental git history verified

**Expected Outcome:** Repository is complete, documented, and ready for the live review and automated test run.
