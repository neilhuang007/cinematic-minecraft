#!/usr/bin/env python3
"""Independently validate the generated templates using nbtlib 2.0.4."""

import argparse
import gzip
import io
from pathlib import Path
import zipfile
import nbtlib


def read(data):
    return nbtlib.File.parse(io.BytesIO(gzip.decompress(data)))


def verify(source, override):
    checked = 0
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(override) as patched:
        templates = [name for name in patched.namelist() if name.endswith(".nbt")]
        assert len(templates) == 9
        for name in templates:
            before, after = read(original.read(name)), read(patched.read(name))
            assert len(before["blocks"]) == len(after["blocks"])
            for old_block, new_block in zip(before["blocks"], after["blocks"]):
                old_nbt, new_nbt = old_block.get("nbt", {}), new_block.get("nbt", {})
                if str(old_nbt.get("id")) == "minecraft:end_gateway":
                    assert list(map(int, new_nbt["exit_portal"])) == [100, 49, 0]
                    assert [int(new_nbt["ExitPortal"][key]) for key in "XYZ"] == [100, 49, 0]
                    assert int(new_nbt["ExactTeleport"]) == 1
                    for key in ("exit_portal", "ExitPortal", "ExactTeleport"):
                        old_nbt.pop(key, None)
                        new_nbt.pop(key, None)
                    checked += 1
            assert before.snbt() == after.snbt(), f"Unrelated NBT changed in {name}"
    assert checked == 208
    print(f"PASS: {checked} destinations; all other template NBT preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("override", type=Path)
    args = parser.parse_args()
    verify(args.source, args.override)
