#!/usr/bin/env python3
"""Turn authoritative Minecraft player session log records into Borg backups.

The Fabric/Carpet server writes fake players as ``Name[local] logged in``.
Only a non-local login creates a tracked real session; disconnect records are
acted on only for names in that set.  This is deliberately stricter than
matching Minecraft's generic "joined the game" line.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable


LOG = logging.getLogger("mc-backup-events")
PLAYER = r"[A-Za-z0-9_]{3,16}"
LOGIN_RE = re.compile(
    rf"\[Server thread/INFO\]: (?P<player>{PLAYER})\[(?P<endpoint>[^\]]+)\] "
    r"logged in with entity id \d+\b"
)
LOGOUT_RE = re.compile(
    rf"\[Server thread/INFO\]: (?P<player>{PLAYER}) left the game(?:\s|$)"
)
SERVICE_BOUNDARY_RE = re.compile(
    r"^(?:Starting|Started) minecraft\.service\b"
)


class EventWatcher:
    """Maintains the real-player session set and triggers matching backups."""

    def __init__(self, state_file: Path, trigger: Callable[[str, str], None]) -> None:
        self.state_file = state_file
        self.trigger = trigger
        self.real_players = self._load_state()

    def _load_state(self) -> set[str]:
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            players = payload.get("real_players", [])
            if not isinstance(players, list) or not all(
                isinstance(player, str) and re.fullmatch(PLAYER, player) for player in players
            ):
                raise ValueError("real_players is not a list of Minecraft names")
            return set(players)
        except FileNotFoundError:
            return set()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            # A corrupt cache must not make a fake player eligible for logout
            # backups. Start safely with no tracked sessions instead.
            LOG.warning("Ignoring unreadable player-session state %s: %s", self.state_file, exc)
            return set()

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        contents = json.dumps({"real_players": sorted(self.real_players)}) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.state_file.parent,
            prefix=f".{self.state_file.name}.",
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                temporary.write(contents)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.state_file)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    def process_line(self, line: str) -> tuple[str, str] | None:
        """Process one journal message and return its emitted event, if any."""
        if SERVICE_BOUNDARY_RE.search(line):
            # A Minecraft process generation owns its player connections.
            # Never carry names from a crashed/stopped generation into the
            # next one, where an unauthenticated attempt could reuse a name.
            if self.real_players:
                self.real_players.clear()
                self._save_state()
            return None

        login = LOGIN_RE.search(line)
        if login:
            player = login.group("player")
            endpoint = login.group("endpoint")
            if endpoint == "local":
                # A stale real-session state (for example after an unclean
                # server stop) must not let a later Carpet fake-player logout
                # inherit that identity and create an event backup.
                if player in self.real_players:
                    self.real_players.remove(player)
                    self._save_state()
                LOG.debug("Ignoring Carpet local-player login for %s", player)
                return None
            if not endpoint.startswith("/"):
                LOG.warning("Ignoring login for %s with non-network endpoint %r", player, endpoint)
                return None
            self.real_players.add(player)
            self._save_state()
            self.trigger("login", player)
            return ("login", player)

        logout = LOGOUT_RE.search(line)
        if logout:
            player = logout.group("player")
            if player not in self.real_players:
                return None
            self.real_players.remove(player)
            self._save_state()
            self.trigger("logout", player)
            return ("logout", player)
        return None


def backup_trigger(backup_command: str) -> Callable[[str, str], None]:
    def trigger(event: str, player: str) -> None:
        LOG.info("Requesting %s backup for real player %s", event, player)
        completed = subprocess.run(
            [backup_command, "--event", event, player],
            check=False,
        )
        if completed.returncode != 0:
            LOG.error("%s backup for %s exited with status %d", event, player, completed.returncode)

    return trigger


def journal_lines() -> Iterable[str]:
    command = [
        "journalctl",
        "-u",
        "minecraft.service",
        "--follow",
        "--lines=0",
        "--no-pager",
        "--output=cat",
    ]
    LOG.info("Following new Minecraft journal records")
    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True, bufsize=1) as process:
        assert process.stdout is not None
        yield from process.stdout
    if process.returncode:
        raise RuntimeError(f"journalctl stopped with status {process.returncode}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("/var/lib/minecraft-backup/real-player-state.json"),
        help="durable set of players whose next disconnect is real",
    )
    parser.add_argument(
        "--backup-command",
        default="/usr/local/bin/mc-backup.sh",
        help="backup script to call with --event EVENT PLAYER",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read log records from stdin (for diagnostics and tests)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    logging.basicConfig(
        level=logging.DEBUG if arguments.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    watcher = EventWatcher(arguments.state_file, backup_trigger(arguments.backup_command))
    source: Iterable[str] = sys.stdin if arguments.stdin else journal_lines()
    try:
        for line in source:
            watcher.process_line(line.rstrip("\n"))
    except KeyboardInterrupt:
        return 0
    except Exception:
        LOG.exception("Minecraft event watcher stopped unexpectedly")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
