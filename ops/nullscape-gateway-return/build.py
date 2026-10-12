#!/usr/bin/env python3
"""Build a gateway-only override from the reviewed Nullscape jar (stdlib only)."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import zipfile

SOURCE_SHA256 = "098debe2dd9abfa9d1d8f0fa71204d998764673e81036ea9ff5082bc8a6f52e4"
DESTINATION = (100, 49, 0)
LINK_FIELDS = {"ExitPortal", "exit_portal", "ExactTeleport"}


def string(value):
    encoded = value.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


def named(kind, name, payload):
    return bytes([kind]) + string(name) + payload


def destination_tags():
    # These templates retain their original DataVersion (including 1.17 ones).
    # Supply the legacy compound for Minecraft's data fixer as well as the
    # current int array. Both describe the same verified arrival platform.
    legacy = b"".join(named(3, key, struct.pack(">i", value))
                      for key, value in zip("XYZ", DESTINATION)) + b"\x00"
    return (named(10, "ExitPortal", legacy)
            + named(11, "exit_portal", struct.pack(">4i", 3, *DESTINATION))
            + named(1, "ExactTeleport", b"\x01"))


class TemplateEditor:
    """Walk NBT while preserving the bytes of every unrelated field."""

    def __init__(self, data):
        self.data = data
        self.offset = 0
        self.gateways = 0

    def take(self, size):
        if size < 0 or self.offset + size > len(self.data):
            raise ValueError("Invalid NBT length")
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def text(self):
        size = struct.unpack(">H", self.take(2))[0]
        return self.take(size).decode("utf-8")

    def payload(self, kind):
        sizes = {1: 1, 2: 2, 3: 4, 4: 8, 5: 4, 6: 8}
        if kind in sizes:
            return self.take(sizes[kind])
        if kind in (7, 11, 12):
            header = self.take(4)
            count = struct.unpack(">i", header)[0]
            return header + self.take(count * {7: 1, 11: 4, 12: 8}[kind])
        if kind == 8:
            header = self.take(2)
            return header + self.take(struct.unpack(">H", header)[0])
        if kind == 9:
            header = self.take(5)
            element, count = struct.unpack(">Bi", header)
            if count < 0:
                raise ValueError("Invalid NBT list length")
            return header + b"".join(self.payload(element) for _ in range(count))
        if kind == 10:
            children = []
            while True:
                start = self.offset
                child_kind = self.take(1)[0]
                if child_kind == 0:
                    break
                name = self.text()
                prefix = self.data[start:self.offset]
                value = self.payload(child_kind)
                children.append((child_kind, name, prefix, value))
            is_gateway = any(kind == 8 and name == "id"
                             and value == string("minecraft:end_gateway")
                             for kind, name, _, value in children)
            if is_gateway:
                self.gateways += 1
                children = [entry for entry in children if entry[1] not in LINK_FIELDS]
            output = b"".join(prefix + value for _, _, prefix, value in children)
            return output + (destination_tags() if is_gateway else b"") + b"\x00"
        raise ValueError(f"Unsupported NBT tag {kind}")

    def rewrite(self):
        if self.take(1) != b"\x0a":
            raise ValueError("Structure root must be an NBT compound")
        self.text()
        prefix = self.data[:self.offset]
        result = prefix + self.payload(10)
        if self.offset != len(self.data):
            raise ValueError("Trailing NBT data")
        return result


def build(source, output):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Nullscape jar differs from the reviewed build; reassess the override")
    entries = {}
    counts = {}
    with zipfile.ZipFile(source) as jar:
        for name in jar.namelist():
            if name.startswith("data/nullscape/structure/") and name.endswith(".nbt"):
                original = gzip.decompress(jar.read(name))
                editor = TemplateEditor(original)
                patched = editor.rewrite()
                if editor.gateways:
                    entries[name] = gzip.compress(patched, mtime=0)
                    counts[name] = editor.gateways
                elif patched != original:
                    raise AssertionError(f"Unrelated template changed: {name}")
    if len(counts) != 9 or sum(counts.values()) != 208:
        raise ValueError(f"Unexpected gateway inventory: {counts}")
    entries["pack.mcmeta"] = json.dumps({"pack": {
        "min_format": 94.1,
        "max_format": 94.1,
        "description": "Cinematic Minecraft: Nullscape gateways return to the main End island"
    }}, indent=2).encode()
    entries["gateway-fix-manifest.json"] = json.dumps({
        "source_sha256": digest, "destination": DESTINATION,
        "templates": counts
    }, indent=2).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as pack:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            pack.writestr(info, data)
    with zipfile.ZipFile(output) as pack:
        if pack.testzip() is not None:
            raise ValueError("Built datapack failed ZIP validation")
    print(f"Built {output}: {len(counts)} templates, {sum(counts.values())} gateway blocks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.output)
