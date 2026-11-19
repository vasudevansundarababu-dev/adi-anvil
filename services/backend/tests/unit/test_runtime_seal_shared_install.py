"""Shared readonly validation is local to one call; all source guards remain."""
import importlib.util
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def sealed(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[3] / "harbor/src/anvil_harbor/operator_proof.py"
    spec = importlib.util.spec_from_file_location("synthetic_operator_seal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    store = object.__new__(module.OperatorProofStore)
    store.owner, store.repository = os.getuid(), tmp_path / "repository"
    prefix, stdlib = tmp_path / "runtime", tmp_path / "stdlib"
    site = prefix / "lib/site-packages"
    manifests = {}

    def file(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)
        return module.sha(data)

    def manifest(value):
        pin = module.sha(module.canonical(value))
        manifests[pin] = value
        return pin

    interpreter = prefix / "bin/python"
    interpreter_pin = file(interpreter, b"synthetic interpreter")
    interpreter.chmod(0o700)
    config_pin = file(prefix / "pyvenv.cfg", b"version = 3.12.15\ninclude-system-site-packages = false\n")
    library = stdlib / "synthetic.py"
    stdlib_pin = manifest({str(library): file(library, b"synthetic stdlib")})
    installed = {}
    packages = {}
    for component, package, folder in (("backend", "anvil", "backend"), ("harbor", "anvil_harbor", "harbor")):
        target = site / package / "__init__.py"
        pin = file(target, ("synthetic " + package).encode())
        file(store.repository / f"services/{folder}/src/{package}/__init__.py", target.read_bytes())
        installed[str(target.relative_to(site))] = pin
        packages[component] = ({package: str(target.parent)}, manifest({str(target): pin}))
    installed["harbor.dist-info/RECORD"] = file(site / "harbor.dist-info/RECORD", b"synthetic record")
    distro = SimpleNamespace(metadata={"Name": "harbor"}, version="0.25.0", files=list(installed),
                             locate_file=lambda name: site / name)
    monkeypatch.setattr(module.importlib.metadata, "distributions", lambda **kwargs: [distro])
    monkeypatch.setattr(store, "_runtime_manifest", lambda pin: manifests[pin])
    common = {"prefix": str(prefix), "site_packages": str(site), "interpreter": str(interpreter),
              "interpreter_sha256": interpreter_pin, "python_version": "3.12.15", "venv_config_sha256": config_pin,
              "distributions": {"harbor": {"version": "0.25.0", "files_sha256": manifest(installed)}},
              "stdlib_root": str(stdlib), "stdlib_files_sha256": stdlib_pin}
    seal = {"schema_version": "anvil.fixed-runtime-seal.v2", "components": {
        component: common | {"source_packages": folders, "source_files_sha256": pin}
        for component, (folders, pin) in packages.items()}}
    return module, store, seal


@pytest.mark.parametrize("readonly,changed,expected", [(True, False, 1), (False, False, 2), (True, True, 2)])
def test_common_closure_dedup_only_for_identical_readonly_install(sealed, monkeypatch, readonly, changed, expected):
    module, store, seal = sealed
    monkeypatch.setattr(module.os, "statvfs", lambda path: SimpleNamespace(f_flag=os.ST_RDONLY if readonly else 0))
    if changed:
        seal["components"]["harbor"]["python_version"] = "3.12.16"
    calls = []
    original = store._validate_runtime_common

    def common(record):
        calls.append(record)
        if changed:
            # Distinct fingerprints must receive independent full validation.
            record = deepcopy(record)
            record["python_version"] = "3.12.15"
        original(record)

    monkeypatch.setattr(store, "_validate_runtime_common", common)
    store.validate_runtime_seal(seal)
    assert len(calls) == expected
    store.validate_runtime_seal(seal)
    assert len(calls) == 2 * expected  # no cross-call cache


@pytest.mark.parametrize("target", ["installed", "mirror", "stdlib", "record", "source_inventory"])
def test_all_full_closure_and_source_guards_remain(sealed, monkeypatch, target):
    module, store, seal = sealed
    monkeypatch.setattr(module.os, "statvfs", lambda path: SimpleNamespace(f_flag=os.ST_RDONLY))
    record = seal["components"]["harbor"]
    paths = {"installed": Path(record["site_packages"]) / "anvil_harbor/__init__.py",
             "mirror": store.repository / "services/harbor/src/anvil_harbor/__init__.py",
             "stdlib": Path(record["stdlib_root"]) / "synthetic.py",
             "record": Path(record["site_packages"]) / "harbor.dist-info/RECORD",
             "source_inventory": Path(record["site_packages"]) / "anvil_harbor/extra.py"}
    paths[target].write_bytes(b"tampered")
    with pytest.raises(module.ProofBlocked):
        store.validate_runtime_seal(seal)


def test_readonly_dedup_still_checks_second_component_mirror(sealed, monkeypatch):
    module, store, seal = sealed
    monkeypatch.setattr(module.os, "statvfs", lambda path: SimpleNamespace(f_flag=os.ST_RDONLY))
    original = store._validate_runtime_common

    def change_after_common(record):
        original(record)
        (store.repository / "services/harbor/src/anvil_harbor/__init__.py").write_bytes(b"changed after common")

    monkeypatch.setattr(store, "_validate_runtime_common", change_after_common)
    with pytest.raises(module.ProofBlocked):
        store.validate_runtime_seal(seal)


def test_loaded_source_manifest_is_hash_verified_once_not_once_per_module(sealed, monkeypatch):
    module, store, seal = sealed
    record = seal["components"]["backend"]
    origin = str(Path(record["site_packages"]) / "anvil/__init__.py")
    loaded = SimpleNamespace(__file__=origin, __spec__=SimpleNamespace(origin=origin))
    monkeypatch.setattr(module, "sys", SimpleNamespace(prefix=record["prefix"], modules={"anvil": loaded, "anvil.synthetic": loaded}))
    original, calls = store._runtime_manifest, []

    def manifest(pin):
        calls.append(pin)
        return original(pin)

    monkeypatch.setattr(store, "_runtime_manifest", manifest)
    store.validate_loaded_origins(seal, component="backend")
    assert calls.count(record["source_files_sha256"]) == 1
    loaded.__file__ = str(store.repository / "foreign.py")
    with pytest.raises(module.ProofBlocked):
        store.validate_loaded_origins(seal, component="backend")


@pytest.mark.parametrize("component", ["backend", "harbor"])
def test_shared_interpreter_checks_each_first_party_package_against_own_seal(sealed, monkeypatch, component):
    module, store, seal = sealed
    record = seal["components"][component]
    site = Path(record["site_packages"])
    backend_origin, harbor_origin = str(site / "anvil/__init__.py"), str(site / "anvil_harbor/__init__.py")
    backend = SimpleNamespace(__file__=backend_origin, __spec__=SimpleNamespace(origin=backend_origin))
    harbor = SimpleNamespace(__file__=harbor_origin, __spec__=SimpleNamespace(origin=harbor_origin))
    monkeypatch.setattr(module, "sys", SimpleNamespace(prefix=record["prefix"], modules={"anvil": backend, "anvil_harbor": harbor}))
    store.validate_loaded_origins(seal, component=component)
    # Being inside the OTHER sealed wheel is not authority for this package.
    backend.__file__ = harbor_origin
    with pytest.raises(module.ProofBlocked, match="backend_editable_fallback_forbidden"):
        store.validate_loaded_origins(seal, component=component)
    backend.__file__, harbor.__file__ = backend_origin, backend_origin
    with pytest.raises(module.ProofBlocked, match="harbor_editable_fallback_forbidden"):
        store.validate_loaded_origins(seal, component=component)


@pytest.mark.parametrize("kind", ["nested_directory", "file_bind", "external_interpreter"])
def test_writable_nested_mount_or_external_interpreter_forbids_dedup(sealed, monkeypatch, tmp_path, kind):
    module, store, seal = sealed
    record = seal["components"]["backend"]
    if kind == "nested_directory":
        writable = Path(record["site_packages"]) / "anvil"
    elif kind == "file_bind":
        writable = Path(record["site_packages"]) / "anvil/__init__.py"
    else:
        interpreter = Path(record["interpreter"])
        writable = tmp_path / "external-python"
        writable.write_bytes(interpreter.read_bytes())
        writable.chmod(0o700)
        interpreter.unlink()
        interpreter.symlink_to(writable)
    observed = []

    def mounts(path):
        path = Path(path)
        observed.append(path)
        return SimpleNamespace(f_flag=0 if path == writable else os.ST_RDONLY)

    monkeypatch.setattr(module.os, "statvfs", mounts)
    calls, original = [], store._validate_runtime_common

    def common(current):
        calls.append(current)
        original(current)

    monkeypatch.setattr(store, "_validate_runtime_common", common)
    store.validate_runtime_seal(seal)
    assert writable in observed
    assert len(calls) == 2
