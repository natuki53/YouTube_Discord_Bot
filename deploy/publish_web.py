"""Immutable assets are retained; replace index.html only after all assets exist."""

import argparse
import os
import shutil
from pathlib import Path


def publish(source: Path, destination: Path):
    source = source.resolve()
    if not (source / "index.html").is_file():
        raise ValueError("Built frontend index.html is missing")
    files = list(source.rglob("*"))
    if any(path.is_symlink() for path in files):
        raise ValueError("Frontend assets must not be symlinks")
    destination.mkdir(parents=True, exist_ok=True)
    for path in files:
        if not path.is_file() or path.name == "index.html":
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".publishing")
        shutil.copyfile(path, temporary)
        os.chmod(temporary, 0o644)
        temporary.replace(target)
    temporary = destination / ".index.publishing"
    shutil.copyfile(source / "index.html", temporary)
    os.chmod(temporary, 0o644)
    temporary.replace(destination / "index.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/app/web/dist"))
    parser.add_argument("--destination", type=Path, default=Path("/published"))
    args = parser.parse_args()
    publish(args.source, args.destination)
