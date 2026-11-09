# Independent replacement-workbench verification

Application checkpoint: `c592b0bd6097db1ddab62956dd0ed541891b15bf`.

The independent benchmark SQL/security suite passed **180 tests**, with **38 explicit skips**, in 82.55 seconds on a new isolated schema-060 database. Nine of those skips required a separate disposable role-probe cluster. After verifying and restarting only the owned probe on loopback 55406, its **nine migration security tests passed** in 2.17 seconds; the probe was stopped again. Combined actual SQL coverage is therefore **189 passes**. The remaining **29 native cases were not run**; historical native results do not qualify this successor.

The standard integration suite passed **190 tests**, with **19 skips**, in 149.39 seconds using a separate new database and a fresh Neo4j container from the already loaded exact image. The skips require explicit Docker/Harbor or authentic Praxis inputs; no Praxis work or provider calls were performed. No intermittent task-fixture failure occurred in this run. Existing Authlib and Alembic configuration deprecation warnings remain.

Two browser tests passed in 5.9 seconds against the immutable c592b0b local preview on loopback 50679. They used a real Keycloak login, actual persisted historical records and actual APIs. They verified all four views, shared filter/reload behavior, no execution/review mutations while navigating, cross-project denial, and a real PDF download bound to the current snapshot with raw prompts disabled.

A separate real-login read probe successfully opened all **27 canonical historical trace endpoints**: 24 public output projections and 486 criterion observations. The dashboard reported zero model traces, 27 historical controls and zero ranked models. All traces remained non-official; no qualification currency, comparison, model performance or human release approval was invented. The first standalone probe used the unavailable default bundled browser; switching to the same installed Chrome channel configured by the passing suite resolved that operator setup issue.

The initial development-only comparison test expected offline cells to count as model traces. That assertion failed and was corrected to the specified control semantics before this checkpoint. The subsequent full suite passed without product guard changes. Focused Golden/remediation evidence is documented separately in `golden-workbench-focused-verification.md`.

## Evidence hashes

| Receipt | SHA-256 |
| --- | --- |
| 934-path pre-test source manifest | `024eca360065dc3c3d5d721239a65e6b46271e08d82577c0d765d1010d76870c` |
| Full benchmark private log | `30f4ac0e98eac62004f0ee0a837aed59193dd5ff2282ab22198ee15579d5435f` |
| Separate nine role-migration private log | `ddf87e53a2aa6ff45e038470abb7725170baa1b8d5f8848ab211063827fb4d7f` |
| Standard integration private log | `9ef6ebabf04052de02eef988c5c9acc1c6352daa688a4cc0546bbda61bafe357` |
| Two real-OIDC/PDF browser private log | `3011fc1e602f64a4b819e55434856f13d6fe6c94e473f4e39eb20b8f18afdee2` |

All 934 tracked file hashes matched after the SQL and integration runs. A later check observed new edits to only `BenchmarkWorkbench.tsx` and its CSS; these later UI edits are outside the c592b0b browser verdict. The browser tests ran DevOps' separate immutable c592b0b source copy, preserving that binding.

The two disposable regression databases and the newly created integration graph container, its named data volume and its automatically created log volume were removed after evidence preservation. Absence was verified. The preview runtime, original stored evidence, existing volumes and older previews were preserved. The new role-probe container and volume were retained stopped. No cloud resources, image pulls, application deployment or paid calls occurred in this verification.
