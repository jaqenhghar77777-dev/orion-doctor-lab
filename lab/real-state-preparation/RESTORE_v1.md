# Verified recovery restoration v1

This stage restores the independently copied checkpoint into a new private directory under /root/orion-real-rehearsal-*. The source is /root/orion-recovery-n3hz4fpf/checkpoint.tar.gz, expected SHA-256 daccf87f3dc4173d7ee52e300d33546e82d73d2cdf279a69c57f8f22df06707c.

The reviewed inventory is 45,923 regular files, 1,364 directories, 24 symbolic links, zero hard links and zero special entries. The script requires those counts and validates the full gzip stream.

All symbolic links are skipped. Hard links, special entries, absolute paths, parent traversal, duplicate names and non-directory ancestors produce STOP. File creation is exclusive inside the newly created directory. Archive ownership, group permissions and special permission bits are discarded. Regular files retain their bytes and optional owner-execute bit. Every restored file is read back and SHA-256 verified. SQLite WAL and SHM companions are copied as regular files.

The script uses Node's built-in SQLite API with read-only handles against the disposable files. It discovers SQLite headers and rejects invalid files bearing SQLite/database extensions. Every discovered database must pass PRAGMA integrity_check. Exactly one main agent database must exist and its user_version must equal 25. Other database versions are reported without assuming they use the agent's schema numbering. WAL and SHM companions require their matching database.

Read-only SQLite handles may update shared-memory sidecars in the disposable directory. The restoration manifest records the copied archive bytes before those checks.

## PASS

- The archive matches its SHA-256 and reviewed inventory and stays stable throughout restoration.
- All regular files are restored and byte-verified in the fresh private directory.
- The 24 symlinks are skipped and all WAL/SHM companions have matching databases.
- Every SQLite integrity check returns ok and the main agent schema is 25.
- The command exits 0 and prints result RESTORE_PASS.

The output identifies the restored_state path, per-database schemas and companion counts. restored-files.jsonl contains the local file hashes. restore-report.json records the result. upload_ready remains false pending export review.

## STOP

Any checksum, archive, path, write, database, schema or timeout failure stops the command with a nonzero exit status. The report includes the failing stage and retained disposable directory when one was created. SQLite failures include the database path, check and error code. Raw engine details stay in sqlite-private-diagnostic.txt inside the private disposable directory.

Retain a failed disposable directory for diagnosis. Stop after a failure and review its result before any corrective attempt. Original archives, production and the existing migration trial are outside restoration targets. The program invokes no OpenClaw CLI and contains no upload operation.

The next gate after RESTORE_PASS is the reviewed table/column inventory and sanitized export preparation. This restoration stage ends before migration.
