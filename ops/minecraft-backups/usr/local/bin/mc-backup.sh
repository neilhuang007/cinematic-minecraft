#!/usr/bin/env bash
# Borg backups from a flushed, read-only LVM snapshot. Secrets remain local.
set -Eeuo pipefail

readonly ENV_FILE="${MC_BACKUP_ENV_FILE:-/etc/minecraft-backup.env}"
readonly LOCK_FILE="${MC_BACKUP_LOCK_FILE:-/run/lock/mc-backup.lock}"
readonly STATE_DIR="${MC_BACKUP_STATE_DIR:-/var/lib/minecraft-backup}"
readonly EVENT_STATE_DIR="${STATE_DIR}/event-debounce"

usage() {
  echo 'Usage: mc-backup.sh --daily | --event login|logout PLAYER | --manual PLAYER | --status PLAYER | --maintenance'
}
mode=daily
event=''
player=''
case "${1:---daily}" in
  --daily) [[ $# -le 1 ]] || { usage >&2; exit 2; } ;;
  --maintenance) [[ $# -eq 1 ]] || { usage >&2; exit 2; }; mode=maintenance ;;
  --manual|--status)
    [[ $# -eq 2 ]] || { usage >&2; exit 2; }
    mode="${1#--}"; player="$2"
    ;;
  --event)
    [[ $# -eq 3 ]] || { usage >&2; exit 2; }
    mode=event; event="$2"; player="$3"
    [[ "$event" == login || "$event" == logout ]] || { usage >&2; exit 2; }
    ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[[ -z "$player" || "$player" =~ ^[A-Za-z0-9_]{3,16}$ ]] || { echo 'Invalid player' >&2; exit 2; }

if [[ "${MC_BACKUP_LOCK_HELD:-0}" != 1 && "$mode" != status ]]; then
  install -d -m 0750 "$STATE_DIR"
  exec flock --close -x "$LOCK_FILE" env MC_BACKUP_LOCK_HELD=1 "$0" "$@"
fi
[[ -r "$ENV_FILE" ]] || { echo "Missing backup environment: $ENV_FILE" >&2; exit 1; }
read -r env_owner env_mode < <(stat -c '%u %a' "$ENV_FILE")
[[ "$env_owner" == 0 && "$env_mode" == 600 ]] || {
  echo 'Backup environment must be root-owned with mode 0600' >&2; exit 1;
}
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a
export BORG_REPO="${BORG_REPO:-${BORG_REPO_PATH:-}}"
: "${BORG_REPO:?}" "${SRV_DIR:?}" "${RCON_HOST:?}" "${RCON_PORT:?}" "${RCON_PASSWORD:?}"
export MCRCON_HOST="$RCON_HOST" MCRCON_PORT="$RCON_PORT" MCRCON_PASS="$RCON_PASSWORD"
unset RCON_PASSWORD

KEEP_DAILY="${KEEP_DAILY:-14}"
KEEP_EVENT_WITHIN="${KEEP_EVENT_WITHIN:-2d}"
KEEP_EVENT_DAILY="${KEEP_EVENT_DAILY:-7}"
KEEP_MANUAL_LAST="${KEEP_MANUAL_LAST:-20}"
EVENT_DEBOUNCE_SECONDS="${EVENT_DEBOUNCE_SECONDS:-0}"
MANUAL_DEBOUNCE_SECONDS="${MANUAL_DEBOUNCE_SECONDS:-60}"
SAVE_FLUSH_WAIT_SECONDS="${SAVE_FLUSH_WAIT_SECONDS:-3}"
MIN_FREE_GIB="${MIN_FREE_GIB:-5}"
SNAPSHOT_DEVICE="${SNAPSHOT_DEVICE:-/dev/vg0/srv}"
SNAPSHOT_SIZE="${SNAPSHOT_SIZE:-8G}"
SNAPSHOT_VIEW="${SNAPSHOT_VIEW:-/run/minecraft-backup/view}"
for number in "$KEEP_DAILY" "$KEEP_EVENT_DAILY" "$KEEP_MANUAL_LAST" "$EVENT_DEBOUNCE_SECONDS" "$MANUAL_DEBOUNCE_SECONDS" "$SAVE_FLUSH_WAIT_SECONDS" "$MIN_FREE_GIB"; do
  [[ "$number" =~ ^[0-9]+$ ]] || { echo 'Invalid numeric backup setting' >&2; exit 2; }
done
(( KEEP_DAILY > 0 && KEEP_EVENT_DAILY > 0 && KEEP_MANUAL_LAST > 0 )) || exit 2
[[ "$KEEP_EVENT_WITHIN" =~ ^[1-9][0-9]*[Hdwmy]$ ]] || exit 2
[[ "$SNAPSHOT_DEVICE" =~ ^/dev/[A-Za-z0-9_+-]+/[A-Za-z0-9_+-]+$ ]] || exit 2
[[ "$SNAPSHOT_SIZE" =~ ^[1-9][0-9]*[GM]$ ]] || exit 2
[[ "$SRV_DIR" == /* && "$SRV_DIR" != / && "$SNAPSHOT_VIEW" == /* && "$SNAPSHOT_VIEW" != / ]] || exit 2
install -d -m 0750 "$STATE_DIR"

notify_player() {
  local message="$1" color="${2:-green}" payload
  echo "$message"
  [[ -n "$player" && "$player" != Server && ( "$mode" == manual || "$mode" == status ) ]] || return 0
  payload="$(python3 -c 'import json,sys; print(json.dumps({"text":sys.argv[1],"color":sys.argv[2]}))' "$message" "$color")"
  mcrcon "tellraw ${player} ${payload}" >/dev/null 2>&1 || echo 'WARN: in-game notification failed' >&2
}

if [[ "$mode" == status ]]; then
  message="$(python3 - "$STATE_DIR/last-success.json" "$BORG_REPO" "$SRV_DIR" <<'PY'
import json, pathlib, shutil, sys
p = pathlib.Path(sys.argv[1])
try:
    last = json.loads(p.read_text())
    text = 'Last successful backup: '+last['archive']+' ('+last['time']+').'
except (OSError, ValueError, KeyError):
    text = 'No successful backup recorded by the new snapshot worker yet.'
free = shutil.disk_usage(sys.argv[2]).free / 2**30
world_free = shutil.disk_usage(sys.argv[3]).free / 2**30
print(f'{text} Free storage: backups {free:.1f} GiB; world/apps {world_free:.1f} GiB.')
PY
)"
  notify_player "$message" aqua
  exit 0
fi

housekeeping() {
  local result=0
  echo 'Pruning completed backup families; incomplete attempts never replace good restore points.'
  borg prune --stats --list --keep-daily "$KEEP_DAILY" --glob-archives 'mc-daily-*' || result=$?
  borg prune --stats --list --keep-daily "$KEEP_DAILY" --glob-archives 'mc-[0-9]*' || result=$?
  borg prune --stats --list --keep-within "$KEEP_EVENT_WITHIN" --keep-daily "$KEEP_EVENT_DAILY" --glob-archives 'mc-event-*' || result=$?
  borg prune --stats --list --keep-last "$KEEP_MANUAL_LAST" --keep-weekly 4 --glob-archives 'mc-manual-*' || result=$?
  borg prune --stats --list --keep-last 2 --glob-archives 'mc-incomplete-*' || result=$?
  # Run compaction even when a preceding command reports a warning/error.
  borg compact --verbose || result=$?
  python3 - "$BORG_REPO" "$SRV_DIR" "$MIN_FREE_GIB" <<'PY' || result=$?
import shutil, sys
healthy = True
for name, path in zip(('backup', 'world/apps'), sys.argv[1:3]):
    disk = shutil.disk_usage(path)
    used_percent = 100 * disk.used / (disk.used + disk.free)
    free_gib = disk.free / 2**30
    print(f'Storage health: {name} {used_percent:.1f}% used, {free_gib:.1f} GiB available.')
    if used_percent >= 85 or free_gib < int(sys.argv[3]):
        print(f'ERROR: {name} storage needs attention.', file=sys.stderr)
        healthy = False
sys.exit(0 if healthy else 1)
PY
  return "$result"
}

if [[ "$mode" == maintenance ]]; then
  housekeeping
  exit $?
fi

event_marker=''
debounce=0
if [[ "$mode" == event ]]; then
  install -d -m 0750 "$EVENT_STATE_DIR"
  event_marker="${EVENT_STATE_DIR}/${event}-${player}.epoch"
  debounce="$EVENT_DEBOUNCE_SECONDS"
elif [[ "$mode" == manual ]]; then
  event_marker="${STATE_DIR}/manual.epoch"
  debounce="$MANUAL_DEBOUNCE_SECONDS"
fi
if [[ -n "$event_marker" && -s "$event_marker" && "$debounce" -gt 0 ]]; then
  last_backup="$(<"$event_marker")"
  if [[ "$last_backup" =~ ^[0-9]+$ ]] && (( $(date +%s) - last_backup < debounce )); then
    notify_player 'A recent checkpoint already completed. Wait a minute before requesting another.' yellow
    exit 0
  fi
fi

free_bytes() { df -B1 --output=avail "$BORG_REPO" | tail -1 | tr -d ' '; }
if (( $(free_bytes) < MIN_FREE_GIB * 1073741824 )); then
  housekeeping || true
  if (( $(free_bytes) < MIN_FREE_GIB * 1073741824 )); then
    notify_player "Backup refused: less than ${MIN_FREE_GIB} GiB of free storage remains." red
    exit 1
  fi
fi

timestamp="$(date -u '+%Y-%m-%dT%H:%M:%S.%N')"
case "$mode" in
  daily) archive="mc-daily-${timestamp}" ;;
  event) archive="mc-event-${event}-${player}-${timestamp}" ;;
  manual) archive="mc-manual-${player}-${timestamp}" ;;
esac
incomplete="mc-incomplete-${archive#mc-}"
snapshot_device="${SNAPSHOT_DEVICE%/*}/mc_backup_snapshot"
snapshot_mount=''
snapshot_created=0
snapshot_mounted=0
autosave_disabled=0
archive_completed=0

resume_saves() {
  if (( autosave_disabled )); then
    if mcrcon save-on >/dev/null; then
      autosave_disabled=0
    else
      return 1
    fi
  fi
}
remove_snapshot() {
  if (( snapshot_mounted )); then
    umount "$snapshot_mount" || return $?
    snapshot_mounted=0
  fi
  if (( snapshot_created )); then
    lvremove --yes "$snapshot_device" || return $?
    snapshot_created=0
  fi
}
cleanup() {
  local result=$?
  trap - EXIT
  resume_saves || { echo 'ERROR: could not re-enable autosave' >&2; result=1; }
  remove_snapshot || { echo 'ERROR: temporary snapshot cleanup failed' >&2; result=1; }
  if (( result != 0 )); then
    if (( archive_completed )); then
      notify_player "Checkpoint saved as ${archive}, but backup housekeeping needs attention." yellow
    else
      notify_player 'Backup failed; earlier successful checkpoints are retained. Check the backup service log.' red
    fi
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

source_mount="$(findmnt -n -o TARGET --target "$SRV_DIR")"
source_device="$(findmnt -n -o SOURCE --target "$SRV_DIR")"
[[ "$source_mount" != / && "$SRV_DIR" == "$source_mount/"* ]] || {
  echo 'Runtime must reside on its own mounted filesystem' >&2; exit 1;
}
[[ "$(readlink -f "$source_device")" == "$(readlink -f "$SNAPSHOT_DEVICE")" ]] || {
  echo 'Configured snapshot device does not contain the runtime' >&2; exit 1;
}
if lvs "$snapshot_device" >/dev/null 2>&1; then
  echo 'A temporary backup snapshot already exists; inspect it before retrying' >&2
  exit 1
fi
snapshot_mount="${SNAPSHOT_VIEW}${source_mount}"
install -d -m 0750 "$snapshot_mount"
if mountpoint -q "$snapshot_mount"; then
  echo 'Snapshot mount point is already in use; refusing to replace it' >&2
  exit 1
fi
if systemctl is-active --quiet minecraft.service; then
  autosave_disabled=1
  mcrcon save-off 'save-all flush' >/dev/null
  sleep "$SAVE_FLUSH_WAIT_SECONDS"
fi
# Device mapper freezes/thaws the filesystem as part of snapshot creation.
# The fixed device is checked absent above and is protected by our shared lock.
snapshot_created=1
lvcreate --snapshot --size "$SNAPSHOT_SIZE" --name mc_backup_snapshot \
  --addtag minecraft_backup_snapshot --permission r "$SNAPSHOT_DEVICE"
resume_saves
mount -o ro,noload,nodev,nosuid,noexec "$snapshot_device" "$snapshot_mount"
snapshot_mounted=1
[[ -f "${SNAPSHOT_VIEW}${SRV_DIR}/world/level.dat" ]] || { echo 'Snapshot lacks world/level.dat' >&2; exit 1; }

echo "Creating ${archive} from the immutable filesystem snapshot."
create_result=0
(
  cd "$SNAPSHOT_VIEW"
  borg create --stats --compression zstd,6 \
    --exclude "${SRV_DIR#/}/logs" \
    --exclude "${SRV_DIR#/}/debug" \
    --exclude "${SRV_DIR#/}/crash-reports" \
    --exclude "${SRV_DIR#/}/world/session.lock" \
    --exclude '*.log.gz' \
    "::${incomplete}" "${SRV_DIR#/}"
) || create_result=$?
snapshot_attributes="$(lvs --noheadings -o lv_attr,data_percent "$snapshot_device")"
[[ "$snapshot_attributes" != *I* ]] || create_result=2
remove_snapshot

if (( create_result != 0 )); then
  echo "Borg returned ${create_result}; retaining the incomplete archive separately." >&2
  housekeeping || true
  exit "$create_result"
fi
borg rename "::${incomplete}" "$archive"
archive_completed=1
python3 - "$STATE_DIR/last-success.json" "$archive" <<'PY'
import datetime, json, os, pathlib, sys, tempfile
path = pathlib.Path(sys.argv[1])
fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.last-success-')
try:
    with os.fdopen(fd, 'w') as stream:
        json.dump({'archive': sys.argv[2], 'time': datetime.datetime.now(datetime.timezone.utc).isoformat()}, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary): os.unlink(temporary)
PY
if [[ -n "$event_marker" ]]; then
  umask 077
  marker_tmp="$(mktemp "${event_marker}.XXXXXX")"
  date +%s > "$marker_tmp"
  mv -f "$marker_tmp" "$event_marker"
fi
housekeeping
notify_player "Checkpoint saved: ${archive}"
