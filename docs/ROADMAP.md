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

## Phase 6 — Job Claiming

**Objective:** Atomically claim the oldest pending job so that no two workers — even across separate OS processes — can ever claim the same job.

**Features Completed:**
- `claim_job(connection, worker_id)` in storage.py
- `BEGIN IMMEDIATE` transaction to acquire the SQLite write lock before reading
- SELECT oldest pending job (`ORDER BY created_at ASC LIMIT 1`)
- Guarded UPDATE with `AND state = 'pending'` to prevent stale-read races
- `cursor.rowcount` verification — commit on success, rollback on race loss
- Claimed job marked with `state='processing'`, `worker_id`, and `updated_at` (prepares for crash recovery in later phases)
- No job execution — claiming only

**Expected Outcome:** A single function can atomically claim one pending job. Concurrent callers from separate OS processes are safe — exactly one wins, the rest get None. No job is ever double-claimed.

---

## Phase 7 — Worker Execution

**Objective:** Build workers that claim pending jobs (via the existing `claim_job()`) and execute them, with support for multiple workers in parallel.

**Features Completed:**
- `queuectl worker start` — starts a single worker in the foreground
- `queuectl worker start --count N` — forks N independent worker processes
- Workers obtain work exclusively through `claim_job()` (no new claiming logic)
- Shell command execution using `subprocess.run()` (synchronous, simple)
- Job state transitions: `processing → completed` (exit code 0) or `processing → failed` (exit code ≠ 0)
- Worker registration in the `workers` table on startup, deregistration on clean exit
- Graceful shutdown on SIGINT/SIGTERM — current job finishes, no new jobs claimed
- Clean exit when the queue is drained (no continuous polling)

**Expected Outcome:** One or more workers process all pending jobs. Each job runs exactly once (guaranteed by `claim_job()`). Workers exit after draining the queue or receiving a shutdown signal. No retries, DLQ, crash recovery, or worker stop.

---

## Phase 8 — Retry with Exponential Backoff

**Objective:** Automatically retry failed jobs with increasing delays, and stop retrying after `max_retries` is exceeded.

**Features Completed:**
- Failed jobs automatically increment `attempts` and return to `pending` if retries remain
- Jobs whose `attempts > max_retries` stay in `failed` state (no further retries)
- Exponential backoff formula: `delay = backoff_base ^ attempts` seconds (default base = 2)
- `claim_job()` enforces backoff — pending jobs with `attempts > 0` are only claimed after their delay has expired
- Backoff is computed in SQL using `datetime(updated_at, '+N seconds')` for accurate, timezone-safe comparisons
- Fresh jobs (`attempts = 0`) are always immediately eligible — no backoff

**Expected Outcome:** A failing job is retried with delays of 2s, 4s, 8s (with base=2). After `max_retries` failures, it stays `failed`. Workers respect the backoff delay — a job is never claimed before its wait period has elapsed.

---

## Phase 9 — Dead Letter Queue

**Objective:** Automatically move permanently failed jobs into the Dead Letter Queue and provide CLI commands to inspect and retry them.

**Features Completed:**
- Jobs whose retries are exhausted transition to `state = 'dead'` (not `failed`)
- The DLQ is implemented using the existing `jobs` table — no new tables, no row duplication
- `queuectl dlq list` — display all dead-lettered jobs with their metadata
- `queuectl dlq retry <id>` — re-enqueue a dead job (resets state to `pending`, attempts to 0)
- `retry_dead_job()` in storage.py — guarded UPDATE (`AND state = 'dead'`) prevents retrying non-dead jobs

**Expected Outcome:** A failing job that exhausts all retries lands in the DLQ (`state = 'dead'`). Users can inspect the DLQ and re-enqueue jobs for another round of execution.

---

## Phase 10 — Crash Recovery

**Objective:** Ensure no job is permanently stuck in `processing` if a worker is killed (including SIGKILL).

**Features Completed:**
- Stale worker detection: Worker PIDs are verified on startup and stale registrations are removed
- Orphaned job detection: Jobs stuck in `processing` with no active worker are identified
- Automatic crash recovery: Orphaned jobs are recovered back to `pending` (worker_id cleared) automatically when any new worker starts

**Expected Outcome:** After a SIGKILL, orphaned jobs are detected and recovered automatically upon the next worker startup. No job is ever permanently stuck.

---

## Phase 11 — Worker Stop (Cross-Process Signaling)

**Objective:** Allow graceful worker shutdown from a separate terminal.

**Features Completed:**
- `queuectl worker stop` — signals all running workers to shut down from another terminal
- Workers finish their in-flight job before exiting

**Expected Outcome:** Running workers can be gracefully stopped from any terminal session.

---

## Phase 12 — Configuration Management

**Objective:** Make retry and backoff settings configurable and persistent.

**Features Completed:**
- `queuectl config set max-retries <N>` — set the maximum retry count
- `queuectl config set backoff-base <N>` — set the backoff base
- Configuration is persisted across restarts

**Expected Outcome:** Users can tune retry and backoff behavior via CLI. Settings are durable.

---

## Phase 13 — Documentation & Submission

**Objective:** Produce all required documentation and prepare the final submission.

**Features Completed:**
- `README.md` — setup instructions, usage examples, architecture overview, testing guide
- `DECISIONS.md` — answers to all five required design questions with specific line references
- CLI demo recording linked in README
- Incremental git history verified

**Expected Outcome:** Repository is complete, documented, and ready for the live review and automated test run.
