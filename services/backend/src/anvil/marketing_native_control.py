"""Closed single-connection root control boundary; no runtime admission.

Source listener/launcher and typed opening actor ownership are present but not
independently qualified. Linux peer credentials and retained bindings are necessary checks,
not runtime/import/physical lifecycle qualification. No caller callback/command.
"""

import asyncio
import hashlib
import hmac
import math
import os
import re
import socket
import struct
from time import monotonic

from anvil.marketing_native_attempt import MarketingAttemptStore
from anvil.marketing_native_boundary import marketing_native_gate
from anvil.marketing_native_collector import _handle
from anvil.marketing_native_mounts import _context_version
from anvil.marketing_native_records import _parse_record

ROUTES = frozenset({"framework_entry", "preflight", "before_start", "start", "logs", "artifact_stat", "copy_output", "collect", "actor", "stop", "collect_private"})


def _remaining(context):
    delta = context["deadline_monotonic"] - monotonic()
    if not math.isfinite(delta) or not 0 < delta <= context["lifecycle_seconds"]:
        raise TimeoutError("marketing_host_control_deadline")
    return delta


def _binding(store, root, claim, writer, *, opening=False):
    binding = _parse_record(store._read(root, "host-control-binding.json"))
    raw = store._read(root, "component-context.json")
    context = _parse_record(raw)
    fields = {"schema_version", "job_id", "request_sha256", "plan_sha256", "scope",
              "context_sha256", "framework_pid", "framework_start_ticks", "boot_id"}
    if opening:
        fields.add('operator_program_sha256')
        from anvil.marketing_native_boundary import _bounded_canonical, _digest

        plan = _parse_record(store._read(root, 'lifecycle-plan.json'))
        if (plan.get('schema_version') != 'anvil.marketing-native-lifecycle-plan.v2'
                or binding.get('operator_program_sha256') != claim['operator_program_sha256']
                or context.get('operator_program_sha256') != claim['operator_program_sha256']
                or _digest(context.get('operator_program')) != claim['operator_program_sha256']
                or _bounded_canonical(context.get('operator_program'), 65536)
                != _bounded_canonical(plan.get('operator_program'), 65536)):
            raise ValueError('marketing_opening_host_program_changed')
    if (set(binding) != fields or binding.get("schema_version") != (
            "anvil.marketing-host-control-binding.v2" if opening else "anvil.marketing-host-control-binding.v1")
            or any(binding.get(k) != claim[k] for k in ("job_id", "request_sha256", "plan_sha256", "scope"))
            or binding.get("context_sha256") != hashlib.sha256(raw).hexdigest()
            or type(binding.get("framework_pid")) is not int or binding["framework_pid"] <= 1
            or type(binding.get("framework_start_ticks")) is not int or binding["framework_start_ticks"] <= 0):
        raise ValueError("marketing_independent_host_binding_required")
    if (context.get("schema_version") != ("anvil.marketing-component-context.v2" if opening
                                          else "anvil.marketing-component-context.v1")
            or any(context.get(k) != claim[k] for k in ("job_id", "request_sha256", "plan_sha256", "trial_name"))
            or context.get("attempt_root") != str(store.parent / claim["trial_name"])
            or type(context.get("control_token")) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", context["control_token"])
            or type(context.get("operation_nonce")) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", context["operation_nonce"])
            or context.get("control_socket") != "/run/anvil-marketing/" + context["operation_nonce"][:20] + "/control.sock"
            or type(context.get("lifecycle_seconds")) is not int or not 1 <= context["lifecycle_seconds"] <= 600
            or type(context.get("deadline_monotonic")) not in (int, float)
            or not math.isfinite(context["deadline_monotonic"])):
        raise ValueError("marketing_bound_host_context_required")
    with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as stream:
        boot = stream.read(64).strip()
    if binding["boot_id"] != boot or context.get("boot_id") != boot:
        raise ValueError("marketing_host_same_boot_required")
    transport = writer.get_extra_info("socket")
    if transport is None or transport.family != socket.AF_UNIX or transport.getsockname() != context["control_socket"]:
        raise ValueError("marketing_fixed_unix_transport_required")
    pid, uid, gid = struct.unpack("3i", transport.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    if pid != binding["framework_pid"] or uid != 0 or gid != 0:
        raise ValueError("marketing_exact_root_framework_peer_required")
    # Linux stat comm may contain spaces/parentheses. Field22 starts at tail[19].
    with open("/proc/" + str(pid) + "/stat", encoding="ascii") as stream:
        proc = stream.read(4097)
    if len(proc) > 4096 or ") " not in proc:
        raise ValueError("marketing_framework_process_identity_required")
    tail = proc.rsplit(") ", 1)[1].split()
    if len(tail) < 20 or int(tail[19]) != binding["framework_start_ticks"]:
        raise ValueError("marketing_framework_process_reuse_denied")
    _remaining(context)
    return context


async def _request(reader, context):
    # Bound bytes independently of StreamReader's caller-configured limit.
    header = bytearray()
    while len(header) < 8192:
        header.extend(await reader.readexactly(1))
        if header.endswith(b"\r\n\r\n"):
            break
    else:
        raise ValueError("marketing_control_header_capacity")
    lines = bytes(header).split(b"\r\n")
    headers = {}
    for line in lines[1:-2]:
        key, value = line.split(b":", 1)
        key = key.lower()
        if key in headers:
            raise ValueError("marketing_control_duplicate_header")
        headers[key] = value.strip()
    if (set(headers) != {b"host", b"authorization", b"content-type", b"connection", b"content-length"}
            or headers[b"host"] != b"localhost" or headers[b"content-type"] != b"application/json"
            or headers[b"connection"] != b"close"
            or not hmac.compare_digest(headers[b"authorization"], b"Bearer " + context["control_token"].encode("ascii"))
            or not re.fullmatch(rb"[1-9][0-9]{0,3}", headers[b"content-length"])):
        raise ValueError("marketing_control_fixed_authenticated_headers_required")
    route = next((name for name in ROUTES if lines[0] == (
        "POST /marketing/component/" + name + " HTTP/1.1").encode("ascii")), None)
    if route is None:
        raise ValueError("marketing_control_unimplemented_route_denied")
    size = int(headers[b"content-length"])
    if size > 4096:
        raise ValueError("marketing_control_body_capacity")
    raw = await reader.readexactly(size)
    event = _parse_record(raw)
    if event.get("event") != route or event.get("operation_nonce") != context["operation_nonce"]:
        raise ValueError("marketing_control_route_identity_required")
    return raw


async def handle_control_connection(request, reader, writer, *, opening=False, actor_owner=None):
    """Future fixed listener binds request independently; this creates no server."""
    marketing_native_gate()
    try:
        with MarketingAttemptStore() as store:
            root, claim, _ = _context_version(store, request, opening=opening)
            try:
                context = _binding(store, root, claim, writer, opening=opening)
            finally:
                os.close(root)

            async def exchange():
                raw = await _request(reader, context)
                _remaining(context)
                if _parse_record(raw)["event"] in {'actor', 'stop'}:
                    from anvil.marketing_native_actor_owner import _OpeningActorOwner

                    if not opening or type(actor_owner) is not _OpeningActorOwner:
                        raise ValueError('marketing_fixed_original_actor_owner_required')
                    if _parse_record(raw)['event'] == 'actor':
                        result = await actor_owner.execute(request, raw)
                    else:
                        result = await actor_owner.stop(request, raw)
                elif _parse_record(raw)["event"] == "framework_entry":
                    from anvil.marketing_native_framework import _record

                    result = _record(store, request, raw, opening=opening)
                elif _parse_record(raw)["event"] == "preflight":
                    from anvil.marketing_native_preflight import _event

                    result = await _event(store, request, raw, opening=opening)
                elif _parse_record(raw)['event'] == 'collect_private':
                    from anvil.marketing_native_actor_owner import _OpeningActorOwner
                    from anvil.marketing_native_enrollment_client import (
                        request_original_physical_event,
                    )
                    from anvil.marketing_native_private_records import (
                        resolve_private_marketing_records,
                    )

                    if not opening or type(actor_owner) is not _OpeningActorOwner or not actor_owner._private:
                        raise ValueError('marketing_explicit_private_original_collection_required')
                    root, _, _ = _context_version(store, request, opening=True)
                    try:
                        result = await request_original_physical_event(store, root, request,
                            resolve_private_marketing_records(request), raw)
                    finally:
                        os.close(root)
                elif _parse_record(raw)["event"] in {"before_start", "start", "logs"}:
                    from anvil.marketing_native_physical import _event

                    result = await _event(store, request, raw, opening=opening,
                                          private=actor_owner is not None and actor_owner._private)
                else:
                    result = _handle(store, request, raw, opening=opening)
                _remaining(context)
                from anvil.marketing_native_boundary import _bounded_canonical

                response = _bounded_canonical(result, 16384)
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: "
                             + str(len(response)).encode("ascii") + b"\r\n\r\n" + response)
                await writer.drain()
                _remaining(context)

            await asyncio.wait_for(exchange(), timeout=_remaining(context))
    finally:
        writer.close()  # No unbounded wait_closed, persistence, retry or error payload.
