"""
db.py — Database connection and initialization for QueueCTL.

This module is responsible for:
  1. Opening a SQLite connection with foreign key support enabled.
  2. Closing a SQLite connection.
  3. Creating the required tables (jobs, config, workers) if they
     do not already exist.

No business logic lives here. Other modules use the connection
returned by open_connection() to read and write data.
"""

import os
import sqlite3


# Default path for the SQLite database file.
# The database lives inside a 'data/' directory at the project root.
# This keeps runtime artifacts separate from source code.
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "jobs.db",
)


def open_connection(db_path=None):
    """
    Open a SQLite connection and enable foreign key support.

    Args:
        db_path: Path to the SQLite database file. If None, uses the
                 default path (data/jobs.db at the project root).

    Returns:
        A sqlite3.Connection object ready for use.

    Notes:
        - The 'data/' directory is created automatically if it does
          not exist, so the caller never needs to worry about it.
        - Foreign keys are enabled via PRAGMA because SQLite has them
          turned off by default. This must be done on every new
          connection — it is not a persistent database setting.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    # Create the parent directory if it doesn't exist yet.
    # This ensures the very first run works without manual setup.
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Connect to the database. SQLite creates the file automatically
    # if it doesn't exist.
    connection = sqlite3.connect(db_path)

    # Enable foreign key constraint enforcement.
    # Without this, foreign key declarations in CREATE TABLE are
    # silently ignored by SQLite.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def close_connection(connection):
    """
    Close a SQLite connection.

    Args:
        connection: The sqlite3.Connection object to close.

    Notes:
        This is a thin wrapper around connection.close(). It exists
        so that all database lifecycle operations live in one module,
        making it easy to add cleanup logic later if needed.
    """
    connection.close()


def initialize_database(connection):
    """
    Create the required tables if they do not already exist.

    This function is safe to call multiple times — it uses
    'CREATE TABLE IF NOT EXISTS' so it won't fail or overwrite
    data if the tables are already present.

    Args:
        connection: An open sqlite3.Connection object.

    Tables created:
        - jobs:    Stores all job data (id, command, state, etc.).
        - config:  Stores key-value configuration pairs
                   (e.g., max-retries, backoff-base).
        - workers: Tracks active worker processes for crash
                   recovery and cross-process signaling.

    The schema follows the design described in ARCHITECTURE.md.
    """
    # --- Jobs table ---
    # This is the core table. Every job enqueued into the system
    # gets a row here. The 'state' column drives the job lifecycle
    # (pending → processing → completed/failed/dead).
    connection.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            command     TEXT NOT NULL,
            state       TEXT NOT NULL DEFAULT 'pending',
            attempts    INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            worker_id   INTEGER,
            started_at  TEXT
        )
    """)

    # --- Config table ---
    # A simple key-value store for persistent configuration.
    # The 'key' column is the primary key so each setting has
    # exactly one value (e.g., key='max-retries', value='3').
    connection.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # --- Workers table ---
    # Tracks every active worker process. Workers register here
    # when they start and update their heartbeat periodically.
    # This table is used for:
    #   - Crash recovery: detecting workers that stopped heartbeating
    #     means they crashed, so their jobs can be reclaimed.
    #   - Worker stop: discovering which workers are running so they
    #     can be signaled to shut down.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            pid          INTEGER PRIMARY KEY,
            started_at   TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL
        )
    """)

    # Commit all three CREATE TABLE statements together.
    # If any one fails, none of them take effect.
    connection.commit()
