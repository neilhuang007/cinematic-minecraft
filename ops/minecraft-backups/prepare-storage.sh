#!/usr/bin/env bash
# One-time, guarded storage layout for the existing Hetzner vg0 server.
# Uses only unallocated VG extents. Never shrinks or formats an existing LV.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
readonly SOURCE=/dev/vg0/srv
readonly BACKUP_DEVICE=/dev/vg0/minecraft_backups
readonly DESTINATION=/var/lib/minecraft-backups
readonly REPO=/srv/minecraft/backups/borg
readonly TARGET_BYTES=$((152 * 1024 * 1024 * 1024))
readonly BACKUP_BYTES=$((40 * 1024 * 1024 * 1024))
readonly RESERVE_BYTES=$((16 * 1024 * 1024 * 1024))

exec 9>/run/lock/mc-backup.lock
flock -w 1800 9
[[ "$(findmnt -n -o FSTYPE --target /srv)" == ext4 ]] || exit 1
[[ "$(readlink -f "$(findmnt -n -o SOURCE --target /srv)")" == "$(readlink -f "$SOURCE")" ]] || exit 1
current="$(lvs --noheadings --units b --nosuffix -o lv_size "$SOURCE" | tr -d ' ')"
current="${current%.*}"
free="$(vgs --noheadings --units b --nosuffix -o vg_free vg0 | tr -d ' ')"
free="${free%.*}"
needed=0
if (( current < TARGET_BYTES )); then needed=$((TARGET_BYTES-current)); fi
if ! lvs "$BACKUP_DEVICE" >/dev/null 2>&1; then needed=$((needed+BACKUP_BYTES)); fi
(( free >= needed + RESERVE_BYTES )) || { echo 'Insufficient unallocated space with snapshot reserve' >&2; exit 1; }
vgcfgbackup -f "/root/vg0-before-minecraft-storage-$(date -u +%Y%m%dT%H%M%SZ).conf" vg0
if (( current < TARGET_BYTES )); then
  lvextend --size 152G --resizefs "$SOURCE"
fi

if ! lvs "$BACKUP_DEVICE" >/dev/null 2>&1; then
  lvcreate --size 40G --name minecraft_backups --addtag minecraft_backup_repository vg0
  # Format only the new LV created by this invocation, after checking it is empty.
  [[ -z "$(wipefs --noheadings --output TYPE "$BACKUP_DEVICE")" ]] || {
    echo 'Unexpected filesystem signature on new backup LV; refusing to format' >&2; exit 1;
  }
  mkfs.ext4 -m 1 -L mc-backups "$BACKUP_DEVICE"
fi
[[ "$(blkid -s TYPE -o value "$BACKUP_DEVICE")" == ext4 ]] || exit 1
install -d -m 0700 "$DESTINATION"
uuid="$(blkid -s UUID -o value "$BACKUP_DEVICE")"
if ! grep -Fq " $DESTINATION " /etc/fstab; then
  cp -a /etc/fstab "/root/fstab-before-minecraft-storage-$(date -u +%Y%m%dT%H%M%SZ)"
  printf 'UUID=%s %s ext4 defaults,nodev,nosuid 0 2\n' "$uuid" "$DESTINATION" >> /etc/fstab
  systemctl daemon-reload
fi
mountpoint -q "$DESTINATION" || mount "$DESTINATION"
[[ "$(readlink -f "$(findmnt -n -o SOURCE --target "$DESTINATION")")" == "$(readlink -f "$BACKUP_DEVICE")" ]] || exit 1

if [[ -L "$REPO" ]]; then
  [[ "$(readlink -f "$REPO")" == "$DESTINATION/borg" ]] || exit 1
  echo 'Borg repository already migrated.'
else
  [[ -f "$REPO/config" && ! -e "$REPO.before-volume-move" ]] || exit 1
  install -d -m 0700 "$DESTINATION/borg"
  rsync -aHAX --numeric-ids "$REPO/" "$DESTINATION/borg/"
  # Exclude Borg's ephemeral lock state when comparing the offline copy.
  difference="$(rsync -aHAXnci --delete --numeric-ids --exclude lock.exclusive --exclude lock.roster "$REPO/" "$DESTINATION/borg/")"
  [[ -z "$difference" ]] || { echo 'Repository copy differs; original retained' >&2; exit 1; }
  BORG_RELOCATED_REPO_ACCESS_IS_OK=yes borg check --repository-only "$DESTINATION/borg"
  # Switch only after validating the complete copy. Keep the original for
  # an explicit verified cleanup after the first new successful backup.
  mv "$REPO" "$REPO.before-volume-move"
  ln -s "$DESTINATION/borg" "$REPO"
fi
df -h /srv "$DESTINATION"
echo 'Repository migration verified. Original is retained at borg.before-volume-move until the new worker is verified.'
