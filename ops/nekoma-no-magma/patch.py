"""Disable only Nekoma's Fixed's magma-to-lava mixin in the pinned server jar."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


ORIGINAL_SHA256 = '7b02eb148ec6d1364bdf6d683233f58fa0632aa8bc391ab647c41a4378f4a2fb'
CONFIG_ENTRY = 'nekomasfixed.mixins.json'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(original, patched):
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(patched) as after:
        names = before.namelist()
        if len(set(names)) != len(names) or names != after.namelist():
            raise RuntimeError('Jar entries changed or contain duplicates')
        if after.testzip() is not None:
            raise RuntimeError('Patched jar failed its CRC check')
        changed = [name for name in names if before.read(name) != after.read(name)]
        if changed != [CONFIG_ENTRY]:
            raise RuntimeError('Unexpected jar changes: ' + repr(changed))
        expected = json.loads(before.read(CONFIG_ENTRY))
        if expected['mixins'].count('BlockMixin') != 1:
            raise RuntimeError('Expected exactly one magma mixin')
        expected['mixins'].remove('BlockMixin')
        if json.loads(after.read(CONFIG_ENTRY)) != expected:
            raise RuntimeError('Other mixin settings changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    original, output = args.original.resolve(), args.output.resolve()
    if digest(original) != ORIGINAL_SHA256:
        raise RuntimeError('Original jar is not the reviewed Nekoma 0.5.3 / MC 1.21.11 build')
    if output.exists():
        raise RuntimeError('Output already exists; refusing to overwrite it')
    temporary = output.with_name(output.name + '.tmp')
    if temporary.exists():
        raise RuntimeError('Temporary output already exists')
    try:
        with zipfile.ZipFile(original) as source:
            text = source.read(CONFIG_ENTRY).decode('utf-8')
            text, count = re.subn(r'(?m)^[ \t]*"BlockMixin",\r?\n', '', text)
            if count != 1:
                raise RuntimeError('Expected exactly one complete BlockMixin line')
            with zipfile.ZipFile(temporary, 'x') as target:
                target.comment = source.comment
                for entry in source.infolist():
                    content = text.encode('utf-8') if entry.filename == CONFIG_ENTRY else source.read(entry)
                    target.writestr(entry, content)
        verify(original, temporary)
        temporary.rename(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({'output': str(output), 'sha256': digest(output),
                      'disabled': 'BlockMixin (magma blocks becoming lava)',
                      'changed_entries': [CONFIG_ENTRY]}))


if __name__ == '__main__':
    main()
