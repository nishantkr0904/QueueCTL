# QueueCTL — Project Structure

```
QueueCTL/
├── README.md
├── DECISIONS.md
├── LICENSE
├── .gitignore
├── requirements.txt
│
├── docs/
│   ├── INSTRUCTIONS.md
│   ├── ROADMAP.md
│   ├── PROJECT_STRUCTURE.md
│   └── ARCHITECTURE.md
│
├── queuectl/
│   ├── __init__.py
│   ├── main.py
│   ├── cli.py
│   ├── models.py
│   ├── storage.py
│   └── worker.py
│
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_models.py
│   ├── test_store.py
│   ├── test_worker.py
│   ├── test_scheduler.py
│   └── test_config.py
│
└── data/                  ← created at runtime, gitignored
    ├── jobs.db
    ├── config.json
    └── pids/
```

---

## Root Files

| File | Responsibility |
|------|---------------|
| `README.md` | Setup instructions, usage examples, architecture overview, and link to CLI demo recording. |
| `DECISIONS.md` | Answers to the five required design questions with specific line references and trade-off reasoning. |
| `LICENSE` | Project license. |
| `.gitignore` | Excludes runtime data, virtual environments, and OS artifacts from version control. |
| `requirements.txt` | Lists all Python dependencies needed to run the project. |
| `setup.py` | Makes the project installable via pip so that `queuectl` works as a system-wide command. |

---

## `docs/` — Project Documentation

Internal planning and reference documents. Not part of the submission deliverables but useful during development.

| File | Responsibility |
|------|---------------|
| `INSTRUCTIONS.md` | Original assignment brief (read-only reference). |
| `ROADMAP.md` | Phased development plan — what gets built and in what order. |
| `PROJECT_STRUCTURE.md` | This file. Describes the purpose of every folder and file. |
| `ARCHITECTURE.md` | High-level architecture and component relationships. |
| `DEVELOPMENT_NOTES.md` | Scratchpad for decisions, trade-offs, and open questions during development. |

---

## `queuectl/` — Application Source Code

The core Python package. All application logic lives here.

| File | Responsibility |
|------|---------------|
| `__init__.py` | Marks the directory as a Python package. |
| `main.py` | Entry point for the CLI binary. Parses the top-level command and delegates to the appropriate handler. |
| `cli.py` | Defines all CLI commands and subcommands (`enqueue`, `list`, `status`, `worker start/stop`, `dlq list/retry`, `config set`). Responsible for argument parsing and output formatting. |
| `models.py` | Defines the Job data model (id, command, state, attempts, max_retries, timestamps). Contains state constants and validation rules. |
| `store.py` | Persistence layer. Handles reading and writing jobs to storage. Owns the locking mechanism that makes job claiming atomic across processes. |
| `worker.py` | Worker lifecycle management. Handles starting workers, executing job commands via the shell, graceful shutdown on signals, and worker registration/deregistration. |
| `scheduler.py` | Retry and backoff logic. Determines which failed jobs are ready to retry based on elapsed time and backoff formula. Detects orphaned jobs stuck in processing (crash recovery). |
| `config.py` | Manages persistent configuration (max-retries, backoff-base). Reads and writes config values to storage. |
| `utils.py` | Shared utilities — timestamp formatting, ID generation, and other small helpers used across modules. |

---

## `tests/` — Test Suite

Mirrors the source structure. Each test file validates the corresponding source module.

| File | Responsibility |
|------|---------------|
| `__init__.py` | Marks the directory as a Python package. |
| `test_cli.py` | Tests CLI command parsing, output format, and the `--json` contract. |
| `test_models.py` | Tests job data model validation and state transitions. |
| `test_store.py` | Tests persistence — writes, reads, atomic claiming, and locking behavior. |
| `test_worker.py` | Tests worker execution, signal handling, and crash recovery. |
| `test_scheduler.py` | Tests retry eligibility, backoff delay calculation, and orphan detection. |
| `test_config.py` | Tests configuration get/set and persistence across restarts. |

---

## `data/` — Runtime Data (gitignored)

Created automatically at runtime. Never committed to version control.

| Path | Responsibility |
|------|---------------|
| `jobs.db` | Persistent storage for all job data (SQLite database). |
| `config.json` | Persisted configuration values (max-retries, backoff-base). |
| `pids/` | Directory for worker PID files, used for cross-process signaling during `worker stop`. |
