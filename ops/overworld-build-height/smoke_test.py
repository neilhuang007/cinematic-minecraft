#!/usr/bin/env python3
"""Test existing chunks, expanded bounds, and save/reload in an isolated server."""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production", type=Path)
    parser.add_argument("checkpoint_world", type=Path)
    parser.add_argument("datapack", type=Path)
    parser.add_argument("staging", type=Path)
    args = parser.parse_args()
    production, checkpoint, pack, staging = (p.resolve() for p in (
        args.production, args.checkpoint_world, args.datapack, args.staging))
    if staging.exists() or not staging.is_relative_to("/srv/minecraft/staging"):
        raise ValueError("Use a new staging directory under /srv/minecraft/staging")
    if checkpoint == (production / "world") or not (checkpoint / "level.dat").is_file():
        raise ValueError("A separate checkpoint with level.dat is required")
    staging.mkdir()
    for name in ("libraries", "versions"):
        (staging / name).symlink_to(production / name, target_is_directory=True)
    shutil.copy2(production / "fabric-server-launch.jar", staging)
    for name in ("config", "defaultconfigs", ".fabric"):
        if (production / name).exists():
            shutil.copytree(production / name, staging / name)
    (staging / "mods").mkdir()
    for jar in (production / "mods").glob("*.jar"):
        # Omit external distribution/voice listeners; retain every worldgen and tick mod.
        if not jar.name.startswith(("automodpack-", "voicechat-")):
            (staging / "mods" / jar.name).symlink_to(jar)
    shutil.copytree(checkpoint, staging / "world", ignore=shutil.ignore_patterns("session.lock"))
    # No production backup scripts or player identities are needed in the test server.
    scripts = staging / "world/scripts"
    if scripts.exists():
        scripts.rename(staging / "checkpoint-scripts-disabled")
    (staging / "eula.txt").write_text("eula=true\n")
    password = secrets.token_hex(24)
    with socket.socket() as game, socket.socket() as rcon_socket:
        game.bind(("127.0.0.1", 0))
        rcon_socket.bind(("127.0.0.1", 0))
        ports = game.getsockname()[1], rcon_socket.getsockname()[1]
    (staging / "server.properties").write_text(
        f"server-ip=127.0.0.1\nserver-port={ports[0]}\nonline-mode=false\n"
        f"enable-rcon=true\nrcon.port={ports[1]}\nrcon.password={password}\n"
        "level-name=world\nview-distance=2\nsimulation-distance=2\n"
        "pause-when-empty-seconds=0\nmax-tick-time=180000\n"
        "spawn-protection=0\nbroadcast-rcon-to-ops=false\n")
    os.chmod(staging / "server.properties", 0o600)
    env = dict(os.environ, MCRCON_HOST="127.0.0.1", MCRCON_PORT=str(ports[1]), MCRCON_PASS=password)

    def rcon(command):
        result = subprocess.run(["/usr/local/bin/mcrcon", "-c", command], env=env,
                                text=True, capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError("Staging RCON failed: " + result.stderr)
        return result.stdout.strip()

    def require_block(x, y, z, block):
        result = rcon(f"execute if block {x} {y} {z} minecraft:{block} run time query gametime")
        if "The time is" not in result:
            raise AssertionError(f"Expected {block} at {(x,y,z)}: {result}")

    baseline = None
    report = {"staging": str(staging), "phases": {}}
    for phase in ("baseline", "expanded", "persisted"):
        if phase == "expanded":
            destination = staging / "world/datapacks/cinematic-build-height.zip"
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(pack, destination)
        log = staging / f"{phase}-console.log"
        print(f"Starting {phase} server", flush=True)
        with log.open("w") as stream:
            process = subprocess.Popen(["/opt/jdk24/bin/java", "-Xms1g", "-Xmx5g",
                "-XX:ActiveProcessorCount=4", "-jar", "fabric-server-launch.jar", "nogui"],
                cwd=staging, stdout=stream, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 300
                while "Done (" not in log.read_text(errors="replace"):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Startup failed or timed out: {log}")
                    time.sleep(1)
                rcon("gamerule minecraft:log_admin_commands false")
                rcon("gamerule minecraft:send_command_feedback false")
                rcon("forceload add -384 432 -353 479")
                sample = rcon("script run map([[-370,63,437],[-370,62,437],[-360,-50,456],[-360,0,456],[-360,60,456]],str(block(_)))")
                sample = re.sub(r" \([^)]*\)$", "", sample)
                if baseline is None:
                    baseline = sample
                elif sample != baseline:
                    raise AssertionError(f"Existing blocks changed: {sample} != {baseline}")
                phase_report = {"existing_blocks": sample}
                if phase == "baseline":
                    result = rcon("setblock -360 1028 456 minecraft:glass")
                    if "Changed the block" in result:
                        raise AssertionError("Baseline unexpectedly allows Y 1028")
                    phase_report["old_limit_rejection"] = result
                else:
                    enabled = rcon("datapack list enabled")
                    if "file/cinematic-build-height.zip" not in enabled:
                        raise AssertionError("Height pack not enabled")
                    if phase == "expanded":
                        for y in (320, 1028, 1039):
                            result = rcon(f"setblock -360 {y} 456 minecraft:glass")
                            if "Changed the block" not in result:
                                raise AssertionError(f"Y {y} rejected: {result}")
                    for y in (320, 1028, 1039):
                        require_block(-360, y, 456, "glass")
                    rejected = rcon("setblock -360 1040 456 minecraft:glass")
                    if "Changed the block" in rejected:
                        raise AssertionError("Y 1040 should be outside the dimension")
                    phase_report["upper_boundary_rejection"] = rejected
                    phase_report["verified_heights"] = [320, 1028, 1039]
                report["phases"][phase] = phase_report
                print(json.dumps({phase: phase_report}), flush=True)
                rcon("save-all flush")
            finally:
                if process.poll() is None:
                    try:
                        rcon("stop")
                        process.wait(timeout=90)
                    except (RuntimeError, subprocess.TimeoutExpired):
                        process.terminate()
                        process.wait(timeout=30)
    (staging / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: existing blocks retained, Y 1028/1039 work, Y 1040 rejected, high blocks survive restart", flush=True)


if __name__ == "__main__":
    main()
