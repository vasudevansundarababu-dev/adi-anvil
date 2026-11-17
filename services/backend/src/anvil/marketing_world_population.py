"""Complete public US-pair source projection, excluding reviewer answers.

Original bytes are hash checked in bounded chunks. Derived records are expanded
only inside the private API controller, avoiding duplicate parsed populations in
the immutable source definition. Missing counts/provenance stay unchanged.
"""

import hashlib
from copy import deepcopy
from datetime import timedelta

from anvil.dataset_export_contract import json_object
from anvil.marketing_task2_runtime import timestamp
from anvil.marketing_world_definition import PublicFixture
from anvil.marketing_world_source_encoding import LIMIT, decode, encode
from anvil.praxis_generic_contract import digest

SHARED = ("product.json", "capabilities.json", "localised_query_drafts.jsonl")
CASE = ("campaigns.json", "daily_query_observations.jsonl", "observation_windows.jsonl", "notices.json",
        "source_collection_contracts.json", "keyword_catalogue.json", "measurement_contract.json",
        "destination_assignments.json", "offer_revisions.json")
TOTAL = 16777216
ORIGINAL_QUESTIONS = "sources/finequestions_selected.jsonl"
PERMISSION = "attribution/FINEQUESTIONS-PERMISSION.txt"


def paths(case):
    if case not in {"GT2-R01", "GT2-R02"}:
        raise ValueError("Exact approved US-pair case required")
    return ({"shared/" + name for name in SHARED} | {f"cases/{case}/{name}" for name in CASE}
            | {ORIGINAL_QUESTIONS, PERMISSION})


def encode_sources(case, files, pins):
    documents, size = {}, 0
    for path in sorted(paths(case)):
        raw = files.get(path)
        if type(raw) is not bytes or not 0 < len(raw) <= TOTAL or hashlib.sha256(raw).hexdigest() != pins.get(path):
            raise ValueError("Exact independently pinned public population bytes required")
        size += len(raw)
        if size > TOTAL:
            raise ValueError("Public source population exceeds original decoded bound")
        documents[path] = [encode(raw[offset:offset + LIMIT]) for offset in range(0, len(raw), LIMIT)]
    return documents


def decode_sources(case, documents, pins):
    if type(documents) is not dict or set(documents) != paths(case):
        raise ValueError("Exact public-only population source set required; no reviewer/answer sources")
    files, total = {}, 0
    for path, chunks in documents.items():
        if type(chunks) is not list or not 1 <= len(chunks) <= 16:
            raise ValueError("Bounded original source chunks required")
        decoded = []
        for index, chunk in enumerate(chunks):
            raw = decode(chunk)
            if index < len(chunks) - 1 and len(raw) != LIMIT:
                raise ValueError("Canonical full source chunk boundaries required")
            total += len(raw)
            if total > TOTAL:
                raise ValueError("Public source population exceeds original decoded bound")
            decoded.append(raw)
        raw = b"".join(decoded)
        if hashlib.sha256(raw).hexdigest() != pins.get(path):
            raise ValueError("Public source population differs from independently pinned bytes")
        files[path] = raw
    return files


def _rows(path, files):
    raw = files[path]
    if path == PERMISSION:
        return {"text": raw.decode("utf-8"), "source_kind": "original_source_permission_notice"}
    if path.endswith(".jsonl"):
        lines = raw.splitlines()
        if not 1 <= len(lines) <= 12000 or any(not line.strip() or len(line) > 49152 for line in lines):
            raise ValueError("Bounded complete source rows required")
        return [json_object(line) for line in lines]
    # json_object rejects duplicate keys/non-finite numbers; JSON arrays need
    # the same strict decoder while retaining their actual original bytes.
    return json_object(b'{"value":' + raw + b'}')["value"]


def compile_population(case, documents, pins, services):
    files = decode_sources(case, documents, pins)
    start = timestamp(services["shared"]["campaign_contract"]["start"] + "T00:00:00Z")
    prefix = f"cases/{case}/"
    values = {path: _rows(path, files) for path in files}
    drafts = values["shared/localised_query_drafts.jsonl"]
    if type(drafts) is not list:
        raise ValueError("Actual question catalogue array required")
    questions = [row for row in drafts if row.get("locale") == "en-US"]
    lookup = {row["id"]: row for row in questions}
    if len(lookup) != len(questions) or not lookup:
        raise ValueError("Distinct actual US question drafts required")
    originals = values[ORIGINAL_QUESTIONS]
    original_index = {row["norm_qn_id"]: row for row in originals}
    if len(original_index) != len(originals) or not original_index:
        raise ValueError("Distinct original FineQuestions records required")
    observations = values[prefix + "observation_windows.jsonl"]
    observation_index = {row["id"]: row for row in observations}
    if len(observation_index) != len(observations):
        raise ValueError("Distinct original observation windows required")
    queries = values[prefix + "daily_query_observations.jsonl"]
    if len({row["id"] for row in queries}) != len(queries):
        raise ValueError("Distinct original query observations required")
    for row in queries:
        if row.get("case_id") != case:
            raise ValueError("Query population contains another case")
        if row.get("locale") != "en-US":
            continue
        parent, question = observation_index.get(row["window_id"]), original_index.get(row["parent_question_id"])
        if (parent is None or question is None
                or any(parent.get(key) != row.get(key) for key in ("date", "locale", "source", "released_at"))
                or row["question_text"] != question["question"]
                or type(row["week"]) is not int or not 1 <= row["week"] <= 12
                or (row["observed_count"] is not None and (type(row["observed_count"]) is not int or row["observed_count"] < 0))):
            raise ValueError("Actual query/window/question lineage and missingness must be preserved")
    if values[prefix + "offer_revisions.json"] != []:
        raise ValueError("Nonempty offer revisions require an explicit reviewed projection successor")
    groups = [
        ("products", "shared/product.json", [values["shared/product.json"]]),
        ("capabilities", "shared/capabilities.json", values["shared/capabilities.json"]),
        ("questions", "shared/localised_query_drafts.jsonl", questions),
        ("questions", ORIGINAL_QUESTIONS,
         [{**row, "id": row["norm_qn_id"], "source_kind": "original_questions",
           "source_label_status": "ORIGINAL_LABEL_DEFINITIONS_UNAVAILABLE_NOT_CAMPAIGN_OBSERVATIONS"} for row in originals]),
        ("documents", PERMISSION, [values[PERMISSION]]),
        ("campaigns", prefix + "campaigns.json", values[prefix + "campaigns.json"]),
        ("questions", prefix + "daily_query_observations.jsonl", [row for row in queries if row.get("locale") == "en-US"]),
        ("observation-windows", prefix + "observation_windows.jsonl", [row for row in observations if row.get("locale") == "en-US"]),
    ]
    for name in ("notices.json", "source_collection_contracts.json", "keyword_catalogue.json", "measurement_contract.json", "destination_assignments.json"):
        value = values[prefix + name]
        if name == "destination_assignments.json":
            value = [row for row in value if row.get("locale") == "en-US"]
        groups.append(("documents", prefix + name, value if type(value) is list else [value]))
    for path in ("shared/campaign_contract.json", prefix + "case.json"):
        raw = services["source_documents"][path].encode()
        if hashlib.sha256(raw).hexdigest() != pins[path]:
            raise ValueError("Exact existing service document bytes required")
        public = json_object(raw)
        if path == prefix + "case.json":
            public = {key: public[key] for key in ("case_id", "focus_locale", "campaign_id", "start", "end", "task", "review_scope")}
        groups.append(("documents", path, [public]))
    result = []
    ids = set()
    for collection, path, rows in groups:
        if type(rows) is not list:
            raise ValueError("Complete bounded projected source array required")
        for original in rows:
            public = deepcopy(original)
            if type(public) is not dict:
                raise ValueError("Actual public source object required")
            public.setdefault("id", "anvil-source-document:" + digest({"path": path, "public": original}))
            if collection == "observation-windows":
                instant = timestamp(public["date"] + "T00:00:00Z")
                if not start <= instant < start + timedelta(days=84):
                    raise ValueError("Observation date outside original campaign")
                public["week"] = (instant - start).days // 7 + 1
            key = (collection, public["id"])
            if key in ids:
                raise ValueError("Duplicate normalized public source identity")
            ids.add(key)
            row = PublicFixture.model_validate({"source_path": path, "source_sha256": pins[path],
                                               "released_at": public.get("released_at", start.isoformat()),
                                               "outcome_binding": None, "public": public})
            result.append((collection, row))
    if len(result) > 20000:
        raise ValueError("Actual public source row population exceeds original bound")
    return result
