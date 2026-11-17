"""Exact permanent pilot namespaces, independent from production/temp-QA settings."""

import os

TARGETS = {
    "qa": (
        "qa-v1",
        "anvil-qa-v1",
        "https://anvil-qa.adi-labs.ai",
        "https://anvil-qa-auth.adi-labs.ai/realms/anvil-qa",
        100_000_000,
        2_000_000,
    ),
    "staging": (
        "staging-v1",
        "anvil-staging-v1",
        "https://anvil-staging.adi-labs.ai",
        "https://anvil-staging-auth.adi-labs.ai/realms/anvil-staging",
        300_000_000,
        5_000_000,
    ),
}
MODELS = {
    "qa": [
        ("openai", "gpt-6.1-sol"),
        ("anthropic", "claude-opus-5-5"),
        ("gemini", "gemini-4-argon"),
    ],
    "staging": [
        ("openai", "gpt-6.1-sol"),
        ("openai", "gpt-6-astra"),
        ("anthropic", "claude-opus-5-5"),
        ("anthropic", "claude-fable-5-2"),
        ("gemini", "gemini-4-argon"),
        ("gemini", "gemini-4-carbon"),
    ],
}


def current():
    env = os.environ.get("ANVIL_PILOT_ENVIRONMENT")
    profile = os.environ.get("ANVIL_CREDENTIAL_STORE_PROFILE", "legacy")
    origin = os.environ.get("WEB_ORIGIN")
    inferred = next((key for key, value in TARGETS.items() if value[2] == origin), None)
    if not env and profile not in {"qa-v1", "staging-v1"} and not inferred:
        return None
    if env not in TARGETS:
        raise ValueError("Exact permanent pilot environment is required")
    expected = TARGETS[env]
    if (
        os.environ.get("ANVIL_ENV") != "cloud"
        or profile != expected[0]
        or origin != expected[2]
        or os.environ.get("OIDC_ISSUER") != expected[3]
    ):
        raise ValueError("Permanent pilot cloud/profile/issuer binding differs")
    return env


def check_flags():
    if current() is None:
        return
    role = os.environ.get("ANVIL_WORKER_BROKER_ROLE")
    governed = os.environ.get("ANVIL_GOVERNED_AI_ENABLED", "false")
    if (
        governed not in {"false", "true"}
        or governed == "true"
        and (current() != "qa" or role not in {"api", "worker"})
    ):
        raise ValueError("Governed AI requires an explicit QA API/scheduler binding")
    if os.environ.get("ANVIL_GOLDEN_KYC_PAID_WORKER_ENABLED", "false") not in {"false", "true"}:
        raise ValueError("Explicit Golden scheduler switch required")
    if os.environ.get("ANVIL_GOLDEN_KYC_PAID_WORKER_ENABLED") == "true" and (
        current() != "qa"
        or role != "worker"
        or not os.environ.get("ANVIL_GOLDEN_SCHEDULER_DATABASE_URL")
        or os.environ.get("WORKER_DATABASE_URL")
        or os.environ.get("ANVIL_GOLDEN_GRADER_DATABASE_URL")
    ):
        raise ValueError("Golden paid scheduler requires dedicated disjoint QA worker binding")
    if os.environ.get("ANVIL_GOLDEN_KYC_PAID_ENABLED", "false") not in {"false", "true"}:
        raise ValueError("Explicit Golden paid admission switch required")
    if os.environ.get("ANVIL_GOLDEN_KYC_PAID_ENABLED") == "true" and (
        current() != "qa"
        or role != "api"
        or os.environ.get("ANVIL_WORKER_BROKER_ENABLED") != "true"
        or os.environ.get("ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED") != "true"
    ):
        raise ValueError("Golden paid scope requires exact QA API broker only")
    if role not in {"api", "worker", "migrate"} or os.environ.get(
        "ANVIL_WORKER_BROKER_ENABLED", "false"
    ) not in {"false", "true"}:
        raise ValueError("Exact pilot process broker role required")
    if role != "api" and any(
        os.environ.get(k)
        for k in (
            "DATABASE_URL",
            "ANVIL_PILOT_SECRET_RESOURCE",
            "ANVIL_PILOT_GCP_PROJECT_NUMBER",
            "ANVIL_CLOUD_SECRET_INDEX",
            "OIDC_CLIENT_SECRET",
        )
    ):
        raise ValueError("Worker/operator must not inherit API credentials or secret index")
    if role == "api" and (
        os.environ.get("WORKER_DATABASE_URL") or os.environ.get("MIGRATION_DATABASE_URL")
    ):
        raise ValueError("API must not inherit worker or owner DSN")
    if role == "migrate" and os.environ.get("ANVIL_WORKER_BROKER_ENABLED", "false") != "false":
        raise ValueError("Migration process cannot dispatch")
    if role == "worker" and os.environ.get("MIGRATION_DATABASE_URL"):
        raise ValueError("Worker must not inherit migration owner DSN")
    if role == "migrate" and os.environ.get("WORKER_DATABASE_URL"):
        raise ValueError("Migration process must not inherit worker DSN")
    for key in (
        "ANVIL_LIVE_PROVIDERS_ENABLED",
        "ANVIL_VERTEX_ENABLED",
        "ANVIL_IMPORT_GENERATION_ENABLED",
        "ANVIL_GENERATION_ENABLED",
        "ANVIL_REAL_EMAIL_ENABLED",
        "ANVIL_BENCHMARK_EVALUATION_ENABLED",
        "ANVIL_BENCHMARK_ENABLED",
        "ANVIL_QA_MODEL_SMOKE_ENABLED",
        "LANGSMITH_TRACING",
    ):
        if os.environ.get(key, "false") != "false":
            raise ValueError("Unbudgeted pilot dispatch path must stay disabled")
    if os.environ.get("ANVIL_SUPPORT_VERTEX_PROJECT") or os.environ.get("ANVIL_SUPPORT_MODEL"):
        raise ValueError("Pilot support inference remains disabled")
