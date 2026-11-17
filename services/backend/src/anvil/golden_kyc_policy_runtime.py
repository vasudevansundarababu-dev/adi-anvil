"""Operational bounded KYC reads for synchronous API/scheduler callers.

The caller supplies its original cutoff. One event loop and one scoped read-only
connection cover source, registry and materialization reads plus cancellation and
closure. No thread bridge, new time allowance, reconnect or retry exists.
"""

import asyncio

from anvil.golden_kyc_application_policy import load_public_application
from anvil.golden_kyc_product_policy import public_policy
from anvil.kyc_registry_database import transaction
from anvil.marketing_native_wire_bounds import remaining


def _run(operation, *args, absolute_deadline):
    remaining(absolute_deadline)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Use the awaited KYC operation on an async caller; no thread fallback")
    result = asyncio.run(operation(*args, absolute_deadline=absolute_deadline))
    remaining(absolute_deadline)
    return result


async def application_async(scope, user, application_id, *, absolute_deadline):
    async with transaction(scope.project_id, user, absolute_deadline=absolute_deadline) as connection:
        result, delivery = await load_public_application(connection, scope, application_id, absolute_deadline=absolute_deadline)
        if delivery.requirement or not delivery.public:
            raise ValueError(delivery.requirement or "AV_KYC_EXACT_POLICY_TEXT_PROVISIONING_REQUIRED")
        return result, delivery


def application(scope, user, application_id, *, absolute_deadline):
    return _run(application_async, scope, user, application_id, absolute_deadline=absolute_deadline)


async def trial_async(project, user, trial_id, generation, governing_state, *, absolute_deadline):
    async with transaction(project, user, absolute_deadline=absolute_deadline,
                           setting_name="ANVIL_GOLDEN_SCHEDULER_DATABASE_URL") as connection:
        remaining(absolute_deadline)
        row = await (await connection.execute("SELECT banking.product_policy_trial_mode(%s,%s) AS value", (trial_id,generation))).fetchone()
        remaining(absolute_deadline)
        if not row or row["value"] != "reusable_application_workflow":
            return False, None
        public = await public_policy(connection, project, trial_id, generation, governing_state, absolute_deadline=absolute_deadline)
        remaining(absolute_deadline)
        return True, public


def trial(project, user, trial_id, generation, governing_state, *, absolute_deadline):
    return _run(trial_async, project, user, trial_id, generation, governing_state, absolute_deadline=absolute_deadline)
