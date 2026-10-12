# Nullscape gateways return to the main End island

On Minecraft 1.21.11, the installed Nullscape jar (filename 1.2.17, internal
metadata 1.2.16) contains rift gateway templates without a return destination.
Entering them creates nearby outer-island gateways that lead back to the rift.
The live reproduction sent a test item from `(1277,126,-1533)` to the gateway
stack at `(747,-881)` and back. This matches
[Nullscape issue 19](https://github.com/Stardust-Labs-MC/Nullscape/issues/19).

`build.py` generates a server datapack overriding only the nine Nullscape
structure templates containing gateways. It preserves every unrelated NBT
field, including geometry, loot and DataVersion. Its 208 gateway blocks receive
an explicit destination `(100,49,0)` and exact teleportation. The obsidian floor
at `(100,48,0)` and two clear blocks above were verified on this world.

Legacy templates receive both `ExitPortal` and `exit_portal` so the existing
Minecraft data-fixer path can migrate their old NBT correctly. The original mod
jar is not modified. The builder pins its SHA-256 and must be reassessed when
Nullscape is updated. Generated third-party templates are not committed here.
The unused `rift/rift_gateway` placed-feature definition has no callers in this
reviewed jar; all gateway structure templates are covered.

Build and validate locally, commit and push, then pull on the server before
running the same builder there:

```sh
python3 /opt/cinematic-minecraft/ops/nullscape-gateway-return/build.py \
  /srv/minecraft/servers/fabric-1.21.11/mods/Nullscape_1.21.x_v1.2.17.jar \
  /srv/minecraft/staging/nullscape-gateway-return.zip
```

Install the resulting archive, owned by `mc:mc`, into `world/datapacks/` and
enable `file/nullscape-gateway-return.zip` last so it overrides Nullscape. Check
the reload log. Existing gateways retain saved destinations and need a separate
live `/data merge block` repair with `{exit_portal:[I;100,49,0],ExactTeleport:1b}`.
Back up each affected block's full NBT before repair. Do not change normal
dragon-generated gateways that already link the main island and outer islands.

Validation must include a temporary item passing through the repaired live
gateway and through a freshly placed patched template, with the item arriving
at `(100.5,49,0.5)`. Remove only tagged test items, test structure blocks and
temporary chunk tickets. No player teleport is necessary.

Rollback: disable this datapack and remove its archive; restore saved live
gateway destinations (or remove `exit_portal` where it was absent). This does
not roll back other world changes or player inventories.
