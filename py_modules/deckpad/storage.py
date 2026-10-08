"""Small JSON files that survive a crash or power loss halfway through a write."""

import json
import logging
import os

log = logging.getLogger("deckpad.storage")


def save(path, data):
    """Raises OSError."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        directory = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def erase(path):
    for p in (path, path + ".tmp"):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning("Could not delete %s: %r", p, e)
