"""Verify the magma hook is removed and survival mining leaves air in staging."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time

from patch import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('production', type=Path)
    parser.add_argument('patched', type=Path)
    parser.add_argument('staging', type=Path)
    args = parser.parse_args()
    production, patched, staging = (p.resolve() for p in
                                   (args.production, args.patched, args.staging))
    if not staging.is_relative_to('/srv/minecraft/staging') or staging.exists():
        raise RuntimeError('Staging must be a new directory under /srv/minecraft/staging')
    original = production / 'mods/nekomasfixed-0.5.3-1.21.11.jar'
    verify(original, patched)
    staging.mkdir()
    for name in ('libraries', 'versions', '.fabric'):
        shutil.copytree(production / name, staging / name)
    shutil.copy2(production / 'fabric-server-launch.jar', staging)
    (staging / 'mods').mkdir()
    names = ['fabric-api-0.141.6+1.21.11.jar',
             'fabric-carpet-1.21.11-1.4.194+v251223.jar',
             'cloth-config-21.11.153-fabric.jar']
    for name in names:
        shutil.copy2(production / 'mods' / name, staging / 'mods' / name)
    (staging / 'eula.txt').write_text('eula=true\n')
    password = secrets.token_hex(24)
    with socket.socket() as game_socket, socket.socket() as rcon_socket:
        game_socket.bind(('127.0.0.1', 0))
        rcon_socket.bind(('127.0.0.1', 0))
        game_port = game_socket.getsockname()[1]
        rcon_port = rcon_socket.getsockname()[1]
    flat_settings = json.dumps({'biome': 'minecraft:plains', 'layers': [
        {'block': 'minecraft:bedrock', 'height': 1},
        {'block': 'minecraft:dirt', 'height': 2},
        {'block': 'minecraft:grass_block', 'height': 1}],
        'features': False, 'lakes': False, 'structure_overrides': []})
    (staging / 'server.properties').write_text(
        'server-ip=127.0.0.1\nserver-port=' + str(game_port) + '\nonline-mode=false\n'
        'enable-rcon=true\nrcon.port=' + str(rcon_port) + '\nrcon.password=' + password + '\n'
        'level-type=minecraft:flat\ngenerator-settings=' + flat_settings + '\n'
        'generate-structures=false\n'
        'view-distance=2\nsimulation-distance=2\nmax-tick-time=180000\n'
        'spawn-protection=0\nbroadcast-rcon-to-ops=false\n')
    os.chmod(staging / 'server.properties', 0o600)
    rcon_env = dict(os.environ, MCRCON_HOST='127.0.0.1',
                    MCRCON_PORT=str(rcon_port), MCRCON_PASS=password)

    def rcon(*commands):
        result = subprocess.run(['mcrcon', *commands], env=rcon_env,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('Staging RCON failed: ' + result.stderr)
        return result.stdout

    for label, jar in [('original', original), ('patched', patched)]:
        shutil.copy2(jar, staging / 'mods' / original.name)
        exported_block = staging / '.mixin.out/class/net/minecraft/class_2248.class'
        if exported_block.exists():
            exported_block.unlink()
        log_path = staging / (label + '-console.log')
        print('Starting ' + label + ' staging server', flush=True)
        with log_path.open('w') as console:
            process = subprocess.Popen(
                ['/opt/jdk24/bin/java', '-Xms512m', '-Xmx2g',
                 '-Dmixin.debug.export=true',
                 '-Dmixin.debug.export.filter=net.minecraft.class_2248',
                 '-Dmixin.debug.export.decompile=false',
                 '-jar', 'fabric-server-launch.jar', 'nogui'],
                cwd=staging, stdout=console, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 240
                while 'Done (' not in log_path.read_text(errors='replace'):
                    if process.poll() is not None:
                        raise RuntimeError('Staging server exited: ' + str(log_path))
                    if time.monotonic() > deadline:
                        raise RuntimeError('Staging startup timed out: ' + str(log_path))
                    time.sleep(1)
                print(label + ' staging ready', flush=True)
                hook_loaded = b'customAfterBreak' in exported_block.read_bytes()
                if hook_loaded != (label == 'original'):
                    raise RuntimeError('Unexpected magma hook in the running Block class')
                rcon('player MagmaProbe spawn at 0.5 6 0.5 facing 0 90',
                     'gamemode survival MagmaProbe',
                     'item replace entity MagmaProbe weapon.mainhand with minecraft:diamond_pickaxe',
                     'setblock 0 4 0 minecraft:obsidian',
                     'setblock 0 5 0 minecraft:magma_block',
                     'tp MagmaProbe 0.5 6 0.5 0 90')
                time.sleep(1)
                rcon('player MagmaProbe attack continuous')
                time.sleep(3)
                rcon('player MagmaProbe attack stop')
                state = {}
                for block in ('lava', 'air', 'magma_block'):
                    response = rcon('execute if block 0 5 0 minecraft:' + block +
                                    ' run time query gametime')
                    state[block] = 'The time is' in response
                print(json.dumps({'variant': label, 'mined_block': state,
                                  'magma_hook_loaded': hook_loaded}), flush=True)
                if sum(state.values()) != 1 or state['magma_block']:
                    raise RuntimeError('Survival player did not mine the magma block')
                if label == 'patched' and not state['air']:
                    raise RuntimeError('Patched survival mining did not leave air')
                rcon('player MagmaProbe kill')
            finally:
                if process.poll() is None:
                    try:
                        rcon('stop')
                        process.wait(timeout=90)
                    except (RuntimeError, subprocess.TimeoutExpired):
                        process.terminate()
                        process.wait(timeout=30)
    print('PASS: magma hook removed from running Block class; patched mining leaves air', flush=True)


if __name__ == '__main__':
    main()
