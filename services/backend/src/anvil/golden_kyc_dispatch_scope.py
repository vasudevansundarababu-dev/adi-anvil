"""Pure private-server KYC cutoff holder; never authentication or Run authority.

Only the dedicated server route activates this after actual leased-job verification.
No configuration, files, database, DNS, credential or environment access occurs.
"""

import math
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

_scope = ContextVar("anvil_private_kyc_dispatch_scope",default=None)


@dataclass(frozen=True,slots=True)
class Scope:
    project_id: str
    user_id: str
    job_id: str
    plan_id: str
    absolute_deadline: float


def current():
    return _scope.get()


@contextmanager
def activate(project,user,job,plan,*,absolute_deadline):
    if type(absolute_deadline) not in (int,float) or not math.isfinite(absolute_deadline):
        raise ValueError("Original private KYC absolute cutoff required")
    values=tuple(str(UUID(str(value))) for value in (project,user,job,plan))
    parent=current()
    if parent is not None:
        if values!=(parent.project_id,parent.user_id,parent.job_id,parent.plan_id):
            raise ValueError("Private KYC scope cannot change identity")
        absolute_deadline=min(parent.absolute_deadline,absolute_deadline)
    if monotonic()>=absolute_deadline:
        raise TimeoutError("Original private KYC cutoff elapsed")
    value=Scope(*values,absolute_deadline)
    token=_scope.set(value)
    try:
        yield value
    finally:
        _scope.reset(token)
