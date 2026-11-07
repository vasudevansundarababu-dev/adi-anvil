import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from test_private_storage import connection
from test_private_storage import lab as storage_lab

lab = storage_lab

TABLES = [
    "benchmark_receipt_tasks",
    "benchmark_qualifications",
    "benchmark_qualification_events",
    "benchmark_version_bindings",
    "benchmark_version_tasks",
    "benchmark_comparisons",
    "benchmark_comparison_groups",
    "benchmark_cells",
    "benchmark_cell_attempts",
    "benchmark_attempt_events",
    "benchmark_evaluator_calls",
    "benchmark_criterion_results",
    "benchmark_score_revisions",
    "benchmark_score_reviews",
    "benchmark_spend_bindings",
    "benchmark_capacity_claims",
    "benchmark_dispatch_intents",
    "benchmark_window_ownership",
]
DIGEST = hashlib.sha256(b"original-fictional-canonical-binding-test").hexdigest()


def test_all_typed_relations_have_project_rls_and_worker_has_no_grants():
    with connection() as c:
        for table in TABLES:
            row = c.execute(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",
                ("anvil." + table,),
            ).fetchone()
            assert row["relrowsecurity"] and row["relforcerowsecurity"]
            assert not c.execute(
                "SELECT has_table_privilege('anvil_worker',%s,'SELECT') AS allowed",
                ("anvil." + table,),
            ).fetchone()["allowed"]


def revision(c, lab, kind):
    resource, rev = str(uuid4()), str(uuid4())
    c.execute(
        "INSERT INTO anvil.resources(id,org_id,project_id,kind,created_by) VALUES(%s,%s,%s,%s,%s)",
        (resource, lab["org"], lab["project"], kind, lab["engineer"]),
    )
    c.execute(
        "INSERT INTO anvil.revisions(id,project_id,resource_id,revision,content,content_hash,created_by) VALUES(%s,%s,%s,1,%s,%s,%s)",
        (
            rev,
            lab["project"],
            resource,
            '{"mode":"original_synthetic_binding_test"}',
            DIGEST,
            lab["engineer"],
        ),
    )
    return rev


@pytest.fixture
def comparison(lab):
    ids = {"run": str(uuid4()), "subject": DIGEST}
    with connection() as c:
        for name, kind in [
            ("benchmark", "benchmark"),
            ("suite", "suite"),
            ("protocol", "protocol"),
            ("task", "task"),
        ]:
            ids[name] = revision(c, lab, kind)
        c.execute(
            "INSERT INTO anvil.benchmark_version_bindings(project_id,benchmark_revision_id,suite_revision_id,subject_sha256,scoring_policy_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
            (lab["project"], ids["benchmark"], ids["suite"], DIGEST, DIGEST, lab["engineer"]),
        )
        c.execute(
            "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by) VALUES(%s,%s,%s,'illustrative',%s)",
            (ids["run"], lab["project"], ids["protocol"], lab["engineer"]),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_comparisons(project_id,run_id,benchmark_revision_id,protocol_revision_id,subject_sha256,planned_cells,created_by) VALUES(%s,%s,%s,%s,%s,18,%s)",
            (
                lab["project"],
                ids["run"],
                ids["benchmark"],
                ids["protocol"],
                DIGEST,
                lab["engineer"],
            ),
        )
    return ids


def test_comparison_protocol_must_equal_canonical_run_protocol(lab, comparison):
    with connection() as c:
        other_protocol = revision(c, lab, "protocol")
        other_run = str(uuid4())
        c.execute(
            "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by) VALUES(%s,%s,%s,'illustrative',%s)",
            (other_run, lab["project"], comparison["protocol"], lab["engineer"]),
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connection() as c:
            c.execute(
                "INSERT INTO anvil.benchmark_comparisons(project_id,run_id,benchmark_revision_id,protocol_revision_id,subject_sha256,planned_cells,created_by) VALUES(%s,%s,%s,%s,%s,18,%s)",
                (
                    lab["project"],
                    other_run,
                    comparison["benchmark"],
                    other_protocol,
                    DIGEST,
                    lab["engineer"],
                ),
            )


def test_typed_revision_kind_is_checked(lab, comparison):
    with connection() as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "INSERT INTO anvil.benchmark_version_bindings(project_id,benchmark_revision_id,suite_revision_id,subject_sha256,scoring_policy_sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
                (
                    lab["project"],
                    comparison["task"],
                    comparison["suite"],
                    DIGEST,
                    DIGEST,
                    lab["engineer"],
                ),
            )


def test_spend_purposes_have_separate_exclusive_windows(lab, comparison):
    windows = [str(uuid4()), str(uuid4())]
    statement = "INSERT INTO anvil.benchmark_spend_bindings(project_id,run_id,purpose,window_id,cap_micro_usd,pricing_sha256,authority_sha256) VALUES(%s,%s,%s,%s,100,%s,%s)"
    with connection() as c:
        for window in windows:
            c.execute(
                "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,100,now()+interval '1 hour','active','original synthetic money mechanics only')",
                (window, lab["project"]),
            )
        c.execute(
            statement, (lab["project"], comparison["run"], "candidate", windows[0], DIGEST, DIGEST)
        )
        c.execute(
            statement, (lab["project"], comparison["run"], "judge", windows[1], DIGEST, DIGEST)
        )
    with pytest.raises((psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation)):
        with connection() as c:
            c.execute(
                statement, (lab["project"], comparison["run"], "judge", windows[0], DIGEST, DIGEST)
            )
    with connection("anvil_app", lab["other_project"], lab["outsider"]) as c:
        assert (
            c.execute(
                "SELECT * FROM anvil.benchmark_spend_bindings WHERE run_id=%s", (comparison["run"],)
            ).fetchall()
            == []
        )


def test_frozen_binding_cannot_update_even_for_owner(lab, comparison):
    with pytest.raises(psycopg.Error):
        with connection() as c:
            c.execute(
                "UPDATE anvil.benchmark_comparisons SET subject_sha256=%s WHERE project_id=%s AND run_id=%s",
                (hashlib.sha256(b"changed").hexdigest(), lab["project"], comparison["run"]),
            )
    with connection("anvil_app", lab["project"], lab["engineer"]) as c:
        assert (
            len(
                c.execute(
                    "SELECT * FROM anvil.benchmark_comparisons WHERE run_id=%s",
                    (comparison["run"],),
                ).fetchall()
            )
            == 1
        )


def test_score_revision_predecessor_cannot_cross_comparison(lab, comparison):
    sid = str(uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.benchmark_score_revisions(id,project_id,run_id,revision,projection_sha256,redacted_projection,created_by) VALUES(%s,%s,%s,1,%s,'{}',%s)",
            (sid, lab["project"], comparison["run"], DIGEST, lab["engineer"]),
        )
    second_run = str(uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by) VALUES(%s,%s,%s,'illustrative',%s)",
            (second_run, lab["project"], comparison["protocol"], lab["engineer"]),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_comparisons(project_id,run_id,benchmark_revision_id,protocol_revision_id,subject_sha256,planned_cells,created_by) VALUES(%s,%s,%s,%s,%s,18,%s)",
            (
                lab["project"],
                second_run,
                comparison["benchmark"],
                comparison["protocol"],
                DIGEST,
                lab["engineer"],
            ),
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with connection() as c:
            c.execute(
                "INSERT INTO anvil.benchmark_score_revisions(id,project_id,run_id,revision,predecessor_id,projection_sha256,redacted_projection,created_by) VALUES(%s,%s,%s,2,%s,%s,'{}',%s)",
                (str(uuid4()), lab["project"], second_run, sid, DIGEST, lab["engineer"]),
            )
    with connection("anvil_app", lab["other_project"], lab["outsider"]) as c:
        assert (
            c.execute(
                "SELECT * FROM anvil.benchmark_score_revisions WHERE id=%s", (sid,)
            ).fetchall()
            == []
        )
    with pytest.raises(psycopg.Error):
        with connection() as c:
            c.execute(
                "UPDATE anvil.benchmark_score_revisions SET redacted_projection='{\"fake_score\":100}' WHERE id=%s",
                (sid,),
            )


def test_benchmark_window_cannot_be_reused_by_legacy_budget(lab, comparison):
    window = str(uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,100,now()+interval '1 hour','active','fictional software-only ledger test')",
            (window, lab["project"]),
        )
        c.execute(
            "INSERT INTO anvil.benchmark_spend_bindings(project_id,run_id,purpose,window_id,cap_micro_usd,pricing_sha256,authority_sha256) VALUES(%s,%s,'candidate',%s,100,%s,%s)",
            (lab["project"], comparison["run"], window, DIGEST, DIGEST),
        )
    with connection() as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "INSERT INTO anvil.run_budgets(project_id,run_id,window_id,cap_micro_usd) VALUES(%s,%s,%s,100)",
                (lab["project"], comparison["run"], window),
            )


def test_spend_binding_cannot_claim_existing_legacy_window(lab, comparison):
    window = str(uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,100,now()+interval '1 hour','active','fictional software-only ledger test')",
            (window, lab["project"]),
        )
        c.execute(
            "INSERT INTO anvil.run_budgets(project_id,run_id,window_id,cap_micro_usd) VALUES(%s,%s,%s,100)",
            (lab["project"], comparison["run"], window),
        )
    with connection() as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(
                "INSERT INTO anvil.benchmark_spend_bindings(project_id,run_id,purpose,window_id,cap_micro_usd,pricing_sha256,authority_sha256) VALUES(%s,%s,'candidate',%s,100,%s,%s)",
                (lab["project"], comparison["run"], window, DIGEST, DIGEST),
            )


def test_concurrent_legacy_and_benchmark_window_claim_has_one_owner(lab, comparison):
    window = str(uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,100,now()+interval '1 hour','active','fictional concurrency only')",
            (window, lab["project"]),
        )
    barrier = threading.Barrier(2)

    def claim(category):
        try:
            with connection("anvil_app", lab["project"], lab["engineer"]) as c:
                barrier.wait(timeout=10)
                if category == "legacy":
                    c.execute(
                        "INSERT INTO anvil.run_budgets(project_id,run_id,window_id,cap_micro_usd) VALUES(%s,%s,%s,100)",
                        (lab["project"], comparison["run"], window),
                    )
                else:
                    c.execute(
                        "INSERT INTO anvil.benchmark_spend_bindings(project_id,run_id,purpose,window_id,cap_micro_usd,pricing_sha256,authority_sha256) VALUES(%s,%s,'candidate',%s,100,%s,%s)",
                        (lab["project"], comparison["run"], window, DIGEST, DIGEST),
                    )
            return category, "committed"
        except psycopg.errors.CheckViolation:
            return category, "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(claim, ["legacy", "benchmark"]))
    assert sorted(results.values()) == ["blocked", "committed"]
    with connection() as c:
        owner = c.execute(
            "SELECT category FROM anvil.benchmark_window_ownership WHERE project_id=%s AND window_id=%s",
            (lab["project"], window),
        ).fetchone()["category"]
        assert results[owner] == "committed"
