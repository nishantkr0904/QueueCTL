# QueueCTL — Architecture

---

## Overview

QueueCTL is a CLI-based background job queue. The user submits jobs through the command line. Workers pick up those jobs and execute them. If a job fails, the system retries it with increasing delays. If it keeps failing, it goes to a Dead Letter Queue. Everything is stored in a database so nothing is lost on crash or restart.

```
 User
  │
  ▼
┌──────────────────────────────────────────────┐
│                    CLI                        │
│  enqueue · list · status · worker · dlq · config │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│               Storage (SQLite)               │
│         Jobs · Config · Worker Registry      │
└──────┬──────────────┬───────────────┬────────┘
       │              │               │
       ▼              ▼               ▼
   ┌────────┐   ┌──────────┐   ┌───────────┐
   │ Worker │   │ Worker   │   │ Worker    │
   │   1    │   │   2      │   │   N       │
   └───┬────┘   └────┬─────┘   └─────┬─────┘
       │              │               │
       ▼              ▼               ▼
     Shell          Shell           Shell
   Execution      Execution       Execution
```

---

## 1. CLI

The CLI is the only way to interact with QueueCTL. There is no API, no web interface — just terminal commands.

**What it does:**
- Accepts user commands (`enqueue`, `list`, `status`, `worker start/stop`, `dlq list/retry`, `config set`)
- Validates input
- Talks directly to the database to read or write data
- Formats output for the terminal (human-readable or JSON)

**Key rule:** `queuectl list --state <state> --json` must print a clean JSON array to stdout with nothing else. The automated test suite depends on this.

---

## 2. Storage (Database)

The database is the single source of truth for the entire system. Every component reads from and writes to it. There is no in-memory state that matters — if a process dies, the database has everything needed to continue.

**What it stores:**
- **Jobs** — all job data (id, command, state, attempts, timestamps)
- **Configuration** — retry count, backoff base
- **Worker registry** — which workers are currently alive

**Why it matters:**
- Multiple workers across separate terminals all share this one database
- Job claiming must be atomic at the database level — two workers must never grab the same job
- The database provides the locking mechanism that prevents duplicate execution

---

## 3. Workers

Workers are the processes that actually execute jobs. They run in the foreground and block until stopped.

**How they work:**
- `worker start --count N` launches N workers in the current terminal
- Each worker polls the database for available jobs
- When a worker finds a job, it atomically claims it (marks it as `processing` in a way no other worker can)
- The worker then executes the job's shell command
- Based on the exit code, it marks the job as `completed` or `failed`
- Workers register themselves in the database when they start and deregister when they stop

**Signals:**
- **SIGTERM / SIGINT (Ctrl+C):** Graceful shutdown — finish the current job, then exit
- **SIGKILL:** Immediate death — no cleanup runs. The recovery mechanism handles this.

**Cross-process stop:**
- `worker stop` runs from a different terminal
- It discovers running workers (via PID files or database registry) and signals them to shut down gracefully

---

## 4. Job Lifecycle

Every job follows this state machine:

```
                    ┌──────────────────────┐
                    │                      │
                    ▼                      │
enqueue ──► PENDING ──► PROCESSING ──► COMPLETED
                ▲           │
                │           │ (exit code ≠ 0)
                │           ▼
                │        FAILED
                │           │
                │           ├── retries left? ──► wait (backoff) ──► PENDING
                │           │
                │           └── retries exhausted
                │                       │
                │                       ▼
                │                     DEAD (DLQ)
                │                       │
                │                       │ (dlq retry)
                └───────────────────────┘
```

**States:**
| State | Meaning |
|-------|---------|
| `pending` | Job is waiting to be picked up by a worker |
| `processing` | A worker has claimed the job and is executing it |
| `completed` | The job's command exited with code 0 — success |
| `failed` | The job's command exited with a non-zero code — will be retried or moved to DLQ |
| `dead` | All retries exhausted — job sits in the Dead Letter Queue until manually retried |

**Transitions:**
- `pending → processing` — a worker atomically claims the job
- `processing → completed` — command exited successfully
- `processing → failed` — command exited with error
- `failed → pending` — retry scheduled after backoff delay elapses
- `failed → dead` — max retries reached, moved to DLQ
- `dead → pending` — user manually runs `dlq retry <id>`

---

## 5. Configuration

Configuration controls retry and backoff behavior. It is managed through the CLI and persisted to storage.

**Configurable values:**
| Setting | Purpose | Default |
|---------|---------|---------|
| `max-retries` | How many times a failed job is retried before going to the DLQ | 3 |
| `backoff-base` | Base for exponential backoff delay calculation (`base ^ attempts` seconds) | 2 |

**How it flows:**
- User runs `config set max-retries 5`
- The value is saved to persistent storage
- Workers read configuration when they need it (e.g., when deciding if a job should retry or go to DLQ)

---

## 6. Storage Design

**Choice:** SQLite — a single file-based database.

**Why SQLite fits this project:**
- No external server to install or manage
- Built-in support for atomic transactions across multiple OS processes
- File-based — survives restarts by nature
- Handles concurrent readers and serialized writers, which matches the worker model

**What the database contains:**

```
┌─────────────────────────────────────────┐
│              SQLite Database             │
│                                         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │  Jobs Table  │  │  Config Table    │  │
│  │             │  │                  │  │
│  │  id          │  │  key             │  │
│  │  command     │  │  value           │  │
│  │  state       │  │                  │  │
│  │  attempts    │  └──────────────────┘  │
│  │  max_retries │                        │
│  │  created_at  │  ┌──────────────────┐  │
│  │  updated_at  │  │ Workers Table    │  │
│  │  worker_id   │  │                  │  │
│  │  started_at  │  │  pid             │  │
│  │              │  │  started_at      │  │
│  └─────────────┘  │  heartbeat_at    │  │
│                    └──────────────────┘  │
└─────────────────────────────────────────┘
```

**Locking:** When a worker claims a job, it does so inside a database transaction. SQLite's file-level locking guarantees that only one process can write at a time, making the claim atomic across separate OS processes.

---

## 7. Crash Recovery

The crash rule: **no job can be stuck in `processing` forever.** If a worker is killed (even via SIGKILL, where no cleanup handler runs), the system must detect and recover the orphaned job.

**How recovery works:**

```
Worker dies (SIGKILL)
        │
        ▼
Job left in "processing" state
        │
        ▼
Other workers (or a new worker start) 
detect the orphaned job
        │
        ▼
Is the worker that claimed it still alive?
        │
   NO ──┤
        │
        ▼
Job is moved back to "pending"
        │
        ▼
Another worker picks it up
```

**Detection mechanism:**
- Each worker records a heartbeat in the database at regular intervals
- A job is considered orphaned if it has been in `processing` and the worker that claimed it has not heartbeated within the timeout window
- Any running worker can detect and recover orphaned jobs during its normal polling cycle

**Worst-case recovery time:** Under 60 seconds (as required by the assignment). This is bounded by the heartbeat interval plus the polling interval.

**Trade-off:** Shorter heartbeat intervals mean faster recovery but more database writes. The default values are chosen to keep recovery well under 60 seconds while avoiding excessive I/O.

---

## Component Dependency Flow

```
┌───────┐
│  CLI  │ ← User interaction
└───┬───┘
    │ reads/writes
    ▼
┌────────┐     ┌────────────┐
│ Store  │ ◄───│   Config   │ ← persisted settings
└───┬────┘     └────────────┘
    │ shared database
    ▼
┌────────────┐
│  Workers   │ ← poll for jobs, execute commands
└─────┬──────┘
      │ state changes
      ▼
┌─────────────┐
│  Scheduler  │ ← backoff timing, retry eligibility, orphan detection
└─────────────┘
```

- **CLI** depends on **Store** for all data access
- **Workers** depend on **Store** for job claiming and state updates
- **Workers** depend on **Scheduler** for retry timing and crash recovery
- **Scheduler** depends on **Config** for backoff-base and max-retries
- **Store** is the shared backbone — everything goes through it
