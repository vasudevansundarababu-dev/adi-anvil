# UI successor verification

Verified application source: `56a6d3fe78add4ebeda66c2dd7f0aa614c7c1832`. Backend and dependency locks are unchanged from c592b0b; no SQL/integration rerun was required for these frontend-only changes.

Both actual Keycloak-login browser tests passed in **5.4 seconds** against the promoted local preview on loopback 50679: four-view context/reload/cross-project access checks and an actual snapshot-bound redacted PDF download with raw prompts disabled. Private log SHA-256: `9b17c557a8c9e29b7e279201790e0c6eb7dfe89d2ef8facdbe4828a35f4e2bb9`.

A separate real-login read probe successfully opened all 27 canonical historical trace endpoints once: 24 public output projections and 486 criterion observations, zero model observations/ranked models and no current qualification authority. Checks did not alter existing drafts, create execution or source/score approvals, or invoke providers.

The promoted process was independently bound to the tested source directory: web PID 59894 listened on loopback 50679 and had its working directory in the new successor copy. PID numbers in an initial coordination message were briefly mistaken for ports; the runtime/browser configuration and actual process inspection agreed on 50679. No wrong-target rerun or product change was necessary.

All three changed frontend files matched their exact Git bytes. SHA-256 bindings:

| File | SHA-256 |
| --- | --- |
| `BenchmarkGoldenWorkbench.tsx` | `a3bec093f2cbbb14b56e465afc418911e737fa63cbb6e27bf7e51357e70390d2` |
| `BenchmarkWorkbench.tsx` | `e3077a7ed0cec954006810b2b59f36493d44a9f2975ce21c5e9ec41d4e9a8f23` |
| `BenchmarkWorkbench.module.css` | `6a56bdc76d55a614b4c0fdc4ac52c367d5ecf43b0cd2f7e683080df2401a6c48` |

This is a local synthetic-access preview of authentic preserved historical QA evidence. It is not staging deployment, model-performance evidence or current source/reviewer approval. The c592b0b backend verdict and its explicit native/Praxis skips remain unchanged. Root's visible manual inspection and empty disposable-dataset lifecycle check are separate evidence.
