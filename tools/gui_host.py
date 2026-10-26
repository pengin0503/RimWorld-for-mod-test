"""Start the validation GUI (W2): a window drawn by the game's own renderer that is never playable.

The GUI (gui/RimWorldValidation.Gui, built against the user's game) runs in a private
run directory next to the results, like the Worker: links to the read-only snapshot,
its own settings and logs, and links to the candidate mod folders. It judges nothing;
every validation it starts is ``validation_host.py run``, and it shows result.json.

    python tools/gui_host.py setup --snapshot C:\\rwmt\\snapshot --results C:\\rwmt\\results
    python tools/gui_host.py launch
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

# By its own package, so tools.gui_host and tools.validation_host share one Blocked class.
if __package__:
    from . import validation_host as vh
else:
    import validation_host as vh

GUI_NAME = 'RimWorldValidationGui'
GUI_SESSION = '.gui-session'
DEFAULT_MEMORY_MIB = 12288
# The window needs the display; nothing else of the user's environment is passed on.
DISPLAY_VARIABLES = ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR', 'XAUTHORITY', 'VK_ICD_FILENAMES')
REPO = Path(__file__).resolve().parents[1]
STEAM_WORKSHOP = ('workshop', 'content', '294100')


def settings_path():
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'rwmt' / 'gui-settings.json'


def load_settings(path):
    path = Path(path)
    if not path.is_file():
        raise vh.Blocked('invalidRequest', f'{path} not found; run "gui_host.py setup" first')
    return json.loads(path.read_text(encoding='utf-8'))


def default_mod_roots(snapshot):
    """The install's own Mods folder and Steam's workshop folder for RimWorld, where they exist."""
    source = Path(snapshot.get('sourcePath') or '')
    roots = [source / 'Mods']
    # <library>/steamapps/common/RimWorld -> <library>/steamapps/workshop/content/294100
    if source.parent.name.lower() == 'common':
        roots.append(source.parent.parent.joinpath(*STEAM_WORKSHOP))
    return [root for root in roots if root.is_dir()]


def default_mods_config(snapshot):
    """The game's own ModsConfig.xml (read only), to import the user's load order."""
    source = Path(snapshot.get('sourcePath') or '')
    tail = ('Ludeon Studios', 'RimWorld by Ludeon Studios', 'Config', 'ModsConfig.xml')
    candidates = [source / 'RimWorld by Ludeon Studios' / 'Config' / 'ModsConfig.xml']
    if os.name == 'nt':
        candidates.append(Path.home() / 'AppData' / 'LocalLow' / Path(*tail))
    else:
        candidates.append(Path.home() / '.config' / 'unity3d' / Path(*tail))
    return next((path for path in candidates if path.is_file()), None)


def discover_mod_folders(roots):
    """Mod folders (with About/About.xml) under the roots. A packageId seen again keeps the first one."""
    found, skipped, seen = [], [], {}
    for root in roots:
        if not Path(root).is_dir():
            # A remembered folder can be gone (deleted, an unplugged drive): the GUI still opens.
            skipped.append({'path': str(root), 'reason': 'mod folder root not found'})
            continue
        for folder in sorted(Path(root).iterdir(), key=lambda p: p.name.lower()):
            if not (folder / 'About' / 'About.xml').is_file():
                continue
            try:
                package_id = vh._about_package_id(folder)
            except vh.Blocked as blocked:
                skipped.append({'path': str(folder), 'reason': blocked.detail})
                continue
            if package_id in seen:
                skipped.append({'path': str(folder), 'reason': f'same packageId {package_id} as {seen[package_id]}'})
                continue
            seen[package_id] = str(folder)
            found.append({'packageId': package_id, 'path': str(folder.resolve()), 'root': str(root)})
    return found, skipped


def _link_name(index, path):
    return f'{index}-{re.sub(r"[^A-Za-z0-9._-]", "_", Path(path).name)[:60]}'


def build_gui_dir(run_dir, snapshot, gui_dir, mods, *, results, python, controller, worker_dir, baseline_cache,
                  mods_config, script=None):
    """host/ (the game, all official content, the GUI and links to the mods), userdata/ and gui-request.json."""
    game = Path(snapshot['path']) / 'game'
    host, userdata = run_dir / 'host', run_dir / 'userdata'
    for sub in (host / 'Data', host / 'Mods', userdata / 'Config', userdata / 'logs', userdata / 'tmp',
                run_dir / 'home', run_dir / 'tmp'):
        sub.mkdir(parents=True)
    link_modes = {}

    def link(source, destination):
        if os.name == 'nt':
            # Windows symlinks need admin rights or Developer Mode: hard links and junctions instead.
            win_fs = vh._win_fs()
            if source.is_dir():
                win_fs.link_dir(source, destination)
                mode = 'junction'
            else:
                mode = win_fs.link_file(source, destination)
        else:
            os.symlink(source, destination)
            mode = 'symlink'
        link_modes[mode] = link_modes.get(mode, 0) + 1

    for name in sorted(os.listdir(game)):
        if name not in vh.GAME_EXCLUDED:
            link(game / name, host / name)
    official = snapshot.get('officialContent') or vh._official_folders(game)
    for folder in official:
        link(game / 'Data' / folder, host / 'Data' / folder)
    mods_map = {}
    for index, mod in enumerate(mods):
        name = _link_name(index, mod['path'])
        link(Path(mod['path']), host / 'Mods' / name)
        mods_map[name] = mod['path']
    for suffix in ('', '.dll', '.exe', '.runtimeconfig.json', '.deps.json'):
        source = gui_dir / (GUI_NAME + suffix)
        if source.is_file():
            shutil.copy2(source, host / (GUI_NAME + suffix))
    for model in gui_dir.glob('RimWorldValidation.Gui.Model.dll'):
        shutil.copy2(model, host / model.name)
    _write_runtime_files(game, host)

    ids = [vh._official_package_id(game, folder) for folder in official]
    (userdata / 'Config' / 'ModsConfig.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<ModsConfigData>'
        f'<version>{vh._xml_text(snapshot["version"])}</version>'
        f'<activeMods>{"".join(f"<li>{i}</li>" for i in ids)}</activeMods>'
        f'<knownExpansions>{"".join(f"<li>{i}</li>" for i in vh.EXPANSION_IDS)}</knownExpansions></ModsConfigData>\n',
        encoding='utf-8')
    try:
        language = vh.resolve_language(game, 'Japanese')
    except vh.Blocked:
        language = 'English'
    # devMode off: the GUI offers none of the game's developer tools.
    (userdata / 'Config' / 'Prefs.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<PrefsData><devMode>false</devMode>'
        '<resetModsConfigOnCrash>false</resetModsConfigOnCrash>'
        f'<langFolderName>{vh._xml_text(language)}</langFolderName></PrefsData>\n', encoding='utf-8')
    request = {
        'recordType': 'rwmtGuiRequest', 'schemaVersion': 1,
        'hostDir': str(host), 'userDataDir': str(userdata), 'resultsDir': str(results),
        'snapshotDir': str(snapshot['path']), 'python': str(python), 'controller': str(controller),
        'workerDir': str(worker_dir), 'baselineCache': str(baseline_cache), 'modsMap': mods_map,
        'userModsConfig': str(mods_config) if mods_config else None, 'script': script,
    }
    vh._write_json(run_dir / 'gui-request.json', request)
    return {'linkModes': link_modes, 'mods': len(mods), 'language': language}


def _write_runtime_files(game, host):
    """The game's runtime settings with the GUI as the application, as the Controller does for the Worker."""
    shutil.copyfile(game / 'RimWorld.runtimeconfig.json', host / f'{GUI_NAME}.runtimeconfig.json')
    deps = json.loads((game / 'RimWorld.deps.json').read_text(encoding='utf-8'))
    target_name = deps['runtimeTarget']['name']
    targets = deps['targets'][target_name]
    root_key = next(k for k in targets if k.startswith('RimWorld/'))
    root = targets.pop(root_key)
    # RimWorld.dll stays a plain assembly next to the GUI: its bootstrap is called by reflection.
    root['runtime'] = {f'{GUI_NAME}.dll': {}, 'RimWorldValidation.Gui.Model.dll': {}, 'RimWorld.dll': {}}
    deps['targets'][target_name] = {f'{GUI_NAME}/{vh.TOOL_VERSION}': root, **targets}
    libraries = deps['libraries']
    library = libraries.pop(root_key)
    deps['libraries'] = {f'{GUI_NAME}/{vh.TOOL_VERSION}': library, **libraries}
    vh._write_json(host / f'{GUI_NAME}.deps.json', deps)


def gui_command(host, request_path):
    name = GUI_NAME + ('.exe' if os.name == 'nt' else '')
    return [str(host / name), '--gui-request', str(request_path)]


def gui_environment(run_dir, memory_mib):
    env = vh.worker_environment(run_dir, {'memoryMiB': memory_mib}, 'waylith')
    env.pop('DOTNET_GCHeapHardLimit', None)  # the job's limit covers the GUI and the runs it starts
    env.update({name: os.environ[name] for name in DISPLAY_VARIABLES if name in os.environ})
    return env


def run_gui(run_dir, memory_mib, environment, *, poll=0.5):
    """Run the GUI until it closes. Its whole process tree stops with it, also on Ctrl+C or an error."""
    host = run_dir / 'host'
    command = gui_command(host, run_dir / 'gui-request.json')
    limit = memory_mib * 1024 * 1024
    windows = os.name == 'nt'
    job = vh._win_job().Job(limit) if windows else None
    started = time.monotonic()
    try:
        with open(run_dir / 'gui-stdout.log', 'wb') as out, open(run_dir / 'gui-stderr.log', 'wb') as err:
            if windows:
                process = job.start(command, cwd=host, env=environment, stdout=out, stderr=err)
            else:
                process = subprocess.Popen(command, cwd=host, env=environment, stdin=subprocess.DEVNULL, stdout=out,
                                           stderr=err, start_new_session=True)
    except BaseException:
        if job:
            job.close()
        raise

    def kill_all():
        if windows:
            job.terminate()
        else:
            os.killpg(process.pid, signal.SIGKILL)

    killed, peak = None, 0
    try:
        while process.poll() is None:
            if windows:
                over = 'memoryLimit' in job.poll_messages()
                peak = job.peak_memory()
            else:
                rss = vh._process_group_rss(process.pid)
                peak = max(peak, rss)
                over = rss > limit
            if over:
                killed = 'memoryLimit'
                kill_all()
                break
            time.sleep(poll)
        code = process.wait()
    finally:
        if process.poll() is None:
            kill_all()
            process.wait()
        # Validations the GUI started end with it.
        if windows:
            stray = job.active_processes() > 0
            if stray:
                job.terminate()
            job.close()
        else:
            stray = vh._group_alive(process.pid)
            if stray:
                os.killpg(process.pid, signal.SIGKILL)
    return {'exitCode': code, 'killedFor': killed, 'strayProcessesKilled': stray, 'peakBytes': peak,
            'seconds': round(time.monotonic() - started, 3)}


def launch(settings, *, gui_dir, worker_dir, script=None, keep_run_dir=False, allow_unknown_build=False, adapters=None,
           platform=None, log=print):
    snapshot = vh.load_snapshot(settings['snapshot'])
    platform = platform or vh.current_platform()
    if snapshot['buildPlatform'] != platform:
        raise vh.Blocked('platformMismatch', f'the snapshot holds the {snapshot["buildPlatform"]} game; this is {platform}')
    # Matched again at launch, as the Controller does per run: the snapshot record alone is not trusted.
    if vh.match_adapter(snapshot['files'], adapters)[0] is None and not allow_unknown_build:
        raise vh.Blocked('unknownBuild', 'the GUI is built against a known game build; this snapshot has no adapter')
    exe = GUI_NAME + ('.exe' if os.name == 'nt' else '')
    if not (Path(gui_dir) / exe).is_file():
        raise vh.Blocked('guiMissing', f'{Path(gui_dir) / exe} not found; build gui/RimWorldValidation.Gui first '
                                       '(see docs/validation-host.md)')
    results = Path(settings['results']).resolve()
    results.mkdir(parents=True, exist_ok=True)
    roots = [Path(p) for p in settings.get('mods') or []] or default_mod_roots(snapshot)
    mods, skipped = discover_mod_folders(roots)
    for item in skipped:
        log(f'skipped mod folder {item["path"]}: {item["reason"]}')
    mods_config = settings.get('modsConfig') or default_mods_config(snapshot)
    run_dir = results / GUI_SESSION
    if run_dir.exists():
        # A session that crashed earlier: its links point into the snapshot, so remove them carefully.
        error = vh.remove_run_host(run_dir / 'host')
        if error:
            raise vh.Blocked('guiSessionBusy', f'{run_dir} is in use or cannot be removed: {error}')
        shutil.rmtree(run_dir)
    info = build_gui_dir(run_dir, snapshot, Path(gui_dir), mods, results=results, python=sys.executable,
                         controller=REPO / 'tools' / 'validation_host.py', worker_dir=Path(worker_dir).resolve(),
                         baseline_cache=results / '.baseline-cache', mods_config=mods_config, script=script)
    log(f'GUI: {len(mods)} mods from {", ".join(map(str, roots)) or "(no mod folder)"}; results in {results}')
    memory = int(settings.get('memoryMiB') or DEFAULT_MEMORY_MIB)
    process = run_gui(run_dir, memory, gui_environment(run_dir, memory))
    process['linkModes'] = info['linkModes']
    if keep_run_dir:
        process['runDir'] = str(run_dir)
    else:
        error = vh.remove_run_host(run_dir / 'host')
        if error:
            process['cleanupError'] = error
        else:
            shutil.rmtree(run_dir, ignore_errors=True)
    return process


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validation GUI drawn by the game (test-only; never playable).')
    commands = parser.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('setup', help='remember the snapshot, results folder and mod folders')
    setup.add_argument('--snapshot', required=True)
    setup.add_argument('--results', required=True)
    setup.add_argument('--mods', action='append', default=[], help='mod folder roots (default: the game\'s Mods and Steam workshop)')
    setup.add_argument('--mods-config', help="the game's ModsConfig.xml to import the load order from (read only)")
    setup.add_argument('--memory-mib', type=int, default=DEFAULT_MEMORY_MIB)
    setup.add_argument('--settings', default=None, help=argparse.SUPPRESS)
    start = commands.add_parser('launch', help='open the GUI')
    start.add_argument('--settings', default=None, help='settings file (default: the one "setup" wrote)')
    start.add_argument('--gui', default=str(REPO / 'gui' / 'bin'))
    start.add_argument('--worker', default=str(REPO / 'worker' / 'bin'))
    start.add_argument('--script', help='test-only JSON list of GUI steps (screenshots and the like)')
    start.add_argument('--keep-run-dir', action='store_true')
    start.add_argument('--allow-unknown-build', action='store_true')
    args = parser.parse_args(argv)
    path = Path(args.settings) if args.settings else settings_path()
    try:
        if args.command == 'setup':
            settings = {'snapshot': str(Path(args.snapshot).resolve()), 'results': str(Path(args.results).resolve()),
                        'mods': [str(Path(p).resolve()) for p in args.mods],
                        'modsConfig': str(Path(args.mods_config).resolve()) if args.mods_config else None,
                        'memoryMiB': args.memory_mib}
            vh.load_snapshot(settings['snapshot'])
            path.parent.mkdir(parents=True, exist_ok=True)
            vh._write_json(path, settings)
            print(f'saved {path}')
            return 0
        script = json.loads(Path(args.script).read_text(encoding='utf-8')) if args.script else None
        process = launch(load_settings(path), gui_dir=args.gui, worker_dir=args.worker, script=script,
                         keep_run_dir=args.keep_run_dir, allow_unknown_build=args.allow_unknown_build)
    except vh.Blocked as blocked:
        print(f'blocked: {blocked.code}: {blocked.detail}', file=sys.stderr)
        return vh.EXIT_CODES['blocked']
    print(json.dumps(process, ensure_ascii=False))
    return 0 if process['exitCode'] == 0 and not process['killedFor'] else 3


if __name__ == '__main__':
    sys.exit(main())
