# Backup and restore rehearsal

`pnpm backup:local` uses a repeatable-read exported PostgreSQL snapshot with `pg_dump`, then copies canonical artifact files and records SHA-256 checksums and record/checkpoint counts. Output is owner-only under ignored `.local/backups/`; `.local/latest-backup` selects the latest backup. Credentials and raw logs are not included. Backups still contain private application data and must remain local.

`pnpm restore:test` verifies the backup and creates a fresh `anvil_restore_<random>` database. It never overwrites the application database or deletes volumes. It restores rows/checkpoints and checks counts and copied artifact checksums. Retained test databases are listed in command output. Graph data is rebuildable and is not canonical backup evidence.

Latest rehearsal (2026-09-28 13:35 UTC): schema007 backup `.local/backups/20260928T133138Z-25f696b8` restored into retained `anvil_restore_5f1ed4794b68`. Verified 668 resources, 149 episodes, 170 assessments, 107 import batches, 6 review issues/resolutions, 5 external receipts, 664 checkpoints, 3 pending reviews and 373 artifact checksums.

`services/backend/.venv/bin/python tests/restore_resume.py` passed using the copied database and copied artifact store: a pending review finalized with unchanged invocation count and unchanged original episode. `services/backend/.venv/bin/python tests/restore_graph.py` rebuilt 61 nodes/39 edges into a separate retained Neo4j test namespace; canonical version hashes matched and live canonical evidence remained unchanged. Neither test overwrites the live database or projection. Rehearse again after later schema or durability changes.

For recovery after interruption, read BUILD-STATUS.md, retain the existing working tree and database, and run the last documented smoke command. Never paste `.env`, local account files, raw candidate output or source documents into an issue.
