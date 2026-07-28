"""
cli.py — CLI command definitions for QueueCTL.

This module defines the command structure using Click:
  - A root command group ('queuectl') that all commands live under.
  - Top-level commands: enqueue, status, list.
  - Command groups with subcommands: worker (start, stop),
    dlq (list, retry), config (set).

At this stage every command is a placeholder that prints
"Not implemented yet." — the real logic will be added in later phases.

The command structure matches the interface contract defined in
INSTRUCTIONS.md (Section: CLI Commands).
"""

import click


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
# Usage: queuectl enqueue '<json>'
# Accepts a JSON string describing the job to add to the queue.

@cli.command()
@click.argument("job_json")
def enqueue(job_json):
    """Add a new job to the queue."""
    click.echo("Not implemented yet.")


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
