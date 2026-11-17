"""Closed executor preparation: owned files and one-way materialization custody.

No framework, API prepare, world, graph or provider is started here. File custody
is not native intent/admission, phase execution, collection or cleanup proof.
"""

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from uuid import UUID

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    PURPOSE,
    MarketingCampaignRequestV1,
    _bounded_canonical,
    marketing_native_gate,
    prepare_marketing_request,
)
from anvil.marketing_native_records import _parse_record
from anvil.marketing_native_renderer import (
    FILES,
    LIFECYCLE_PHASES,
    MarketingTaskProjectionV1,
    MarketingTaskProjectionV2,
)

PARENT = Path("/var/lib/anvil-qa-v1/runtime-functional/marketing-attempts")


def _owned(info, owner, *, directory=False, private=False):
    if ((not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or info.st_uid != owner or info.st_mode & (0o077 if private else 0o022)
            or not directory and info.st_nlink != 1):
        raise ValueError("marketing_owned_file_custody_required")


def _write_at(folder, name, raw, *, mode=0o600):
    if "/" in name or name in {"", ".", ".."} or type(raw) is not bytes or len(raw) > DOCUMENT_CAP:
        raise ValueError("marketing_fixed_bounded_write_required")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=folder)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(folder)


class MarketingAttemptStore:
    def __init__(self):
        if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
            raise ValueError("marketing_existing_QA_root_required")
        self._initialize(PARENT, owner=0, scope="root_QA_materialization_NOT_native_admission")

    @classmethod
    def for_owned_local_test(cls, parent):
        instance = object.__new__(cls)
        instance._initialize(Path(parent), owner=os.geteuid(), scope="owned_test_NOT_QA")
        return instance

    def _initialize(self, parent, *, owner, scope):
        if not parent.is_absolute() or parent.resolve() != parent:
            raise ValueError("marketing_canonical_existing_parent_required")
        self.parent, self.owner, self.scope = parent, owner, scope
        self.fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _owned(os.fstat(self.fd), owner, directory=True, private=True)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _dir(self, folder, name):
        if "/" in name or name in {"", ".", ".."}:
            raise ValueError("marketing_fixed_component_required")
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
        try:
            _owned(os.fstat(fd), self.owner, directory=True)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _walk(self, folder, parts):
        fd = os.dup(folder)
        try:
            for part in parts:
                child = self._dir(fd, part)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _read(self, folder, name):
        if "/" in name or name in {"", ".", ".."}:
            raise ValueError("marketing_fixed_component_required")
        # A FIFO/device must not block before fstat can reject its type.
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=folder)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            _owned(before, self.owner)
            raw = stream.read(DOCUMENT_CAP + 1)
            after = os.fstat(stream.fileno())
        if (len(raw) > DOCUMENT_CAP or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("marketing_materialized_file_changed")
        return raw

    def materialize(self, request, projection):
        if type(request) is not MarketingCampaignRequestV1 or type(projection) is not MarketingTaskProjectionV1:
            raise ValueError("marketing_exact_materialization_types_required")
        return self._materialize(request, projection, opening=False)

    def materialize_opening(self, request, projection):
        if type(request) is not MarketingCampaignRequestV1 or type(projection) is not MarketingTaskProjectionV2:
            raise ValueError('marketing_exact_opening_materialization_types_required')
        return self._materialize(request, projection, opening=True)

    def materialize_private_opening(self, request, projection):
        """Explicit successor; same per-job marker forbids a new attempt/reset."""
        from anvil.marketing_native_verifier_renderer import (
            MarketingPrivateProjectionV1,
            validate_private_program,
        )

        if type(request) is not MarketingCampaignRequestV1 or type(projection) is not MarketingPrivateProjectionV1:
            raise ValueError('marketing_exact_private_materialization_types_required')
        program = validate_private_program(_parse_record(projection.private_program))
        if program != projection.private_program:
            raise ValueError('marketing_private_program_exact_bytes_required')
        receipt = self._materialize(request, projection, opening=True)
        root = None
        try:
            root = self._dir(self.fd, receipt['trial_name'])
            _write_at(root, 'private-verifier-program-intent.json', _bounded_canonical({
                'schema_version': 'anvil.marketing-private-program-materialization-intent.v1',
                'request_sha256': receipt['request_sha256'], 'plan_sha256': receipt['plan_sha256'],
                'private_program_sha256': hashlib.sha256(program).hexdigest(), 'replay_permitted': False,
            }, DOCUMENT_CAP))
            os.mkdir('sealed-verifier', 0o700, dir_fd=root)
            _write_at(root, 'private-verifier-program.json', program, mode=0o400)
            if self._read(root, 'private-verifier-program.json') != program:
                raise RuntimeError('marketing_private_program_materialization_unknown')
            _write_at(root, 'private-verifier-program-receipt.json', _bounded_canonical({
                'schema_version': 'anvil.marketing-private-program-materialization-receipt.v1',
                'request_sha256': receipt['request_sha256'], 'plan_sha256': receipt['plan_sha256'],
                'private_program_sha256': hashlib.sha256(program).hexdigest(),
                'status': 'private_program_and_empty_sealed_directory_ONLY', 'native_qualified': False,
            }, DOCUMENT_CAP))
            return receipt
        except BaseException:
            try:
                _write_at(self.fd, receipt['job_id'] + '.materialization-terminal.json', _bounded_canonical({
                    'request_sha256': receipt['request_sha256'], 'scope': self.scope,
                    'status': 'private_materialization_unknown_no_replay',
                }, DOCUMENT_CAP))
            except OSError:
                pass
            raise
        finally:
            if root is not None:
                os.close(root)

    def _materialize(self, request, projection, *, opening):
        prepare_marketing_request(request.canonical_bytes)
        value = json.loads(request.canonical_bytes)
        job = value["job_id"]
        if str(UUID(job)) != job:
            raise ValueError("marketing_canonical_job_required")
        plan = _parse_record(projection.lifecycle_plan)
        name = plan["trial_name"]
        pin = hashlib.sha256(request.canonical_bytes).hexdigest()
        if (set(plan) != {"schema_version", "purpose", "request_sha256", "attempt_root", "trial_name",
                          "expected_files", "bounds", "runtime", "expected_effective_services", "phases"}
                    | ({'operator_program', 'operator_program_sha256'} if opening else set())
                or plan["schema_version"] != ('anvil.marketing-native-lifecycle-plan.v2' if opening
                                              else 'anvil.marketing-native-lifecycle-plan.v1')
                or plan["purpose"] != PURPOSE or plan["request_sha256"] != pin
                or plan["phases"] != list(LIFECYCLE_PHASES)
                or type(name) is not str or not re.fullmatch(r"anvil-marketing-[a-f0-9]{20}", name)
                or plan["attempt_root"] != str(PARENT / name)):
            raise ValueError("marketing_exact_attempt_plan_required")
        if opening:
            from anvil.marketing_native_opening import validate_opening_program

            if validate_opening_program(request, plan['operator_program']) != plan['operator_program_sha256']:
                raise ValueError('marketing_opening_plan_program_changed')
        files = dict(projection.files)
        if (len(projection.files) != 7 or set(files) != FILES
                or any(type(raw) is not bytes or not raw or len(raw) > DOCUMENT_CAP for raw in files.values())
                or {key: hashlib.sha256(raw).hexdigest() for key, raw in files.items()} != plan["expected_files"]):
            raise ValueError("marketing_exact_materialization_file_pins_required")
        claim = {"schema_version": "anvil.marketing-materialization-intent.v1", "scope": self.scope,
                 "job_id": job, "request_sha256": pin, "trial_name": name,
                 "plan_sha256": hashlib.sha256(projection.lifecycle_plan).hexdigest(),
                 "expected_files": plan["expected_files"]}
        if opening:
            claim['schema_version'] = 'anvil.marketing-materialization-intent.v2'
            claim['operator_program_sha256'] = plan['operator_program_sha256']
        # Fixed per-job marker, independent of fresh directory or trial name.
        # Failure to claim is outside the mutation/terminal block: never touch an
        # earlier attempt's files or successful/unknown outcome during a replay.
        _write_at(self.fd, job + ".materialization-intent.json", _bounded_canonical(claim, DOCUMENT_CAP))
        root = None
        try:
            os.mkdir(name, 0o700, dir_fd=self.fd)
            os.fsync(self.fd)
            root = self._dir(self.fd, name)
            directories = ["task", "task/environment", "task/environment/actor", "task/tests", "sealed",
                           "trials", "trials/" + name, "trials/" + name + "/agent",
                           "trials/" + name + "/artifacts", "trials/" + name + "/artifacts/logs",
                           "trials/" + name + "/artifacts/logs/artifacts", "trials/" + name + "/verifier"]
            for relative in directories:
                parts = relative.split("/")
                parent = self._walk(root, parts[:-1])
                try:
                    os.mkdir(parts[-1], 0o700, dir_fd=parent)
                    os.fsync(parent)
                finally:
                    os.close(parent)
            for relative, raw in sorted(files.items()):
                parts = ("task/" + relative).split("/")
                parent = self._walk(root, parts[:-1])
                try:
                    _write_at(parent, parts[-1], raw, mode=0o444 if relative.startswith("environment/actor/") else 0o400)
                finally:
                    os.close(parent)
            actor = self._walk(root, ["task", "environment", "actor"])
            try:
                os.fchmod(actor, 0o555)
                os.fsync(actor)
            finally:
                os.close(actor)
            _write_at(root, "lifecycle-plan.json", projection.lifecycle_plan)
            receipt = claim | {"schema_version": "anvil.marketing-materialization-receipt.v2",
                               "status": "files_sealed_ONLY", "native_framework_started": False,
                               "this_component_invoked_API_prepare": False, "paid_calls": False, "replay_permitted": False}
            if opening:
                receipt['schema_version'] = 'anvil.marketing-materialization-receipt.v3'
            _write_at(root, "materialization-receipt.json", _bounded_canonical(receipt, DOCUMENT_CAP))
            return receipt
        except BaseException:
            # Retain claimed/partial state. No directory removal, repair or replay.
            try:
                _write_at(self.fd, job + ".materialization-terminal.json", _bounded_canonical({
                    "request_sha256": pin, "scope": self.scope,
                    "status": "materialization_unknown_no_replay",
                }, DOCUMENT_CAP))
            except OSError:
                pass
            raise
        finally:
            if root is not None:
                os.close(root)

    def read_status(self, request):
        """Read-only file reconciliation, never native recovery or retry authority."""
        return self._read_status(request, opening=False)

    def read_opening_status(self, request):
        return self._read_status(request, opening=True)

    def _read_status(self, request, *, opening):
        unknown = {"status": "unknown_or_unmaterialized_no_replay", "scope": self.scope,
                   "native_qualified": False, "replay_permitted": False}
        root = None
        try:
            prepare_marketing_request(request.canonical_bytes)
            job = json.loads(request.canonical_bytes)["job_id"]
            if str(UUID(job)) != job:
                return unknown
            claim = _parse_record(self._read(self.fd, job + ".materialization-intent.json"))
            if (set(claim) != {"schema_version", "scope", "job_id", "request_sha256", "trial_name", "plan_sha256", "expected_files"}
                    | ({'operator_program_sha256'} if opening else set())
                    or claim["schema_version"] != ('anvil.marketing-materialization-intent.v2' if opening
                                                   else 'anvil.marketing-materialization-intent.v1')
                    or claim["request_sha256"] != hashlib.sha256(request.canonical_bytes).hexdigest()
                    or claim["scope"] != self.scope or claim["job_id"] != job
                    or not re.fullmatch(r"anvil-marketing-[a-f0-9]{20}", claim["trial_name"])):
                return unknown
            try:
                self._read(self.fd, job + ".materialization-terminal.json")
            except FileNotFoundError:
                pass
            else:
                return unknown
            root = self._dir(self.fd, claim["trial_name"])
            receipt = _parse_record(self._read(root, "materialization-receipt.json"))
            plan = self._read(root, "lifecycle-plan.json")
            if (set(receipt) != set(claim) | {"status", "native_framework_started", "this_component_invoked_API_prepare", "paid_calls", "replay_permitted"}
                    or receipt["schema_version"] != ('anvil.marketing-materialization-receipt.v3' if opening
                                                     else 'anvil.marketing-materialization-receipt.v2')
                    or any(receipt[key] != claim[key] for key in set(claim) - {"schema_version"})
                    or receipt["request_sha256"] != claim["request_sha256"]
                    or receipt["plan_sha256"] != claim["plan_sha256"]
                    or hashlib.sha256(plan).hexdigest() != claim["plan_sha256"]
                    or receipt["expected_files"] != claim["expected_files"]
                    or receipt["status"] != "files_sealed_ONLY"
                    or any(receipt[key] is not False for key in ("native_framework_started", "this_component_invoked_API_prepare", "paid_calls", "replay_permitted"))
                    or set(claim["expected_files"]) != FILES):
                return unknown
            if opening:
                from anvil.marketing_native_opening import validate_opening_program

                body = _parse_record(plan)
                if (body['schema_version'] != 'anvil.marketing-native-lifecycle-plan.v2'
                        or validate_opening_program(request, body['operator_program']) != claim['operator_program_sha256']
                        or body['operator_program_sha256'] != claim['operator_program_sha256']):
                    return unknown
            for relative, expected in claim["expected_files"].items():
                parts = ("task/" + relative).split("/")
                parent = self._walk(root, parts[:-1])
                try:
                    if hashlib.sha256(self._read(parent, parts[-1])).hexdigest() != expected:
                        return unknown
                finally:
                    os.close(parent)
            return {"status": "files_sealed_ONLY", "scope": self.scope, "native_qualified": False, "replay_permitted": False}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return unknown
        finally:
            if root is not None:
                os.close(root)


def prepare_marketing_attempt(request, prepared):
    marketing_native_gate()
    from anvil.marketing_native_renderer import render_marketing_task

    projection = render_marketing_task(request, prepared)
    with MarketingAttemptStore() as store:
        return store.materialize(request, projection)


def prepare_marketing_opening_attempt(request, prepared):
    marketing_native_gate()
    from anvil.marketing_native_renderer import render_marketing_opening_task

    projection = render_marketing_opening_task(request, prepared)
    with MarketingAttemptStore() as store:
        return store.materialize_opening(request, projection)
