"""Versioned, materialized reference worlds. All records are explicitly fictional.

These are environment fixtures, never replacements for published Praxis Tasks or law.
No generator/model/provider is contacted. Decimal values are serialized as strings.
"""

import base64
import copy
import hashlib
import json
import struct
import zlib
from decimal import Decimal

from anvil.db import digest

VERSION = "1"
CLOCK = "2026-01-15T12:00:00Z"
CATALOG = {
    "BOD-FIN": {
        "name": "Bodhium financial statements",
        "scenarios": ["comparable", "unit_mismatch", "missing_line", "restated", "reconcile"],
        "collections": [
            "companies",
            "reporting_periods",
            "financial_statement_lines",
            "source_documents",
            "saved_analysis",
        ],
        "tools": [
            "list_records",
            "read_file",
            "query_statements",
            "calculate_financial",
            "save_analysis",
        ],
        "source_binding": "Actual Bodhium financial case studies pending; marketing data is not financial data",
    },
    "MKT-PHONE": {
        "name": "Phone launch campaign",
        "scenarios": [
            "compliant",
            "unsupported_claim",
            "missing_approval",
            "budget_overrun",
            "channel_unavailable",
        ],
        "collections": [
            "products",
            "audiences",
            "channels",
            "campaigns",
            "allocations",
            "approvals",
            "placements",
        ],
        "tools": [
            "list_records",
            "read_file",
            "create_campaign",
            "allocate_budget",
            "request_approval",
            "schedule_placement",
        ],
        "source_binding": "Actual product brief, marketing Task and reviewed rules pending",
    },
    "MKT-LOCALE": {
        "name": "Creative and locale compliance",
        "scenarios": [
            "complete",
            "missing_variant",
            "missing_disclosure",
            "invalid_size",
            "ambiguous_translation",
        ],
        "collections": [
            "bundles",
            "channel_specs",
            "locale_requirements",
            "variants",
            "approvals",
            "submissions",
        ],
        "tools": [
            "list_records",
            "read_file",
            "render_variant",
            "inspect_asset",
            "request_approval",
            "submit_variant",
        ],
        "source_binding": "Actual locale Task, licensed assets and reviewed brand rules pending",
    },
    "BNK-KYC": {
        "name": "KYC onboarding and refresh",
        "scenarios": ["incomplete", "complete", "expired", "conflict", "refresh_due"],
        "collections": [
            "customers",
            "cases",
            "documents",
            "checks",
            "requests",
            "decisions",
            "refresh_schedule",
        ],
        "tools": [
            "list_records",
            "read_file",
            "screen_case",
            "request_information",
            "record_decision",
        ],
        "source_binding": "Published authentic KYC-001 and reviewed banking rules pending; fixture is not KYC-001",
    },
    "BNK-KYB": {
        "name": "KYB beneficial ownership",
        "scenarios": ["layered", "missing_evidence", "ambiguous_screening", "boundary", "cycle"],
        "collections": [
            "entities",
            "persons",
            "ownership_edges",
            "control_relationships",
            "documents",
            "cases",
            "checks",
            "requests",
            "decisions",
            "calculations",
        ],
        "tools": [
            "list_records",
            "read_file",
            "ownership_paths",
            "screen_case",
            "request_information",
            "record_decision",
        ],
        "source_binding": "Published KYB Task, ownership sources and reviewed rules pending",
    },
    "BNK-AML": {
        "name": "AML investigation",
        "scenarios": [
            "explainable",
            "unresolved",
            "missing_context",
            "duplicate",
            "prohibited_disclosure",
        ],
        "collections": [
            "customers",
            "accounts",
            "transactions",
            "alerts",
            "cases",
            "checks",
            "investigation_steps",
            "dispositions",
            "escalations",
            "case_links",
        ],
        "tools": [
            "list_records",
            "read_file",
            "query_transactions",
            "record_step",
            "link_case",
            "record_disposition",
        ],
        "source_binding": "Published AML Task and investigation/disposition rules pending; no legal thresholds inferred",
    },
}


def catalog():
    return [
        {
            "id": key,
            "version": VERSION,
            **copy.deepcopy(value),
            "origin": "synthetic_reference",
            "provider_calls": 0,
        }
        for key, value in CATALOG.items()
    ]


def png(width=320, height=180, caption="", disclosure=""):
    """Real RGB PNG bytes for the local creative reference implementation."""
    if caption or disclosure:
        import io
        import textwrap

        from PIL import Image, ImageDraw

        if not (caption + disclosure).isascii():
            raise ValueError(
                "Reference renderer supports ASCII text only; configure a qualified locale renderer for other scripts"
            )
        image = Image.new("RGB", (width, height), (32, 74, 122))
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (12, 12), "\n".join(textwrap.wrap(caption, 42)[:5]), fill="white", spacing=4
        )
        draw.multiline_text(
            (12, height - 42), "\n".join(textwrap.wrap(disclosure, 42)[:2]), fill="white", spacing=3
        )
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        return stream.getvalue()

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    scan = (b"\0" + bytes((32, 74, 122)) * width) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scan))
        + chunk(b"IEND", b"")
    )


def file(path, body, media="text/plain"):
    data = body.encode() if isinstance(body, str) else body
    return {
        "path": path,
        "media_type": media,
        "bytes_base64": base64.b64encode(data).decode(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def generate(template, scenario, seed=1):
    if template not in CATALOG or scenario not in CATALOG[template]["scenarios"]:
        raise ValueError("Unknown template/scenario version")
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("Seed must be an integer from 0 through 2147483647")
    rows = {key: [] for key in CATALOG[template]["collections"]}
    files = []

    def add(collection, **values):
        rows[collection].append(values)

    if template == "BOD-FIN":
        for company in range(1, 4):
            cid = f"fictional-{seed}-{company}"
            add("companies", id=cid, name=f"Fictional Company {company}")
            for year in (2023, 2024, 2025):
                pid = f"{cid}-{year}"
                currency = "USD" if scenario == "unit_mismatch" and year == 2024 else "INR"
                scale = "1000000" if scenario == "unit_mismatch" and year == 2025 else "1000"
                revision = (
                    "restated-v2" if scenario == "restated" and year == 2024 else "original-v1"
                )
                add(
                    "reporting_periods",
                    id=pid,
                    company_id=cid,
                    start=f"{year}-01-01",
                    end=f"{year}-12-31",
                    currency=currency,
                    unit_scale=scale,
                    basis="consolidated",
                    revision=revision,
                )
                values = {
                    "assets": "1000.00",
                    "liabilities": "400.00",
                    "equity": "600.00",
                    "revenue": str(Decimal(200 + company * 10 + year - 2023)),
                    "expenses": "150.00",
                    "cash_open": "100.00",
                    "cash_movement": "25.00",
                    "cash_close": "125.00",
                }
                if scenario == "restated" and year == 2024:
                    values["revenue"] = "240.00"
                if scenario == "missing_line" and year == 2025:
                    values["revenue"] = None
                path = f"sources/{pid}.json"
                artifact = file(path, json.dumps(values, sort_keys=True), "application/json")
                files.append(artifact)
                add(
                    "source_documents",
                    id=pid,
                    path=path,
                    sha256=artifact["sha256"],
                    revision=revision,
                )
                for item, value in values.items():
                    add(
                        "financial_statement_lines",
                        id=f"{pid}-{item}",
                        company_id=cid,
                        period_id=pid,
                        line_item=item,
                        value=value,
                        currency=currency,
                        unit_scale=scale,
                        basis="consolidated",
                        revision=revision,
                        source_document_id=pid,
                        source_row=item,
                    )
    elif template == "MKT-PHONE":
        add(
            "products",
            id="phone",
            name="Fictional QuietPhone",
            fact_version="1",
            approved_claims=["noise cancelling", "fictional reference product"],
            budget="1000.00",
            currency="INR",
        )
        for audience in ("commuter", "student"):
            add("audiences", id=audience, locale_ids=["en-IN", "ta-IN"])
        for channel in ("search", "social", "display"):
            add(
                "channels",
                id=channel,
                available=not (scenario == "channel_unavailable" and channel == "social"),
                mode="local_simulated_placement",
            )
        add(
            "campaigns",
            id="campaign",
            product_id="phone",
            objective="Fictional launch",
            status="draft",
            copy="Guaranteed cures" if scenario == "unsupported_claim" else "noise cancelling",
            audience_ids=["commuter", "student"],
        )
        if scenario == "budget_overrun":
            for index in range(2):
                add(
                    "allocations",
                    id=f"allocation-{index}",
                    campaign_id="campaign",
                    amount="600.00",
                    currency="INR",
                )
        files.append(
            file(
                "inputs/launch-brief.txt",
                "Fictional product. Only supplied approved facts may be claimed. No external ad purchase or publication.",
            )
        )
    elif template == "MKT-LOCALE":
        add("bundles", id="bundle", name="Fictional launch assets", source_version="1")
        for channel in ("search", "social", "display"):
            add("channel_specs", id=channel, width=320, height=180, format="image/png", version="1")
        for locale in ("en-IN", "ta-IN"):
            add(
                "locale_requirements",
                id=locale,
                disclosure="Fictional reference offer",
                translation_status="ambiguous"
                if scenario == "ambiguous_translation" and locale == "ta-IN"
                else "not_evaluated",
            )
            for channel in ("search", "social", "display"):
                if scenario == "missing_variant" and locale == "ta-IN" and channel == "social":
                    continue
                vid = f"{channel}-{locale}"
                path = f"assets/{vid}.png"
                files.append(
                    file(
                        path,
                        png(
                            100 if scenario == "invalid_size" and vid == "search-en-IN" else 320,
                            180,
                            "Fictional caption",
                            ""
                            if scenario == "missing_disclosure" and vid == "search-en-IN"
                            else "Fictional reference offer",
                        ),
                        "image/png",
                    )
                )
                add(
                    "variants",
                    id=vid,
                    bundle_id="bundle",
                    channel=channel,
                    locale=locale,
                    path=path,
                    caption="Fictional caption",
                    disclosure=""
                    if scenario == "missing_disclosure" and vid == "search-en-IN"
                    else "Fictional reference offer",
                    source_version="1",
                )
        files.append(file("sources/original.png", png(), "image/png"))
    elif template == "BNK-KYC":
        add(
            "customers",
            id="customer",
            name=f"Fictional Customer {seed}",
            identity_conflict=scenario == "conflict",
        )
        add(
            "cases",
            id="case",
            customer_id="customer",
            status="open",
            type="refresh" if scenario == "refresh_due" else "onboarding",
            source_task_id=None,
        )
        if scenario != "incomplete":
            path = "documents/identity.txt"
            files.append(
                file(
                    path,
                    "SYNTHETIC IDENTITY DOCUMENT\nFictional Customer only. Not a real identity.",
                )
            )
            add(
                "documents",
                id="identity",
                case_id="case",
                customer_id="customer",
                kind="identity",
                path=path,
                issue_date="2020-01-01",
                expiry_date="2025-01-01" if scenario == "expired" else "2030-01-01",
            )
        files.append(
            file("documents/address.txt", "SYNTHETIC ADDRESS DOCUMENT. Fictional address.")
        )
        add(
            "documents",
            id="address",
            case_id="case",
            customer_id="customer",
            kind="address",
            path="documents/address.txt",
            expiry_date=None,
        )
        add(
            "refresh_schedule",
            id="refresh",
            case_id="case",
            due="2026-01-01" if scenario == "refresh_due" else "2027-01-01",
        )
        add(
            "checks",
            id="screening-fixture",
            case_id="case",
            status="unavailable"
            if scenario == "incomplete"
            else "ambiguous"
            if scenario == "conflict"
            else "clear",
            origin="synthetic_stub",
        )
    elif template == "BNK-KYB":
        for entity in ("company", "holding"):
            add("entities", id=entity, name=f"Fictional {entity}")
        for person in ("person-a", "person-b"):
            add("persons", id=person, name=f"Fictional {person}")
        edges = [
            ("holding", "company", "50.00"),
            ("person-a", "holding", "50.00"),
            ("person-a", "company", "10.00"),
            ("person-b", "company", "40.00"),
        ]
        if scenario == "boundary":
            edges = [("person-a", "company", "25.00"), ("person-b", "company", "75.00")]
        if scenario == "cycle":
            edges.append(("company", "holding", "10.00"))
        for index, (owner, owned, share) in enumerate(edges):
            path = f"documents/ownership-{index}.txt"
            missing = scenario == "missing_evidence" and index == 0
            if not missing:
                files.append(
                    file(
                        path,
                        f"Fictional declaration: {owner} owns {share}% of {owned} as of 2026-01-01",
                    )
                )
                add("documents", id=f"doc-{index}", path=path)
            add(
                "ownership_edges",
                id=f"edge-{index}",
                owner=owner,
                owned=owned,
                share=share,
                as_of="2026-01-01",
                document_id=None if missing else f"doc-{index}",
            )
        add("cases", id="case", entity_id="company", status="open")
        add(
            "checks",
            id="screening-fixture",
            case_id="case",
            status="ambiguous" if scenario == "ambiguous_screening" else "clear",
            origin="synthetic_stub",
        )
    else:
        if scenario != "missing_context":
            add(
                "customers",
                id="customer",
                name=f"Fictional Customer {seed}",
                activity="fictional retail",
            )
        add(
            "accounts",
            id="account",
            customer_id="customer",
            context_available=scenario != "missing_context",
        )
        for index in range(6):
            add(
                "transactions",
                id=f"txn-{index}",
                account_id="account",
                amount=str(Decimal("100.25") * (index + 1)),
                currency="INR",
                timestamp=f"2026-01-{index + 1:02d}T10:00:00Z",
                counterparty=f"fictional-counterparty-{index % 2}",
            )
        add(
            "alerts",
            id="alert",
            account_id="account",
            status="open",
            trigger="synthetic-pattern",
            window_start="2026-01-01T00:00:00Z",
            window_end=CLOCK,
        )
        add(
            "cases", id="case", alert_id="alert", status="open", unresolved=scenario == "unresolved"
        )
        if scenario == "duplicate":
            add(
                "alerts",
                id="related-alert",
                account_id="account",
                status="open",
                trigger="synthetic-pattern",
                window_start="2026-01-01T00:00:00Z",
                window_end=CLOCK,
            )
            add("cases", id="related-case", alert_id="related-alert", status="open")
        files.append(
            file(
                "inputs/procedure.txt",
                "Fictional investigation exercise. No regulatory filing or customer communication. No legal threshold supplied.",
            )
        )
    pack = {
        "schema_version": "anvil.environment-pack.v1",
        "template": template,
        "template_version": VERSION,
        "scenario": scenario,
        "seed": seed,
        "clock": CLOCK,
        "origin": "synthetic_reference",
        "source_binding": CATALOG[template]["source_binding"],
        "records": rows,
        "files": files,
        "provider_calls": 0,
    }
    validate(pack)
    return pack


def validate(pack):
    if set(pack) - {"input_sources"} != {
        "schema_version",
        "template",
        "template_version",
        "scenario",
        "seed",
        "clock",
        "origin",
        "source_binding",
        "records",
        "files",
        "provider_calls",
    }:
        raise ValueError("Unexpected or missing pack fields")
    template = pack["template"]
    if (
        template not in CATALOG
        or pack["template_version"] != VERSION
        or pack["schema_version"] != "anvil.environment-pack.v1"
    ):
        raise ValueError("Unsupported template/schema version")
    if (
        pack["scenario"] not in CATALOG[template]["scenarios"]
        or pack["origin"] not in {"synthetic_reference", "hybrid_reference"}
        or pack["provider_calls"] != 0
    ):
        raise ValueError("Unsupported reference pack provenance")
    if set(pack["records"]) != set(CATALOG[template]["collections"]):
        raise ValueError("Component collection coverage mismatch")
    if len(json.dumps(pack).encode()) > 4 * 1024 * 1024:
        raise ValueError("Pack exceeds 4 MiB")
    for records in pack["records"].values():
        ids = [r.get("id") for r in records]
        if (
            len(ids) > 1000
            or any(not isinstance(i, str) or not i or len(i) > 160 for i in ids)
            or len(ids) != len(set(ids))
        ):
            raise ValueError("Invalid or duplicate record identities")
    paths = set()
    for artifact in pack["files"]:
        path = artifact["path"]
        if (
            not isinstance(path, str)
            or len(path) > 240
            or path.startswith("/")
            or "\\" in path
            or any(p in ("", ".", "..") or p.startswith(".") for p in path.split("/"))
            or path in paths
            or any(ord(char) < 32 for char in path)
        ):
            raise ValueError("Unsafe or duplicate file path")
        paths.add(path)
        data = base64.b64decode(artifact["bytes_base64"], validate=True)
        if (
            len(data) > 262144
            or artifact["size"] != len(data)
            or artifact["sha256"] != hashlib.sha256(data).hexdigest()
        ):
            raise ValueError("File size/hash mismatch")
    if pack["origin"] == "hybrid_reference":
        sources = pack.get("input_sources", [])
        if not 1 <= len(sources) <= 20 or any(
            s.get("rights_status") != "declared_unverified" or s.get("path") not in paths
            for s in sources
        ):
            raise ValueError("Hybrid pack requires its retained declared source")
    elif pack.get("input_sources"):
        raise ValueError("Synthetic pack cannot claim imported provenance")
    _references(pack)
    return {
        "status": "validated_pack",
        "sha256": digest(pack),
        "collections": {k: len(v) for k, v in pack["records"].items()},
        "files": len(paths),
        "runtime_loaded": False,
    }


def _references(pack):
    """Validate modeled references, retaining deliberately missing evidence as null."""
    r = pack["records"]
    ids = {name: {v["id"] for v in values} for name, values in r.items()}
    files = {f["path"] for f in pack["files"]}
    links = {
        "reporting_periods": [("company_id", "companies")],
        "financial_statement_lines": [
            ("company_id", "companies"),
            ("period_id", "reporting_periods"),
            ("source_document_id", "source_documents"),
        ],
        "campaigns": [("product_id", "products")],
        "allocations": [("campaign_id", "campaigns")],
        "variants": [
            ("bundle_id", "bundles"),
            ("channel", "channel_specs"),
            ("locale", "locale_requirements"),
        ],
        "ownership_edges": [("document_id", "documents")],
        "transactions": [("account_id", "accounts")],
        "alerts": [("account_id", "accounts")],
    }
    for collection, references in links.items():
        for row in r.get(collection, []):
            for field, target in references:
                if target in ids and row.get(field) is not None and row[field] not in ids[target]:
                    raise ValueError(f"Unresolved {collection}.{field} reference")
    for rows in r.values():
        for row in rows:
            if "path" in row and row["path"] not in files:
                raise ValueError("Record references an absent file")
    for edge in r.get("ownership_edges", []):
        if (
            edge["owner"] not in ids["entities"] | ids["persons"]
            or edge["owned"] not in ids["entities"]
            or not Decimal(0) <= Decimal(edge["share"]) <= Decimal(100)
        ):
            raise ValueError("Invalid ownership identity or exact share")
