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

install -o root -g root -m 0755 \
  "$SOURCE_DIR/usr/local/bin/mc-backup.sh" \
  /usr/local/bin/mc-backup.sh
install -o root -g root -m 0755 \
  "$SOURCE_DIR/usr/local/bin/mc-backup-event-watch.py" \
  /usr/local/bin/mc-backup-event-watch.py

for unit in mc-backup.service mc-backup.timer mc-backup-events.service; do
  install -o root -g root -m 0644 \
    "$SOURCE_DIR/etc/systemd/system/$unit" \
    "/etc/systemd/system/$unit"
done

systemd-analyze verify \
  /etc/systemd/system/mc-backup.service \
  /etc/systemd/system/mc-backup.timer \
  /etc/systemd/system/mc-backup-events.service
systemctl daemon-reload
systemctl enable --now mc-backup.timer mc-backup-events.service

echo "Minecraft daily and player-event backup services installed."
