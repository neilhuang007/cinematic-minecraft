#!/usr/bin/env python3
"""Raise build ceilings while preserving the reviewed mod dimension definitions."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

SOURCE_SHA256 = "a745907c5f2e5fdb1a0786fa32ce00a03890e30f1b87e6c0ea10caa07dc29ad6"
RESOURCE = "resourcepacks/tectonic/data/minecraft/dimension_type/overworld.json"
TARGET = "data/minecraft/dimension_type/overworld.json"
NETHER_SHA256 = "d537aeb61d7e3aa3ca18c158571f6809d3e3aecfb70de2939f92dbc7ab4844b1"
NETHER_RESOURCE = "data/minecraft/dimension_type/the_nether.json"


def build(source, output, ceiling=1040, nether_source=None):
    if ceiling % 16 or not 320 < ceiling <= 2032:
        raise ValueError("Ceiling must be a multiple of 16 above 320 and at most 2032")
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Tectonic source differs from the reviewed 1.21.11 build")
    with zipfile.ZipFile(source) as jar:
        original = json.loads(jar.read(RESOURCE))
    if (original["min_y"], original["height"], original["logical_height"]) != (-64, 384, 384):
        raise ValueError("Unexpected source bounds; reassess the existing world first")
    dimension = dict(original, height=ceiling + 64, logical_height=ceiling + 64)
    assert {k: v for k, v in dimension.items() if k not in ("height", "logical_height")} == {
        k: v for k, v in original.items() if k not in ("height", "logical_height")}
    entries = {
        "pack.mcmeta": {"pack": {"min_format": 94.1, "max_format": 94.1,
            "description": f"Cinematic Minecraft: Overworld build ceiling Y {ceiling}"}},
        TARGET: dimension,
        "build-height-manifest.json": {"source_sha256": SOURCE_SHA256,
            "source_resource": RESOURCE, "min_y": -64, "ceiling_exclusive": ceiling,
            "highest_placeable_y": ceiling - 1, "minecraft_version": "1.21.11"},
    }
    if nether_source is not None:
        if hashlib.sha256(nether_source.read_bytes()).hexdigest() != NETHER_SHA256:
            raise ValueError("Incendium source differs from the reviewed 5.4.12 build")
        with zipfile.ZipFile(nether_source) as jar:
            nether_original = json.loads(jar.read(NETHER_RESOURCE))
        if (nether_original["min_y"], nether_original["height"],
                nether_original["logical_height"]) != (0, 256, 192):
            raise ValueError("Unexpected Incendium bounds; reassess the existing Nether")
        # Physical height controls building; retain Incendium's portal-search height.
        entries[NETHER_RESOURCE] = dict(nether_original, height=ceiling)
        entries["pack.mcmeta"]["pack"]["description"] = (
            f"Cinematic Minecraft: Overworld and Nether build ceilings Y {ceiling}")
        entries["build-height-manifest.json"]["nether"] = {
            "source_sha256": NETHER_SHA256, "source_resource": NETHER_RESOURCE,
            "min_y": 0, "ceiling_exclusive": ceiling,
            "highest_placeable_y": ceiling - 1, "logical_height": 192}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as pack:
        for name, value in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            pack.writestr(info, json.dumps(value, indent=2) + "\n")
    with zipfile.ZipFile(output) as pack:
        if pack.testzip() is not None:
            raise ValueError("ZIP validation failed")
    print(f"Built {output}: Overworld -64 through {ceiling - 1}"
          + (f", Nether 0 through {ceiling - 1}" if nether_source else "")
          + "; terrain generators unchanged")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ceiling", type=int, default=1040)
    parser.add_argument("--nether-source", type=Path)
    args = parser.parse_args()
    build(args.source, args.output, args.ceiling, args.nether_source)
