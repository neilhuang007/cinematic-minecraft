#!/usr/bin/env bash
# Minecraft Borg backup entry point.  Invoked by the daily timer and the
# player-event watcher.  Configuration (including Borg/RCON secrets) stays in
# /etc/minecraft-backup.env and is deliberately not part of this repository.
set -Eeuo pipefail

readonly ENV_FILE="${MC_BACKUP_ENV_FILE:-/etc/minecraft-backup.env}"
readonly LOCK_FILE="${MC_BACKUP_LOCK_FILE:-/run/lock/mc-backup.lock}"
readonly STATE_DIR="${MC_BACKUP_STATE_DIR:-/var/lib/minecraft-backup}"
readonly EVENT_STATE_DIR="${STATE_DIR}/event-debounce"

usage() {
  cat <<'USAGE'
Usage:
  mc-backup.sh --daily
  mc-backup.sh --event login|logout PLAYER

Repeated copies of the same player event can be rate-limited with
EVENT_DEBOUNCE_SECONDS. The default is zero, so every genuine login and logout
gets a snapshot. Both forms take the same exclusive lock, so Borg never runs
concurrently with itself.
USAGE
}

mode="daily"
event=""
player=""

case "${1:---daily}" in
  --daily)
    [[ "$#" -eq 1 || "$#" -eq 0 ]] || { usage >&2; exit 2; }
    ;;
  --event)
    [[ "$#" -eq 3 ]] || { usage >&2; exit 2; }
    mode="event"
    event="$2"
    player="$3"
    [[ "$event" == "login" || "$event" == "logout" ]] || { echo "Invalid event: $event" >&2; exit 2; }
    [[ "$player" =~ ^[A-Za-z0-9_]{3,16}$ ]] || { echo "Invalid Minecraft player name" >&2; exit 2; }
    ;;
  --help|-h)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

# Keep daily and event backups mutually exclusive.  Re-exec after acquiring
# the lock so every caller re-evaluates debounce state only when it is current.
if [[ "${MC_BACKUP_LOCK_HELD:-0}" != "1" ]]; then
  install -d -m 0750 "$STATE_DIR"
  exec flock -x "$LOCK_FILE" env MC_BACKUP_LOCK_HELD=1 "$0" "$@"
fi

[[ -r "$ENV_FILE" ]] || { echo "Backup environment is missing: $ENV_FILE" >&2; exit 1; }
read -r env_owner env_mode < <(stat -c '%u %a' "$ENV_FILE")
if [[ "$env_owner" != "0" || "$env_mode" != "600" ]]; then
  echo "Backup environment must be owned by root with mode 0600: $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

# The production environment predates this repository and uses
# BORG_REPO_PATH. Keep that name compatible while standardizing on the
# variable Borg itself consumes.
if [[ -z "${BORG_REPO:-}" && -n "${BORG_REPO_PATH:-}" ]]; then
  BORG_REPO="$BORG_REPO_PATH"
fi
: "${BORG_REPO:?BORG_REPO must be set in the backup environment}"
: "${SRV_DIR:?SRV_DIR must be set in the backup environment}"
: "${RCON_HOST:?RCON_HOST must be set in the backup environment}"
: "${RCON_PORT:?RCON_PORT must be set in the backup environment}"
: "${RCON_PASSWORD:?RCON_PASSWORD must be set in the backup environment}"
export BORG_REPO

readonly KEEP_DAILY="${KEEP_DAILY:-14}"
readonly KEEP_EVENT_WITHIN="${KEEP_EVENT_WITHIN:-2d}"
readonly KEEP_EVENT_DAILY="${KEEP_EVENT_DAILY:-7}"
readonly EVENT_DEBOUNCE_SECONDS="${EVENT_DEBOUNCE_SECONDS:-0}"
readonly SAVE_FLUSH_WAIT_SECONDS="${SAVE_FLUSH_WAIT_SECONDS:-3}"

for number in "$KEEP_DAILY" "$KEEP_EVENT_DAILY" "$EVENT_DEBOUNCE_SECONDS" "$SAVE_FLUSH_WAIT_SECONDS"; do
  [[ "$number" =~ ^[0-9]+$ ]] || { echo "Backup retention and timing values must be non-negative integers" >&2; exit 2; }
done
[[ "$KEEP_EVENT_WITHIN" =~ ^[1-9][0-9]*[Hdwmy]$ ]] || {
  echo "KEEP_EVENT_WITHIN must be a positive Borg interval such as 48H or 2d" >&2
  exit 2
}

event_marker=""
if [[ "$mode" == "event" ]]; then
  install -d -m 0750 "$EVENT_STATE_DIR"
  event_marker="${EVENT_STATE_DIR}/${event}-${player}.epoch"
fi

if [[ -n "$event_marker" && "$EVENT_DEBOUNCE_SECONDS" -gt 0 && -s "$event_marker" ]]; then
  last_backup="$(<"$event_marker")"
  now_epoch="$(date +%s)"
  if [[ "$last_backup" =~ ^[0-9]+$ ]] && (( now_epoch - last_backup < EVENT_DEBOUNCE_SECONDS )); then
    echo "Skipping duplicate ${event} backup for ${player}: the same event completed $(( now_epoch - last_backup ))s ago."
    exit 0
  fi
fi

if [[ "$mode" == "daily" ]]; then
  archive="mc-daily-{now:%Y-%m-%dT%H:%M:%S}"
else
  archive="mc-event-${event}-${player}-{now:%Y-%m-%dT%H:%M:%S.%f}"
fi

# mcrcon supports environment-based credentials. Keep the password out of the
# process argument list, where non-root process inspection may expose it.
export MCRCON_HOST="$RCON_HOST"
export MCRCON_PORT="$RCON_PORT"
export MCRCON_PASS="$RCON_PASSWORD"
unset RCON_PASSWORD
rcon=(mcrcon)
server_up=0
autosave_disabled=0
if systemctl is-active --quiet minecraft.service; then
  server_up=1
fi

resume_saves() {
  if (( autosave_disabled )); then
    "${rcon[@]}" "save-on" >/dev/null 2>&1 || echo "WARN: failed to re-enable autosave" >&2
  fi
}
trap resume_saves EXIT

if (( server_up )); then
  echo "Server running: flushing world to disk for ${archive}."
  autosave_disabled=1
  "${rcon[@]}" "save-off" "save-all flush" >/dev/null
  sleep "$SAVE_FLUSH_WAIT_SECONDS"
else
  echo "Server not running: creating a cold-copy archive ${archive}."
fi

echo "Creating Borg archive ${archive}."
borg create \
  --stats --compression zstd,6 \
  --exclude "${SRV_DIR}/logs" \
  --exclude "${SRV_DIR}/debug" \
  --exclude "${SRV_DIR}/crash-reports" \
  --exclude "${SRV_DIR}/world/session.lock" \
  --exclude '*.log.gz' \
  "::${archive}" \
  "${SRV_DIR}"

# An event archive now exists, so duplicate copies of that same event should
# not create another archive even if retention housekeeping later fails.
if [[ -n "$event_marker" ]]; then
  umask 077
  marker_tmp="$(mktemp "${event_marker}.XXXXXX")"
  printf '%s\n' "$(date +%s)" >"$marker_tmp"
  mv -f "$marker_tmp" "$event_marker"
fi

resume_saves
autosave_disabled=0
trap - EXIT

echo "Pruning daily and event archive families."
borg prune --stats --list --keep-daily "$KEEP_DAILY" --glob-archives 'mc-daily-*'
# The original timer used mc-YYYY... labels.  Keep those bounded during the
# transition without conflating them with event archives.
borg prune --stats --list --keep-daily "$KEEP_DAILY" --glob-archives 'mc-[0-9]*'
borg prune --stats --list \
  --keep-within "$KEEP_EVENT_WITHIN" \
  --keep-daily "$KEEP_EVENT_DAILY" \
  --glob-archives 'mc-event-*'

# Compaction is intentionally daily: it reclaims data pruned from potentially
# frequent event archives without adding that cost to every player transition.
if [[ "$mode" == "daily" ]]; then
  borg compact
fi

echo "Backup complete: ${archive}"
