"""Private PG+Neo readiness; one owned Python child includes driver cleanup."""

import hashlib
import hmac
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

DOMAIN = b'anvil.deployment-readiness.v1'
READY = b'{"postgres":"ready","neo4j":"ready"}'
_slot = threading.BoundedSemaphore(1)


def token(secret):
    if len(secret) < 32:
        raise ValueError('Configured session secret required')
    return hmac.new(secret.encode(), DOMAIN, hashlib.sha256).hexdigest()


def worker():
    # All connection/query/session/driver shutdown runs inside the owned child.
    try:
        import psycopg
        from neo4j import READ_ACCESS, Query

        from anvil.config import setting
        from anvil.graph import driver

        with psycopg.connect(setting('DATABASE_URL'), connect_timeout=2,
                options='-c statement_timeout=2000 -c default_transaction_read_only=on') as connection:
            row = connection.execute('SELECT 1').fetchone()
            if row != (1,) or type(row[0]) is not int:
                raise ValueError('PostgreSQL readiness result mismatch')
        with driver() as graph, graph.session(default_access_mode=READ_ACCESS) as session:
            result = session.run(Query('RETURN 1 AS anvil_neo_ready', timeout=2))
            record = result.single(strict=True)
            result.consume()
            if (record is None or record.data() != {'anvil_neo_ready': 1}
                    or type(record.data()['anvil_neo_ready']) is not int):
                raise ValueError('Neo readiness result mismatch')
        sys.stdout.buffer.write(READY)
        sys.stdout.buffer.flush()
        return 0
    except BaseException:
        # Never return/log credentials, database addresses, or raw exceptions.
        return 1


def bounded_check():
    if not _slot.acquire(blocking=False):
        return False
    child = None
    deadline = time.monotonic() + 10
    passed = False
    try:
        code = ('import sys; sys.path.insert(0,sys.argv[1]); '
                'from anvil.deployment_readiness import worker; sys.exit(worker())')
        child = subprocess.Popen([sys.executable, '-I', '-B', '-c', code,
            str(Path(__file__).resolve().parent.parent)], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        output, _ = child.communicate(timeout=max(0.001, deadline - time.monotonic() - 2))
        passed = child.returncode == 0 and output == READY
    except (OSError, subprocess.SubprocessError, TimeoutError):
        passed = False
    finally:
        try:
            if child is not None:
                if child.poll() is None:
                    child.kill()  #Only our exact Python child; no Docker/Java/vendor process.
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    child.wait(timeout=remaining)
                if child.poll() is None or time.monotonic() > deadline:
                    passed = False
                if child.stdout is not None:
                    child.stdout.close()
        except (OSError, subprocess.SubprocessError):
            passed = False
        finally:
            # Unreaped child locks readiness closed until owned-container recovery.
            if child is None or child.poll() is not None:
                _slot.release()
    return passed


def routes():
    router = APIRouter()

    @router.get('/api/v1/internal/deployment-ready', include_in_schema=False)
    def readiness(request: Request):
        from anvil.config import setting

        supplied = request.headers.get('x-anvil-readiness', '')
        if not re.fullmatch('[a-f0-9]{64}', supplied) or not hmac.compare_digest(supplied, token(setting('ANVIL_SESSION_KEY'))):
            return JSONResponse({'detail': 'Not found'}, status_code=404, headers={'Cache-Control': 'no-store'})
        ready = bounded_check()
        return JSONResponse({'data': json.loads(READY) if ready else {'status': 'unready'}},
            status_code=200 if ready else 503, headers={'Cache-Control': 'no-store'})

    return router
