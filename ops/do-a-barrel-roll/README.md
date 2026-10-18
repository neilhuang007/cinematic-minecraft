# Do a Barrel Roll for Fabric 1.21.11

Installs Do a Barrel Roll 3.8.3 with Cicada 0.14.3 and YACL 3.8.2. The latter
two releases match the current client profile. Although Modrinth lists YACL as
optional, this Do a Barrel Roll jar declares it in `fabric.mod.json` dependencies.
Cicada's filename mentions 1.21.9-1.21.10, but its official release metadata
also supports 1.21.11. Fabric API is already installed.

The server component synchronizes player roll animations. Clients need their
own copy to use flight controls or view those animations; clients without the
mod can continue playing. Default server settings are retained.

Sources:
- https://modrinth.com/mod/do-a-barrel-roll/version/QyuEXDMC
- https://modrinth.com/mod/cicada/version/CqAskfnS
- https://modrinth.com/mod/yacl/version/pHWDw3Vc

Commit and push locally, then pull on the server. Hold the Minecraft backup
lock, gracefully stop `minecraft.service`, run `python3
ops/do-a-barrel-roll/install.py`, and restart the service in a finally block.
The installer verifies all downloads and rejects conflicting existing mods.
It only adds the three pinned jars; existing files and configuration are retained.

Verify the three loaded versions, successful startup and RCON availability.
To roll back, stop the server and move the files listed in the installer's
`added-mods.json` out of the mods directory, then restart.
