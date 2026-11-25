"""G1 (KYC Judgment v1 C4): what the agent reads.
- S4 shows only the policy library in force (document, version, title): never a list of rules, never the private
  expectedRules or notes, even if an export carried them into the actor part.
- S5 `decisionRights` is a table, not a JSON line.
- The template's output schema (rules_applied, assessments, notices_considered, the audit trail and the officer flag
  when the template has them) is rendered as "Output fields", from the activation; a template without one (v8) gets
  exactly today's text and hash."""

import inspect
from pathlib import Path

from anvil.rlgym.runs import instructions

V8 = {
    "sections": {
        "S1": {"title": "KYC onboarding", "scope": "US bank"},
        "S4": {
            "statePolicies": [
                {
                    "ruleId": "KYC-01",
                    "locator": "doc#1",
                    "ruleVersion": 1,
                    "contentSha256": "a" * 64,
                }
            ]
        },
        "S5": {"steps": [{"action": "Read the application", "tool": "application.read"}]},
        "S6": {"outputContract": "One recommendation."},
    }
}
JUDGMENT = {
    "sections": {
        "S1": {"title": "Joint account onboarding"},
        "S4": {
            "policyLibrary": [
                {
                    "documentId": "doc-fed-cip",
                    "documentVersion": 3,
                    "title": "Customer identification program",
                },
                {"documentId": "doc-ca", "documentVersion": 1, "title": "California rules"},
            ],
            "expectedRules": [{"ruleId": "R-SECRET", "ruleVersion": 2, "textSha256": "b" * 64}],
            "notes": "private SME note",
        },
        "S5": {
            "steps": [{"action": "Read the application", "tool": "application.read"}],
            "decisionRights": [
                {
                    "action": "Approve the account",
                    "whoMay": "case_lead",
                    "needsApprovalFrom": "",
                    "escalateTo": "",
                },
                {
                    "action": "Refer to a specialist",
                    "whoMay": "agent",
                    "needsApprovalFrom": "",
                    "escalateTo": "specialist",
                },
            ],
        },
        "S6": {"outputContract": "Return the JSON output described below."},
    }
}
SCHEMA = {
    "type": "object",
    "required": [
        "recommendation",
        "rules_applied",
        "assessments",
        "notices_considered",
        "rationale",
        "audit_trail",
        "officer_verification",
    ],
    "properties": {
        "recommendation": {
            "type": "string",
            "enum": ["ready_for_approval", "request_information", "specialist_review"],
        },
        "rules_applied": {
            "type": "array",
            "description": "Every rule you relied on, in the version in force when you decided.",
            "items": {
                "type": "object",
                "required": ["rule_id", "version"],
                "properties": {
                    "rule_id": {"type": "string"},
                    "version": {"type": "integer"},
                    "governs": {"type": "boolean"},
                },
            },
        },
        "assessments": {
            "type": "array",
            "description": "One per party.",
            "items": {
                "type": "object",
                "required": ["party_id", "outcome"],
                "properties": {
                    "party_id": {"type": "string"},
                    "outcome": {
                        "type": "string",
                        "enum": ["clear", "request_information", "specialist_review"],
                    },
                },
            },
        },
        "notices_considered": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
        "audit_trail": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["sop_step", "data_seen"],
                "properties": {"sop_step": {"type": "integer"}, "data_seen": {"type": "array"}},
            },
        },
        "officer_verification": {
            "type": "boolean",
            "description": "Flag the account for officer verification.",
        },
    },
}


def test_a_v8_task_renders_exactly_as_before():
    a = instructions.build(V8)
    b = instructions.build(V8, None, output_schema=None)
    assert a == b
    assert "Rule KYC-01 (doc#1, version 1" in a["text"] and "Output fields" not in a["text"]


def test_s4_shows_only_the_policy_library():
    text = instructions.build(JUDGMENT)["text"]
    assert "Customer identification program (document doc-fed-cip, version 3)" in text
    assert "California rules (document doc-ca, version 1)" in text
    for secret in ("R-SECRET", "expectedRules", "private SME note", "b" * 64):
        assert secret not in text


def test_decision_rights_render_as_a_table():
    text = instructions.build(JUDGMENT)["text"]
    assert "| Action | Who may | Needs approval from | Escalate to |" in text
    assert "| Approve the account | case_lead | — | — |" in text
    assert "| Refer to a specialist | agent | — | specialist |" in text
    assert "decisionRights:" not in text


def test_the_output_fields_come_from_the_template_schema():
    text = instructions.build(JUDGMENT, None, output_schema=SCHEMA)["text"]
    part = text.split("## Output fields", 1)[1]
    assert (
        "- recommendation (required): one of ready_for_approval, request_information, specialist_review"
        in part
    )
    assert "- rules_applied (required, a list): Every rule you relied on" in part
    assert "each with: rule_id (required), version (required), governs" in part
    assert "- audit_trail (required, a list)" in part
    assert (
        "- officer_verification (required, true or false): Flag the account for officer verification."
        in part
    )
    assert (
        instructions.build(JUDGMENT, None, output_schema=SCHEMA)["sha256"]
        != instructions.build(JUDGMENT)["sha256"]
    )


def test_the_schema_is_frozen_in_the_manifest_and_used_by_admission_and_the_worker():
    from anvil.rlgym.runs import service, worker

    assert "output_schema=" in inspect.getsource(service.admission_check)
    assert '(m.get("template") or {}).get("output_schema")' in inspect.getsource(worker)
    assert '"output_schema"' in inspect.getsource(service._manifest)


def test_activation_keeps_the_output_schema_and_each_criterion_skill():
    from anvil.rlgym.catalog import templates

    src = inspect.getsource(templates.activate)
    assert "output_schema" in src and 'cr.get("skill")' in src
    sql = (
        Path(__file__).resolve().parents[2] / "migrations/068_rlgym_template_skills_output.sql"
    ).read_text()
    assert "ADD COLUMN output_schema jsonb" in sql and "ADD COLUMN skill text" in sql
    for s in ("tool_calling", "instruction_following", "reasoning", "decisioning", "safety"):
        assert s in sql
