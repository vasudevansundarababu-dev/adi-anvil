"""Private derived facts for a future application-type execution variant.

Existing dataset/snapshot identities remain unchanged. This module neither
widens legacy state selectors nor registers an export/template/capability. A
type match is not task review, policy applicability, qualification or run authority.
"""

from dataclasses import dataclass, field

from anvil.campaign_semantic_contract import bounded_json
from anvil.db import digest as banking_digest
from anvil.golden_kyc_data import PRODUCTS
from anvil.praxis_case_dataset import CaseDataset, content_hash
from anvil.praxis_generic_contract import canonical
from anvil.project_input_contract import MAX_BYTES, actor_json


@dataclass(frozen=True, slots=True)
class TypeRow:
    application_id: str
    application_sha256: str
    governing_state: str
    product: str | None
    blocked_reason: str | None


@dataclass(frozen=True, slots=True)
class TypeIndex:
    canonical_body: bytes = field(repr=False)
    sha256: str
    rows: tuple[TypeRow, ...]

    def matching(self, product):
        """Facts only; caller must still prove a reviewed applicable workflow."""
        if product not in PRODUCTS:
            raise ValueError("Supported workflow application type required")
        return tuple(row for row in self.rows if row.product == product and row.blocked_reason is None)


def derive(dataset, reference, snapshots):
    """Join every immutable member to its actual original snapshot once.

    snapshots is the private Anvil source iterator, not caller-provided routing
    hints or a coverage matrix. Raw applicant facts/expectations are not returned.
    """
    if type(dataset) is not CaseDataset or reference != dataset.reference():
        raise ValueError("Exact original dataset identity/version/hash/count required")
    expected = {member.id: member for member in dataset.cases}
    seen, rows, size = set(), [], 0
    for source in snapshots:
        if (len(seen) >= dataset.case_count or type(source) is not dict
                or not {"id", "snapshot", "snapshot_sha256"} <= set(source)
                or type(source["id"]) is not str or source["id"] not in expected
                or source["id"] in seen):
            raise ValueError("Complete unique original snapshot membership required")
        member, snapshot = expected[source["id"]], source["snapshot"]
        size += bounded_json(snapshot, MAX_BYTES, max_nodes=100000, max_depth=8)
        if size > MAX_BYTES:
            raise ValueError("Existing actor-input population byte bound exceeded; no truncation")
        actor_json(snapshot)
        if (type(snapshot) is not dict or snapshot.get("id") != source["id"]
                or source["snapshot_sha256"] != member.snapshot_sha256
                or banking_digest(snapshot) != member.snapshot_sha256
                or snapshot.get("governing_state") != member.governing_state):
            raise ValueError("Original member snapshot/hash/state changed")
        product = snapshot.get("product")
        supported = type(product) is str and product in PRODUCTS
        rows.append(TypeRow(member.id, member.snapshot_sha256, member.governing_state,
                            product if supported else None,
                            None if supported else "unsupported_or_missing_application_type"))
        seen.add(member.id)
    if seen != set(expected):
        raise ValueError("Missing original application rows; no partial index")
    rows.sort(key=lambda row: row.application_id)
    counts = {product: sum(row.product == product for row in rows) for product in PRODUCTS}
    blocked = sum(row.blocked_reason is not None for row in rows)
    if sum(counts.values()) + blocked != dataset.case_count:
        raise ValueError("Every input row must be indexed or explicitly blocked")
    body = {"schema_version": "anvil.private-kyc-case-type-index.v1",
            "case_dataset": reference.model_dump(), "input_count": dataset.case_count,
            "supported_type_counts": counts, "blocked_type_count": blocked,
            "rows": [{"application_id": row.application_id, "application_sha256": row.application_sha256,
                      "governing_state": row.governing_state, "product": row.product,
                      "blocked_reason": row.blocked_reason} for row in rows],
            "run_authority": "not_granted", "runtime_qualified": False, "policy_qualified": False}
    bounded_json(body, MAX_BYTES, max_nodes=150512, max_depth=8)
    return TypeIndex(canonical(body), content_hash(body), tuple(rows))
