"""Closed fixed root Unix listener; existing connection handler remains gated.

No native admission, process binding or physical lifecycle proof is supplied.
Retained socket/intent state is never unlinked or silently reused on restart.
"""

import asyncio
import os
import socket
from dataclasses import dataclass
from time import monotonic

from anvil.marketing_native_attempt import _owned, _write_at
from anvil.marketing_native_boundary import DOCUMENT_CAP, _bounded_canonical, marketing_native_gate
from anvil.marketing_native_control import handle_control_connection


@dataclass
class _Listener:
    server: object
    connections: set
    state: dict

    def close(self):
        self.state["closing"] = True
        self.server.close()
        for task in tuple(self.connections):
            task.cancel()

    async def wait_closed(self):
        await self.server.wait_closed()
        if self.connections:
            await asyncio.gather(*tuple(self.connections), return_exceptions=True)


async def _listen(store, root, claim, context, request, *, opening=False, actor_owner=None):
    nonce = context["operation_nonce"]
    address = "/run/anvil-marketing/" + nonce[:20] + "/control.sock"
    if context["control_socket"] != address:
        raise ValueError("marketing_fixed_listener_address_required")
    _write_at(root, "control-listener-intent.json", _bounded_canonical({
        "schema_version": "anvil.marketing-control-listener-intent.v1",
        "job_id": claim["job_id"], "request_sha256": claim["request_sha256"],
        "plan_sha256": claim["plan_sha256"], "operation_nonce": nonce,
        "address": address, "scope": claim["scope"],
    }, DOCUMENT_CAP))
    run = os.open("/run", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    base = folder = None
    listener = None
    server = None
    connections = set()
    state = {"closing": False}
    try:
        _owned(os.fstat(run), 0, directory=True)
        try:
            os.mkdir("anvil-marketing", 0o700, dir_fd=run)
            os.fsync(run)
        except FileExistsError:
            pass
        base = os.open("anvil-marketing", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=run)
        _owned(os.fstat(base), 0, directory=True, private=True)
        # Exclusive nonce directory: no old socket, unlink or broad chmod path.
        os.mkdir(nonce[:20], 0o700, dir_fd=base)
        os.fsync(base)
        folder = os.open(nonce[:20], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
        _owned(os.fstat(folder), 0, directory=True, private=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.setblocking(False)
        listener.bind(address)  # Kernel-exclusive bind; never asyncio path cleanup.
        os.chmod("control.sock", 0o600, dir_fd=folder, follow_symlinks=False)
        os.fsync(folder)
        listener.listen(1)
        active = False

        async def connection(reader, writer):
            nonlocal active
            task = asyncio.current_task()
            connections.add(task)
            admitted = False
            try:
                if active or state["closing"]:
                    writer.close()
                    return
                active = admitted = True
                await handle_control_connection(request, reader, writer, opening=opening, actor_owner=actor_owner)
            except (Exception, asyncio.CancelledError):
                # No retry/error payload or promotion to recorded success.
                writer.close()
            finally:
                if admitted:
                    active = False
                connections.discard(task)

        # Passing the bound socket avoids start_unix_server's path unlink logic.
        server = await asyncio.start_unix_server(connection, sock=listener, limit=8192)
        listener = None  # Ownership transferred to server.
        _write_at(root, "control-listener-receipt.json", _bounded_canonical({
            "schema_version": "anvil.marketing-control-listener-receipt.v1",
            "job_id": claim["job_id"], "request_sha256": claim["request_sha256"],
            "plan_sha256": claim["plan_sha256"], "operation_nonce": nonce,
            "address": address, "scope": claim["scope"], "native_admitted": False,
        }, DOCUMENT_CAP))
        return _Listener(server, connections, state)
    except BaseException:
        state["closing"] = True
        if server is not None:
            server.close()
        for task in tuple(connections):
            task.cancel()
        if listener is not None:
            listener.close()
        if server is not None or connections:
            # This handle has not escaped to the launcher. Its failure path
            # therefore owns shutdown AND joining, not merely cancellation.
            remaining = context["deadline_monotonic"] - monotonic()
            if not 0 < remaining <= context["lifecycle_seconds"]:
                raise RuntimeError("marketing_listener_cleanup_unknown_no_replay") from None

            async def join_owned():
                if server is not None:
                    await server.wait_closed()
                if connections:
                    await asyncio.gather(*tuple(connections), return_exceptions=True)

            join = asyncio.create_task(join_owned())
            try:
                done, _ = await asyncio.wait({join}, timeout=remaining)
                if join not in done:
                    raise RuntimeError("marketing_listener_cleanup_unknown_no_replay")
                join.result()  # A failed/cancelled join never becomes success.
            finally:
                if not join.done():
                    join.cancel()
            # Propagate the original setup failure after the owned join.
        raise
    finally:
        for fd in (folder, base, run):
            if fd is not None:
                os.close(fd)


async def prepare_control_listener(request):
    marketing_native_gate()
    from anvil.marketing_native_attempt import MarketingAttemptStore
    from anvil.marketing_native_mounts import _context
    from anvil.marketing_native_reconcile import _context_status
    from anvil.marketing_native_records import _parse_record

    with MarketingAttemptStore() as store:
        root, claim, plan = _context(store, request)
        try:
            status = _context_status(store, root, claim, plan)
            if status["same_boot_observed"] is not True or status["deadline_elapsed_observed"] is not False:
                raise ValueError("marketing_current_listener_context_required")
            context = _parse_record(store._read(root, "component-context.json"))
            return await _listen(store, root, claim, context, request)
        finally:
            os.close(root)
