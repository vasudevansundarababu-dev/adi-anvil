"""Print a planning checklist only. No executed rehearsal or deployment."""
import json


def main():
    print(json.dumps({"mode": "planning_checklist_only", "rehearsal_executed": False, "deploy_authorized": False, "actions_not_executed": [
        "Validate reviewed staging plan and fresh sanitized inventory",
        "Verify new staging disk identity; never format an existing application disk",
        "Verify fresh owner-only 0700 non-symlink private/config roots and parent components",
        "Install reviewed non-secret configuration and independently supplied stage-only secret env files",
        "Initialize distinct application and identity databases and reviewed scoped roles",
        "Verify immutable preloaded image digests; no implicit pull or build",
        "Run reviewed migration rehearsal against staging database only",
        "Start isolated core Compose services after independent release approval",
        "Keep benchmark admission/evaluation, all paid paths and email disabled",
        "Verify source identity, HTTPS/OIDC, data persistence, authorization and paid-off state"
    ], "blocked_on": ["exact endpoint/IAM/release decisions", "reviewed database initialization", "audited benchmark coordinator/executor wiring", "independent testing", "deployment approval"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
