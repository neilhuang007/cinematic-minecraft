# Minecraft backups

The production server uses Borg to back up the Fabric server directory.  The
deployment payload lives in `ops/minecraft-backups`; credentials do not belong
in this repository.

## What is backed up

`mc-backup.sh` flushes the running server over local RCON (`save-off`,
`save-all flush`), creates a Borg archive, and restores autosave even if Borg
or the flush fails.  It omits transient logs, debug output, crash reports, and
the world session lock.

It creates clearly separated archive families:

| Trigger | Archive label | Retention |
| --- | --- | --- |
| Daily timer | `mc-daily-…` | 14 daily archives |
| Real-player login/logout | `mc-event-login-PLAYER-…` / `mc-event-logout-PLAYER-…` | Every event for 2 days, then 7 daily archives |
| Earlier timer archives | `mc-YYYY…` | 14 daily archives during migration |

The event retention applies across all players and both event types. Both ends
of a short session remain recoverable during the two-day incident-response
window. Borg compaction happens with the daily run; event runs still prune
their old archives immediately.

The production repository currently uses Borg encryption mode `none`. The
event service explicitly acknowledges its first access from the service's
isolated, persistent Borg security directory; this avoids an interactive
prompt without exposing the root account's Borg state.

## Player-event detection

`mc-backup-events.service` tails only new `minecraft.service` journal lines.
It treats a login as real only when the authoritative server login record is
of this form:

```text
PlayerName[/network-endpoint] logged in …
```

Carpet fake/local players have the distinct `[local]` endpoint and are ignored.
The watcher records only real logged-in names. A subsequent authoritative
`left the game` record triggers a logout backup only if that name was
previously recorded as real. This also prevents fake-player disconnects and
unauthenticated connection attempts from creating backups. A local-player
login also clears a stale matching real session, preventing a fake player from
inheriting an identity after an unclean server stop.

The watcher starts before Minecraft at boot and follows only new journal
records rather than replaying old player events. Its state is stored atomically
in `/var/lib/minecraft-backup` so a watcher-only restart does not forget active
real sessions. A Minecraft service start boundary clears that state so a name
from a crashed server generation cannot authorize a later logout backup.

## Reconnect and concurrency behavior

All backup requests use `/run/lock/mc-backup.lock`. A login/logout event waits
for a daily backup or another event backup to finish. By default, every
genuine login and logout creates a snapshot. An optional positive debounce
checks the timestamp of the same event for the same player. Login and logout
use separate markers, so one never suppresses the other.

## Installation

This repository does not contain the server's Borg or RCON secrets. The
idempotent installer preserves `/etc/minecraft-backup.env`, validates the
units, installs the following files, and enables the timer and watcher:

```text
/usr/local/bin/mc-backup.sh
/usr/local/bin/mc-backup-event-watch.py
/etc/systemd/system/mc-backup.service
/etc/systemd/system/mc-backup.timer
/etc/systemd/system/mc-backup-events.service
```

On an existing server, retain its root-only `/etc/minecraft-backup.env` and
run:

```bash
sudo ops/minecraft-backups/install.sh
```

For a new server, create `/etc/minecraft-backup.env` from the example with
restrictive root-only permissions first. Do not copy the example password
value into production. Verify a real login and logout produces the expected
event archive label; verify a Carpet `/player` local player produces no event
backup.

## Checks before deployment

Run the parser tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

On the server, validate the units before enabling them:

```bash
systemd-analyze verify /etc/systemd/system/mc-backup.service \
  /etc/systemd/system/mc-backup.timer \
  /etc/systemd/system/mc-backup-events.service
```

The event watcher is intentionally driven by server-authenticated login log
records, not the generic `joined the game` line.  Keep that distinction when
upgrading Minecraft, Fabric Carpet, or log configuration.
