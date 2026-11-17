"""Fixed existing public worker settings; no secrets or activation defaults."""

import os

ISOLATED_BASE_ENV = {
    'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/nonexistent',
    # A virtual directory cannot acquire a .env entry. Pure worker imports
    # must not accidentally load credentials from an application checkout.
    'ANVIL_ROOT': '/proc/self/fd',
}
PUBLIC_CONTROL_SETTINGS = (
    'ANVIL_ENV', 'ANVIL_PILOT_ENVIRONMENT', 'ANVIL_CREDENTIAL_STORE_PROFILE',
    'WEB_ORIGIN', 'OIDC_ISSUER', 'ANVIL_WORKER_BROKER_ROLE', 'ANVIL_WORKER_BROKER_ENABLED',
    'ANVIL_WORKER_BROKER_URL', 'ANVIL_MARKETING_WORLD_ENABLED', 'ANVIL_MARKETING_WORLD_STOP_ENABLED',
    'ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED', 'ANVIL_LIVE_PROVIDERS_ENABLED', 'ANVIL_REAL_EMAIL_ENABLED',
)
_EXACT = {
    'ANVIL_ENV': 'cloud', 'ANVIL_PILOT_ENVIRONMENT': 'qa', 'ANVIL_CREDENTIAL_STORE_PROFILE': 'qa-v1',
    'WEB_ORIGIN': 'https://anvil-qa.adi-labs.ai',
    'OIDC_ISSUER': 'https://anvil-qa-auth.adi-labs.ai/realms/anvil-qa',
    'ANVIL_WORKER_BROKER_ROLE': 'worker',
    'ANVIL_WORKER_BROKER_URL': 'http://api:8200/internal/v1/worker-dispatch',
    'ANVIL_LIVE_PROVIDERS_ENABLED': 'false', 'ANVIL_REAL_EMAIL_ENABLED': 'false',
}


def current_control_environment():
    """Copy existing values only. Missing/false remains missing/false."""
    result = dict(ISOLATED_BASE_ENV)
    for name in PUBLIC_CONTROL_SETTINGS:
        value = os.environ.get(name)
        if value is None:
            continue
        if type(value) is not str or (value != _EXACT[name] if name in _EXACT else value not in {'false', 'true'}):
            raise ValueError('marketing_private_original_public_worker_setting_required')
        result[name] = value
    return result
