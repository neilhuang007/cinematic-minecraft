"""Exercise the real shell entry point with isolated system-command doubles.

Run on Linux/WSL. No live Borg repository, RCON server or block device is used.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "ops/minecraft-backups/usr/local/bin/mc-backup.sh"


@unittest.skipUnless(os.name == "posix", "shell integration tests require Linux/WSL")
class BackupScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.source = self.root / "source"
        self.server = self.source / "minecraft"
        self.server.mkdir(parents=True)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.view = self.root / "view"
        (self.view / str(self.server).lstrip("/") / "world").mkdir(parents=True)
        (self.view / str(self.server).lstrip("/") / "world/level.dat").write_text("world")
        self.calls = self.root / "calls"
        self.state = self.root / "state"
        self.state.mkdir()
        self.env_file = self.root / "backup.env"
        self.env_file.write_text(
            f"BORG_REPO='{self.repo}'\nSRV_DIR='{self.server}'\n"
            "RCON_HOST=127.0.0.1\nRCON_PORT=25575\nRCON_PASSWORD=test-only\n"
            "SAVE_FLUSH_WAIT_SECONDS=0\nSNAPSHOT_DEVICE=/dev/test/source\n"
            f"SNAPSHOT_VIEW='{self.view}'\nMIN_FREE_GIB=0\n"
        )
        self.env_file.chmod(0o600)
        stub = '''#!/bin/bash
set -eu
command=${0##*/}
printf '%s %s\\n' "$command" "$*" >> "$TEST_CALLS"
case "$command" in
 stat) printf '0 600\\n' ;;
 systemctl) exit 0 ;;
 findmnt) case "$*" in *TARGET*) echo "$TEST_SOURCE";; *) echo /dev/test/source;; esac ;;
 readlink) case "$*" in */dev/test/source*) echo /dev/test/source;; *) /usr/bin/readlink "$@";; esac ;;
 lvs) case "$*" in *lv_attr*) echo 'sri-a-s--- 0.01';; *) exit 5;; esac ;;
 lvcreate) touch "$TEST_ROOT/lv" ;;
 lvremove) rm -f "$TEST_ROOT/lv" ;;
 mount) if [[ ${TEST_MOUNT_FAIL:-0} == 1 ]]; then exit 32; fi; touch "$TEST_ROOT/mounted" ;;
 umount) rm -f "$TEST_ROOT/mounted" ;;
 mountpoint) test -f "$TEST_ROOT/mounted" ;;
 mcrcon) if [[ ${TEST_FLUSH_FAIL:-0} == 1 && "$*" == *'save-all flush'* ]]; then exit 1; fi ;;
 borg) case "$1" in create) exit "${TEST_CREATE_RC:-0}";; prune) exit "${TEST_PRUNE_RC:-0}";; esac ;;
esac
'''
        for name in ("stat", "systemctl", "findmnt", "readlink", "lvs", "lvcreate", "lvremove", "mount", "umount", "mountpoint", "mcrcon", "borg"):
            path = self.bin / name
            path.write_text(stub)
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        MC_BACKUP_ENV_FILE=str(self.env_file), MC_BACKUP_LOCK_HELD="1",
                        MC_BACKUP_STATE_DIR=str(self.state), TEST_CALLS=str(self.calls),
                        TEST_SOURCE=str(self.source), TEST_ROOT=str(self.root))

    def run_backup(self, *args, **settings):
        result = subprocess.run(["bash", str(SCRIPT), *args], env=dict(self.env, **settings),
                                text=True, capture_output=True, timeout=20)
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        return result, calls

    def test_success_reads_snapshot_resumes_saves_and_removes_snapshot(self):
        result, calls = self.run_backup("--daily")
        self.assertEqual(0, result.returncode, result.stderr)
        create = next(i for i, c in enumerate(calls) if c.startswith("borg create "))
        self.assertTrue(any(c.startswith("lvcreate ") for c in calls[:create]), calls)
        self.assertIn("mcrcon save-on", calls[:create])
        self.assertTrue(any(c.startswith("borg rename ") for c in calls), calls)
        self.assertFalse((self.root / "lv").exists())
        self.assertFalse((self.root / "mounted").exists())
        self.assertTrue(any(c.startswith("borg compact") for c in calls), calls)

    def test_warning_never_promotes_archive_but_still_runs_housekeeping(self):
        result, calls = self.run_backup("--daily", TEST_CREATE_RC="1")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(any(c.startswith("borg rename ") for c in calls), calls)
        self.assertTrue(any(c.startswith("borg prune ") for c in calls), calls)
        self.assertTrue(any(c.startswith("borg compact") for c in calls), calls)
        self.assertIn("mcrcon save-on", calls)
        self.assertFalse((self.root / "lv").exists())

    def test_mount_failure_restores_saves_and_cleans_device(self):
        result, calls = self.run_backup("--daily", TEST_MOUNT_FAIL="1")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("mcrcon save-on", calls)
        self.assertFalse((self.root / "lv").exists())
        self.assertFalse(any(c.startswith("borg create ") for c in calls))

    def test_flush_failure_restores_saves_without_creating_snapshot(self):
        result, calls = self.run_backup("--daily", TEST_FLUSH_FAIL="1")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("mcrcon save-on", calls)
        self.assertFalse(any(c.startswith("lvcreate ") for c in calls))

    def test_manual_backup_and_repeat_have_clear_feedback(self):
        result, calls = self.run_backup("--manual", "TestPlayer")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(any("mc-manual-TestPlayer-" in c for c in calls), calls)
        self.assertTrue(any(c.startswith("mcrcon tellraw TestPlayer ") for c in calls))
        self.calls.write_text("")
        result, calls = self.run_backup("--manual", "TestPlayer")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(any(c.startswith("borg create ") for c in calls))

    def test_fatal_create_failure_is_not_reported_as_success(self):
        result, calls = self.run_backup("--daily", TEST_CREATE_RC="2")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(any(c.startswith("borg rename ") for c in calls))
        self.assertFalse((self.state / "last-success.json").exists())
        self.assertFalse((self.root / "lv").exists())

    def test_compaction_runs_even_if_retention_errors(self):
        result, calls = self.run_backup("--maintenance", TEST_PRUNE_RC="2")
        self.assertNotEqual(0, result.returncode)
        self.assertTrue(any(c.startswith("borg compact") for c in calls), calls)

    def test_public_entrypoint_acquires_and_releases_shared_lock(self):
        lock = self.root / "backup.lock"
        result, calls = self.run_backup("--daily", MC_BACKUP_LOCK_HELD="0",
                                        MC_BACKUP_LOCK_FILE=str(lock))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(any(c.startswith("borg create ") for c in calls))
        unlocked = subprocess.run(["flock", "-n", str(lock), "true"], timeout=5)
        self.assertEqual(0, unlocked.returncode)
