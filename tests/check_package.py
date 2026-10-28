"""Check the actual ZIP produced by the official Decky CLI.

Run from the repository: python3 -m tests.check_package /path/to/DeckPad.zip
"""

import json
import os
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent


def _shipped_files():
    """Repository paths that Decky CLI 0.0.7 puts in the plugin ZIP."""
    files = ["LICENSE", "main.py", "package.json", "plugin.json", "README.md"]
    files += [name for name in os.listdir(ROOT) if name.endswith(".py")]
    for directory in ("dist", "bin", "defaults", "py_modules"):
        for parent, dirs, names in os.walk(ROOT / directory):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            files += [os.path.relpath(os.path.join(parent, name), ROOT) for name in names]
    return sorted(set(f for f in files if (ROOT / f).is_file()))


def check(path):
    with ZipFile(path) as package:
        assert package.testzip() is None, "corrupt ZIP entry"
        names = package.namelist()
        assert all(PurePosixPath(name).parts[0] == "DeckPad" for name in names), names
        assert all(".." not in PurePosixPath(name).parts for name in names), names
        files = {name.removeprefix("DeckPad/") for name in names if not name.endswith("/")}
        assert files == set(_shipped_files()), files.symmetric_difference(_shipped_files())
        assert "dist/index.js" in files
        assert not any("__pycache__" in name or name.endswith((".pyc", ".so")) for name in files)
        metadata = json.loads(package.read("DeckPad/plugin.json"))
        assert metadata["api_version"] == 1
        assert metadata["flags"] == ["root"]
        # The container rebuilds the frontend; backend code and notices must ship byte-for-byte.
        for name in files:
            if not name.startswith("dist/"):
                assert package.read("DeckPad/" + name) == Path(ROOT, name).read_bytes(), name
    print(f"Verified {len(files)} files in {path}")


if __name__ == "__main__":
    check(sys.argv[1])
