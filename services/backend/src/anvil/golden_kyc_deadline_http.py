"""Private API-only deadline transport with exact numeric destination custody.

Original HTTPS hostname/SNI/certificate verification remain intact. A qualified
numeric endpoint map avoids DNS executor threads, fallback addresses and proxy
discovery. No SDK/metadata/secret request is retried or given a new allowance.
"""

import asyncio
import ipaddress
import json
import os
import re

import httpx
from httpcore._backends.anyio import AnyIOBackend

from anvil.golden_kyc_dispatch_scope import current
from anvil.marketing_native_wire_bounds import remaining
from anvil.praxis_case_dataset import content_hash

HOSTS=frozenset({'secretmanager.googleapis.com','api.openai.com','api.anthropic.com','generativelanguage.googleapis.com'})
MAP='ANVIL_KYC_RUNTIME_HTTPS_TARGETS'
PIN='ANVIL_KYC_RUNTIME_HTTPS_TARGETS_SHA256'


def configuration():
    raw=os.environ.get(MAP,'')
    if not 0<len(raw.encode())<=8192:
        raise ValueError('Qualified private KYC HTTPS destinations required')
    value=json.loads(raw)
    if (type(value) is not dict or set(value)!={'schema_version','hosts'}
            or value['schema_version']!='anvil.kyc-runtime-https-targets.v1'
            or type(value['hosts']) is not dict or not value['hosts'] or set(value['hosts'])-HOSTS):
        raise ValueError('Exact fixed private KYC HTTPS destination map required')
    for address in value['hosts'].values():
        if type(address) is not str or '%' in address or str(ipaddress.ip_address(address))!=address:
            raise ValueError('One canonical numeric address per HTTPS hostname required')
        parsed=ipaddress.ip_address(address)
        if not parsed.is_global or parsed.is_multicast or parsed.is_reserved or parsed.is_unspecified:
            raise ValueError('Public HTTPS destination address required')
    fingerprint=content_hash(value)
    if not re.fullmatch('[a-f0-9]{64}',os.environ.get(PIN,'')) or os.environ[PIN]!=fingerprint:
        raise ValueError('Private KYC HTTPS destination qualification changed')
    return value['hosts'],fingerprint


class FixedBackend(AnyIOBackend):
    def __init__(self,hosts):
        self.hosts=dict(hosts)

    async def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        if local_address is not None:
            raise ValueError('Private KYC HTTPS cannot change source routing')
        if host=='169.254.169.254' and port==80:
            numeric=host
        elif host in self.hosts and port==443:
            numeric=self.hosts[host]
        else:
            raise ValueError('Unqualified private KYC HTTPS destination')
        return await super().connect_tcp(numeric,port,timeout=timeout,socket_options=socket_options)


def _transport():
    hosts,_=configuration()
    transport=httpx.AsyncHTTPTransport(trust_env=False,retries=0,
        limits=httpx.Limits(max_connections=1,max_keepalive_connections=0))
    transport._pool._network_backend=FixedBackend(hosts)
    return transport


async def _read(client,method,url,*,headers=None,body=None,limit,deadline):
    remaining(deadline)
    headers=[(key,value) for key,value in (headers or []) if key.lower()!='accept-encoding']
    headers.append(('Accept-Encoding','identity'))
    async with client.stream(method,url,headers=headers,content=body,timeout=remaining(deadline)) as response:
        if response.headers.get('content-encoding','identity').lower()!='identity':
            raise ValueError('Private KYC response compression is outside the qualified profile')
        data=bytearray()
        async for chunk in response.aiter_raw():
            remaining(deadline)
            if len(data)+len(chunk)>limit:
                raise ValueError('Private KYC complete HTTP response exceeded its bound')
            data.extend(chunk)
        remaining(deadline)
        return response.status_code,list(response.headers.multi_items()),bytes(data)


def _run(operation):
    scope=current()
    if scope is None:
        raise RuntimeError('Private verified KYC server scope required')
    remaining(scope.absolute_deadline)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError('Private KYC sync HTTP caller cannot borrow an active event loop')

    async def bounded():
        async with asyncio.timeout(remaining(scope.absolute_deadline)):
            value=await operation(scope.absolute_deadline)
            remaining(scope.absolute_deadline)
            return value

    value=asyncio.run(bounded())
    remaining(scope.absolute_deadline)
    return value


def secret_request(method,path,body=None,*,transport=None):
    """Caller has already enforced the existing exact pilot secret resource."""
    if transport is not None and type(transport) is not httpx.MockTransport:
        raise ValueError('Only explicit MockTransport for offline software controls')

    async def operation(deadline):
        async with httpx.AsyncClient(transport=transport or _transport(),trust_env=False,follow_redirects=False) as client:
            status,_,raw=await _read(client,'GET','http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token',
                headers=[('Metadata-Flavor','Google')],limit=16384,deadline=deadline)
            if status!=200:
                raise RuntimeError('Private KYC metadata identity unavailable; no retry')
            token=json.loads(raw)['access_token']
            if type(token) is not str or not 1<=len(token)<=16384 or not token.isascii():
                raise ValueError('Bounded original workload identity token required')
            payload=None if body is None else json.dumps(body,separators=(',',':')).encode()
            headers=[('Authorization','Bearer '+token),('Content-Type','application/json')]
            status,_,raw=await _read(client,method,'https://secretmanager.googleapis.com/v1/'+path,
                headers=headers,body=payload,limit=65536,deadline=deadline)
            if not 200<=status<300:
                raise RuntimeError('Private KYC managed credential unavailable; no retry')
            return json.loads(raw)

    return _run(operation)


class ProviderTransport(httpx.BaseTransport):
    """Existing provider guard validates the exact request before this transport."""
    def handle_request(self,request):
        async def operation(deadline):
            async with httpx.AsyncClient(transport=_transport(),trust_env=False,follow_redirects=False) as client:
                return await _read(client,request.method,str(request.url),headers=list(request.headers.multi_items()),
                                   body=request.content,limit=2000000,deadline=deadline)

        status,headers,body=_run(operation)
        headers=[(key,value) for key,value in headers if key.lower() not in {'content-length','transfer-encoding'}]
        return httpx.Response(status,headers=headers,content=body,request=request)
