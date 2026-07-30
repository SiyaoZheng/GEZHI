from __future__ import annotations

import contextlib
import os
import re
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

from gezhi.cli import STARTER_CONFIG
from gezhi.config import API_TIK_ENV_FILE_ENV_VAR, ConfigError, api_tik_env_file_paths, load_config


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_TEXT_ALLOWLIST = {
    "docs/migration.md",
    "src/gezhi/migration.py",
}


class BrandIdentityTests(unittest.TestCase):
    def test_pyproject_exposes_only_the_canonical_console_script(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["project"]["name"], "gezhi")
        self.assertEqual(metadata["project"]["scripts"], {"gezhi": "gezhi.cli:main"})

    def test_runtime_defaults_use_canonical_config_state_and_environment_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "gezhi.toml"
            config_path.write_text(STARTER_CONFIG, encoding="utf-8")

            with contextlib.chdir(root):
                config = load_config()

            self.assertEqual(config.path, config_path.resolve())
            self.assertEqual(config.state_dir, (root / ".gezhi").resolve())
            self.assertEqual(config.runs_dir, (root / ".gezhi" / "runs").resolve())
            self.assertEqual(config.no_mistakes.branch_prefix, "gezhi")
            self.assertEqual(config.observability.service_name, "gezhi")
            self.assertEqual(API_TIK_ENV_FILE_ENV_VAR, "GEZHI_API_ENV_FILE")

            xdg_config = root / "xdg"
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg_config)}, clear=False):
                self.assertEqual(api_tik_env_file_paths(), (xdg_config / "gezhi" / "api.env",))

    def test_default_config_fails_closed_beside_legacy_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_state_dir = root / ("." + "goal")
            legacy_state_dir.mkdir()
            config_text = STARTER_CONFIG.replace('state_dir = ".gezhi"\n', "").replace(
                'runs_dir = ".gezhi/runs"\n',
                "",
            )
            (root / "gezhi.toml").write_text(config_text, encoding="utf-8")

            with contextlib.chdir(root), self.assertRaisesRegex(ConfigError, "legacy runtime state"):
                load_config()

            self.assertFalse((root / ".gezhi").exists())

    def test_legacy_config_filename_is_rejected_even_with_canonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / ("goal" + ".toml")
            config_path.write_text(STARTER_CONFIG, encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "legacy config filename"):
                load_config(config_path)

    def test_canonical_config_fails_closed_beside_legacy_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canonical_config = root / "gezhi.toml"
            canonical_config.write_text(STARTER_CONFIG, encoding="utf-8")
            (root / ("goal" + ".toml")).write_text(STARTER_CONFIG, encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "legacy config remains"):
                load_config(canonical_config)

    def test_legacy_named_symlink_to_canonical_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            aliases = root / "aliases"
            project.mkdir()
            aliases.mkdir()
            canonical_config = project / "gezhi.toml"
            canonical_config.write_text(STARTER_CONFIG, encoding="utf-8")
            legacy_alias = aliases / ("goal" + ".toml")
            legacy_alias.symlink_to(canonical_config)

            with self.assertRaisesRegex(ConfigError, "legacy config filename"):
                load_config(legacy_alias)

    def test_dangling_legacy_state_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ("." + "goal")).symlink_to(root / "missing-state", target_is_directory=True)
            config_path = root / "gezhi.toml"
            config_path.write_text(STARTER_CONFIG, encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "legacy runtime state"):
                load_config(config_path)

            self.assertFalse((root / ".gezhi").exists())

    def test_tracked_paths_have_no_pre_gezhi_product_or_state_names(self) -> None:
        forbidden_fragments = ("goal" + "-cli", "goal" + "_cli", "goal" + ".toml")
        legacy_state_dir = "." + "goal"
        failures: list[str] = []

        for relative_path in self._tracked_paths():
            normalized = relative_path.lower()
            if any(fragment in normalized for fragment in forbidden_fragments):
                failures.append(relative_path)
            if legacy_state_dir in PurePosixPath(relative_path).parts:
                failures.append(relative_path)

        self.assertEqual(sorted(set(failures)), [])

    def test_tracked_text_has_no_pre_gezhi_product_or_state_names(self) -> None:
        forbidden_literals = (
            "goal" + ".toml",
            "com." + "goal" + "-cli",
        )
        legacy_product_reference = re.compile("goal" + r"[-_ ]cli", re.IGNORECASE)
        legacy_state_reference = re.compile(
            r"(?<![A-Za-z0-9_])\." + "goal" + r"(?=$|[/\\\"'`\s])"
        )
        failures: list[str] = []

        for relative_path in self._tracked_paths():
            if relative_path in HISTORICAL_TEXT_ALLOWLIST:
                continue
            try:
                text = (ROOT / relative_path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            matched = [literal for literal in forbidden_literals if literal in text]
            if matched or legacy_product_reference.search(text) or legacy_state_reference.search(text):
                failures.append(relative_path)

        self.assertEqual(failures, [])

    def _tracked_paths(self) -> tuple[str, ...]:
        if (ROOT / ".git").exists():
            result = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
            )
            return tuple(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)

        excluded_parts = {"__pycache__", "build", "dist", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        return tuple(
            sorted(
                path.relative_to(ROOT).as_posix()
                for path in ROOT.rglob("*")
                if path.is_file()
                and not any(part in excluded_parts or part.endswith(".egg-info") for part in path.parts)
            )
        )


if __name__ == "__main__":
    unittest.main()
