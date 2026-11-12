# Orion real-state rehearsal preparation v1

Status is PREPARATION ONLY. Phone-side checkpoint verification, recovery-copy creation and export approval are pending.

## Existing evidence

[Run 43154734394](https://github.com/jaqenhghar77777-dev/orion-doctor-lab/actions/runs/43154734394) succeeded at source commit bcd245c21677ecafb5d83ea4266bcc3e7fbe19db. It migrated populated synthetic state with stock beta.2 on native ARM64 Linux, transferred it between independent containers, verified both SQLite databases and the original two messages, and obtained Gateway health. The executable synthetic ZIP passed with beta.1 and beta.2 under simulated missing PID links.

The user's actual DSHBox output records beta.1, Node 24.19.0, Linux ARM64, a missing PID link, two healthy databases at schema 38, the same two fictional messages, and SYNTHETIC REHEARSAL PASS. Gateway operation on that phone remains unverified.

The rehearsal will reuse the ordinary-Linux migration approach. The proposed migrator is the existing pinned stock beta.2 package, SHA-1 752decdb823486435d8884e655ecbe8fffdfa08c. DSHBox reopening uses the existing beta.1 package. This version choice is part of this plan's review. Ownership checks run normally.

## Boundary and review order

The source for the proposed rehearsal is the checkpoint /root/orion-beta-trial-pre-migration-20261107.tar.gz. The checkpoint's name and reported verification are historical evidence. Its actual hash, archive structure, database versions and recoverability require fresh checks.

Production /root/.openclaw and the existing migration trial /root/orion-beta-trial-20261107/.openclaw are excluded from the commands and exports in this plan. A checkpoint-based rehearsal establishes continuity relative to that checkpoint. Later conversations require a separate decision.

First review this proposed export scope and recovery procedure. Next run checkpoint_inspect_v1.py locally against the checkpoint. It reads the archive, verifies the gzip trailer/CRC, measures its SHA-256, inventories database candidates, and hashes the four named identity files. It extracts no files and has no network operations. Its JSON contains metadata and fingerprints. It deliberately reports upload_ready=false.

## Recovery procedure before export

1. Compare the measured archive SHA-256 against an independently retained digest if one exists. A newly measured hash establishes a baseline and does not prove earlier provenance.
2. Check free space for the compressed recovery copy, a complete restored copy, the sanitized export and working SQLite files.
3. Create a uniquely named private directory outside all protected paths. Copy the checkpoint into a new file opened exclusively. Hash source and recovery copy independently, require equality, flush the copy and its directory, and verify the source metadata stayed stable.
4. Restore the recovery copy into another new private directory. Validate every archive path before extraction. Review links, duplicate names and special files. Use ordinary file creation with restricted permissions and omit archive owner/group restoration. Reject any link or path that can escape the restoration directory.
5. Check every restored SQLite database with read-only SQLite access, preserving WAL companions. Require integrity_check=ok. Record user_version and registered agent schema, including which databases are actually schema 25. Stop on unsupported/encrypted/corrupt databases or inconsistent versions.
6. Record counts, logical record identities, ordered transcript fingerprints and identity-file hashes. Review all missing identity files explicitly. Restore success requires both archive recovery and these database checks.

Raw restored data and the independent recovery copy stay on the phone. All redaction takes place in a second disposable clone of this recovered state.

## Proposed export manifest for review

| Candidate | Treatment |
| --- | --- |
| Agent SQLite databases at schema 25 | Export only after table/column inspection and credential redaction on the disposable clone |
| Shared SQLite state | Retain migration-required registration and session relations, remove authentication/provider/channel secrets |
| Other SQLite databases | Inventory locally first, include only an identified migration or continuity dependency |
| SOUL.md, IDENTITY.md, AGENTS.md, USER.md | Include reviewed copies with original and exported fingerprints and any redactions recorded |
| Other memory markdown and transcript files | Inventory and review, include when needed for conversation continuity, scan for embedded secrets |
| OpenClaw JSON config | Generate a minimal rehearsal config with explicit agent/workspace mapping, plugins disabled and no real provider/channel authentication |
| Channel credential directories and session state | Exclude WhatsApp authentication, Discord tokens, cookies, credential stores, auth profiles and OAuth material |
| Environment files, secret files, private keys, logs, caches, installed code and plugins | Exclude |
| Manifest and verification baselines | Include reviewed relative paths, sizes, checksums, counts, logical fingerprints and the redaction/change ledger |

This is a proposed file-class manifest. The final exact file, table and column allowlist will be derived from the restored checkpoint and reviewed before packing or transfer. An unknown table or opaque blob remains excluded pending classification. Absence of a regex match does not establish absence of credentials.

Credential review covers JSON payloads, transcripts, identity text, attachments and database rows as well as filenames. Anything requiring credential redaction must be reported. Deterministic identifier mappings must preserve foreign-key and cross-file relationships.

SQLite export requires rebuilding the sanitized database into a fresh file and rebuilding or explicitly excluding derived search data. Deleted rows, free pages, WALs and journals can retain previous values. Verify the rebuilt file and scan it again. Upload only the final rebuilt databases and reviewed text files.

Maintain two baselines. The private original-versus-sanitized ledger identifies deliberate exclusions and redactions. The exported sanitized baseline is the migration comparison input. Use local keyed fingerprints where original content or identifiers would otherwise be exposed. Never upload the key or secret values. CI compares canonical logical records from the sanitized baseline and preserves record identity, message order and message content.

Any required redaction of conversation content is an explicit change in the report. Matching post-migration counts alone cannot establish continuity or absence of data loss.

## Transfer and Actions design after export review

Use a uniquely named temporary draft release asset for the sanitized input archive and a separate expected SHA-256. Phone authentication uses the user's GitHub CLI credential store. Credentials stay outside the input archive, workflow inputs and logs.

A manual workflow_dispatch run in the existing repository will retrieve the asset with its scoped Actions token, verify its exact digest and manifest, and check the sanitized baseline before migration. Input state is fetched during job execution and stays outside Git history. Repository administrators and authorized Actions users can access retained inputs and artifacts. Review release/artifact retention and cleanup with the input manifest.

Reuse the native ubuntu-24.04-arm runner and the tested pinned package-building code. Fetch dependencies before exposing the input to application code. Run migration in an unprivileged container with networking disabled, capabilities dropped, a read-only root filesystem and explicit writable disposable state. Point HOME, XDG paths, config and state to that disposable directory. Keep input and baseline mounted read-only.

The existing synthetic workflow is a reference, not the real-state workflow. Its seed, hardcoded fictional session checks, raw CLI log tail and synthetic ZIP publication need replacing. Real-state logs must show aggregate results and identifiers/fingerprints approved in the manifest. Raw exception text and CLI output can contain transcript or token material and require local redaction before becoming an artifact.

One primary migration attempt is allowed. On any failed verification, stop and preserve the sanitized diagnostic evidence. One corrective attempt may follow only after the exact cause and correction are reviewed. Infrastructure retries must be recorded and cannot hide an application or data verification failure.

## Required comparison and report

- Before migration require valid input digests, a schema 25 agent baseline, healthy SQLite files and complete inventory.
- After migration require agent schema 38, consistent shared registrations, SQLite integrity and foreign-key checks where applicable.
- Compare every retained conversation/session identity, ordered event count and canonical content fingerprint. Classify intentionally changed schema-derived representations explicitly.
- Compare retained memory records and all reviewed identity-file bytes. Missing original files are recorded as baseline facts, with review disposition.
- Reopen the migrated disposable copy through the supported SDK and sessions CLI. Verify all retained logical conversations with bounded pagination. Confirm that read/reopen checks introduce no unexplained changes.
- Produce a complete file inventory diff across input and output, including additions, removals, changed hashes and sizes, databases/WALs, config, generated files and identity files.
- Report original-to-sanitized exclusions and redactions separately from sanitized-to-migrated changes. Identify every loss, mismatch or unverified item.
- Return only reviewed migrated state and redacted diagnostics as artifacts. Keep successful artifacts only for the agreed retention period.

## Rehearsal rollback

On failure, freeze the disposable migration output for diagnosis and stop. Reconstruct a new disposable working copy from the verified recovery archive and repeat its integrity, schema and fingerprint checks. Replacing or deleting production is outside rehearsal rollback. Keep the recovery archive and its checksum available independently of GitHub retention.

A later production cutover and production rollback procedure require a separate approved plan with current-state checks. This rehearsal ends with a verified disposable migrated copy and its report.

## Pending gates

Plan review → checkpoint inspection → independent recovery copy → isolated restore verification → exact export allowlist and redaction review → sanitized export approval → transfer → one migration rehearsal → report.
