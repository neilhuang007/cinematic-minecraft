# Client/server block-state synchronization

Nekoma's Fixed 0.5.3 (internally versioned 0.5.2) was installed only on the
client. Its vanilla block-state changes shifted network state IDs: client ID
27722 decoded as an oxidized copper golem statue instead of deepslate. The
server's saved section at chunk (-32, 22), section Y=-4 contained 3,306
deepslate blocks; Bobby cached those as 3,306 statues. July 24, July 30 and
September 13 backups contain the same intact section. A complete read of
102,576 saved chunks found no unreadable chunks and only 14 statue blocks.

The fix keeps the local pack intact and matches supported gameplay mods on the
server. The manifest pins every addition/replacement to the local jar hash.
Client renderers, menus, shaders and GPU-only acceleration remain client-side.
Existing server-only helpers remain installed. Minecraft and Fabric Loader are
unchanged. The world is preserved.

Build the private binary payload locally, commit and push these operations
files, then pull that commit on the server. Run `apply.py TARGET PAYLOAD
--backup NEW_BACKUP_DIRECTORY` against an isolated, stopped staging copy first.
Staging must bind to localhost on a separate port, with RCON, query, voice chat
and AutoModpack hosting disabled. Test startup and compare vanilla state IDs
against the full client pack. Do not start pregeneration during recovery.

Before production deployment, stop Minecraft cleanly and create a new Borg
recovery archive without pruning. Apply the same payload, start the service,
verify RCON/startup/registry decoding and retain the runtime snapshot. Preserve
and reset the affected server's local Bobby and Voxy caches, since they hold
the previously misdecoded terrain. No local mods need to be removed.

For rollback, stop the server, preserve its new runtime/world, restore the
previous mods/configuration snapshot and the cold world snapshot together,
then restart. Restoring old server mods alone reintroduces the client mismatch.
