"""Trusted non-HTTP worker flag predicate; never API admission or activation."""

import os


def trusted_worker_live_enabled():
    environment = os.environ.get('ANVIL_ENV')
    if environment == 'cloud':
        name = 'ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED'
    elif environment == 'local':
        name = 'ANVIL_LIVE_PROVIDERS_ENABLED'
    else:
        return False
    return os.environ.get(name) == 'true'
