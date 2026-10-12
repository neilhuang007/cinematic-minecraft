# Minecraft backups

The production server uses Borg to back up the Fabric server directory.  The
deployment payload lives in `ops/minecraft-backups`; credentials do not belong
in this repository.

## What is backed up

`mc-backup.sh` flushes the running server over local RCON (`save-off`,
`save-all flush`), takes an LVM snapshot, and immediately restores autosave.
Borg reads only the read-only snapshot. This avoids racing asynchronous mod
writes that continue after vanilla's save flush. The archive preserves the
original `srv/minecraft/servers/fabric-1.21.11/...` paths. It omits transient
logs, debug output, crash reports, and the world session lock.

The snapshot is a temporary copy-on-write view, not another full world copy.
LVM freezes/thaws the filesystem during creation. An 8 GiB reserve covers
changes to the source volume while Borg reads it. The worker unmounts and
removes its snapshot on completion, errors, and graceful termination. Failed
snapshot creation, mounting, or world flushing aborts the backup and restores
autosave. Snapshotting provides a stable filesystem image after the game's
flush; mod data with separate transactional requirements may need additional
integration. No Minecraft restart is needed for routine backups.

It creates clearly separated archive families:

| Trigger | Archive label | Retention |
| --- | --- | --- |
| Daily timer | `mc-daily-…` | 14 daily archives |
| Real-player login/logout | `mc-event-login-PLAYER-…` / `mc-event-logout-PLAYER-…` | Every event for 2 days, then 7 daily archives |
| Earlier timer archives | `mc-YYYY…` | 14 daily archives during migration |
| `/backup` or `/checkpoint` | `mc-manual-PLAYER-…` | Last 20 plus 4 weekly archives |
| Unsuccessful attempts | `mc-incomplete-…` | Last 2, separate from good backups |

## In-game commands

- `/backup` and `/checkpoint` request the same incremental Borg checkpoint.
- `/backup status` and `/checkpoint status` report the latest successful
  archive and available backup storage.
- Commands require operator permission level 2. Arbitrary `/script` access is
  restricted to operators as part of installation.
- A request returns immediately. Completion or failure is sent privately to
  the requesting player; a request acknowledgement is not a success report.
- Both aliases share a 60-second cooldown after a successful manual checkpoint.

The installer loads two small Scarpet apps using the existing Carpet mod.
`stay_loaded` and `scriptsAutoload` retain the commands across server restarts.
The apps emit exact server log markers. The existing worker accepts only
anchored server records, validates player names, and invokes fixed backup
actions with argument arrays. Chat text and RCON feedback containing a marker
do not trigger backups. No shell commands or paths come from players.

The event retention applies across all players and both event types. Both ends
of a short session remain recoverable during the two-day incident-response
window. Every run performs retention and compaction, and an independent hourly
maintenance timer runs even when backup creation fails. Each new archive is
created in the incomplete family and promoted only after Borg succeeds with
no warnings and the temporary snapshot is removed. An incomplete attempt can
never displace the last successful daily archive. Compaction still runs if a
prune command reports an error. Permanent `mc-preserved-*` historical archives
are deliberately outside automatic retention.

A 5 GiB free-space guard attempts maintenance before refusing another backup.
This reserves headroom for repository maintenance. `last-success.json` in
`/var/lib/minecraft-backup` records only successfully completed archives.
Hourly maintenance reports both filesystems and exits with an error at 85%
used or below the configured free-space reserve, making capacity pressure
visible in systemd before either volume fills.

## Storage layout

The Hetzner deployment uses `/dev/vg0/srv` for `/srv` and the `/opt` bind mount.
`prepare-storage.sh` grows that LV online to 152 GiB and allocates a separate
40 GiB LV at `/var/lib/minecraft-backups`, using existing unallocated space.
It preserves at least 16 GiB of unallocated VG space for temporary snapshots.
The original Borg path is a symlink to `/var/lib/minecraft-backups/borg`, so
Hill175's existing backup integration continues to use the same repository.
The volume is mounted through UUID in `/etc/fstab`; backup services require it.

Migration holds the shared backup lock, verifies a checksummed repository copy
and a Borg repository check, then switches the path. The original directory
is retained as `borg.before-volume-move` until the new worker and restores are
verified. This is separate local storage on the same physical mirror, not an
off-site backup. A separate machine or object-store destination is still
needed for protection against loss of this host.

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
/etc/systemd/system/mc-backup-maintenance.service
/etc/systemd/system/mc-backup-maintenance.timer
world/scripts/backup.sc
world/scripts/checkpoint.sc
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

Run the parser and actual shell-entry-point regression tests from Linux/WSL:

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

After deployment, run a daily backup and each command through RCON, verify
the command-to-worker-to-Borg flow, test a dry-run extraction, check that no
temporary LV/mount remains, and confirm autosave was re-enabled. A leftover
`mc_backup_snapshot` after an ungraceful host/process failure must be inspected
under the shared lock before removal; the worker will not delete an unknown
pre-existing snapshot automatically.
