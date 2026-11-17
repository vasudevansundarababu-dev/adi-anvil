"""One private KYC worker RPC under its original controller cutoff; no retry."""

import asyncio
import ipaddress
import json
import os
from time import monotonic

import httpx
from httpcore._backends.anyio import AnyIOBackend

from anvil import pilot_environment
from anvil.marketing_native_wire_bounds import remaining
from anvil.marketing_native_worker_flags import trusted_worker_live_enabled
from anvil.praxis_case_dataset import content_hash
from anvil.worker_dispatch_broker import DispatchRequest, NativeFinish, _forward_value

ADDRESS='ANVIL_KYC_BROKER_HOSTADDR'
PIN='ANVIL_KYC_BROKER_TARGET_SHA256'


def configuration():
    numeric=os.environ.get(ADDRESS,'')
    if '%' in numeric or str(ipaddress.ip_address(numeric))!=numeric:
        raise ValueError('One exact numeric private KYC API address required')
    address=ipaddress.ip_address(numeric)
    if address.is_global or address.is_link_local or address.is_multicast or address.is_unspecified:
        raise ValueError('Private KYC broker must remain on the qualified internal network')
    expected=content_hash({'schema_version':'anvil.kyc-private-broker-target.v1','host':'api','port':8200,'hostaddr':numeric})
    if os.environ.get(PIN)!=expected:
        raise ValueError('Qualified private KYC API address required')
    return numeric


class FixedBackend(AnyIOBackend):
    def __init__(self,numeric):
        self.numeric=numeric

    async def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        if host!='api' or port!=8200 or local_address is not None:
            raise ValueError('Fixed private KYC API connection required')
        return await super().connect_tcp(self.numeric,8200,timeout=timeout,socket_options=socket_options)


def forward(job,actor,plan,stage,*,remaining_seconds=120,operation='dispatch',transport=None,native=None,
            effect_key=None,absolute_deadline=None):
    if (pilot_environment.current()!='qa' or os.environ.get('ANVIL_WORKER_BROKER_ROLE')!='worker'
            or not trusted_worker_live_enabled()
            or os.environ.get('ANVIL_WORKER_BROKER_ENABLED')!='true'
            or os.environ.get('ANVIL_WORKER_BROKER_URL')!='http://api:8200/internal/v1/worker-dispatch'):
        raise RuntimeError('Fixed QA KYC worker broker required')
    if operation not in {'prepare','readiness','dispatch','finish'} or effect_key is not None:
        raise ValueError('Fixed KYC operation required')
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError('Only explicit MockTransport for software controls')
    if type(remaining_seconds) is not int or not 1<=remaining_seconds<=600:
        raise ValueError('Original bounded KYC request interval required')
    # The trusted controller passes its cutoff on every operational call.
    remaining(absolute_deadline)
    deadline=min(absolute_deadline,monotonic()+remaining_seconds)
    left=int(remaining(deadline))
    if left<1:
        raise TimeoutError('Original KYC broker interval elapsed')
    body=DispatchRequest(project_id=job['project_id'],actor_id=actor,job_id=job['id'],lease_token=job['lease_token'],
                         plan_id=plan,stage_index=stage,remaining_seconds=left)
    if operation=='finish':
        body=NativeFinish(**body.model_dump(),native=native)
    elif native is not None:
        raise ValueError('Unexpected native KYC receipt')
    payload=body.model_dump(mode='json',exclude_none=True)
    raw=json.dumps(payload,separators=(',',':')).encode()
    if len(raw)>(1048576 if operation=='finish' else 98304):
        raise ValueError('Bounded private KYC RPC required')

    async def send():
        selected=transport
        if selected is None:
            selected=httpx.AsyncHTTPTransport(trust_env=False,retries=0,
                limits=httpx.Limits(max_connections=1,max_keepalive_connections=0))
            selected._pool._network_backend=FixedBackend(configuration())
        async with asyncio.timeout(remaining(deadline)):
            async with httpx.AsyncClient(transport=selected,trust_env=False,follow_redirects=False) as client:
                async with client.stream('POST','http://api:8200/internal/v1/worker-dispatch/kyc/'+operation,
                    headers={'Content-Type':'application/json','Accept-Encoding':'identity'},content=raw,timeout=remaining(deadline)) as response:
                    if response.status_code!=200 or response.headers.get('content-encoding','identity')!='identity':
                        raise RuntimeError('Private KYC RPC denied or unknown')
                    value=bytearray()
                    async for chunk in response.aiter_raw():
                        remaining(deadline)
                        if len(value)+len(chunk)>131072:
                            raise ValueError('Private KYC response bound exceeded')
                        value.extend(chunk)
                    return json.loads(value)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError('KYC synchronous controller cannot borrow an active event loop')
    try:
        result=asyncio.run(send())
        remaining(deadline)
        return _forward_value(result,operation)
    except Exception:
        raise RuntimeError('Private KYC RPC outcome unknown; no retry') from None
