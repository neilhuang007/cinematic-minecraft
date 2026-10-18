"""Replace Servux 0.9.5 with the protocol-compatible 1.21.11 release."""

import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile


def main():
    manifest = json.loads(Path(__file__).with_name('manifest.json').read_text())
    root = Path(manifest['server'])
    state = subprocess.check_output(
        ['systemctl', 'show', 'minecraft.service', '--property=ActiveState', '--value'],
        text=True,
    ).strip()
    if state not in ('inactive', 'failed'):
        raise RuntimeError('Stop minecraft.service before replacing Servux')

    old = root / 'mods' / manifest['old_file']
    new = root / 'mods' / manifest['new_file']
    if hashlib.sha256(old.read_bytes()).hexdigest() != manifest['old_sha256']:
        raise RuntimeError('Installed Servux differs from the pinned previous release')
    if new.exists():
        raise RuntimeError('Replacement already exists; inspect before retrying')
    with urllib.request.urlopen(manifest['url'], timeout=30) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != manifest['new_sha256']:
        raise RuntimeError('Replacement checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        metadata = json.loads(archive.read('fabric.mod.json'))
    if (metadata['id'], metadata['version'], metadata['depends']['minecraft']) != (
        'servux', '0.9.9', manifest['minecraft']
    ):
        raise RuntimeError('Unexpected mod metadata')

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/var/backups/minecraft') / ('servux-protocol-' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(old, backup / old.name)
    shutil.copy2(root / 'config/servux.json', backup / 'servux.json')
    shutil.copy2(Path(__file__).with_name('manifest.json'), backup / 'manifest.json')
    owner = old.stat()
    temporary = new.with_suffix('.incoming')
    try:
        temporary.write_bytes(data)
        os.chown(temporary, owner.st_uid, owner.st_gid)
        os.chmod(temporary, 0o644)
        temporary.replace(new)
        old.unlink()
    except Exception:
        shutil.copy2(backup / old.name, old)
        os.chown(old, owner.st_uid, owner.st_gid)
        new.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise
    print(json.dumps({'installed': new.name, 'sha256': manifest['new_sha256'],
                      'backup': str(backup)}))


if __name__ == '__main__':
    main()
