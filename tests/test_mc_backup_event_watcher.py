from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import subprocess


WATCHER_PATH = (
    Path(__file__).resolve().parents[1]
    / "ops"
    / "minecraft-backups"
    / "usr"
    / "local"
    / "bin"
    / "mc-backup-event-watch.py"
)
SPEC = importlib.util.spec_from_file_location("mc_backup_event_watch", WATCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EventWatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temporary_directory.name) / "real-player-state.json"
        self.events: list[tuple[str, str]] = []
        self.watcher = MODULE.EventWatcher(
            self.state_file,
            lambda event, player: self.events.append((event, player)),
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def process(self, message: str) -> tuple[str, str] | None:
        return self.watcher.process_line(f"[12:34:56] [Server thread/INFO]: {message}")

    def test_real_login_and_logout_trigger_backups(self) -> None:
        self.assertEqual(
            ("login", "RealPlayer"),
            self.process("RealPlayer[/198.51.100.10:25565] logged in with entity id 42 at (0.0, 64.0, 0.0)"),
        )
        self.assertEqual(("logout", "RealPlayer"), self.process("RealPlayer left the game"))
        self.assertEqual([("login", "RealPlayer"), ("logout", "RealPlayer")], self.events)
        self.assertEqual({"real_players": []}, json.loads(self.state_file.read_text(encoding="utf-8")))

    def test_carpet_local_player_never_triggers_or_becomes_tracked(self) -> None:
        self.assertIsNone(
            self.process("VillagerBreeder[local] logged in with entity id 1548 at (-355.7, 64.0, 471.7)")
        )
        self.assertIsNone(self.process("VillagerBreeder left the game"))
        self.assertEqual([], self.events)
        self.assertFalse(self.state_file.exists())

    def test_local_login_clears_matching_stale_real_session(self) -> None:
        self.process("RealPlayer[/198.51.100.10:25565] logged in with entity id 42 at (0.0, 64.0, 0.0)")
        self.assertIsNone(
            self.process("RealPlayer[local] logged in with entity id 43 at (0.0, 64.0, 0.0)")
        )
        self.assertIsNone(self.process("RealPlayer left the game"))
        self.assertEqual([("login", "RealPlayer")], self.events)

    def test_non_network_endpoint_is_not_treated_as_real(self) -> None:
        self.assertIsNone(
            self.process("SomePlayer[proxy] logged in with entity id 42 at (0.0, 64.0, 0.0)")
        )
        self.assertIsNone(self.process("SomePlayer left the game"))
        self.assertEqual([], self.events)

    def test_minecraft_restart_clears_stale_real_sessions(self) -> None:
        self.process("RealPlayer[/198.51.100.10:25565] logged in with entity id 42 at (0.0, 64.0, 0.0)")
        self.assertIsNone(
            self.watcher.process_line(
                "Started minecraft.service - Minecraft Fabric Server (1.21.11)."
            )
        )
        self.assertIsNone(self.process("RealPlayer left the game"))
        self.assertEqual([("login", "RealPlayer")], self.events)

    def test_logout_requires_a_previously_real_login(self) -> None:
        self.assertIsNone(self.process("Scanner (/198.51.100.20:1) lost connection: Disconnected"))
        self.assertEqual([], self.events)

    def test_lost_connection_waits_for_authoritative_left_game(self) -> None:
        self.process("RealPlayer[/198.51.100.10:25565] logged in with entity id 42 at (0.0, 64.0, 0.0)")
        self.assertIsNone(self.process("RealPlayer lost connection: Disconnected"))
        self.assertEqual(("logout", "RealPlayer"), self.process("RealPlayer left the game"))
        self.assertEqual([("login", "RealPlayer"), ("logout", "RealPlayer")], self.events)

    def test_state_survives_watcher_restart(self) -> None:
        self.process("RealPlayer[/198.51.100.10:25565] logged in with entity id 42 at (0.0, 64.0, 0.0)")
        resumed_events: list[tuple[str, str]] = []
        resumed = MODULE.EventWatcher(
            self.state_file,
            lambda event, player: resumed_events.append((event, player)),
        )
        self.assertEqual(
            ("logout", "RealPlayer"),
            resumed.process_line("[12:35:00] [Server thread/INFO]: RealPlayer left the game"),
        )
        self.assertEqual([("logout", "RealPlayer")], resumed_events)

    def test_operator_command_requests_a_manual_checkpoint(self) -> None:
        self.assertEqual(
            ("manual", "RealPlayer"),
            self.process("[MC_BACKUP_REQUEST] RealPlayer"),
        )
        self.assertEqual([("manual", "RealPlayer")], self.events)

    def test_command_marker_in_chat_or_rcon_feedback_is_ignored(self) -> None:
        for message in (
            "<RealPlayer> [MC_BACKUP_REQUEST] RealPlayer",
            "[Rcon: [MC_BACKUP_REQUEST] RealPlayer]",
            "[MC_BACKUP_REQUEST] RealPlayer extra",
            "[MC_BACKUP_REQUEST] ../../etc",
        ):
            self.assertIsNone(self.process(message))
        self.assertEqual([], self.events)

    def test_status_command_uses_separate_status_action(self) -> None:
        self.assertEqual(("status", "Server"), self.process("[MC_BACKUP_STATUS] Server"))

    def test_interrupted_logout_keeps_session_eligible_for_replay(self) -> None:
        self.process("RealPlayer[/198.51.100.10:25565] logged in with entity id 42 at (0, 0, 0)")
        self.watcher.trigger = MagicMock(side_effect=RuntimeError("worker interrupted"))
        with self.assertRaises(RuntimeError):
            self.process("RealPlayer left the game")
        self.assertIn("RealPlayer", json.loads(self.state_file.read_text())["real_players"])


class JournalCursorTests(unittest.TestCase):
    def test_follower_resumes_cursor_and_commits_only_processed_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cursor = Path(directory) / "cursor"
            cursor.write_text("saved-position\n")
            process = MagicMock()
            process.__enter__.return_value = process
            process.returncode = 0
            process.stdout = iter([
                json.dumps({"MESSAGE": "request", "__CURSOR": "request-position"}),
                json.dumps({"MESSAGE": "next", "__CURSOR": "next-position"}),
            ])
            with patch.object(MODULE.subprocess, "Popen", return_value=process) as popen, patch.object(MODULE, "notify_ready") as ready:
                records = iter(MODULE.journal_lines(cursor))
                self.assertEqual("request", next(records))
                self.assertEqual("saved-position", cursor.read_text().strip())
                ready.assert_called_once()
                self.assertIn("--after-cursor", popen.call_args.args[0])
                self.assertIn("saved-position", popen.call_args.args[0])
                self.assertEqual("next", next(records))
                self.assertEqual("request-position", cursor.read_text().strip())
                with self.assertRaises(StopIteration):
                    next(records)
                self.assertEqual("next-position", cursor.read_text().strip())

    def test_first_start_captures_position_before_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cursor = Path(directory) / "cursor"
            process = MagicMock()
            process.__enter__.return_value = process
            process.returncode = 0
            process.stdout = iter([json.dumps({"MESSAGE": "arrived during startup", "__CURSOR": "new"})])
            tail = subprocess.CompletedProcess([], 0, json.dumps({"__CURSOR": "startup-position"}), "")
            def ready():
                self.assertEqual("startup-position", cursor.read_text().strip())
            with patch.object(MODULE.subprocess, "run", return_value=tail), patch.object(MODULE.subprocess, "Popen", return_value=process) as popen, patch.object(MODULE, "notify_ready", side_effect=ready):
                self.assertEqual(["arrived during startup"], list(MODULE.journal_lines(cursor)))
                self.assertIn("startup-position", popen.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
