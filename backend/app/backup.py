"""Consistent online SQLite backup; restore to a new, stopped data directory."""

import argparse
import sqlite3
from pathlib import Path


def backup(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if destination.exists():
        raise ValueError("Destination already exists; choose a new backup file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True) as origin:
        with sqlite3.connect(destination) as target:
            origin.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Backup integrity check failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    backup(args.source, args.destination)
