"""Fixed original job value codec; no pickle, class loading or world transfer."""

import math
from datetime import datetime
from uuid import UUID


def _encode(value, depth):
    if depth > 16:
        raise ValueError('marketing_original_job_packet_depth')
    if value is None or type(value) in (str, bool, int):
        return {'kind': 'scalar', 'value': value}
    if type(value) is float and math.isfinite(value):
        return {'kind': 'float', 'value': value.hex()}
    if type(value) is UUID:
        return {'kind': 'uuid', 'value': str(value)}
    if type(value) is datetime and value.tzinfo is not None:
        return {'kind': 'datetime', 'value': value.isoformat()}
    if type(value) is list:
        return {'kind': 'array', 'value': [_encode(v, depth + 1) for v in value]}
    if type(value) is dict and all(type(k) is str for k in value):
        return {'kind': 'object', 'value': [[k, _encode(value[k], depth + 1)] for k in sorted(value)]}
    raise ValueError('marketing_original_job_packet_type_not_supported')


def _decode(node, depth):
    if depth > 16 or type(node) is not dict or set(node) != {'kind', 'value'}:
        raise ValueError('marketing_original_job_packet_node_required')
    kind, value = node['kind'], node['value']
    if kind == 'scalar' and (value is None or type(value) in (str, bool, int)):
        return value
    if kind == 'float' and type(value) is str:
        number = float.fromhex(value)
        if math.isfinite(number) and number.hex() == value:
            return number
    if kind == 'uuid' and type(value) is str and str(UUID(value)) == value:
        return UUID(value)
    if kind == 'datetime' and type(value) is str:
        result = datetime.fromisoformat(value)
        if result.tzinfo is not None and result.isoformat() == value:
            return result
    if kind == 'array' and type(value) is list:
        return [_decode(v, depth + 1) for v in value]
    if kind == 'object' and type(value) is list:
        result = {}
        for row in value:
            if type(row) is not list or len(row) != 2 or type(row[0]) is not str or row[0] in result:
                raise ValueError('marketing_original_job_packet_exact_object_required')
            result[row[0]] = _decode(row[1], depth + 1)
        if list(result) != sorted(result):
            raise ValueError('marketing_original_job_packet_order_required')
        return result
    raise ValueError('marketing_original_job_packet_fixed_type_required')


def encode_original_job(job):
    if type(job) is not dict:
        raise ValueError('marketing_original_job_dictionary_required')
    value = _encode(job, 0)
    # Round-trip compares every original field, including UUID/datetime values.
    if _decode(value, 0) != job:
        raise ValueError('marketing_original_job_packet_value_changed')
    return value


def decode_original_job(value):
    job = _decode(value, 0)
    if type(job) is not dict or _encode(job, 0) != value:
        raise ValueError('marketing_original_job_packet_round_trip_required')
    return job
