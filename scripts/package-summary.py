"""Report the actual README-shaped ZIP without changing its runtime payload."""

import io
from pathlib import PurePosixPath
import sys
import zipfile


with zipfile.ZipFile(sys.argv[1]) as archive:
    files = [entry for entry in archive.infolist() if not entry.is_dir()]
    names = {entry.filename for entry in files}
    assert {
        "DeckPad/plugin.json", "DeckPad/package.json", "DeckPad/main.py",
        "DeckPad/dist/index.js", "DeckPad/LICENSE", "DeckPad/README.md",
    } <= names
    for name in names:
        parts = PurePosixPath(name).parts
        assert parts[0] == "DeckPad" and ".." not in parts, name
        assert not {"node_modules", "__pycache__", "tests", ".venv", "venv", "docs"} & set(parts), name
        assert not name.endswith((".pyc", ".pyo")), name
    assert archive.testzip() is None
    print("| Payload | Bytes |\n| --- | ---: |")
    print(f"| Actual ZIP | {archive.fp.seek(0, 2)} |")
    print(f"| Extracted ({len(files)} files) | {sum(entry.file_size for entry in files)} |")
    print(f"| Frontend JS | {archive.getinfo('DeckPad/dist/index.js').file_size} |")
    for level in (1, 9):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=level) as candidate:
            for entry in files:
                candidate.writestr(entry.filename, archive.read(entry))
        print(f"| Same files/order, DEFLATE {level} (audit only) | {len(output.getvalue())} |")
    print("\n| Largest entry | Extracted | Compressed |\n| --- | ---: | ---: |")
    for entry in sorted(files, key=lambda entry: entry.compress_size, reverse=True)[:10]:
        print(f"| `{entry.filename}` | {entry.file_size} | {entry.compress_size} |")
