from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from gezhi.lease import detect_mutations, snapshot_tree
from gezhi.transaction import (
    InjectedTransactionCrash,
    commit_transaction,
    load_transaction,
    mark_transaction_checkpointed,
    prepare_transaction,
    repository_lock_path,
)


class CrashSafeTransactionTests(unittest.TestCase):
    def test_multi_file_transaction_records_and_commits_create_modify_delete_rename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            isolated = Path(temp_dir) / "isolated"
            state_dir = root / ".gezhi"
            self._write_baseline(root)
            self._write_after(isolated)
            before = snapshot_tree(root, excluded=(".git", ".gezhi"))
            after = snapshot_tree(isolated)
            mutations = detect_mutations(before, after)

            journal_path = prepare_transaction(root, state_dir, "attempt-0001", mutations, isolated)
            prepared = load_transaction(journal_path)

            self.assertEqual(prepared["status"], "PREPARED")
            self.assertEqual(prepared["attempt_id"], "attempt-0001")
            self.assertEqual(prepared["baseline"], before)
            self.assertEqual(
                [(item["operation"], item["path"], item.get("source_path")) for item in prepared["mutations"]],
                [
                    ("create", "create.txt", None),
                    ("delete", "delete.txt", None),
                    ("modify", "modify.txt", None),
                    ("rename", "new-name.txt", "old-name.txt"),
                ],
            )
            self.assertTrue(all("before_identity" in item and "after_identity" in item for item in prepared["mutations"]))

            result = commit_transaction(root, journal_path)

            self.assertTrue(result.committed)
            self.assertFalse(result.conflict)
            self.assertEqual(snapshot_tree(root, excluded=(".git", ".gezhi")), after)
            committed = load_transaction(journal_path)
            self.assertEqual(committed["status"], "COMMITTED")
            self.assertEqual(committed["applied_count"], len(committed["steps"]))

            mark_transaction_checkpointed(journal_path)
            mark_transaction_checkpointed(journal_path)
            self.assertEqual(load_transaction(journal_path)["status"], "CHECKPOINTED")

    def test_recovery_is_idempotent_across_every_applying_boundary(self) -> None:
        for crash_index in range(5):
            with self.subTest(crash_index=crash_index), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir) / "repo"
                isolated = Path(temp_dir) / "isolated"
                state_dir = root / ".gezhi"
                self._write_baseline(root)
                self._write_after(isolated)
                before = snapshot_tree(root, excluded=(".git", ".gezhi"))
                after = snapshot_tree(isolated)
                mutations = detect_mutations(before, after)
                journal_path = prepare_transaction(root, state_dir, f"attempt-{crash_index}", mutations, isolated)

                def crash(stage: str, index: int) -> None:
                    if stage == "after_apply_before_journal" and index == crash_index:
                        raise InjectedTransactionCrash(f"crash at {index}")

                with self.assertRaisesRegex(InjectedTransactionCrash, f"crash at {crash_index}"):
                    commit_transaction(root, journal_path, fault=crash)

                recovered = commit_transaction(root, journal_path)
                recovered_again = commit_transaction(root, journal_path)

                self.assertTrue(recovered.committed)
                self.assertTrue(recovered_again.committed)
                self.assertEqual(snapshot_tree(root, excluded=(".git", ".gezhi")), after)
                self.assertEqual(load_transaction(journal_path)["status"], "COMMITTED")

    def test_unknown_canonical_edit_is_preserved_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            isolated = Path(temp_dir) / "isolated"
            state_dir = root / ".gezhi"
            self._write_baseline(root)
            self._write_after(isolated)
            before = snapshot_tree(root, excluded=(".git", ".gezhi"))
            after = snapshot_tree(isolated)
            journal_path = prepare_transaction(root, state_dir, "attempt-conflict", detect_mutations(before, after), isolated)
            (root / "modify.txt").write_text("unknown user edit\n", encoding="utf-8")

            result = commit_transaction(root, journal_path)

            self.assertFalse(result.committed)
            self.assertTrue(result.conflict)
            self.assertIn("modify.txt", result.detail)
            self.assertEqual((root / "modify.txt").read_text(encoding="utf-8"), "unknown user edit\n")
            journal = load_transaction(journal_path)
            self.assertEqual(journal["status"], "CONFLICT")
            self.assertIn("modify.txt", journal["conflict"])

    def test_two_state_directories_share_repo_lock_and_later_baseline_is_revalidated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            first_isolated = Path(temp_dir) / "isolated-first"
            second_isolated = Path(temp_dir) / "isolated-second"
            self._write_baseline(root)
            self._copy_tree(root, first_isolated)
            self._copy_tree(root, second_isolated)
            (first_isolated / "modify.txt").write_text("first\n", encoding="utf-8")
            (second_isolated / "modify.txt").write_text("second\n", encoding="utf-8")
            before = snapshot_tree(root, excluded=(".git", ".gezhi-a", ".gezhi-b"))
            first_mutations = detect_mutations(before, snapshot_tree(first_isolated, excluded=(".git",)))
            second_mutations = detect_mutations(before, snapshot_tree(second_isolated, excluded=(".git",)))
            first_journal = prepare_transaction(root, root / ".gezhi-a", "attempt-first", first_mutations, first_isolated)
            second_journal = prepare_transaction(root, root / ".gezhi-b", "attempt-second", second_mutations, second_isolated)

            self.assertEqual(repository_lock_path(root), root.resolve() / ".git" / "gezhi-repository.lock")
            self.assertTrue(commit_transaction(root, first_journal).committed)
            second_result = commit_transaction(root, second_journal)

            self.assertFalse(second_result.committed)
            self.assertTrue(second_result.conflict)
            self.assertEqual((root / "modify.txt").read_text(encoding="utf-8"), "first\n")

    def test_journal_cannot_be_recovered_against_a_different_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_a = Path(temp_dir) / "repo-a"
            repo_b = Path(temp_dir) / "repo-b"
            isolated = Path(temp_dir) / "isolated"
            self._write_baseline(repo_a)
            self._write_baseline(repo_b)
            self._write_after(isolated)
            before = snapshot_tree(repo_a, excluded=(".git", ".gezhi"))
            mutations = detect_mutations(before, snapshot_tree(isolated))
            self.assertEqual(
                {mutation.operation for mutation in mutations},
                {"create", "modify", "delete", "rename"},
            )
            journal_path = prepare_transaction(
                repo_a,
                repo_a / ".gezhi",
                "attempt-cross-root",
                mutations,
                isolated,
            )
            repo_b_before = snapshot_tree(repo_b, excluded=(".git", ".gezhi"))

            result = commit_transaction(repo_b, journal_path)

            self.assertFalse(result.committed)
            self.assertTrue(result.conflict)
            self.assertIn("repository root mismatch", result.detail)
            self.assertEqual(snapshot_tree(repo_b, excluded=(".git", ".gezhi")), repo_b_before)
            self.assertEqual(load_transaction(journal_path)["status"], "PREPARED")

    def test_active_legacy_repository_lock_fails_closed_before_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            isolated = Path(temp_dir) / "isolated"
            self._write_baseline(root)
            self._write_after(isolated)
            before = snapshot_tree(root, excluded=(".git", ".gezhi"))
            journal_path = prepare_transaction(
                root,
                root / ".gezhi",
                "attempt-legacy-lock",
                detect_mutations(before, snapshot_tree(isolated)),
                isolated,
            )
            legacy_lock = root / ".git" / ("goal" + "-cli-repository.lock")

            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import fcntl, pathlib, sys; "
                        "lock = pathlib.Path(sys.argv[1]).open('a+b'); "
                        "fcntl.flock(lock.fileno(), fcntl.LOCK_EX); "
                        "print('ready', flush=True); sys.stdin.read()"
                    ),
                    str(legacy_lock),
                ],
                text=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            assert holder.stdout is not None
            self.assertEqual(holder.stdout.readline().strip(), "ready")
            try:
                result = commit_transaction(root, journal_path)
            finally:
                holder.communicate("\n", timeout=5)

            self.assertFalse(result.committed)
            self.assertTrue(result.conflict)
            self.assertIn("legacy repository lock is active", result.detail)
            self.assertEqual(snapshot_tree(root, excluded=(".git", ".gezhi")), before)
            self.assertEqual(load_transaction(journal_path)["status"], "PREPARED")

    def test_concurrent_gezhi_transaction_waits_instead_of_looking_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            isolated = Path(temp_dir) / "isolated"
            self._write_baseline(root)
            self._write_after(isolated)
            before = snapshot_tree(root, excluded=(".git", ".gezhi"))
            after = snapshot_tree(isolated)
            journal_path = prepare_transaction(
                root,
                root / ".gezhi",
                "attempt-concurrent-gezhi",
                detect_mutations(before, after),
                isolated,
            )
            canonical_lock = repository_lock_path(root)
            legacy_lock = root / ".git" / ("goal" + "-cli-repository.lock")

            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import fcntl, pathlib, sys; "
                        "canonical = pathlib.Path(sys.argv[1]).open('a+b'); "
                        "legacy = pathlib.Path(sys.argv[2]).open('a+b'); "
                        "fcntl.flock(canonical.fileno(), fcntl.LOCK_EX); "
                        "fcntl.flock(legacy.fileno(), fcntl.LOCK_EX); "
                        "print('ready', flush=True); sys.stdin.read()"
                    ),
                    str(canonical_lock),
                    str(legacy_lock),
                ],
                text=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            assert holder.stdout is not None
            assert holder.stdin is not None
            self.assertEqual(holder.stdout.readline().strip(), "ready")

            def release_holder() -> None:
                holder.stdin.close()

            release = threading.Timer(0.2, release_holder)
            release.start()
            try:
                result = commit_transaction(root, journal_path)
            finally:
                release.join(timeout=5)
                holder.wait(timeout=5)

            self.assertTrue(result.committed)
            self.assertFalse(result.conflict)
            self.assertEqual(snapshot_tree(root, excluded=(".git", ".gezhi")), after)

    def test_prepared_journal_is_self_contained_after_isolated_workspace_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            isolated = Path(temp_dir) / "isolated"
            self._write_baseline(root)
            self._write_after(isolated)
            before = snapshot_tree(root, excluded=(".git", ".gezhi"))
            after = snapshot_tree(isolated)
            journal_path = prepare_transaction(root, root / ".gezhi", "attempt-staged", detect_mutations(before, after), isolated)
            self._remove_tree(isolated)

            result = commit_transaction(root, journal_path)

            self.assertTrue(result.committed)
            self.assertEqual(snapshot_tree(root, excluded=(".git", ".gezhi")), after)
            staged_files = list((journal_path.parent / "staged").rglob("*"))
            self.assertTrue(any(path.is_file() for path in staged_files))

    def _write_baseline(self, root: Path) -> None:
        root.mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "modify.txt").write_text("old\n", encoding="utf-8")
        (root / "delete.txt").write_text("delete\n", encoding="utf-8")
        (root / "old-name.txt").write_text("rename\n", encoding="utf-8")

    def _write_after(self, root: Path) -> None:
        root.mkdir(parents=True)
        (root / "modify.txt").write_text("new\n", encoding="utf-8")
        (root / "create.txt").write_text("create\n", encoding="utf-8")
        (root / "new-name.txt").write_text("rename\n", encoding="utf-8")

    def _copy_tree(self, source: Path, destination: Path) -> None:
        destination.mkdir(parents=True)
        for path in source.iterdir():
            if path.name == ".git":
                (destination / ".git").mkdir()
            elif path.is_file():
                (destination / path.name).write_bytes(path.read_bytes())

    def _remove_tree(self, root: Path) -> None:
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink()
            else:
                path.rmdir()
        root.rmdir()


if __name__ == "__main__":
    unittest.main()
