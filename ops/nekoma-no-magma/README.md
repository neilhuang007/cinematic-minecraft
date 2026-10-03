# Disable magma becoming lava

Neil requested that mined magma blocks stop becoming lava on the multiplayer
server. The installed Nekoma's Fixed 0.5.3 for Minecraft 1.21.11 implements
only this behavior in `net.greenjab.nekomasfixed.mixin.BlockMixin`, via its
`customAfterBreak` injection. There is no saved server setting for it.

`patch.py` removes only `BlockMixin` from `nekomasfixed.mixins.json`. It requires
the reviewed original jar's SHA-256, preserves every other jar entry's contents,
and verifies both the ZIP CRCs and the complete mixin configuration. It does not
change registrations, block-state IDs, items, other features, or the client jar.
The patch must be reassessed before updating Nekoma's Fixed to another build.

Build and verify locally first, commit/push this directory, then pull the commit
on the server. Generate a new jar outside the active mods directory:

```sh
python3 /opt/cinematic-minecraft/ops/nekoma-no-magma/patch.py \
  /srv/minecraft/servers/fabric-1.21.11/mods/nekomasfixed-0.5.3-1.21.11.jar \
  /srv/minecraft/backups/nekoma-no-magma-20261003/nekomasfixed-no-magma.jar
```

Test the jar in an isolated localhost-only staging server with a disposable
world. `smoke_test.py` checks the actual transformed Minecraft Block class:
the original loads the magma hook and the patched version does not. It also
verifies that a survival fake player mining magma with a normal pickaxe leaves
air in the patched server. Stop staging after testing.

For production, stop `minecraft.service` gracefully, preserve the original jar
in the backup directory, install the patched jar with the same filename and
ownership, restart, and verify `Done`, RCON, and absence of mixin errors.
Physics Mod must remain disabled. Do not resume paused world pregeneration.
For rollback, stop Minecraft and restore the saved original jar before starting
the service again. Preserve this patch through later profile synchronization;
the ordinary client jar would otherwise re-enable magma becoming lava.
