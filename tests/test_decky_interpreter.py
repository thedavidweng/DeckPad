"""The backend must load inside Decky Loader's frozen Python, which ships `xml` without `xml.etree`."""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml

from tests.support.fake_decky import REPO_ROOT


class LoadingInDeckysInterpreter(unittest.TestCase):
    def test_the_backend_loads_without_xml_etree(self):
        with tempfile.TemporaryDirectory() as tmp:
            stripped = os.path.join(tmp, "xml")
            shutil.copytree(os.path.dirname(xml.__file__), stripped, ignore=shutil.ignore_patterns("etree"))
            script = textwrap.dedent(
                """
                import sys, types
                sys.path.insert(0, %r)
                import xml
                try:
                    import xml.etree
                    raise SystemExit("xml.etree should be missing in this interpreter")
                except ModuleNotFoundError:
                    pass
                decky = types.ModuleType("decky")
                async def emit(*a): pass
                decky.emit = emit
                sys.modules["decky"] = decky
                sys.path.insert(0, %r)
                import main
                from dbus_fast import introspection
                from dbus_fast.aio import MessageBus
                print(introspection.Node.parse("<node><interface name='a.b'/></node>").interfaces[0].name)
                """
            ) % (tmp, REPO_ROOT)
            result = subprocess.run(
                [sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=30
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stdout.strip(), "a.b")


if __name__ == "__main__":
    unittest.main()
