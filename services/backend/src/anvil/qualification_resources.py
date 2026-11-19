"""Qualification evidence paths for source checkouts and the isolated runtime.

This binds installed first-party source files to the sealed source tree. It does
not qualify native mappings, process custody, or permission to execute a run.
No environment variable, working directory or import search path selects a root.
"""

import base64
import hashlib
import importlib
import importlib.metadata
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
BEARTYPE_LOADER_MODULE = "beartype.claw._importlib._clawimpfileloader"
BEARTYPE_LOADER_SHA256 = "88d43fa418e844d33771b20636d48f31fbc27446c1b666f56b0326713ca2e000"


def _pinned_beartype_loader():
    """Permit one sealed dependency implementation, never arbitrary subclasses."""
    distributions = [dist for dist in importlib.metadata.distributions(path=[str(INSTALLED_ROOT)])
                     if dist.metadata["Name"].lower() == "beartype"]
    if len(distributions) != 1 or distributions[0].version != "0.23.1":
        raise RuntimeError("Exact sealed Beartype distribution required")
    distribution = distributions[0]
    if distribution.files is None or not 1 <= len(distribution.files) <= 2048:
        raise RuntimeError("Complete Beartype RECORD required")
    recorded = set()
    for entry in distribution.files:
        relative = Path(str(entry))
        if (relative.is_absolute() or ".." in relative.parts or not relative.parts
                or relative.parts[0] not in {"beartype", "beartype-0.23.1.dist-info"}):
            raise RuntimeError("Unexpected Beartype distribution member")
        path = Path(distribution.locate_file(entry))
        if path != INSTALLED_ROOT / relative:
            raise RuntimeError("Unexpected Beartype distribution origin")
        _custody(path)
        if path.stat().st_size > MAX_MEMBER_BYTES:
            raise RuntimeError("Beartype member exceeds bound")
        raw = path.read_bytes()
        if entry.hash is None:
            if str(relative) != "beartype-0.23.1.dist-info/RECORD":
                raise RuntimeError("Unhashed Beartype member")
        elif (entry.hash.mode != "sha256" or entry.size != len(raw)
              or base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode() != entry.hash.value):
            raise RuntimeError("Beartype RECORD content changed")
        recorded.add(relative)
    actual = {path.relative_to(INSTALLED_ROOT) for path in (INSTALLED_ROOT / "beartype").rglob("*")
              if path.is_file() and path.suffix != ".pyc"}
    for path in (INSTALLED_ROOT / "beartype").rglob("*"):
        if path.is_dir():
            _custody(path, directory=True)
    if actual != {path for path in recorded if path.parts[0] == "beartype" and path.suffix != ".pyc"}:
        raise RuntimeError("Incomplete Beartype source inventory")
    origin = INSTALLED_ROOT.joinpath(*BEARTYPE_LOADER_MODULE.split(".")).with_suffix(".py")
    if hashlib.sha256(origin.read_bytes()).hexdigest() != BEARTYPE_LOADER_SHA256:
        raise RuntimeError("Pinned Beartype loader source changed")
    module = importlib.import_module(BEARTYPE_LOADER_MODULE)
    spec = module.__spec__
    if (spec.name != BEARTYPE_LOADER_MODULE or spec.origin != str(origin)
            or module.__file__ != str(origin) or module.SourceFileLoader is not SourceFileLoader):
        raise RuntimeError("Unexpected Beartype loader module identity")
    loader_class = module.BeartypeSourceFileLoader
    if (loader_class.__module__ != BEARTYPE_LOADER_MODULE
            or loader_class.__name__ != "BeartypeSourceFileLoader"
            or loader_class.__bases__ != (SourceFileLoader,)):
        raise RuntimeError("Unexpected Beartype loader class identity")
    # Class methods themselves must still be the pinned source implementation.
    source = compile(origin.read_bytes(), str(origin), "exec", dont_inherit=True, optimize=sys.flags.optimize)
    class_code = next(code for code in source.co_consts if getattr(code, "co_name", None) == "BeartypeSourceFileLoader")
    methods = {code.co_name: code for code in class_code.co_consts if hasattr(code, "co_code")}
    for name in ("__init__", "get_code", "source_to_code"):
        method = vars(loader_class).get(name)
        if (getattr(method, "__code__", None) != methods[name]
                or method.__globals__ is not vars(module)
                or any(cell.cell_contents is not loader_class for key, cell in
                       zip(method.__code__.co_freevars, method.__closure__ or ()) if key == "__class__")):
            raise RuntimeError("Beartype loader implementation changed")
    return loader_class


def _validate_loader_code(name, loader, origin, expected_code, *, beartype_class=None, beartype_methods=None):
    if (type(loader) is not SourceFileLoader and type(loader) is not beartype_class
            or loader.name != name or loader.path != origin
            or any(key in vars(loader) for key in ("get_code", "source_to_code", "get_data", "get_filename", "path_stats"))):
        raise RuntimeError("Unexpected loaded first-party module loader")
    if type(loader) is beartype_class and beartype_methods is not None:
        if any(vars(beartype_class).get(key) is not method or method.__code__ != code
               for key, (method, code) in beartype_methods.items()):
            raise RuntimeError("Beartype loader implementation changed during verification")
    # Invoke both the actual loader and a separate exact stdlib instance. Calling
    # the base method on a subclass would still dynamically delegate transforms.
    if (loader.get_code(name) != expected_code
            or SourceFileLoader(name, origin).get_code(name) != expected_code):
        raise RuntimeError("Cached or transformed first-party code differs from source")


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
    beartype_class = None
    beartype_methods = None
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
            if type(spec.loader) is not SourceFileLoader and beartype_class is None:
                beartype_class = _pinned_beartype_loader()
                beartype_methods = {key: (vars(beartype_class)[key], vars(beartype_class)[key].__code__)
                                    for key in ("__init__", "get_code", "source_to_code")}
            _validate_loader_code(name, spec.loader, origin, expected_code, beartype_class=beartype_class,
                                  beartype_methods=beartype_methods)
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
