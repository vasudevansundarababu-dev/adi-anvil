# Modern workspace credentials — local development

The modern workspace's Models & keys page supports Admin-only write-only credential
creation, rotation and revocation. These actions require a sign-in within ten minutes.
Credentials can be bound to model profiles at an exact saved version. A rotated or revoked
version cannot resolve for new dispatch. There is no API to reveal a stored value.

This increment stores encrypted blobs in ignored `.local/workspace-secrets/`, with a
separate randomly generated `wrapping-key.v1`. Directory mode0700 and file mode0600 are
required; descriptor-based traversal refuses unsafe parents and symlinks. The authenticated
envelope binds project, credential, version and provider. PostgreSQL holds metadata and
immutable version references, never plaintext keys. The wrapping key is not a provider key.

Do not copy this directory into Git, reports, raw logs or screenshots. A private recovery
backup must preserve the whole directory, wrapping key and matching database metadata.
Integration with the existing backup/restore command has not yet been qualified; do not
assume a database-only backup can recover credentials. Missing wrapping keys with existing
ciphertext fail closed instead of generating a replacement. Restore an owner-controlled
matching backup or configure new credentials; no recovery of lost key material is promised.

An interrupted database save can leave an inert ciphertext orphan. It grants no authority
and is not listed as a credential. Automatic pruning is not implemented. Rotation preserves
older ciphertext and metadata for provenance; historical run evidence is never rewritten.

Cloud entry is explicitly disabled pending a managed secret-store adapter and separate
provisioning authority. Existing private provider files remain a separate legacy path.
New workspace model profiles are blocked from legacy dispatch so a selected credential
can never silently be replaced with the global provider key. Full broker/profile admission
is a later milestone. Saving any credential/profile enables no inference, SDK install,
external trace transmission or spending authority.

All credential verification so far uses clearly labeled test-only values and encrypted
temporary/local test storage. No real model key has been supplied or paid call performed
under the modern-workspace build authority.
