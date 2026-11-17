"""Qualification evidence paths for source checkouts and the isolated runtime.

This binds installed first-party source files to the sealed source tree. It does
not qualify native mappings, process custody, or permission to execute a run.
No environment variable, working directory or import search path selects a root.
"""

import hashlib
import os
import stat
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

SEALED_ROOT = Path("/opt/anvil-runtime-source")
INSTALLED_ROOT = Path("/opt/anvil-runtime/lib/python3.12/site-packages")
PACKAGING_INPUTS = (
    "services/harbor/pyproject.toml",
    "services/harbor/runtime/pyproject.toml",
    "services/harbor/runtime/uv.lock",
    "infra/docker/marketing-runtime.Dockerfile",
    "services/harbor/runtime/build-requirements.in",
    "services/harbor/runtime/build-requirements.lock",
    "infra/docker/seal-runtime-wheels.py",
)
MAX_MEMBER_BYTES = 32 * 1024 * 1024


def _custody(path: Path, *, directory: bool = False):
    """Check each lexical ancestor; resolving first would conceal symlinks."""
    for item in (path, *path.parents):
        info = item.lstat()
        is_dir = item != path or directory
        if (
            info.st_uid != 0
            or info.st_mode & 0o022
            or stat.S_ISLNK(info.st_mode)
            or (is_dir and not stat.S_ISDIR(info.st_mode))
            or (not is_dir and not stat.S_ISREG(info.st_mode))
            or (not is_dir and info.st_nlink != 1)
        ):
            raise RuntimeError("Unsealed qualification resource custody")


def _members(package: Path):
    _custody(package, directory=True)
    result = {}
    total = 0
    directory_count = 0
    for parent, directories, files in os.walk(package, followlinks=False):
        directory_count += 1
        if directory_count > 1024:
            raise RuntimeError("Qualification package directory count exceeds bound")
        current = Path(parent)
        _custody(current, directory=True)
        for name in list(directories):
            _custody(current / name, directory=True)
            if name == "__pycache__":
                directories.remove(name)
        for name in files:
            path = current / name
            # Bytecode is not source evidence. Loaded origins are checked below;
            # actual interpreter/bytecode execution remains runtime qualification.
            if path.suffix == ".pyc":
                continue
            _custody(path)
            if path.stat().st_size > MAX_MEMBER_BYTES:
                raise RuntimeError("Qualification source member exceeds bound")
            total += path.stat().st_size
            if len(result) >= 8192 or total > 256 * 1024 * 1024:
                raise RuntimeError("Qualification package exceeds bound")
            result[str(path.relative_to(package))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    if not result:
        raise RuntimeError("Empty qualification package")
    return result


def qualification_root():
    actual = Path(__file__)
    checkout = actual.parents[4]
    if actual == checkout / "services/backend/src/anvil/qualification_resources.py":
        # Preserve ordinary checkout operation; ANVIL_ROOT never selects evidence.
        if actual.resolve() != actual:
            raise RuntimeError("Aliased qualification source checkout")
        return checkout
    if actual != INSTALLED_ROOT / "anvil/qualification_resources.py":
        raise RuntimeError("Unexpected installed qualification module origin")
    _custody(SEALED_ROOT, directory=True)
    for package, relative in (
        ("anvil", "services/backend/src/anvil"),
        ("anvil_harbor", "services/harbor/src/anvil_harbor"),
    ):
        installed = INSTALLED_ROOT / package
        if _members(installed) != _members(SEALED_ROOT / relative):
            raise RuntimeError("Installed package differs from sealed source")
        for name, module in tuple(sys.modules.items()):
            if name != package and not name.startswith(package + "."):
                continue
            spec = getattr(module, "__spec__", None)
            origin = getattr(spec, "origin", None)
            if (
                not origin
                or getattr(spec, "name", None) != name
                or type(spec.loader) is not SourceFileLoader
                or spec.loader.name != name
                or spec.loader.path != origin
            ):
                raise RuntimeError("Unexpected loaded first-party module loader")
            loaded = Path(origin)
            module_path = INSTALLED_ROOT.joinpath(*name.split("."))
            if loaded not in (
                module_path.with_suffix(".py"), module_path / "__init__.py"
            ):
                raise RuntimeError("Unexpected loaded first-party module origin")
            if getattr(module, "__file__", None) != origin:
                raise RuntimeError("Inconsistent loaded first-party module origin")
            _custody(loaded)
            expected_code = compile(
                loaded.read_bytes(), str(loaded), "exec",
                dont_inherit=True, optimize=sys.flags.optimize,
            )
            if spec.loader.get_code(name) != expected_code:
                raise RuntimeError("Cached first-party code differs from source")
    return SEALED_ROOT


def qualification_path(root: Path, relative: str):
    member = Path(relative)
    if member.is_absolute() or not member.parts or ".." in member.parts:
        raise RuntimeError("Invalid qualification resource name")
    path = root / member
    if root == SEALED_ROOT:
        _custody(path)
    elif path.resolve() != path:
        raise RuntimeError("Aliased qualification resource")
    if not path.is_file() or path.stat().st_size > MAX_MEMBER_BYTES:
        raise RuntimeError("Missing or oversized qualification resource")
    return path
