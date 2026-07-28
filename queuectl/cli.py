"""
cli.py — CLI command definitions for QueueCTL.

This module defines the command structure using Click:
  - A root command group ('queuectl') that all commands live under.
  - Top-level commands: enqueue, status, list.
  - Command groups with subcommands: worker (start, stop),
    dlq (list, retry), config (set).

Implemented commands:
  - enqueue      — add a new job to the queue
  - worker start — start one or more workers in the foreground
  - worker stop  — gracefully stop all running workers
  - dlq list     — list all dead-lettered jobs
  - dlq retry    — re-enqueue a dead job

All other commands are placeholders that print "Not implemented yet."

The command structure matches the interface contract defined in
INSTRUCTIONS.md (Section: CLI Commands).
"""

import json
import os
import signal
import sqlite3

import click

from queuectl.db import open_connection, close_connection, initialize_database
from queuectl.models import Job, DEFAULT_MAX_RETRIES, STATE_DEAD
from queuectl.storage import (
    insert_job,
    get_jobs_by_state,
    retry_dead_job,
    get_all_worker_pids,
    get_config,
    set_config,
)
from queuectl.worker import (
    register_worker,
    deregister_worker,
    run_worker,
    _handle_shutdown_signal,
    perform_crash_recovery,
)


# ---------------------------------------------------------------------------
# Root command group
# ---------------------------------------------------------------------------
# This is the top-level entry point for the CLI.  Every command and
# subgroup is registered under this group.  When the user runs
# 'queuectl <command>', Click routes to the matching function below.

@click.group()
def cli():
    """QueueCTL — A CLI-based background job queue system."""
    pass


# ---------------------------------------------------------------------------
# enqueue command
# ---------------------------------------------------------------------------
# Usage: queuectl enqueue '{"id":"job1","command":"sleep 2"}'
#
# Accepts a JSON string with at least 'id' and 'command' fields.
# All other job fields (state, attempts, max_retries, timestamps) are
# filled in automatically by the Job model's defaults.

@cli.command()
@click.argument("job_json")
def enqueue(job_json):
    """Add a new job to the queue."""

    # --- Step 1: Parse the JSON string ---
    # If the user provides malformed JSON, we catch it here and
    # print a helpful error instead of a Python traceback.
    try:
        data = json.loads(job_json)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON — {e}", err=True)
        raise SystemExit(1)

    # --- Step 2: Validate required fields ---
    # The assignment spec requires at least 'id' and 'command'.
    # Everything else has sensible defaults in the Job model.
    if "id" not in data or not data["id"]:
        click.echo("Error: Missing required field 'id'.", err=True)
        raise SystemExit(1)

    if "command" not in data or not data["command"]:
        click.echo("Error: Missing required field 'command'.", err=True)
        raise SystemExit(1)

    # --- Step 3: Determine configuration and create Job ---
    # We open the database connection early to read configuration.
    connection = open_connection()
    try:
        initialize_database(connection)
        
        if "max_retries" in data:
            max_retries = data["max_retries"]
        else:
            config_retries = get_config(connection, "max-retries")
            max_retries = int(config_retries) if config_retries is not None else DEFAULT_MAX_RETRIES

        job = Job(
            id=data["id"],
            command=data["command"],
            max_retries=max_retries,
        )

        # --- Step 4: Store the job in the database ---
        insert_job(connection, job)
    except sqlite3.IntegrityError:
        # This happens when a job with the same ID already exists.
        click.echo(f"Error: A job with id '{data['id']}' already exists.", err=True)
        raise SystemExit(1)
    finally:
        close_connection(connection)

    # --- Step 5: Confirm success ---
    click.echo(f"Job '{job.id}' enqueued successfully.")


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------
# Usage: queuectl status
# Will show a summary of all job states and active workers.

@cli.command()
def status():
    """Show a summary of all job states and active workers."""
    click.echo("Not implemented yet.")


# ---------------------------------------------------------------------------
# list command
# ---------------------------------------------------------------------------
# Usage: queuectl list --state <state> [--json]
# Will list jobs filtered by state, with optional JSON output.
#
# Note: Click reserves 'list' as a Python builtin, but using it as a
# command name is fine — Click refers to it by the decorated function
# name only for registration, and we name the function 'list_jobs'
# while setting the Click command name to 'list' explicitly.

@cli.command("list")
@click.option("--state", default=None, help="Filter jobs by state.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON array.")
def list_jobs(state, as_json):
    """List jobs, optionally filtered by state."""
    click.echo("Not implemented yet.")


# ---------------------------------------------------------------------------
# worker command group
# ---------------------------------------------------------------------------
# 'worker' is a group with two subcommands: start and stop.

@cli.group()
def worker():
    """Manage background workers."""
    pass


# Usage: queuectl worker start [--count N]
#
# Starts one or more workers that claim pending jobs and execute them.
# The command blocks until all workers finish (queue drained or signal).
#
# With --count 1 (default): runs the worker directly in this process.
# With --count N (N > 1):   forks N child processes, each running an
#                           independent worker.  The parent waits for
#                           all children to finish.

@worker.command()
@click.option("--count", default=1, type=int, help="Number of workers to start.")
def start(count):
    """Start workers in the foreground."""

    if count < 1:
        click.echo("Error: --count must be at least 1.", err=True)
        raise SystemExit(1)

    if count == 1:
        # --- Single worker: run directly in this process ---
        _run_single_worker()
    else:
        # --- Multiple workers: fork child processes ---
        _run_multiple_workers(count)


def _run_single_worker():
    """
    Run a single worker in the current process.

    Opens a database connection, registers the worker, installs
    signal handlers for graceful shutdown, runs the worker loop,
    and deregisters on exit.
    """
    pid = os.getpid()

    # Install signal handlers BEFORE starting work so that a
    # signal received at any point sets the shutdown flag.
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)

    connection = open_connection()
    try:
        initialize_database(connection)

        # --- Crash Recovery ---
        # Detect and recover orphaned jobs from any previously crashed workers
        # BEFORE this new worker registers itself.
        perform_crash_recovery(connection)

        register_worker(connection, pid)

        # Run the claim → execute loop until the queue is drained
        # or a shutdown signal is received.
        run_worker(connection)

        deregister_worker(connection, pid)
    finally:
        close_connection(connection)


def _run_multiple_workers(count):
    """
    Fork 'count' child processes, each running an independent worker.

    The parent process waits for all children to finish.  Each child
    opens its own database connection (SQLite connections must not be
    shared across forks) and runs _run_single_worker().

    Args:
        count: Number of worker processes to launch.
    """
    child_pids = []

    for _ in range(count):
        pid = os.fork()

        if pid == 0:
            # --- Child process ---
            # Run a worker and exit.  os._exit() is used instead of
            # sys.exit() to avoid running parent cleanup handlers
            # (e.g., atexit) in the child.
            try:
                _run_single_worker()
            except Exception:
                os._exit(1)
            os._exit(0)
        else:
            # --- Parent process ---
            child_pids.append(pid)

    # Parent: wait for every child to finish.
    # This makes 'worker start --count N' block until all workers
    # are done, which matches the interface contract ("runs in the
    # foreground").
    for cpid in child_pids:
        os.waitpid(cpid, 0)


# Usage: queuectl worker stop
@worker.command()
def stop():
    """Gracefully stop all running workers."""
    connection = open_connection()
    try:
        initialize_database(connection)
        pids = get_all_worker_pids(connection)
    finally:
        close_connection(connection)

    if not pids:
        click.echo("No workers currently running.")
        return

    signalled_count = 0
    gone_count = 0

    for pid in pids:
        try:
            # Send SIGTERM to the worker to initiate graceful shutdown.
            # The worker's signal handler will catch this, finish its
            # current job, deregister, and exit cleanly.
            os.kill(pid, signal.SIGTERM)
            signalled_count += 1
        except OSError:
            # The process no longer exists (or we lack permission, but
            # for this assignment, it means the worker has exited/crashed).
            gone_count += 1

    click.echo(f"Sent SIGTERM to {signalled_count} worker(s).")
    if gone_count > 0:
        click.echo(f"Skipped {gone_count} worker(s) that already exited.")


# ---------------------------------------------------------------------------
# dlq command group
# ---------------------------------------------------------------------------
# 'dlq' is a group with two subcommands: list and retry.

@cli.group()
def dlq():
    """Manage the Dead Letter Queue."""
    pass


# Usage: queuectl dlq list
#
# Shows every job whose state is 'dead' — the Dead Letter Queue.
# Reuses get_jobs_by_state() from the storage layer.

@dlq.command("list")
def dlq_list():
    """List all dead-lettered jobs."""
    connection = open_connection()
    try:
        initialize_database(connection)
        dead_jobs = get_jobs_by_state(connection, STATE_DEAD)
    finally:
        close_connection(connection)

    if not dead_jobs:
        click.echo("No jobs in the Dead Letter Queue.")
        return

    # Simple, readable output — one line per job showing the key
    # fields a user would need when deciding whether to retry.
    click.echo(f"Dead Letter Queue ({len(dead_jobs)} job(s)):")
    click.echo()
    for job in dead_jobs:
        click.echo(f"  ID:          {job.id}")
        click.echo(f"  Command:     {job.command}")
        click.echo(f"  Attempts:    {job.attempts}")
        click.echo(f"  Max Retries: {job.max_retries}")
        click.echo(f"  Created:     {job.created_at}")
        click.echo(f"  Updated:     {job.updated_at}")
        click.echo()


# Usage: queuectl dlq retry <job_id>
#
# Re-enqueues a dead job so workers can pick it up again.
# Resets state='pending', attempts=0, worker_id=NULL.
# Preserves id, command, created_at, max_retries.

@dlq.command()
@click.argument("job_id")
def retry(job_id):
    """Re-enqueue a dead job."""
    connection = open_connection()
    try:
        initialize_database(connection)
        success = retry_dead_job(connection, job_id)
    finally:
        close_connection(connection)

    if success:
        click.echo(f"Job '{job_id}' re-enqueued from the Dead Letter Queue.")
    else:
        # Either the job doesn't exist, or it's not in 'dead' state.
        click.echo(
            f"Error: No dead job with id '{job_id}' found.",
            err=True,
        )
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# config command group
# ---------------------------------------------------------------------------
# 'config' is a group with a 'set' subcommand.

@cli.group()
def config():
    """Manage persistent configuration."""
    pass


# Usage: queuectl config set <key> <value>
@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a configuration value."""
    # Validation
    if key not in ("max-retries", "backoff-base"):
        click.echo(f"Error: Unsupported configuration key '{key}'. Supported keys are: max-retries, backoff-base.", err=True)
        raise SystemExit(1)
        
    try:
        val_int = int(value)
        if val_int < 0:
            raise ValueError()
        
        # backoff-base must be at least 1 (since 0^N = 0)
        if key == "backoff-base" and val_int < 1:
            raise ValueError()
            
    except ValueError:
        click.echo(f"Error: Invalid value '{value}' for key '{key}'. Must be a valid positive integer.", err=True)
        raise SystemExit(1)
        
    connection = open_connection()
    try:
        initialize_database(connection)
        set_config(connection, key, val_int)
    finally:
        close_connection(connection)
        
    click.echo(f"Configuration '{key}' successfully set to {val_int}.")

