# QueueCTL

A CLI-based background job queue system. It manages background jobs with worker processes, retries failures with exponential backoff, and maintains a Dead Letter Queue (DLQ) for permanently failed jobs.

## Objective

Build a minimal, production-grade job queue that supports:

- Enqueuing and managing background jobs via CLI
- Running multiple worker processes in parallel across separate terminals
- Automatic retries with exponential backoff
- A Dead Letter Queue after retries are exhausted
- Persistent job storage across restarts and crashes
- Crash recovery — no job is ever stuck in processing

## Current Status

🚧 **In Development** — Phase 1 (Project Setup & Core Data Model)

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Project Setup & Core Data Model | 🔄 In Progress |
| 2 | Job Enqueue & Listing | ⬜ Not Started |
| 3 | Single Worker Execution | ⬜ Not Started |
| 4 | Multi-Worker Concurrency & Atomic Job Claiming | ⬜ Not Started |
| 5 | Retry with Exponential Backoff & Dead Letter Queue | ⬜ Not Started |
| 6 | Crash Recovery | ⬜ Not Started |
| 7 | Worker Stop (Cross-Process Signaling) | ⬜ Not Started |
| 8 | Configuration Management | ⬜ Not Started |
| 9 | Documentation & Submission | ⬜ Not Started |

See [docs/ROADMAP.md](docs/ROADMAP.md) for detailed phase descriptions.

## Repository Structure

```
QueueCTL/
├── README.md               ← This file
├── DECISIONS.md             ← Design decisions (added later)
├── docs/                    ← Planning & architecture docs
│   ├── INSTRUCTIONS.md
│   ├── ROADMAP.md
│   ├── PROJECT_STRUCTURE.md
│   └── ARCHITECTURE.md
├── queuectl/                ← Application source code
│   ├── main.py              ← CLI entry point
│   ├── cli.py               ← Command definitions
│   ├── models.py            ← Job data model
│   ├── store.py             ← Persistence & locking
│   ├── worker.py            ← Worker lifecycle
│   ├── scheduler.py         ← Retry, backoff & recovery
│   ├── config.py            ← Configuration management
│   └── utils.py             ← Shared utilities
├── tests/                   ← Test suite
└── data/                    ← Runtime data (gitignored)
```

See [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for detailed file responsibilities.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
