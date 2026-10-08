"""Check the actual ZIP produced by the official Decky CLI.

Run from the repository: python3 -m tests.check_package /path/to/DeckPad.zip
"""

import json
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from tests.test_store_package import ROOT, _shipped_files


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
