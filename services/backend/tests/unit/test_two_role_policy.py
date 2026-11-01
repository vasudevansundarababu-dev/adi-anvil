import pytest
from fastapi import HTTPException

from anvil.auth import require
from anvil.invitations import validate


def test_admin_includes_engineering_and_engineer_cannot_authorize_budget_or_keys():
    for permission in (
        "admin",
        "product-owner",
        "sales",
        "researcher",
        "data-engineer",
        "reviewer",
    ):
        require({"admin"}, permission)
    for permission in ("researcher", "data-engineer", "advisor", "reviewer"):
        require({"rl-engineer"}, permission)
    for permission in ("admin", "product-owner", "sales"):
        with pytest.raises(HTTPException) as error:
            require({"rl-engineer"}, permission)
        assert error.value.status_code == 403
    for historical_role in ("product-owner", "data-engineer", "researcher", "sales"):
        with pytest.raises(HTTPException):
            require({historical_role}, historical_role)


def test_only_one_of_the_two_current_roles_can_be_invited():
    for role in ("admin", "rl-engineer"):
        validate("contract.user", "contract@example.test", [role], [])
    for roles in (["product-owner"], ["researcher"], ["admin", "rl-engineer"]):
        with pytest.raises(ValueError):
            validate("contract.user", "contract@example.test", roles, [])


def test_run_author_cannot_read_or_grade_their_own_independent_review():
    from anvil.evaluation import assigned_grader, grading_position

    protocol = {"reviewer_ids": ["author"], "adjudicator_id": "author"}
    run = {"created_by": "author"}
    assert not assigned_grader(None, "project", protocol, {}, run, "author")
    assert grading_position(None, "project", protocol, {}, run, "author") is None
