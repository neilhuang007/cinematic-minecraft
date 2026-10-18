# Overworld and Nether build height

For the production Fabric 1.21.11 world, this raises the exclusive Overworld
ceiling to Y 1040 (highest block Y 1039), including the requested Y 1028.
The minimum stays -64. The only dimension fields changed are `height` and
`logical_height`, both to 1104. With `--nether-source`, the Nether's `height`
also becomes 1040, allowing blocks at Y 0 through 1039. Its existing Incendium
`logical_height` of 192 is preserved to retain portal-search behavior.
Terrain noise settings, bedrock roofs, and the End are not changed. The builder
preserves the active Tectonic/Incendium dimension definitions and refuses
different source jars pending review.

Build with Python 3, using the installed Tectonic 3.0.19 jar:

```sh
python3 ops/overworld-build-height/build.py /path/to/tectonic-3.0.19-fabric-1.21.11.jar /path/to/cinematic-build-height.zip --nether-source /path/to/Incendium_26.1_v5.4.12.jar
```

Before deployment, create and verify a Borg checkpoint. Extract `level.dat`,
the base region `world/region/r.-1.0.mca`, and the world's datapacks into a
separate checkpoint directory. The optional Overworld smoke test uses it:

```sh
python3 ops/overworld-build-height/smoke_test.py /srv/minecraft/servers/fabric-1.21.11 /path/to/checkpoint/world /path/to/cinematic-build-height.zip /srv/minecraft/staging/height-test-UNIQUE
```

The test binds game/RCON listeners to localhost, omits AutoModpack and voice
listeners, and checks the same existing blocks before/after the expansion.
It tests placement at Y 320, 1028, 1039, rejection at Y 1040, and high-block
persistence through another restart. No production world files are written.

Deploy through local commit/push followed by `git pull` on the server. Stop
Minecraft cleanly, retain a final stopped-world checkpoint, install the ZIP
as `world/datapacks/cinematic-build-height.zip` owned by `mc:mc`, then start
Minecraft. Verify the pack is enabled and confirm the boundary in a loaded
existing chunk using temporary blocks that are removed immediately afterward.
Worldgen registry changes require a restart; `/reload` alone is insufficient.

Keep the datapack installed permanently after players build above Y 319 in
the Overworld or Y 255 in the Nether.
Removing it later can discard those high sections. A rollback after high
building requires restoring a compatible backup, not just removing the pack.
