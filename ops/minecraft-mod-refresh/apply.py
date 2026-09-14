"""Apply the checked-in, hash-pinned mod refresh to a stopped server copy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name('manifest.json').read_text())
    target, payload, backup = (p.resolve() for p in (args.target, args.payload, args.backup))
    production = Path(manifest['server'])
    if target != production and not target.is_relative_to('/srv/minecraft/staging'):
        raise RuntimeError('Target must be production or an isolated staging directory')
    if not backup.is_relative_to('/srv/minecraft') or backup.exists():
        raise RuntimeError('Backup must be a new directory under /srv/minecraft')
    if target == production:
        state = subprocess.check_output(['systemctl', 'show', 'minecraft.service',
                                         '--property=ActiveState', '--value'], text=True).strip()
        if state not in ('inactive', 'failed'):
            raise RuntimeError('Stop minecraft.service before applying the production update')
    if json.loads((payload / 'manifest.json').read_text()) != manifest:
        raise RuntimeError('Payload does not match the reviewed manifest')
    changes = manifest['changes']
    names = [change['new_file'] for change in changes]
    if len(set(names)) != len(names):
        raise RuntimeError('Duplicate replacement filenames')
    for change in changes:
        for key in ('old_file', 'new_file'):
            name = change[key]
            if Path(name).name != name or not name.endswith('.jar'):
                raise RuntimeError('Invalid mod filename')
        old, new = target / 'mods' / change['old_file'], payload / 'mods' / change['new_file']
        if digest(old) != change['old_sha256'] or digest(new) != change['new_sha256']:
            raise RuntimeError(f"Mod checksum mismatch: {change['id']}")
        destination = target / 'mods' / change['new_file']
        if destination != old and destination.exists():
            raise RuntimeError(f'Unexpected existing replacement: {destination.name}')
    for root, key in ((target, 'old_sha256'), (payload, 'new_sha256')):
        if digest(root / 'fabric-server-launch.jar') != manifest['loader'][key]:
            raise RuntimeError('Launcher checksum mismatch')

    # A complete mod/config snapshot makes runtime rollback independent of staging.
    backup.mkdir(parents=True)
    for name in ('mods', 'config', 'defaultconfigs', 'villagerpacks', 'automodpack'):
        source = target / name
        if source.exists():
            shutil.copytree(source, backup / name)
    shutil.copy2(target / 'fabric-server-launch.jar', backup / 'fabric-server-launch.jar')
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        for change in changes:
            old = target / 'mods' / change['old_file']
            new = target / 'mods' / change['new_file']
            temporary = new.with_suffix('.jar.refresh-tmp')
            shutil.copy2(payload / 'mods' / change['new_file'], temporary)
            temporary.replace(new)
            if old != new:
                old.unlink()
        temporary = target / 'fabric-server-launch.jar.refresh-tmp'
        shutil.copy2(payload / 'fabric-server-launch.jar', temporary)
        temporary.replace(target / 'fabric-server-launch.jar')
        for change in changes:
            if digest(target / 'mods' / change['new_file']) != change['new_sha256']:
                raise RuntimeError('Post-install checksum failed')
    except Exception:
        # Preserve the failed update for inspection, then restore the original binaries.
        (target / 'mods').rename(backup / 'failed-mods')
        shutil.copytree(backup / 'mods', target / 'mods')
        shutil.copy2(backup / 'fabric-server-launch.jar', target / 'fabric-server-launch.jar')
        raise
    subprocess.run(['chown', '-R', 'mc:mc', str(target / 'mods'),
                    str(target / 'fabric-server-launch.jar')], check=True)
    print(json.dumps({'updated_mods': len(changes), 'loader': manifest['loader']['new'],
                      'backup': str(backup), 'target': str(target)}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Update failed: {error}', file=sys.stderr)
        raise SystemExit(1)
