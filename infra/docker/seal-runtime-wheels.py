"""Build-time byte provenance only; never runtime admission or qualification."""

import hashlib
import json
import os
import stat
from pathlib import Path

ROOT = Path('/opt/anvil-runtime-source')
WHEELS = Path('/opt/anvil-runtime-wheels')
EXPECTED = {
    'adi_anvil-0.2.1-py3-none-any.whl': 'adi-anvil',
    'anvil_harbor_adapter-0.1.0-py3-none-any.whl': 'anvil-harbor-adapter',
}


def digest(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or info.st_mode & 0o022 or info.st_size > 33554432):
        raise ValueError('exact bounded root-owned build artifact required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, raw):
    fd = os.open(WHEELS / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def seal_builder_lock(builder_root):
    # uv creates this empty coordination file mode 0666. It is not package code,
    # but must meet the same ownership and write-protection rules before sealing.
    fd = os.open(builder_root / '.lock', os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_nlink != 1 or info.st_size != 0
                or stat.S_IMODE(info.st_mode) not in (0o600, 0o666)):
            raise ValueError('exact empty root-owned uv builder lock required')
        os.fchmod(fd, 0o600)
        os.fsync(fd)
    finally:
        os.close(fd)


def main():
    if {p.name for p in WHEELS.glob('*.whl')} != set(EXPECTED):
        raise ValueError('exact two first-party wheels required')
    pins = {name: digest(WHEELS / name) for name in EXPECTED}
    resources = [
        'services/harbor/runtime/uv.lock',
        'services/harbor/runtime/build-requirements.in',
        'services/harbor/runtime/build-requirements.lock',
        'services/harbor/runtime/pyproject.toml',
        'services/harbor/pyproject.toml',
        'services/backend/pyproject.toml',
        'infra/docker/marketing-runtime.Dockerfile',
        'infra/docker/seal-runtime-wheels.py',
        'integrations/evaluators/local_worker.py',
        'integrations/evaluators/nemo/uv.lock',
        'integrations/evaluators/promptfoo/worker.mjs',
        'integrations/evaluators/promptfoo/package-lock.json',
    ]
    code = {}
    for prefix in ('services/backend/src/anvil', 'services/harbor/src/anvil_harbor'):
        for path in sorted((ROOT / prefix).rglob('*.py')):
            code[str(path.relative_to(ROOT))] = digest(path)
    if not code or len(code) > 4096:
        raise ValueError('bounded complete first-party source inventory required')
    builder_root = Path('/opt/anvil-runtime-builder')
    seal_builder_lock(builder_root)
    builder = {}
    for path in sorted(builder_root.rglob('*')):
        if path.is_symlink() and path == builder_root / 'lib64' and os.readlink(path) == 'lib':
            builder['lib64'] = {'symlink_target': 'lib'}
            continue
        if path.is_dir() and not path.is_symlink():
            continue
        builder[str(path.relative_to(builder_root))] = digest(path)
    if not builder or len(builder) > 8192:
        raise ValueError('bounded complete builder byte inventory required')
    manifest = {
        'schema_version': 'anvil.marketing-runtime-wheel-build-bytes.v1',
        'wheels': pins, 'source_python_files': code,
        'actual_builder_files': builder,
        'inputs': {name: digest(ROOT / name) for name in resources},
        'uv_version_file_sha256': digest(WHEELS / 'uv-version.txt'),
        'native_qualified': False,
    }
    requirements = ''.join(
        f'{EXPECTED[name]} @ {(WHEELS / name).as_uri()} --hash=sha256:{pin}\n'
        for name, pin in sorted(pins.items())
    )
    write('first-party.requirements.lock', requirements.encode())
    write('build-bytes.json', (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode())
    fd = os.open(WHEELS, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
