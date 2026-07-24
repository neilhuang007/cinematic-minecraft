from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
