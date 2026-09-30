# Reusable Anvil Google Cloud configuration

The source of truth for future deployments is `infra/gcp/deployment.json`.
It stores non-secret target choices only. Its unset fields are intentional; no cloud
project, spending amount or public access choice has been inferred. Configuration does
not yet make the current local-only application cloud-ready.

## One time setup

1. In Google Cloud Console, select or create the intended Anvil project and enable its
   billing. Record the project ID, not just the display name. Use a project explicitly
   authorized for Anvil. Do not infer that an existing Praxis project is the target.
2. Choose a region and zone, HTTPS application hostname, OIDC hostname/issuer, access
   mode (`private_advisor` or `public_invited_users`) and monthly infrastructure budget.
   Fill the corresponding JSON fields. `web_origin` must be a complete HTTPS origin;
   `oidc_issuer` must be the exact realm issuer, such as
   `https://auth.YOUR_DOMAIN/realms/anvil`. The example hostname is not a configured domain.
3. Use an independently installed Google Cloud CLI. The currently discovered CLI path
   lives in the Praxis checkout; no credentials from that repository are reused here.
   Authenticate into Anvil's ignored credential directory using the commands below.
4. Create a project-scoped billing budget and alerts in the Console. An alerts-only
   budget is not an automatic spending cap. Confirm service coverage separately if using
   a spend-cap budget. Do not interpret the JSON budget value as an enforced cloud cap.
5. Keep application secrets in Google Secret Manager with access granted only to the
   eventual Anvil runtime identity. Save resource names in `secret_resource_references`,
   never values. Separate database owner, application and worker credentials, OIDC client
   secret, session encryption key and Neo4j credentials. Do not upload local `.env`.

## Initial CLI authentication

Run from `/Users/vasudevansundarababu/Code-Repo/ADI-Anvil` after installing an independent
CLI. Replace the three uppercase placeholders with the choices saved in the JSON.
These commands configure CLI access; they do not provision an application.

```sh
export CLOUDSDK_CONFIG="$PWD/.local/gcloud-anvil"
mkdir -p "$CLOUDSDK_CONFIG"
chmod 700 "$CLOUDSDK_CONFIG"
gcloud config configurations create anvil-mvp-v1
gcloud auth login
gcloud --configuration=anvil-mvp-v1 config set project YOUR_PROJECT_ID
gcloud --configuration=anvil-mvp-v1 config set compute/region YOUR_REGION
gcloud --configuration=anvil-mvp-v1 config set compute/zone YOUR_ZONE
gcloud --configuration=anvil-mvp-v1 config list
```

Run configuration creation once. If the configuration already exists, select it with
`gcloud config configurations activate anvil-mvp-v1` rather than creating it again.
Login happens through Google's browser flow. Do not paste a password, token or service
account private key into the tracked JSON or chat. CLI configuration names separate
properties; the dedicated `CLOUDSDK_CONFIG` directory separates Anvil's local credential
store from other applications. Access still follows the authenticated account's IAM grants.

## Reuse for the next deployment

Read `infra/gcp/deployment.json` and this guide first. Set the same `CLOUDSDK_CONFIG`,
select `anvil-mvp-v1`, and verify project/account before any mutation. If login has expired,
repeat `gcloud auth login` in that directory. Authentication availability is not a promise
that credentials remain valid forever.

Do not run `gcloud init`, automatically select another project, or use sibling credential
files as a fallback. Confirm any target change and save it in the JSON. Machine size,
disk size, service identity and secret references stay unset until the deployment design
and budget are fixed. No IAM role grants or paid resource creation are performed by
these instructions.

After a successful deployment, record the verified commit, endpoint, timestamp and
resource IDs under `last_deployment`. Never mark an attempted rollout as successful.
The actual deployment must follow `google-cloud-mvp-v1.md`, including cloud environment
support, secure cookies, production Keycloak, containerization and deployed smoke checks.

## Official references

- CLI authentication: https://docs.cloud.google.com/sdk/docs/authenticate
- Named configurations: https://docs.cloud.google.com/sdk/docs/configurations
- Billing budgets and alerts: https://docs.cloud.google.com/billing/docs/how-to/budgets
- Spend-cap coverage: https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
