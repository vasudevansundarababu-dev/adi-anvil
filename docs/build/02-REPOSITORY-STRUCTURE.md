# New repository and directory structure

Repository name: **ADI-Anvil**. Suggested future GitHub path: `<confirmed-owner>/ADI-Anvil`, **private**. Owner is intentionally unset. Local path is the root of this handoff. No remote is created/pushed until review.

This is one repository containing only the Anvil application components, not a shared ADI multi-product monorepo. Create the following during implementation. Files marked supplied already exist; all application code below is to be built.

```text
ADI-Anvil/
  README.md                          # supplied; replace status/run instructions truthfully
  AGENTS.md                          # supplied coding constraints
  START-HERE.md                      # supplied VS Code launch guide
  CODEX-OVERNIGHT-PROMPT.md           # supplied single launch prompt
  BUILD-DECISIONS.json                # supplied, no secrets
  BUILD-STATUS.md                    # live checkpoint log
  QUESTIONS.md                       # confirmed/pending choices
  .gitignore                         # supplied exclusions
  .env.example                       # names, flags, paths; no working credentials
  .node-version
  .python-version
  package.json                       # root command contract
  pnpm-workspace.yaml
  pnpm-lock.yaml
  .github/
    PULL_REQUEST_TEMPLATE.md          # supplied
    ISSUE_TEMPLATE/bug_report.md      # supplied
    workflows/ci.yml                 # lint/types/build/unit/integration/E2E, no deploy
    workflows/dependency-review.yml  # scoped supply-chain checks
    dependabot.yml                   # updates only, no automatic merge
  apps/web/
    package.json
    next.config.ts
    Dockerfile
    public/brand/adi-anvil-logo-v1.png
    src/app/(auth)/login/page.tsx
    src/app/(app)/p/[projectId]/
      objectives/ cases/ rubrics/ suites/ protocols/
      providers/ runs/ reviews/ diagnostics/ reports/ sales-kits/
    src/components/{ui,layout,forms,graph,review}/
    src/lib/{api,auth,theme,validation}/
    tests/
  packages/api-client/                # Anvil-owned generated OpenAPI types/client
  services/backend/
    pyproject.toml
    uv.lock
    Dockerfile
    alembic.ini
    migrations/versions/
    src/anvil/
      api/{main,routes,dependencies,middleware}.py
      domain/{identity,objectives,intake,rights,qualification,protocols}/
      domain/{evaluation,review,findings,reports,releases,sales_kits}/
      db/{models,repositories,session,rls}/
      worker/{main,queue,leases,dispatch,reconcile}.py
      orchestration/{graph,state,checkpoints,resume,versions}/
      adapters/candidates/{base,fixture,openai,anthropic,gemini,mistral,meta,compatible}.py
      adapters/{artifacts,secrets,identity,scanner,graph,mail}/
      graph/{outbox,projector,queries,rebuild}.py
      reports/{content,render_pdf,render_html,export}.py
      cli/{preflight,seed,fixtures,backup,restore_test}.py
      schemas/                       # typed inputs, outputs and errors
    tests/{unit,integration,contracts}/
  contracts/{openapi,schemas}/
  infra/local/
    compose.yaml
    keycloak/realm.template.json      # no committed passwords
    postgres/bootstrap.sql
    neo4j/constraints.cypher
    scanner/                         # production file intake gated until qualified
  scripts/{preflight,setup,dev,stop,check,smoke,live,seed-demo}/
  tests/e2e/{login,intake,evaluation,review,graph,report,sales-kit,security}.spec.ts
  tests/helpers/
  fixtures/
    cases/{MKT-001,FIN-001,STR-001}/actor/
    cases/{MKT-001,FIN-001,STR-001}/private/
    candidate-outputs/               # predetermined responses; fixture mode ONLY
    expected/                       # test-only assertions; never candidate input
    negative/                       # invalidity/rights/version/mode scenario recipes
    README.md
  assets/brand/                      # supplied approved-family derivative
  docs/
    product/                         # detailed baseline supplied with portable links
    product/mockups/adi-anvil-v1.html
    build/                           # current overnight specification supplied
    architecture/                    # implementation ADRs, resolved dependencies
    runbooks/{local,backup,provider-onboarding,incident}.md
    generated/{test-matrix,morning-report,api-compatibility}.md
  artifacts/test-runs/               # ignored evidence, screenshots, JUnit, PDFs
  .local/                            # ignored local accounts/process IDs
  .secrets/                          # ignored local key files, owner-only
  .data/                             # ignored private artifacts
```

Brace groups describe folders/files to create, not literal brace-containing paths. Use a conventional module layout if an exact dotted-name stub would be awkward; record the decision. No empty placeholder “implementation” files counted as a delivered feature.

## Local Git and future GitHub

After the user launches the build: inspect the directory and any existing Git status. If not a repository, initialize an independent local repository with a `main` default branch and working branch `build/overnight-v1`. Preserve existing Git/user changes if already initialized. Use existing Git identity; if missing, record checkpoint blockage rather than invent a name/email or alter global Git settings. Commit only an explicit reviewed file set after tests and secret scan; never `git add .` blindly over new secrets/artifacts.

Prepare GitHub Actions YAML, a PR template, issue template and dependency update configuration locally. No remote, repository creation, collaborators, branch protection changes, release, Pages site or Actions execution is authorized now. After user review, confirm owner and inspect for an existing private repository before creating/pushing. Never overwrite an existing remote, force-push or publish to a guessed account.

CI uses synthetic data and local service containers, pinned actions/images, minimal `contents: read` permission and no production/model secrets. Required checks: type/lint/build, unit, API/DB/worker integration, browser E2E, migration tests, dependency and secret scan. Vendor availability tests are opt-in local commands, not PR jobs. Do not add `pull_request_target` with untrusted code execution.
