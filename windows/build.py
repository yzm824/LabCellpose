"""Build the Windows (x64, CPU) LabCellpose folder from this repository.

    python windows/build.py --stage STAGE_DIR --cache CACHE_DIR [--shell SHELL_OUTPUT_DIR]

Run on Windows with any Python 3.9+; the bundled runtime does the rest. Unlike the macOS build, which carries the runtime
of the previous release forward, this one starts from nothing: the standalone CPython build and the Cellpose-SAM weights
are downloaded (and checked against pinned SHA-256 values), and the dependencies are installed from the same pinned
versions as the macOS runtime (engine/requirements.lock.txt) plus the two packages that only Windows needs.

Result:  STAGE_DIR/LabCellpose/
             LabCellpose.exe ...        the shell, when --shell is given
             resources/                 interface.html, desktop_backend.py
             payload/                   app, assets, presets, licenses, models, runtime, LabCellpose.cmd, ...
"""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tarfile, urllib.request

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
sys.path.insert(0, str(HERE))
from user_guide import windows_guide
PYTHON_VERSION = '3.12.14'
PYTHON_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/20260825/'
              'cpython-3.12.14%2B20260825-x86_64-pc-windows-msvc-install_only.tar.gz')
PYTHON_SHA256 = '15d25c455ea25d6b24d7e58eabdf744fd0db3cfb977934ae08fd2237acd8ccc1'
MODEL_URL = 'https://huggingface.co/mouseland/cellpose-sam/resolve/main/cpsam_v2'
MIRRORED = ('app', 'assets', 'presets', 'licenses')
# Files that windows/THIRD_PARTY_NOTICES.md points to (relative to site-packages), and a phrase each must contain.
NOTICE_FACTS = (
    ('fastremap-1.20.0.dist-info/licenses/LICENSE', 'GNU LESSER GENERAL PUBLIC LICENSE'),
    ('fill_voids-2.1.2.dist-info/licenses/COPYING.LESSER', 'GNU LESSER GENERAL PUBLIC LICENSE'),
    ('fill_voids-2.1.2.dist-info/licenses/COPYING', 'GNU GENERAL PUBLIC LICENSE'),
    ('cv2/opencv_videoio_ffmpeg500_64.dll', None),
    ('cv2/LICENSE-3RD-PARTY.txt', 'GNU LESSER GENERAL PUBLIC LICENSE'),
    ('numpy-2.5.3.dist-info/licenses/LICENSE.txt', 'GCC runtime'),
    ('scipy-1.18.1.dist-info/LICENSE.txt', 'GCC RUNTIME LIBRARY EXCEPTION'),
)
MARKER = re.compile(r'/\*__INCLUDE:([A-Za-z0-9_]+\.(?:js|css))__\*/')
# Longest path inside the folder that still unpacks under a typical C:\Users\name\Downloads\... location.
MAX_RELATIVE_PATH = 200


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(4 << 20), b''): h.update(block)
    return h.hexdigest()


def fetch(url, destination, expected):
    """Download once into the cache; a file with the wrong SHA-256 is never used."""
    if destination.exists() and sha(destination) == expected: return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + '.part')
    print('downloading', url, flush=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'LabCellpose-build'})
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, 'wb') as out:
        shutil.copyfileobj(response, out, 4 << 20)
    actual = sha(partial)
    if actual != expected:
        partial.unlink(); raise SystemExit(f'SHA-256 mismatch for {url}: {actual}')
    partial.replace(destination)
    return destination


def model_sha():
    text = (SOURCE / 'engine/app/analyze.py').read_text(encoding='utf-8')
    return re.search(r"^MODEL_SHA256 = '([0-9a-f]{64})'", text, re.M).group(1)


def version():
    text = (SOURCE / 'engine/app/analyze.py').read_text(encoding='utf-8')
    return re.search(r"^VERSION = '([^']+)'", text, re.M).group(1)


def read_text(path):
    """Source text exactly as committed. A checkout that rewrote line endings would change every hash in the package."""
    data = Path(path).read_bytes()
    if b'\r\n' in data: raise SystemExit(f'{path} has CRLF line endings; check it out with core.autocrlf=false')
    return data.decode('utf-8')


def setup_page():
    """The setup page with the styles and scripts it shares with the review page inlined (as in the macOS build)."""
    assets = SOURCE / 'engine/assets'
    page = read_text(SOURCE / 'desktop/interface.html')
    if not MARKER.search(page): raise SystemExit('interface.html has no include markers')
    def include(match):
        text = read_text(assets / match.group(1))
        if '</script' in text.lower() or '</style' in text.lower(): raise SystemExit(f'{match.group(1)} cannot be inlined')
        return text
    page = MARKER.sub(include, page)
    if '__INCLUDE:' in page: raise SystemExit('Unresolved include marker in interface.html')
    return page


def shipped(folder):
    return [p for p in sorted(folder.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name != '.DS_Store']


def run(command, **options):
    print('>', ' '.join(str(c) for c in command), flush=True)
    return subprocess.run([str(c) for c in command], check=True, **options)


DEPENDENCY_LISTING = r'''
import importlib.metadata as md, json, platform, sys
packages = []
for dist in sorted(md.distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = dist.metadata['Name']
    if name.lower() == 'pip': continue
    files = [str(f).replace('\\', '/') for f in (dist.files or [])]
    licenses = sorted(f for f in files if f.split('/')[-1].upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'AUTHORS'))
                      or '/licenses/' in f)
    packages.append(dict(name=name, version=dist.version,
                         license=dist.metadata.get('License-Expression') or dist.metadata.get('License') or '',
                         license_files=licenses))
json.dump(dict(python=platform.python_version(), packages=packages), sys.stdout, indent=1)
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True); parser.add_argument('--cache', required=True)
    parser.add_argument('--shell', help='folder with the compiled shell (LabCellpose.exe and the files beside it)')
    args = parser.parse_args()
    if os.name != 'nt': raise SystemExit('Build the Windows package on Windows.')
    stage, cache = Path(args.stage).resolve(), Path(args.cache).resolve()
    root = stage / 'LabCellpose'
    if root.exists(): shutil.rmtree(root)
    payload, resources = root / 'payload', root / 'resources'
    payload.mkdir(parents=True); resources.mkdir()

    # 1. The standalone CPython runtime, at payload/runtime.
    archive = fetch(PYTHON_URL, cache / 'python-install_only.tar.gz', PYTHON_SHA256)
    with tarfile.open(archive) as tar: tar.extractall(stage / 'python-unpacked', filter='data')
    shutil.move(str(stage / 'python-unpacked/python'), str(payload / 'runtime'))
    shutil.rmtree(stage / 'python-unpacked')
    python = payload / 'runtime/python.exe'
    isolated = [python, '-I', '-X', 'utf8']

    # 2. The same pinned dependencies as the macOS runtime, as wheels only, plus what tqdm and pandas need on Windows.
    run(isolated + ['-m', 'pip', 'install', '--no-deps', '--only-binary=:all:', '--no-compile', '--disable-pip-version-check',
                    '--no-warn-script-location', '--cache-dir', cache / 'pip',
                    '-r', SOURCE / 'engine/requirements.lock.txt', '-r', HERE / 'requirements.windows.txt'])
    run(isolated + ['-m', 'pip', 'check', '--disable-pip-version-check'])
    # The runtime is not an installer: no pip, and no launcher scripts (they record the build machine's paths).
    run(isolated + ['-m', 'pip', 'uninstall', '--yes', '--disable-pip-version-check', 'pip'])
    shutil.rmtree(payload / 'runtime/Scripts', ignore_errors=True)
    listing = subprocess.run([str(c) for c in isolated + ['-B', '-c', DEPENDENCY_LISTING]], check=True, capture_output=True, text=True, encoding='utf-8').stdout
    dependencies = json.loads(listing)
    if dependencies['python'] != PYTHON_VERSION: raise SystemExit('Unexpected Python ' + dependencies['python'])
    installed = {p['name'].lower().replace('_', '-'): p['version'] for p in dependencies['packages']}
    for line in read_text(SOURCE / 'engine/requirements.lock.txt').split():
        name, wanted = line.split('==')
        if installed.get(name.lower().replace('_', '-')) != wanted:
            raise SystemExit(f'{name}: installed {installed.get(name.lower().replace("_", "-"))}, the lock says {wanted}')

    # 3. Hash-checked bytecode, as in the macOS runtime: the app runs Python with -B and never writes into its folder.
    run(isolated + ['-m', 'compileall', '-q', '--invalidation-mode', 'checked-hash', payload / 'runtime/Lib'],
        stdout=subprocess.DEVNULL)

    # 4. The engine, mirrored from the source tree.
    for part in MIRRORED:
        for src in shipped(SOURCE / 'engine' / part):
            dst = payload / part / src.relative_to(SOURCE / 'engine' / part)
            dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
    for src in (SOURCE / 'engine').iterdir():
        if src.is_file() and src.name not in ('FILE_HASHES.json', '.DS_Store', 'DEPENDENCIES.json', 'PACKAGE.json', 'requirements.lock.txt', 'THIRD_PARTY_NOTICES.md'):
            shutil.copyfile(src, payload / src.name)
    # This package carries different compiled libraries than the macOS app, so it has its own notices. Whatever
    # they say about a file is checked here against the files that were just installed.
    shutil.copyfile(HERE / 'THIRD_PARTY_NOTICES.md', payload / 'THIRD_PARTY_NOTICES.md')
    packages = payload / 'runtime/Lib/site-packages'
    for relative, phrase in NOTICE_FACTS:
        file = packages / relative
        if not file.is_file(): raise SystemExit(f'The notices name {relative}, which is not in this build')
        if phrase and phrase.lower() not in file.read_bytes().decode('utf-8', 'replace').lower():
            raise SystemExit(f'The notices rely on {relative} mentioning {phrase!r}, and it does not')
    (payload / 'requirements.lock.txt').write_bytes('\n'.join(f"{p['name']}=={p['version']}" for p in dependencies['packages']).encode() + b'\n')
    (payload / 'DEPENDENCIES.json').write_bytes(json.dumps(dependencies, indent=1).encode('utf-8') + b'\n')
    package = json.loads(read_text(SOURCE / 'engine/PACKAGE.json'))
    for key in ('minimum_macos', 'tested_macos', 'apple_notarized'): package.pop(key, None)
    package.update(version=version(), platform='windows-x64', minimum_windows='10', processing='CPU', python=PYTHON_VERSION,
                   tested_windows=[], code_signed=False)
    (payload / 'PACKAGE.json').write_bytes(json.dumps(package, indent=2).encode('utf-8') + b'\n')
    # cmd.exe expects CRLF in a batch file; the repository stores LF.
    (payload / 'LabCellpose.cmd').write_bytes(read_text(HERE / 'LabCellpose.cmd').replace('\n', '\r\n').encode('ascii'))
    # Beside the program: the license of LabCellpose itself and the guide, with the line endings Notepad expects.
    (root / 'LICENSE.txt').write_bytes(read_text(SOURCE / 'LICENSE').replace('\n', '\r\n').encode('utf-8'))
    (root / 'USER_GUIDE.txt').write_bytes(windows_guide().replace('\n', '\r\n').encode('utf-8'))

    # 5. The model weights.
    weights = fetch(MODEL_URL, cache / 'cpsam_v2', model_sha())
    (payload / 'models').mkdir(); shutil.copyfile(weights, payload / 'models/cpsam_v2')

    # 6. The setup page and its backend, beside the shell.
    (resources / 'interface.html').write_bytes(setup_page().encode('utf-8'))
    shutil.copyfile(SOURCE / 'desktop/desktop_backend.py', resources / 'desktop_backend.py')
    if args.shell:
        for src in Path(args.shell).iterdir():
            if src.is_file() and src.suffix.lower() in ('.exe', '.dll', '.config') and 'Wpf' not in src.name: shutil.copyfile(src, root / src.name)
        for name in ('LabCellpose.exe', 'Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll', 'WebView2Loader.dll'):
            if not (root / name).is_file(): raise SystemExit(f'The compiled shell lacks {name}')
        # The license of the WebView2 SDK files, from the package they were restored from.
        found = sorted((Path.home() / '.nuget/packages/microsoft.web.webview2').glob('*/LICENSE.txt'))
        if not found: raise SystemExit('The WebView2 SDK license was not found in the NuGet package folder')
        shutil.copyfile(found[-1], payload / 'licenses/WEBVIEW2_LICENSE.txt')

    # 7. Integrity list: every payload file, bytecode included.
    hashes = {p.relative_to(payload).as_posix(): sha(p) for p in sorted(payload.rglob('*')) if p.is_file() and p.name != 'FILE_HASHES.json'}
    (payload / 'FILE_HASHES.json').write_bytes(json.dumps(hashes, indent=2).encode('utf-8') + b'\n')

    files = [p for p in root.rglob('*') if p.is_file()]
    longest = max(files, key=lambda p: len(str(p.relative_to(stage))))
    report = dict(folder=str(root), version=version(), python=PYTHON_VERSION, packages=len(dependencies['packages']),
                  payload_hash_entries=len(hashes), files=len(files), bytes=sum(p.stat().st_size for p in files),
                  longest_relative_path=len(str(longest.relative_to(stage))), longest_path=str(longest.relative_to(stage)),
                  shell=bool(args.shell))
    print(json.dumps(report, indent=2), flush=True)
    (stage / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if report['longest_relative_path'] > MAX_RELATIVE_PATH:
        print(f'WARNING: a path is longer than {MAX_RELATIVE_PATH} characters; unpacking can fail in a deep folder', flush=True)


if __name__ == '__main__':
    main()
