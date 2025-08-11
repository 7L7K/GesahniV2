Encrypted backups at rest

Overview
- Backups are created via the POST /v1/admin/backup endpoint (requires admin scope and ADMIN_TOKEN).
- Contents: data/*.json, stories/*.jsonl, sessions/archive/*.tar.gz (if present).
- Output directory: BACKUP_DIR (defaults to app/backups/).
- Encryption: AES-256-CBC using OpenSSL with PBKDF2. Fallback to XOR+base64 if OpenSSL is unavailable.

Environment
- BACKUP_KEY: required secret passphrase used to encrypt the tarball.
- BACKUP_DIR: optional, target directory for backup artifacts.

Key rotation
- Rotate BACKUP_KEY by:
  1. Setting a new BACKUP_KEY value.
  2. Trigger a fresh backup to produce a new encrypted archive with the new key.
  3. Optionally decrypt old backups with the old key and re-encrypt using the new key for consistency.

Decrypting
- With OpenSSL:
  openssl enc -d -aes-256-cbc -pbkdf2 -pass pass:$BACKUP_KEY -in backup.tar.gz.enc -out backup.tar.gz

Security notes
- BACKUP_KEY must be managed in your secret store and never checked into version control.
- The redaction substitution maps are stored in data/redactions/ and are included in backups; access to backups must be restricted to trusted operators.


