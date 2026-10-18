"""Install the pinned Do a Barrel Roll release and dependencies on a stopped server."""

import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
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
        raise RuntimeError('Stop minecraft.service before installing mods')

    installed_ids = {}
    for path in (root / 'mods').glob('*.jar'):
        with zipfile.ZipFile(path) as archive:
            if 'fabric.mod.json' in archive.namelist():
                metadata = json.loads(archive.read('fabric.mod.json'))
                installed_ids.setdefault(metadata['id'], []).append(path)

    pending = []
    for mod in manifest['mods']:
        destination = root / 'mods' / mod['filename']
        if Path(mod['filename']).name != mod['filename']:
            raise RuntimeError('Invalid filename')
        existing = installed_ids.get(mod['id'], [])
        if existing:
            if existing != [destination] or hashlib.sha256(destination.read_bytes()).hexdigest() != mod['sha256']:
                raise RuntimeError('Conflicting installed mod: ' + mod['id'])
            continue
        if destination.exists():
            raise RuntimeError('Unexpected existing destination: ' + str(destination))
        with urllib.request.urlopen(mod['url'], timeout=45) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != mod['sha256']:
            raise RuntimeError('Checksum mismatch: ' + mod['id'])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            metadata = json.loads(archive.read('fabric.mod.json'))
        if (metadata['id'], metadata['version']) != (mod['id'], mod['version']):
            raise RuntimeError('Unexpected metadata: ' + mod['id'])
        pending.append((destination, data))

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/var/backups/minecraft') / ('do-a-barrel-roll-' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (backup / 'previous-mods.json').write_text(json.dumps(sorted(p.name for p in (root / 'mods').glob('*.jar')), indent=2))
    owner = pwd.getpwnam('mc')
    added = []
    temporary = None
    try:
        for destination, data in pending:
            temporary = destination.with_suffix('.incoming')
            temporary.write_bytes(data)
            os.chown(temporary, owner.pw_uid, owner.pw_gid)
            os.chmod(temporary, 0o644)
            temporary.replace(destination)
            added.append(destination)
    except Exception:
        for path in added:
            path.unlink()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    (backup / 'added-mods.json').write_text(json.dumps([p.name for p in added], indent=2))
    print(json.dumps({'installed': [p.name for p in added], 'rollback_record': str(backup)}))


if __name__ == '__main__':
    main()
