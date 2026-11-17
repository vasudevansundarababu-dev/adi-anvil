"""Private synchronous KYC routes; ordinary broker routes remain unchanged."""

from time import monotonic

from fastapi import APIRouter, HTTPException

from anvil.golden_kyc_deadline_database import transaction as bounded_transaction
from anvil.golden_kyc_dispatch_scope import activate
from anvil.marketing_native_wire_bounds import remaining
from anvil.worker_dispatch_broker import DispatchRequest, NativeFinish

VERIFY_SQL="""
SELECT p.config,b.started_at,b.deadline_at,j.lease_until,statement_timestamp() AS observed_at
FROM anvil.jobs j JOIN anvil.harbor_checks h ON h.id=j.target_id AND h.project_id=j.project_id
JOIN anvil.harbor_agent_plans p ON p.id=h.agent_plan_id AND p.project_id=h.project_id
JOIN banking.paid_episode_bounds b ON b.project_id=j.project_id AND b.job_id=j.id AND b.plan_id=p.id
WHERE j.project_id=%s AND j.id=%s AND j.lease_token=%s AND j.status='leased'
 AND j.lease_until>statement_timestamp() AND j.kind='benchmark_golden_paid'
 AND p.id=%s AND p.created_by=%s AND h.created_by=%s AND p.state='launched'
 AND p.config->>'golden_kyc_paid'='true' AND coalesce(p.config->>'marketing_paid','false')<>'true'
 AND b.actor_id=p.created_by AND b.plan_subject_sha256=p.subject_hash
 AND b.lease_sha256=encode(sha256(convert_to(j.lease_token::text,'UTF8')),'hex')
 AND b.deadline_at>statement_timestamp()
"""


def verified_deadline(claim,*,started):
    """Read actual leased-job authority before activating private routing context."""
    deadline=started+claim.remaining_seconds
    remaining(deadline)
    before=monotonic()
    with bounded_transaction(claim.project_id,claim.actor_id,absolute_deadline=deadline) as connection:
        row=connection.execute(VERIFY_SQL,(claim.project_id,claim.job_id,claim.lease_token,
            claim.plan_id,claim.actor_id,claim.actor_id)).fetchone()
        if not row:
            raise RuntimeError('Actual current KYC lease required')
        seconds=row['config'].get('episode_timeout_seconds')
        if type(seconds) is not int or not 1<=seconds<=600:
            raise ValueError('Actual frozen KYC episode bound required')
        deadline=min(deadline,started+seconds,before+(row['lease_until']-row['observed_at']).total_seconds())
        deadline=min(deadline,before+(row['deadline_at']-row['observed_at']).total_seconds())
        connection.tighten_deadline(deadline)
        remaining(deadline)
    remaining(deadline)
    return deadline


def routes(gate):
    router=APIRouter(prefix='/kyc')

    def run(claim,operation):
        started=monotonic()
        gate()
        from anvil import pilot_environment

        if pilot_environment.current()!='qa':
            raise HTTPException(404,'Private KYC runtime is QA only')
        try:
            deadline=verified_deadline(claim,started=started)
            with activate(claim.project_id,claim.actor_id,claim.job_id,claim.plan_id,absolute_deadline=deadline):
                if operation=='prepare':
                    from anvil.golden_kyc_paid_execution import prepare

                    value=prepare(claim)
                    remaining(deadline)
                    return value
                if operation=='finish':
                    from anvil.golden_kyc_paid_execution import finish

                    value=finish(claim)
                    remaining(deadline)
                    return value
                if operation=='readiness':
                    from anvil import workspace_execution
                    from anvil.db import transaction
                    from anvil.harbor_agents import plan
                    from anvil.worker_dispatch_broker import authorize

                    with transaction(claim.project_id,claim.actor_id) as connection:
                        authorize(connection,claim)
                        if not workspace_execution.plan_readiness(connection,plan(connection,claim.plan_id))['ready']:
                            raise RuntimeError('KYC readiness revoked')
                    remaining(deadline)
                    return {'ready':True}
                from anvil.workspace_execution import decision

                text=decision(claim.project_id,claim.actor_id,claim.plan_id,claim.stage_index,
                              remaining_seconds=claim.remaining_seconds,broker_claim=claim)
                remaining(deadline)
                return {'output':text}
        except Exception:
            raise HTTPException(409,'KYC operation denied or outcome unknown; do not retry') from None

    @router.post('/prepare')
    def prepare(body: DispatchRequest):
        return run(body,'prepare')

    @router.post('/readiness')
    def readiness(body: DispatchRequest):
        return run(body,'readiness')

    @router.post('/dispatch')
    def dispatch(body: DispatchRequest):
        return run(body,'dispatch')

    @router.post('/finish')
    def finish(body: NativeFinish):
        return run(body,'finish')

    return router
