from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from anvil.schemas import Rights


def test_rights_scope_and_expiry_are_explicit():
    body = {
        "operation": "managed_evaluation",
        "destination": "local_fixture",
        "status": "approved",
        "evidence": "Synthetic independent rights evidence for local testing.",
    }
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    assert Rights.model_validate({**body, "expires_at": expires}).expires_at == expires
    for mutation in [
        {"destination": "internal_fixture"},
        {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
        {"expires_at": "2027-01-01T12:00:00"},
    ]:
        with pytest.raises(ValidationError):
            Rights.model_validate({**body, **mutation})
