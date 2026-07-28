"""
main.py — Application entry point for QueueCTL.

This module provides the main() function that serves as the single
entry point for the CLI binary.  It simply invokes the root Click
command group defined in cli.py.

When the package is installed via pip (using setup.py), the 'queuectl'
console script points here.  It can also be run directly with:

    python -m queuectl.main
"""

from queuectl.cli import cli


def main():
    """
    Entry point for the QueueCTL CLI.

    Delegates all command routing and argument parsing to Click.
    """
    cli()


# Allow running this file directly: python -m queuectl.main
# or: python queuectl/main.py
if __name__ == "__main__":
    main()
