"""
cli.py — CLI command definitions for QueueCTL.

This module defines the command structure using Click:
  - A root command group ('queuectl') that all commands live under.
  - Top-level commands: enqueue, status, list.
  - Command groups with subcommands: worker (start, stop),
    dlq (list, retry), config (set).

The 'enqueue' command is fully implemented. All other commands are
placeholders that print "Not implemented yet."

The command structure matches the interface contract defined in
INSTRUCTIONS.md (Section: CLI Commands).
"""

import json
import sqlite3

import click

from queuectl.db import open_connection, close_connection, initialize_database
from queuectl.models import Job, DEFAULT_MAX_RETRIES
from queuectl.storage import insert_job


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

    # --- Step 3: Create a Job object ---
    # We pass only 'id' and 'command' from user input.
    # The Job constructor fills in state='pending', attempts=0,
    # max_retries=3, and timestamps automatically.
    # If the user provides 'max_retries' in their JSON, we honour it.
    job = Job(
        id=data["id"],
        command=data["command"],
        max_retries=data.get("max_retries", DEFAULT_MAX_RETRIES),
    )

    # --- Step 4: Store the job in the database ---
    # Open a connection, ensure tables exist, insert, then close.
    # The connection is always closed, even if the insert fails.
    connection = open_connection()
    try:
        initialize_database(connection)
        insert_job(connection, job)
    except sqlite3.IntegrityError:
        # This happens when a job with the same ID already exists.
        click.echo(f"Error: A job with id '{job.id}' already exists.", err=True)
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
@worker.command()
@click.option("--count", default=1, type=int, help="Number of workers to start.")
def start(count):
    """Start workers in the foreground."""
    click.echo("Not implemented yet.")


# Usage: queuectl worker stop
@worker.command()
def stop():
    """Gracefully stop all running workers."""
    click.echo("Not implemented yet.")


# ---------------------------------------------------------------------------
# dlq command group
# ---------------------------------------------------------------------------
# 'dlq' is a group with two subcommands: list and retry.

@cli.group()
def dlq():
    """Manage the Dead Letter Queue."""
    pass


# Usage: queuectl dlq list
# Note: same naming trick as the top-level 'list' command — the Python
# function is called 'dlq_list' but the Click command name is 'list'.
@dlq.command("list")
def dlq_list():
    """List all dead-lettered jobs."""
    click.echo("Not implemented yet.")


# Usage: queuectl dlq retry <job_id>
@dlq.command()
@click.argument("job_id")
def retry(job_id):
    """Re-enqueue a dead job."""
    click.echo("Not implemented yet.")


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
    click.echo("Not implemented yet.")
