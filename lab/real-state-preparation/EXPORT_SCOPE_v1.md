# Local sanitized candidate review v1

This stage prepares a local candidate from the successful disposable restoration /root/orion-real-rehearsal-9a_4zlyq. It has no transfer, archive-packing or OpenClaw command. The checkpoint, recovery archive, original production and existing trial are outside its write targets.

## Exact file scope

The candidate contains three rebuilt databases at their normal state-relative paths:

- agents/main/agent/openclaw-agent.sqlite, schema 25
- agents/openclaw/agent/openclaw-agent.sqlite, schema 25
- state/openclaw.sqlite, schema 20

It includes workspace Markdown files inventoried in the restored archive, excluding node_modules, .git, extensions, plugins, tmp, caches and skills. The four direct workspace files SOUL.md, IDENTITY.md, AGENTS.md and USER.md must be present. If a required identity file needs redaction, preparation stops for review.

The candidate excludes original configuration, channel credentials and authentication sessions, plugins and installed code, caches, logs, quarantine storage, temporary plugin captures, generation-lock companions, non-Markdown workspace assets and workspace skills. Its manifest lists the exact included files and their hashes. The future workflow will create its own minimal config.

## Agent database rules

All agent tables and their rows are retained except auth_profile_state, auth_profile_store, cache_entries and memory_embedding_cache. Excluded table schemas remain present with zero rows.

The provided baseline has three cache entries and 128 embedding-cache entries to exclude. The 70 memory chunks, their embeddings and provenance remain in scope. The 819 trajectory events remain in scope along with all conversation, session, transcript and identity records.

All retained text is checked for known credential values harvested locally from the disposable databases and configuration/credential JSON. Credential fields and recognizable token, authorization and private-key patterns are redacted. JSON and zstd transcript payloads are both decoded and processed. Any transcript redaction is a reported content change with stable record identity and count.

The program stops on an unreviewed retained binary column. Allowed binary data is limited to decoded/re-encoded transcript compression, memory chunk embeddings and profile avatars. These allowed raw blobs are also checked for known credential bytes.

## Shared database data allowlist

Only these tables retain rows:

- agent_databases
- agent_provenance
- audit_events
- schema_meta
- session_groups
- session_state_events
- session_state_heads
- session_upstream_links
- session_watch_cursors
- skill_usage
- skill_workshop_changes
- state_leases
- user_profiles
- user_profile_identities
- worker_session_placements
- workspace_generated_bootstrap_hashes
- workspace_path_aliases
- workspace_setup_state

All other shared tables retain their schemas and have their rows removed in the candidate. The report lists every excluded nonempty table and its original row count, including device authentication/private identities, config snapshots/HMAC keys, pairing state, plugin state, channel ingress/delivery queues, diagnostics and cron jobs.

State lease rows are retained for the stock migration to evaluate. No lease check is bypassed. Agent registry paths are explicitly rebased to /home/replay/.openclaw/agents/<agent>/agent/openclaw-agent.sqlite for the tested Actions container. Both registrations retain schema 25.

Retained structured shared data is subject to the same credential checks and redaction. This scope represents a migration rehearsal subset. Original channel integration and runtime configuration remain in the private recovery archive.

## Rebuild and verification

Source databases use read-only SQLite handles. SHA-256 checks bind each main file to inventory-v1.json and each WAL to the restoration manifest. SQLite backup incorporates committed WAL data into separate working copies.

The program sanitizes the working copies, rebuilds and optimizes FTS5 indexes, checks foreign keys, and uses VACUUM INTO to produce fresh candidate database files. It verifies integrity, original schema versions, exclusion of credential/cache rows and recognizable credential bytes, and logical fingerprints of every retained table. Physical rowids in ordinary tables are excluded from logical fingerprints. Declared identities and transcript sequence values are included. FTS rowids are preserved in their fingerprints.

Transcript fingerprints decode JSON/zstd into canonical logical events, preserving session and event sequence identity across representation changes. The candidate manifest contains sanitized per-table counts and fingerprints for later migration comparison. Original-content HMAC fingerprints and the random HMAC key stay outside the candidate directory.

Source main files and WALs are checked again after preparation. Required identity-file bytes must match their restoration hashes exactly. Every candidate file has an explicit path, size and SHA-256 in the manifest.

## Local outputs and review gate

The new /root/orion-export-review-* directory contains:

- candidate/ with only the proposed files and manifest.json
- export-review.json with counts, excluded tables and changed-cell counts
- private-original-baseline.json with keyed original-record fingerprints
- private-fingerprint.key
- private diagnostics or intermediate files if preparation stops

The parent directory and private files are local recovery/review materials. Only the explicitly reviewed candidate scope may become a later transfer archive.

Successful preparation prints EXPORT_CANDIDATE_REVIEW_REQUIRED with upload_ready=false. Review the exact candidate manifest, exclusions, redaction counts and any content changes before approving packing or transfer.

Credential scanning provides specific checks, not a proof that arbitrary natural-language text or opaque encodings contain no secrets. Any unresolved finding or redaction affecting required identity files requires review. A STOP reports its stage, database/table when known and error code, with raw details kept locally.

The next gate is approval of the candidate manifest and changes. No real-state migration has occurred at this stage.
