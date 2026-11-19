"""Pinned loader compatibility; synthetic files never qualify an installed image."""

import json
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from anvil import qualification_resources as resources


@pytest.fixture
def pinned(monkeypatch):
    beartype = pytest.importorskip("beartype")
    site = Path(beartype.__file__).parent.parent
    monkeypatch.setattr(resources, "INSTALLED_ROOT", site)
    observed = []
    # Local checkout is not root-owned. Production custody is never bypassed;
    # only this test replaces it to exercise actual pinned RECORD/source checks.
    monkeypatch.setattr(resources, "_custody", lambda path, **kwargs: observed.append(path))
    loader_class = resources._pinned_beartype_loader()
    assert len(observed) >= 488
    return loader_class


def test_exact_stdlib_and_pinned_loader_preserve_raw_code(tmp_path, pinned):
    path = tmp_path / "plain.py"
    path.write_text("def f(value: int) -> int:\n    return value + 1\n")
    expected = compile(path.read_bytes(), str(path), "exec", dont_inherit=True, optimize=sys.flags.optimize)
    for loader in (SourceFileLoader("plain", str(path)), pinned("plain", str(path))):
        resources._validate_loader_code("plain", loader, str(path), expected, beartype_class=pinned)
    changed = compile("answer = 'changed'", str(path), "exec", dont_inherit=True)
    with pytest.raises(RuntimeError, match="differs from source"):
        resources._validate_loader_code("plain", pinned("plain", str(path)), str(path), changed, beartype_class=pinned)


def test_unknown_name_spoof_and_instance_delegation_rejected(tmp_path, pinned):
    path = tmp_path / "plain.py"
    path.write_text("answer = 1\n")
    expected = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
    spoof = type("BeartypeSourceFileLoader", (SourceFileLoader,), {"__module__": resources.BEARTYPE_LOADER_MODULE})
    with pytest.raises(RuntimeError, match="Unexpected"):
        resources._validate_loader_code("plain", spoof("plain", str(path)), str(path), expected, beartype_class=pinned)
    loader = pinned("plain", str(path))
    loader.get_code = lambda name: expected
    with pytest.raises(RuntimeError, match="Unexpected"):
        resources._validate_loader_code("plain", loader, str(path), expected, beartype_class=pinned)


def test_mutated_pinned_class_implementation_rejected(pinned, monkeypatch):
    monkeypatch.setattr(pinned, "get_code", lambda self, name: SourceFileLoader(name, self.path).get_code(name))
    with pytest.raises(RuntimeError, match="implementation changed"):
        resources._pinned_beartype_loader()


def test_class_mutation_between_instances_is_rejected(tmp_path, pinned, monkeypatch):
    path = tmp_path / "plain.py"
    path.write_text("answer = 1\n")
    expected = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
    methods = {key: (vars(pinned)[key], vars(pinned)[key].__code__)
               for key in ("__init__", "get_code", "source_to_code")}
    loader = pinned("plain", str(path))
    monkeypatch.setattr(pinned, "get_code", lambda self, name: expected)
    with pytest.raises(RuntimeError, match="during verification"):
        resources._validate_loader_code("plain", loader, str(path), expected,
                                         beartype_class=pinned, beartype_methods=methods)


@pytest.mark.parametrize("fault", ["record_content", "version", "import_origin"])
def test_pinned_distribution_record_version_and_import_origin_rejected(tmp_path, pinned, monkeypatch, fault):
    original = resources.INSTALLED_ROOT
    for name in ("beartype", "beartype-0.23.1.dist-info"):
        shutil.copytree(original / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(resources, "INSTALLED_ROOT", tmp_path)
    if fault == "record_content":
        with (tmp_path / "beartype/__init__.py").open("ab") as stream:
            stream.write(b"\n# synthetic changed source\n")
        expected = "RECORD content changed"
    elif fault == "version":
        metadata = tmp_path / "beartype-0.23.1.dist-info/METADATA"
        metadata.write_bytes(metadata.read_bytes().replace(b"Version: 0.23.1", b"Version: 0.23.2"))
        expected = "distribution required"
    else:
        expected = "module identity"
    with pytest.raises(RuntimeError, match=expected):
        resources._pinned_beartype_loader()


def test_actual_hook_global_loader_and_transformed_package_fail_closed(tmp_path):
    pytest.importorskip("beartype")
    plain = tmp_path / "unregistered_firstparty.py"
    plain.write_text("def f(value: int) -> int:\n    return value + 1\n")
    package = tmp_path / "registered_control"
    package.mkdir()
    (package / "__init__.py").write_text("def f(value: int) -> int:\n    return value + 1\n")
    # Isolate Beartype's global path-hook installation from the rest of pytest.
    program = r'''
import importlib,json,runpy,sys
from pathlib import Path
from beartype.claw import beartype_package
from beartype.claw._importlib._clawimpfileloader import BeartypeSourceFileLoader
r=runpy.run_path(sys.argv[1],run_name='qualification_loader_control')
sys.path.insert(0,sys.argv[2]);beartype_package('registered_control');importlib.invalidate_caches()
m=importlib.import_module('unregistered_firstparty');p=Path(m.__file__)
assert type(m.__loader__) is BeartypeSourceFileLoader
r['_validate_loader_code'](m.__name__,m.__loader__,str(p),compile(p.read_bytes(),str(p),'exec',dont_inherit=True),beartype_class=BeartypeSourceFileLoader)
t=importlib.import_module('registered_control');p=Path(t.__file__)
try:
 r['_validate_loader_code'](t.__name__,t.__loader__,str(p),compile(p.read_bytes(),str(p),'exec',dont_inherit=True),beartype_class=BeartypeSourceFileLoader)
except RuntimeError:
 print(json.dumps({'unregistered_raw_code':'passed','registered_transform':'rejected'}))
else:
 raise AssertionError('AST transformed first-party code accepted')
'''
    result = subprocess.run([sys.executable, "-B", "-c", program, resources.__file__, str(tmp_path)],
                            capture_output=True, timeout=15, check=True)
    assert json.loads(result.stdout) == {"unregistered_raw_code": "passed", "registered_transform": "rejected"}
