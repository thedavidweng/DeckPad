"""Small JSON files that survive a crash or power loss halfway through a write."""

import json
import logging
import os

log = logging.getLogger("deckpad.storage")


def save(path, data):
    """Raises OSError."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def erase(path):
    for p in (path, path + ".tmp"):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning("Could not delete %s: %r", p, e)
