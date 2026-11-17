"""Separate container-operator network candidate; consistency, never admission.

Original independently retained Engine observations are inputs, not obtained
here. No DNS, socket, Engine command, namespace entry or container mutation.
Network agreement does not qualify source/mount isolation or broker authority.
"""

import hashlib
import ipaddress
import json
import math
import os
import re
from dataclasses import dataclass


def _pairs(rows):
    value = {}
    for key, item in rows:
        if key in value:
            raise ValueError('marketing_operator_duplicate_network_member')
        value[key] = item
    return value


def _document(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ValueError('marketing_operator_network_document_bound')
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    if type(value) is not dict:
        raise ValueError('marketing_operator_network_object_required')
    return value


def _hex(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


@dataclass(frozen=True, slots=True)
class ContainerOperatorNetworkCandidate:
    # Canonical candidate bytes only; never a qualified receipt or API input.
    canonical_bytes: bytes


def validate_container_operator_network(profile_raw, operator_raw, api_raw, network_raw):
    """Compare a NEW candidate with three original retained inspect documents.

    Caller must independently establish observation provenance/currentness and
    actual DNS/routing, exact installed code, mount secrecy and scoped authority.
    Even successful comparison does not create a dispatchable Docker recipe.
    """
    profile = _document(profile_raw, 8192)
    fields = {'schema_version', 'operator_container_id', 'api_container_id', 'network_id',
              'operator_image_id', 'operator_host_pid', 'network_namespace',
              'original_deadline_monotonic', 'original_cleanup_seconds', 'operator_inspect_sha256',
              'api_inspect_sha256', 'network_inspect_sha256'}
    if set(profile) != fields or profile['schema_version'] != 'anvil.marketing-container-operator-network-candidate.v1':
        raise ValueError('marketing_exact_container_operator_network_candidate_required')
    for key in ('operator_container_id', 'api_container_id', 'network_id',
                'operator_inspect_sha256', 'api_inspect_sha256', 'network_inspect_sha256'):
        if not _hex(profile[key]):
            raise ValueError('marketing_original_operator_network_identity_required')
    if (profile['operator_container_id'] == profile['api_container_id']
            or type(profile['operator_image_id']) is not str
            or not _hex(profile['operator_image_id'].removeprefix('sha256:'))
            or not profile['operator_image_id'].startswith('sha256:')
            or type(profile['operator_host_pid']) is not int or profile['operator_host_pid'] <= 0):
        raise ValueError('marketing_disjoint_original_operator_container_required')
    namespace = profile['network_namespace']
    if (type(namespace) is not dict or set(namespace) != {'device', 'inode'}
            or any(type(namespace[k]) is not int or namespace[k] <= 0 for k in namespace)):
        raise ValueError('marketing_actual_operator_network_namespace_required')
    cutoff = profile['original_deadline_monotonic']
    if type(cutoff) not in (int, float) or not math.isfinite(cutoff) or cutoff <= 0:
        raise ValueError('marketing_original_operator_network_cutoff_required')
    if (type(profile['original_cleanup_seconds']) is not int
            or not 1 <= profile['original_cleanup_seconds'] <= 600
            or cutoff <= profile['original_cleanup_seconds']):
        raise ValueError('marketing_original_operator_cleanup_reserve_required')
    documents = []
    for role, raw in (('operator', operator_raw), ('api', api_raw), ('network', network_raw)):
        if hashlib.sha256(raw).hexdigest() != profile[role + '_inspect_sha256']:
            raise ValueError('marketing_retained_operator_network_inspect_changed')
        documents.append(_document(raw, 1048576))
    operator, api, network = documents
    host = operator.get('HostConfig', {})
    if (operator.get('Id') != profile['operator_container_id']
            or operator.get('Image') != profile['operator_image_id']
            or operator.get('State', {}).get('Running') is not True
            or operator.get('State', {}).get('Pid') != profile['operator_host_pid']
            or host.get('NetworkMode') != profile['network_id']
            or host.get('PidMode') != 'host' or host.get('CgroupnsMode') != 'host'
            or host.get('ReadonlyRootfs') is not True or host.get('Privileged') is not False
            or host.get('PortBindings') or host.get('PublishAllPorts') is not False
            or host.get('ExtraHosts') or host.get('Dns') or host.get('DnsSearch') or host.get('DnsOptions')):
        raise ValueError('marketing_exact_private_operator_namespace_profile_required')
    if (api.get('Id') != profile['api_container_id'] or api.get('State', {}).get('Running') is not True
            or network.get('Id') != profile['network_id'] or network.get('Driver') != 'bridge'
            or network.get('Scope') != 'local' or network.get('Ingress') is not False):
        raise ValueError('marketing_existing_private_compose_network_required')
    for container, role in ((operator, 'operator'), (api, 'api')):
        endpoints = container.get('NetworkSettings', {}).get('Networks', {})
        matches = [item for item in endpoints.values() if item.get('NetworkID') == profile['network_id']]
        if len(matches) != 1 or (role == 'operator' and len(endpoints) != 1):
            raise ValueError('marketing_exact_original_operator_network_endpoint_required')
        endpoint = matches[0]
        if role == 'api' and 'api' not in (endpoint.get('Aliases') or []):
            raise ValueError('marketing_original_private_api_alias_required')
        address = ipaddress.IPv4Address(endpoint.get('IPAddress'))
        retained = network.get('Containers', {}).get(container['Id'], {})
        if (not endpoint.get('EndpointID') or retained.get('EndpointID') != endpoint['EndpointID']
                or ipaddress.IPv4Interface(retained.get('IPv4Address')).ip != address):
            raise ValueError('marketing_original_network_endpoint_custody_changed')
    canonical = json.dumps(profile, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return ContainerOperatorNetworkCandidate(canonical)


def require_current_operator_namespace(candidate, *, absolute_deadline):
    """Read only actual current PID/netns; no authority or network probe."""
    from time import monotonic

    if type(candidate) is not ContainerOperatorNetworkCandidate:
        raise ValueError('marketing_typed_operator_network_candidate_required')
    value = _document(candidate.canonical_bytes, 8192)
    if (type(absolute_deadline) not in (int, float) or not math.isfinite(absolute_deadline)
            or not monotonic() < absolute_deadline <= value['original_deadline_monotonic']
            or os.geteuid() != 0 or os.getpid() != value['operator_host_pid']):
        raise ValueError('marketing_original_operator_namespace_process_required')
    descriptor = os.open('/proc/self/ns/net', os.O_RDONLY | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if {'device': info.st_dev, 'inode': info.st_ino} != value['network_namespace']:
            raise ValueError('marketing_actual_operator_network_namespace_changed')
    finally:
        os.close(descriptor)
    if monotonic() >= absolute_deadline:
        raise TimeoutError('marketing_original_operator_network_deadline')


def container_operator_pair_candidate(runtime_raw, original_deadline, network_candidate):
    """Separate gated compatibility entry; no existing launcher is switched.

    Full independently qualified mount/capability/source/layout and activation
    gates remain prerequisites. This function supplies none of them.
    """
    from anvil.marketing_native_boundary import marketing_native_gate
    from anvil.marketing_native_private_pair import _OriginalPrivatePair

    marketing_native_gate()
    require_current_operator_namespace(network_candidate, absolute_deadline=original_deadline)
    profile = _document(network_candidate.canonical_bytes, 8192)
    return _OriginalPrivatePair(runtime_raw, original_deadline,
        original_cleanup_seconds=profile['original_cleanup_seconds'])
