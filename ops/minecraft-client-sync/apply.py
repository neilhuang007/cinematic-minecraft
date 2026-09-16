"""Apply a hash-pinned client-compatible mod set to a stopped server."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    target, payload, backup = (p.resolve() for p in (args.target, args.payload, args.backup))
    manifest = json.loads(Path(__file__).with_name('manifest.json').read_text())
    production = Path(manifest['server'])
    if target != production and not target.is_relative_to('/srv/minecraft/staging'):
        raise RuntimeError('Target is outside production/staging')
    if not backup.is_relative_to('/srv/minecraft') or backup.exists():
        raise RuntimeError('Backup must be a new directory under /srv/minecraft')
    if target == production:
        state = subprocess.check_output(['systemctl', 'show', 'minecraft.service',
                                         '--property=ActiveState', '--value'], text=True).strip()
        if state not in ('inactive', 'failed'):
            raise RuntimeError('Stop minecraft.service before changing production')
    if json.loads((payload / 'manifest.json').read_text()) != manifest:
        raise RuntimeError('Payload differs from the reviewed manifest')
    changes = manifest['changes']
    if len({item['new_file'] for item in changes}) != len(changes):
        raise RuntimeError('Duplicate mod destinations')
    for item in changes:
        for key in ('new_file', 'old_file'):
            name = item.get(key)
            if name is not None and (Path(name).name != name or not name.endswith('.jar')):
                raise RuntimeError('Invalid mod filename')
        if digest(payload / 'mods' / item['new_file']) != item['new_sha256']:
            raise RuntimeError('Payload checksum mismatch: ' + item['id'])
        old = target / 'mods' / item['old_file'] if item.get('old_file') else None
        if old is not None and digest(old) != item['old_sha256']:
            raise RuntimeError('Existing mod checksum mismatch: ' + item['id'])
        destination = target / 'mods' / item['new_file']
        if destination != old and destination.exists():
            raise RuntimeError('Unexpected existing destination: ' + str(destination))
    for item in manifest['configs']:
        path = Path(item['path'])
        if path.is_absolute() or '..' in path.parts or path.parts[0] != 'config':
            raise RuntimeError('Invalid config path')
        if digest(payload / path) != item['sha256']:
            raise RuntimeError('Config checksum mismatch')
        if (target / path).exists():
            raise RuntimeError('New-mod config unexpectedly exists: ' + str(path))
    backup.mkdir(parents=True)
    for name in ('mods', 'config', 'defaultconfigs', 'villagerpacks', 'automodpack'):
        if (target / name).exists():
            shutil.copytree(target / name, backup / name)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        for item in changes:
            new = target / 'mods' / item['new_file']
            temporary = new.with_suffix('.jar.sync-tmp')
            shutil.copy2(payload / 'mods' / item['new_file'], temporary)
            temporary.replace(new)
            if item.get('old_file') and item['old_file'] != item['new_file']:
                (target / 'mods' / item['old_file']).unlink()
        for item in manifest['configs']:
            path = Path(item['path'])
            (target / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(payload / path, target / path)
        for item in changes:
            if digest(target / 'mods' / item['new_file']) != item['new_sha256']:
                raise RuntimeError('Installed checksum mismatch')
    except Exception:
        (target / 'mods').rename(backup / 'failed-mods')
        shutil.copytree(backup / 'mods', target / 'mods')
        (target / 'config').rename(backup / 'failed-config')
        shutil.copytree(backup / 'config', target / 'config')
        raise
    subprocess.run(['chown', '-R', 'mc:mc', str(target / 'mods'), str(target / 'config')], check=True)
    print(json.dumps({'target': str(target), 'backup': str(backup), 'mods_synced': len(changes)}))


if __name__ == '__main__':
    main()
