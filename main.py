"""Deprecated entry point - use the `corvus` command instead (pip install -e .).

    python main.py "task"   is the same as   corvus run "task"
"""
import sys

from cli import cmd_run

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd_run(" ".join(sys.argv[1:]))
