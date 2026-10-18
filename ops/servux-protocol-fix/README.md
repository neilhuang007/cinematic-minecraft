# Servux packet compatibility fix

MiniHUD 0.38.16 disconnected on joining with `ServuxHudPacket#fromPacket:
error reading Weather Tick`, followed by `custom_payload ... larger than I
expected`. This occurred both before and after the shared ghast farm placements
were installed. Servux 0.9.5 used the older NBT wire format; the installed
MiniHUD/MaLiLib/Litematica versions expect the newer data-tag protocol.

[Servux 0.9.6](https://modrinth.com/mod/servux/version/hP2cDwH3) documents the
backwards-incompatible protocol change. This deployment pins
[Servux 0.9.9 for Minecraft 1.21.11](https://modrinth.com/mod/servux/version/9041JwWA),
matching MiniHUD 0.38.16, MaLiLib 0.27.20 and Litematica 0.26.16.

Commit and push locally, then pull on the server. With the backup lock held and
`minecraft.service` stopped, run `python3 ops/servux-protocol-fix/apply.py`.
Restart the service in a finally block. The installer checks both jar hashes
and release metadata, backs up the old jar and Servux configuration, and
preserves existing configuration, world data and Syncmatica placements.

Verify that startup loads Servux 0.9.9 and RCON responds, then reconnect the
existing client and check for another HUD decoder error. Captured disconnects
and the upstream protocol change establish the failure; no artificial packet
test is claimed to replace this client reconnect check. A successful startup
alone does not establish that the client disconnect is fixed.

For rollback, stop Minecraft, move the new jar out of `mods`, restore the old
jar and `servux.json` from the installer backup, and restart. Older clients
using the pre-August protocol need matching client mod updates.
