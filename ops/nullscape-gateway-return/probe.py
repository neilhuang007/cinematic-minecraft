#!/usr/bin/env python3
"""Exercise a real End gateway with a tagged item, then clean up the probe."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


def probe(server, source):
    props = dict(line.split("=", 1) for line in
                 (server / "server.properties").read_text().splitlines()
                 if "=" in line and not line.startswith("#"))
    env = dict(os.environ, MCRCON_PASS=props["rcon.password"])

    def rcon(command):
        return subprocess.run(
            ["/usr/local/bin/mcrcon", "-H", "127.0.0.1", "-P",
             props["rcon.port"], "-c", "execute in minecraft:the_end run " + command],
            env=env, check=True, capture_output=True, text=True,
        ).stdout.strip()

    tag = "gateway_return_probe_" + uuid.uuid4().hex
    selector = f"@e[type=minecraft:item,tag={tag},limit=1]"
    added = []
    x, y, z = source
    try:
        for cx, cz in {(x, z), (100, 0)}:
            status = rcon(f"forceload query {cx} {cz}")
            if "not marked" in status:
                rcon(f"forceload add {cx} {cz}")
                added.append((cx, cz))
            elif "marked for force loading" not in status:
                raise RuntimeError(status)
        time.sleep(0.5)
        block = rcon(f"data get block {x} {y} {z}")
        if 'id: "minecraft:end_gateway"' not in block:
            raise RuntimeError(f"No gateway at {source}: {block}")
        current_exit = re.search(r"exit_portal: \[I;\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\]", block)
        if current_exit:
            ex, _, ez = map(int, current_exit.groups())
            status = rcon(f"forceload query {ex} {ez}")
            if "not marked" in status:
                rcon(f"forceload add {ex} {ez}")
                added.append((ex, ez))
            elif "marked for force loading" not in status:
                raise RuntimeError(status)
        result = rcon(
            f'summon minecraft:item {x + 0.5} {y + 0.2} {z + 0.5} '
            f'{{Item:{{id:"minecraft:paper",count:1}},Tags:["{tag}"],'
            'NoGravity:1b,Invulnerable:1b,PickupDelay:32767s,Motion:[0.0d,0.0d,0.0d]}'
        )
        if "Summoned" not in result:
            raise RuntimeError(result)
        deadline = time.monotonic() + 8
        position = None
        while time.monotonic() < deadline:
            time.sleep(0.25)
            result = rcon(f"data get entity {selector} Pos")
            match = re.search(r"entity data: \[([^]]+)\]", result)
            if match:
                position = [float(value.strip().removesuffix("d"))
                            for value in match.group(1).split(",")]
                if abs(position[0] - (x + 0.5)) > 1 or abs(position[2] - (z + 0.5)) > 1:
                    break
        expected = [100.5, 49.0, 0.5]
        if position is None or any(abs(a - b) > 0.1 for a, b in zip(position, expected)):
            raise AssertionError(f"FAIL: gateway {source} sent item to {position}; expected {expected}")
        print(f"PASS: gateway {source} sent item to {position}")
    finally:
        print(rcon(f"kill {selector}"))
        for cx, cz in added:
            print(rcon(f"forceload remove {cx} {cz}"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("x", type=int)
    parser.add_argument("y", type=int)
    parser.add_argument("z", type=int)
    parser.add_argument("--server", type=Path,
                        default=Path("/srv/minecraft/servers/fabric-1.21.11"))
    args = parser.parse_args()
    probe(args.server, (args.x, args.y, args.z))
