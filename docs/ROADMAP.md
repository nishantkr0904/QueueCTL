# QueueCTL — Project Roadmap

---

## Phase 1 — Project Setup & Core Data Model

**Objective:** Establish the project foundation, define the job data model, and set up persistent storage.

**Features Completed:**
- Project scaffolding and CLI entry point
- Job data model (id, command, state, attempts, max_retries, timestamps)
- Persistent storage layer (jobs survive restarts)
- Basic CLI skeleton wired up

**Expected Outcome:** A runnable CLI binary that can initialize and read/write job data to persistent storage.

---

## Phase 2 — Job Enqueue & Listing

**Objective:** Allow users to submit jobs and inspect the queue.

**Features Completed:**
- `queuectl enqueue '<json>'` — add a new job to the queue
- `queuectl list --state <state> --json` — list jobs filtered by state, JSON output to stdout
- `queuectl status` — summary of all job states and active workers

**Expected Outcome:** Users can enqueue jobs and verify them via list and status commands. JSON output matches the interface contract.

---

## Phase 3 — Single Worker Execution

**Objective:** Build a single worker that picks up pending jobs and executes them.

**Features Completed:**
- `queuectl worker start` — starts a single worker in the foreground
- Worker polls for pending jobs, claims them atomically, and executes the shell command
- Job state transitions: `pending → processing → completed` (on exit code 0) or `pending → processing → failed` (on non-zero exit code)
- Graceful shutdown on SIGTERM/SIGINT — finish the in-flight job, then exit

**Expected Outcome:** A single worker can pick up and execute jobs end-to-end. Graceful shutdown works correctly.

---

## Phase 4 — Multi-Worker Concurrency & Atomic Job Claiming

**Objective:** Support multiple workers running in parallel across separate terminal sessions without duplicate execution.

**Features Completed:**
- `queuectl worker start --count N` — start N workers in the foreground
- Workers from separate OS processes can run concurrently
- Atomic job claiming — no two workers can execute the same job
- Worker registration (tracking active workers)

**Expected Outcome:** Multiple workers across separate terminals process jobs in parallel. Every job runs exactly once.

---

## Phase 5 — Retry with Exponential Backoff & Dead Letter Queue

**Objective:** Handle job failures with automatic retries and move permanently failed jobs to the DLQ.

**Features Completed:**
- Failed jobs retry automatically after a delay of `base ^ attempts` seconds
- Default backoff base is 2
- After `max_retries` exhausted, job moves to `dead` state (DLQ)
- `queuectl dlq list` — view all dead-lettered jobs
- `queuectl dlq retry <id>` — re-enqueue a dead job

**Expected Outcome:** Failing jobs are retried with increasing delays. Permanently failed jobs land in the DLQ and can be retried manually.

---

## Phase 6 — Crash Recovery

**Objective:** Ensure no job is permanently stuck in `processing` if a worker is killed (including SIGKILL).

**Features Completed:**
- Detection of orphaned jobs stuck in `processing` due to worker crashes
- Automatic recovery of orphaned jobs back to `pending`
- Worst-case recovery time under 60 seconds

**Expected Outcome:** After a SIGKILL, orphaned jobs are detected and re-queued automatically. No job is ever permanently stuck.

---

## Phase 7 — Worker Stop (Cross-Process Signaling)

**Objective:** Allow graceful worker shutdown from a separate terminal.

**Features Completed:**
- `queuectl worker stop` — signals all running workers to shut down from another terminal
- Workers finish their in-flight job before exiting

**Expected Outcome:** Running workers can be gracefully stopped from any terminal session.

---

## Phase 8 — Configuration Management

**Objective:** Make retry and backoff settings configurable and persistent.

**Features Completed:**
- `queuectl config set max-retries <N>` — set the maximum retry count
- `queuectl config set backoff-base <N>` — set the backoff base
- Configuration is persisted across restarts

**Expected Outcome:** Users can tune retry and backoff behavior via CLI. Settings are durable.

---

## Phase 9 — Documentation & Submission

**Objective:** Produce all required documentation and prepare the final submission.

**Features Completed:**
- `README.md` — setup instructions, usage examples, architecture overview, testing guide
- `DECISIONS.md` — answers to all five required design questions with specific line references
- CLI demo recording linked in README
- Incremental git history verified

**Expected Outcome:** Repository is complete, documented, and ready for the live review and automated test run.
