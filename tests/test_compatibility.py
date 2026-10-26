"""Keeps the documented NetBox range in line with the PluginConfig."""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def plugin_config():
    tree = ast.parse((ROOT / "netbox_vmware_importer" / "__init__.py").read_text())
    values = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = node.value.value
    return values


def documented(version):
    # "4.7.99" is the conventional upper bound for "any 4.7 release"
    return re.sub(r"\.99$", ".x", version)


class CompatibilityTest(unittest.TestCase):
    def setUp(self):
        config = plugin_config()
        self.version = config["version"]
        self.min_version = documented(config["min_version"])
        self.max_version = documented(config["max_version"])

    def test_readme_matches_plugin_config(self):
        readme = (ROOT / "README.md").read_text()
        expected = f"`{self.min_version}` – `{self.max_version}`"
        self.assertIn(f"| **NetBox** | {expected} |", readme)
        self.assertIn(f"- NetBox {expected}", readme)

    def test_compatibility_matrix_lists_current_release(self):
        matrix = (ROOT / "COMPATIBILITY.md").read_text()
        row = re.search(rf"^\|\s*{re.escape(self.version)}\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|$", matrix, re.M)
        self.assertIsNotNone(row, f"COMPATIBILITY.md has no row for {self.version}")
        self.assertEqual(row.groups(), (self.min_version, self.max_version))

    def test_pyproject_version_matches_plugin_config(self):
        pyproject = (ROOT / "pyproject.toml").read_text()
        self.assertIn(f'version = "{self.version}"', pyproject)


if __name__ == "__main__":
    unittest.main()
