"""Explicit private v4: complete original reports and pinned alternatives.

Compressed source bytes avoid duplicating all parsed private outcome books in
the persisted definition. All existing outer source-size/node bounds remain.
"""

from copy import deepcopy
from typing import Literal

from pydantic import model_validator

from anvil.dataset_export_contract import Sha
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_calendar import propose as propose_calendar
from anvil.marketing_world_finance import FILES, normalize
from anvil.marketing_world_finance_transition import validate_transition
from anvil.marketing_world_financial_records import records as financial_records
from anvil.marketing_world_outcome_data import ALTERNATIVE_FILES, BASE_FILES, compile_reports
from anvil.marketing_world_service_definition import ServiceWorldDefinition
from anvil.marketing_world_source_encoding import decode, encode
from anvil.praxis_generic_contract import canonical, digest


def paths(case):
    return {f"cases/{case}/{name}" for name in BASE_FILES} | {
        f"reviewer_only/us-pair/{case}/reuse-test-{branch}/{name}"
        for branch in ("positive", "null", "negative")
        for name in (*ALTERNATIVE_FILES, *FILES, "reservation_lifecycle.json")}


def decode_sources(case, values):
    if type(values) is not dict or set(values) != paths(case):
        raise ValueError("Exact bounded activation source set required")
    files = {}
    size = 0
    for path, value in values.items():
        files[path] = decode(value)
        size += len(files[path])
        if size > 16777216:
            raise ValueError("Decoded activation source total exceeds existing definition ceiling")
    return files


def baseline_records(case, program, pins):
    for public in program["baseline"]:
        index = int(public["report_detail"]) * 2 + int(public["report_grain"] == "weekly")
        path = f"cases/{case}/{BASE_FILES[index]}"
        yield {"source_path": path, "source_sha256": pins[path], "released_at": public["released_at"],
               "outcome_binding": None, "public": deepcopy(public)}


class ActivationWorldDefinition(ServiceWorldDefinition):
    schema_version: Literal["anvil.marketing-private-world-definition.v4"]
    finance_source_documents: dict[str, str]
    finance_book_sha256: Sha
    activation_source_documents: dict[str, str]

    def expected_observation_start(self, program):
        return timestamp(program["episode_observation_start"])

    @property
    def finance_book(self):
        if set(self.finance_source_documents) != {f"cases/{self.case_id}/{name}" for name in FILES}:
            raise ValueError("Exact original parent-finance source set required")
        book = normalize(self.case_id, {path: raw.encode("utf-8") for path, raw in self.finance_source_documents.items()}, self.source_hashes)
        if digest(book) != self.finance_book_sha256:
            raise ValueError("Original finance book differs from pinned bytes")
        return book

    @model_validator(mode="after")
    def exact_activation(self):
        files = decode_sources(self.case_id, self.activation_source_documents)
        finance = self.finance_book
        issued = timestamp(self.service_contract["conditional_campaign_approval_sources"]["positive"]["issued_at_if_selected"])
        first_order = timestamp(self.service_contract["case"]["experiment_proposal_contract"]["start"] + "T00:00:00Z")
        if not any(issued <= window.instant < first_order for window in self.windows):
            raise ValueError("No observation window permits non-retroactive conditional campaign authority")
        program = propose_calendar(self.case_id, files, self.source_hashes, self.service_contract)
        if (self.start != self.expected_observation_start(program)
                or [window.instant for window in self.windows] != [timestamp(row["instant"]) for row in program["windows"]]):
            raise ValueError("Source report-review clocks must match the explicit twelve-observation operator program")
        baseline = None
        for branch in ("positive", "null", "negative"):
            selected = normalize(self.case_id, files, self.source_hashes, branch=branch)
            validate_transition(finance, selected)
            program = compile_reports(self.case_id, files, self.source_hashes, branch=branch)
            if baseline is not None and canonical(program["baseline"]) != canonical(baseline):
                raise ValueError("Private outcomes disagree on original public reports")
            baseline = program["baseline"]
        expected = list(baseline_records(self.case_id, program, self.source_hashes))
        observed = [row.model_dump(mode="json") for row in self.records["reports"]]
        # Timestamps are normalized by the outer model; compare parsed rows.
        from anvil.marketing_world_definition import PublicFixture

        expected = [PublicFixture.model_validate(row).model_dump(mode="json") for row in expected]
        if canonical(sorted(observed, key=lambda r: r["public"]["id"])) != canonical(sorted(expected, key=lambda r: r["public"]["id"])):
            raise ValueError("Actual initial reports differ from complete pinned baseline")
        expected_finance = {}
        for collection, path, public in financial_records(self.finance_source_documents, f"cases/{self.case_id}"):
            row = {"source_path": path, "source_sha256": self.source_hashes[path], "released_at": public["released_at"],
                   "outcome_binding": None, "public": public}
            expected_finance.setdefault(collection, []).append(PublicFixture.model_validate(row).model_dump(mode="json"))
        for collection, rows in expected_finance.items():
            actual = [row.model_dump(mode="json") for row in self.records[collection]]
            if canonical(sorted(actual, key=lambda r: r["public"]["id"])) != canonical(sorted(rows, key=lambda r: r["public"]["id"])):
                raise ValueError("Actual initial finance differs from complete pinned baseline")
        return self

    def selected_programs(self, branch):
        """Private API only; caller selects the original controller's branch."""
        files = decode_sources(self.case_id, self.activation_source_documents)
        return (normalize(self.case_id, files, self.source_hashes, branch=branch),
                compile_reports(self.case_id, files, self.source_hashes, branch=branch))


def with_activation(world, files):
    """Source preparation only; no persistence, activation or qualification."""
    if type(world) is not dict or world.get("schema_version") != "anvil.marketing-private-world-definition.v3":
        raise ValueError("Explicit private funding-world v3 required")
    value = deepcopy(world)
    # Keep the independent original byte/hash binding; do not duplicate the
    # large derived book alongside the complete public report projection.
    value.pop("finance_book")
    program = compile_reports(value["case_id"], files, value["source_hashes"], branch="positive")
    value["records"]["reports"] = list(baseline_records(value["case_id"], program, value["source_hashes"]))
    value["public_columns"]["reports"] = sorted({k for row in program["baseline"] for k in row})
    for collection in ("ledger", "budget-snapshots", "budget-envelopes"):
        value["records"][collection] = []
    for collection, path, public in financial_records(value["finance_source_documents"], f"cases/{value['case_id']}"):
        value["records"][collection].append({"source_path": path, "source_sha256": value["source_hashes"][path],
                                              "released_at": public["released_at"], "outcome_binding": None, "public": public})
        value["public_columns"][collection] = sorted(set(value["public_columns"][collection]) | set(public))
    value.update(schema_version="anvil.marketing-private-world-definition.v4",
                 activation_source_documents={path: encode(files[path]) for path in sorted(paths(value["case_id"]))})
    return value
