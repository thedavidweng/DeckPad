"""What the Decky Plugin Store reads from this repository.

The store CI (decky-plugin-database `build-plugins.yml`, Decky CLI `plugin build`) takes the plugin's name,
author, description, image, and tags from `plugin.json`, the version from `package.json`, and zips `dist/`,
`py_modules/`, `bin/`, `defaults/`, `LICENSE`, `main.py`, `package.json`, `plugin.json`, and `README.md`.
Reviewers reject unused template leftovers (`backend/`, `assets/`, `defaults/defaults.txt`).
"""

import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_URL = "https://github.com/thedavidweng/DeckPad"


def _read(name):
    with open(os.path.join(ROOT, name)) as f:
        return f.read()


def _json(name):
    return json.loads(_read(name))


class PluginJsonTest(unittest.TestCase):
    def test_release_build_runs_as_root_without_dev_hot_reload(self):
        self.assertEqual(_json("plugin.json")["flags"], ["root"])

    def test_store_listing_has_its_own_image_and_description(self):
        publish = _json("plugin.json")["publish"]
        self.assertTrue(publish["image"].startswith("https://"))
        self.assertNotIn("SteamDeckHomebrew/PluginLoader", publish["image"])
        self.assertIn("controller", publish["description"])
        self.assertNotIn("dnu", publish["tags"])


class PackageJsonTest(unittest.TestCase):
    def test_describes_deckpad_rather_than_the_template(self):
        package = _json("package.json")
        self.assertEqual(package["name"], "deckpad")
        self.assertIn("Bluetooth game controller", package["description"])
        self.assertNotIn("you@you.tld", package["author"])
        self.assertNotIn("plugin-template", package["keywords"])

    def test_points_at_this_repository(self):
        package = _json("package.json")
        self.assertEqual(package["repository"]["url"], "git+%s.git" % REPO_URL)
        self.assertEqual(package["bugs"]["url"], REPO_URL + "/issues")
        self.assertEqual(package["homepage"], REPO_URL + "#readme")

    def test_license_matches_the_license_file(self):
        self.assertEqual(_json("package.json")["license"], "BSD-3-Clause")
        self.assertTrue(_read("LICENSE").startswith("BSD 3-Clause License"))

    def test_license_names_deckpad_first_and_keeps_the_template_license_last(self):
        license_text = _read("LICENSE")
        self.assertNotIn("Hypothetical Plugin Developer", license_text)
        self.assertIn("Copyright (c) 2026, thedavidweng", license_text.split("\n\n", 2)[1])
        template_start = license_text.rindex("Original Copyright (c) 2022-2024, Steam Deck Homebrew")
        self.assertGreater(template_start, license_text.index("thedavidweng"))
        self.assertTrue(license_text.rstrip().endswith("SUCH DAMAGE."))

    def test_test_script_runs_the_backend_suite(self):
        self.assertIn("unittest discover -s tests", _json("package.json")["scripts"]["test"])


def _shipped_files():
    """Repository paths that the Decky CLI (0.0.7, used by the store CI) puts in the plugin zip."""
    files = ["LICENSE", "main.py", "package.json", "plugin.json", "README.md"]
    files += [name for name in os.listdir(ROOT) if name.endswith(".py")]
    for directory in ("dist", "bin", "defaults", "py_modules"):
        for parent, dirs, names in os.walk(os.path.join(ROOT, directory)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            files += [os.path.relpath(os.path.join(parent, name), ROOT) for name in names]
    return sorted(set(f for f in files if os.path.isfile(os.path.join(ROOT, f))))


class ShippedFilesTest(unittest.TestCase):
    def test_every_vendored_module_ships_with_its_license(self):
        shipped = _shipped_files()
        for name in os.listdir(os.path.join(ROOT, "py_modules")):
            if name in ("deckpad", "__pycache__") or not os.path.isdir(os.path.join(ROOT, "py_modules", name)):
                continue
            self.assertIn(os.path.join("py_modules", name, "LICENSE"), shipped)

    def test_the_xbox_descriptor_ships_with_its_mit_notice(self):
        notices = [
            f for f in _shipped_files()
            if "Copyright (c) 2021 lemmingDev" in _read(f) and "Permission is hereby granted" in _read(f)
        ]
        self.assertTrue(notices, "no shipped file carries ESP32-BLE-CompositeHID's MIT notice")

    def test_no_unused_template_leftovers(self):
        for leftover in ("backend", "assets", os.path.join("defaults", "defaults.txt")):
            self.assertFalse(os.path.exists(os.path.join(ROOT, leftover)), leftover)


if __name__ == "__main__":
    unittest.main()
