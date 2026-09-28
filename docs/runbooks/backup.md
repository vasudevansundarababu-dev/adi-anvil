# Backup and restore rehearsal

`pnpm backup:local` uses a repeatable-read exported PostgreSQL snapshot with `pg_dump`, then copies canonical artifact files and records SHA-256 checksums and record/checkpoint counts. Output is owner-only under ignored `.local/backups/`; `.local/latest-backup` selects the latest backup. Credentials and raw logs are not included. Backups still contain private application data and must remain local.

`pnpm restore:test` verifies the backup and creates a fresh `anvil_restore_<random>` database. It never overwrites the application database or deletes volumes. It restores rows/checkpoints and checks counts and copied artifact checksums. Retained test databases are listed in command output. Graph data is rebuildable and is not canonical backup evidence.

The original checkpoint of this build verified a restore with 102 checkpoint records, 3 pending reviews and 31 artifact checksums. That evidence predates later migrations. A newer rehearsal is required before accepting the final build. A passed checksum/count check alone does not prove restored worker resume; record that separate result honestly.

For recovery after interruption, read BUILD-STATUS.md, retain the existing working tree and database, and run the last documented smoke command. Never paste `.env`, local account files, raw candidate output or source documents into an issue.
