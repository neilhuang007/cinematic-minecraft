# September 2026 mod refresh

Updates the existing Fabric 1.21.11 server to the matching local profile jars.
`manifest.json` pins the before/after SHA-256 values for 18 mod replacements and
Fabric Loader 0.19.3 -> 0.19.5. Loader 0.19.5 is required by the new Kotlin library.
VSS 0.2.3 becomes LSS 0.14.0; the jar still uses the local filename
`voxy-server-side-fabric.jar`.

AutoModpack already runs on this server. Its newer 4.0.6 jar is taken from the
locally disabled client copy without enabling it in the client. RoadWeaver and
Elytra Trims have identical local disabled copies and remain unchanged. Servux
has no local replacement. The client-only Fancy World Animations update is
excluded. Other client mods and newly added world-generation mods are outside
this refresh. Existing server configuration and the world are retained.

The binary payload is transferred privately using plink and is not committed.
Build locally, commit and push this directory, then pull the commit on the
server before running `apply.py`. The payload's manifest must exactly match
the checked-in manifest; all old and new jar hashes are verified before writes.

Before deployment, create a Borg snapshot using the existing backup service.
Extract its world into an isolated staging directory, copy the server runtime,
and run `apply.py STAGING PAYLOAD --backup STAGING_BACKUP`. Bind the staging
server to localhost on a separate port and disable its RCON, voice chat and
AutoModpack hosting. Confirm Minecraft/Fabric versions, dependency resolution,
successful world loading, RoadWeaver initialization and a server status response.

For production, stop `minecraft.service` gracefully, take a cold Borg snapshot,
and run `apply.py /srv/minecraft/servers/fabric-1.21.11 PAYLOAD --backup BACKUP`.
Start the service and verify startup, RCON, world/chunk loading and mod hashes.
The script snapshots the previous mods, launcher and configuration. If startup
fails, stop the service and restore that snapshot. The Borg archive additionally
preserves the world before the update. Do not resume paused pregeneration as
part of a mod refresh.
