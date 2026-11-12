# Single corrective restoration attempt

The phone's v1 restoration stopped on the zero-byte file orion-beta-trial-20261107/.openclaw/agents/main/agent/openclaw-agent.sqlite.generation-lock.sqlite. The v1 suffix check incorrectly required this empty companion to have a SQLite header. Database integrity checks had not yet run.

v2 restores and byte-verifies this file just like every other regular file. An empty file ending in .sqlite.generation-lock.sqlite is listed as a preserved empty companion and excluded from database opening only if its corresponding .sqlite file is present with a valid SQLite header. That database must pass the ordinary SQLite integrity and schema checks. An unmatched companion, any other invalid database header, or WAL/SHM files without their matching SQLite database produces STOP.

The original archive hash, reviewed inventory, path checks, skipped symlinks, WAL preservation and schema-25 requirements are identical to v1. v2 creates a fresh private disposable directory. Retain /root/orion-real-rehearsal-432tnuz6 as the failed-attempt record.

Run v2 once as the corrective attempt. Success is exit 0 with RESTORE_PASS. Confirm preserved_empty_generation_lock_companions includes the observed file, main_agent_schema is 25 and every reported database integrity value is ok. Any STOP ends this corrective attempt and requires review before further work.

The phone result is pending. This code change has been tested with generated SQLite fixtures; it establishes no real-state restoration or migration success.
