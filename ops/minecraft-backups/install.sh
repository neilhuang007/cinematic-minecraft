#!/usr/bin/env bash
# Install the version-controlled Minecraft backup scripts and systemd units.
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

readonly SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly ENV_FILE="/etc/minecraft-backup.env"

if [[ ! -r "$ENV_FILE" ]]; then
  echo "Refusing to install without the existing production environment: $ENV_FILE" >&2
  exit 1
fi
read -r env_owner env_mode < <(stat -c '%u %a' "$ENV_FILE")
if [[ "$env_owner" != "0" || "$env_mode" != "600" ]]; then
  echo "Refusing to source an environment not owned by root with mode 0600: $ENV_FILE" >&2
  exit 1
fi

for dependency in borg mcrcon lvcreate lvremove lvs findmnt mount umount python3; do
  command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
exec 9>/run/lock/mc-backup.lock
flock -w 1800 9

# Preserve all existing credentials and retention settings.
set -a
source "$ENV_FILE"
set +a
: "${SRV_DIR:?}" "${RCON_HOST:?}" "${RCON_PORT:?}" "${RCON_PASSWORD:?}"
systemctl stop mc-backup-events.service

install -o root -g root -m 0755 \
  "$SOURCE_DIR/usr/local/bin/mc-backup.sh" \
  /usr/local/bin/mc-backup.sh
install -o root -g root -m 0755 \
  "$SOURCE_DIR/usr/local/bin/mc-backup-event-watch.py" \
  /usr/local/bin/mc-backup-event-watch.py

for unit in mc-backup.service mc-backup.timer mc-backup-events.service mc-backup-maintenance.service mc-backup-maintenance.timer; do
  install -o root -g root -m 0644 \
    "$SOURCE_DIR/etc/systemd/system/$unit" \
    "/etc/systemd/system/$unit"
done

install -d -o mc -g mc -m 0755 "$SRV_DIR/world/scripts"
for app in backup checkpoint; do
  install -o root -g mc -m 0644 "$SOURCE_DIR/scarpet/backup.sc" "$SRV_DIR/world/scripts/$app.sc"
done

systemd-analyze verify \
  /etc/systemd/system/mc-backup.service \
  /etc/systemd/system/mc-backup.timer \
  /etc/systemd/system/mc-backup-events.service \
  /etc/systemd/system/mc-backup-maintenance.service \
  /etc/systemd/system/mc-backup-maintenance.timer
systemctl daemon-reload
systemctl enable --now mc-backup.timer
systemctl enable --now mc-backup-maintenance.timer
systemctl enable mc-backup-events.service
flock -u 9
systemctl restart mc-backup-events.service

if systemctl is-active --quiet minecraft.service; then
  export MCRCON_HOST="$RCON_HOST" MCRCON_PORT="$RCON_PORT" MCRCON_PASS="$RCON_PASSWORD"
  unset RCON_PASSWORD
  # Only operators may run arbitrary Scarpet code or the backup commands.
  mcrcon 'carpet setDefault commandScript ops' 'carpet setDefault scriptsAutoload true' \
    'script load backup' 'script load checkpoint'
fi

echo "Minecraft snapshot backups, in-game commands and independent maintenance installed."
