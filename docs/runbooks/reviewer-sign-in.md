# Hosted reviewer access

Browser entry points checked on 2 November 2026 (America/Chicago). These are existing
GCP applications. No new reviewer accounts or passwords are created by this guide.

| Application | URL | Observed entry behavior |
| --- | --- | --- |
| Anvil | [Workspace](https://anvil-34-36-217-66.sslip.io/workspace) | Existing authenticated Admin session opens the modern project workspace. API reports ready; Harbor dispatch is gated. |
| Praxis | [Console](https://praxis-web-yu2jtyqhea-uc.a.run.app/) | Existing authenticated Admin session opens Home; visible build `demo-a03cb10d-20261102`. |
| Praxis contributors | [Candidate sign-in](https://praxis-candidate-yu2jtyqhea-uc.a.run.app/sign-in) | Sign-in form visibly labels simulated Google/identity and synthetic-only demo data. |

## Anvil

1. Open the workspace and use your assigned Anvil/Keycloak account when prompted.
2. Select a project you are assigned to. Inspect Tasks and existing run results first.
3. For a paid diagnostic, confirm the exact saved model, task/package and displayed cap.
   Run records authorization and performs budget/rights/readiness checks.
4. If Anvil says **Please sign in again to authorize this run budget**, sign out, sign
   back in and return to the same saved group. Budget authorization requires an Admin
   sign-in within ten minutes. Do not recreate or replay an already-started group.

The browser session check above is not a claim that a new reviewer completed their
first login. A separate user-confirmed fresh sign-in admitted the bounded Gemini
diagnostic on this date; its outcome is recorded in BUILD-STATUS. Anvil sign-in and
Google Cloud CLI sign-in are separate. Refreshing GCP credentials does not refresh
Anvil authorization.

## Praxis

1. Open the console and sign in with your assigned console account. An existing
   session may open Home immediately. A temporary password requires the user to choose
   their own password before normal access; passwords are shared privately.
2. Start with Projects, Reviews and Approved exports; the Praxis repository's
   `docs/MODULE-GUIDE.md` explains each module and its implementation boundary.
3. The candidate app is a different audience. The hosted demo shows Email, Name and
   **Continue with Google (mock)**, along with age/terms/privacy notices. Use only
   fictional demo data and personally review any terms before proceeding.

Praxis's hosted environment uses real configured Vertex AI alongside simulated candidate
sign-in/identity/email. It is not a production identity or payment qualification.

## Versions and evidence

Anvil corrective image `556689f-1793654382` was inspected running in API, web and Harbor
worker containers. The deployed Gemini success/503/504 MockTransport proof and native
Harbor roundtrip use zero provider calls and persist no fake model results. See
[current build status](../../BUILD-STATUS.md) for live results and limitations.

The earlier [YC release report](../generated/yc-release-2026-11-01.md) remains dated
historical evidence; its initial image IDs and disabled evaluation flag are not the
current corrective rollout. Source publication and website availability alone do not
prove successful model execution. Keep credentials, auth codes, session cookies and
private data out of repositories and reviewer screenshots.
