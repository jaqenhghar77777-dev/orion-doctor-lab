# Real-state migration rehearsal v1

Prepared for the reviewed sanitized input archive with SHA-256 d991442d8e5175dd2d38eb7402c148507b93d855a5e91d4ffe6038c059bfffd3 and manifest SHA-256 38cc930e6aa93cb14b0eb6f7f0e4b9babf51ab1bf95ceef34cd70d554e7864ad. The archive is 2,744,028 bytes and contains exactly eight regular files.

## Transfer gate

Install and authenticate GitHub CLI in the existing DSHBox environment. Use its browser/device login and keep credentials in its local credential store. The sanitized archive is the only upload. The parent export directory contains private keys and original baseline material and is outside transfer scope.

After authentication, create a temporary draft release named orion-rehearsal-input-20261112-v1 in jaqenhghar77777-dev/orion-doctor-lab, targeting the reviewed workflow commit. Attach only orion_sanitized_rehearsal_v1.tar.gz. Verify the receipt checksum before upload and verify the remote asset checksum before dispatch. Publish neither the draft release nor original state.

A separate input-download job uses contents: write because GitHub draft release listings require push access. That job has no checkout or application execution and performs only release reads, exact archive size/hash verification and a one-day artifact handoff. The migration job retains contents: read and actions: read. The input stays outside Git history. Its exact length, archive digest, manifest digest, file set and file hashes are checked before use.

## Manual run and attempt budget

orion-real-state-rehearsal.yml runs only through workflow_dispatch. A primary migration and one reviewed corrective migration are permitted. Prior setup-only failures remain in Actions history and can be retried with a fresh dispatch. A workflow rerun is stopped at the gate. A corrective run requires exactly one failed primary migration, no prior corrective migration, and a reviewed_change_commit equal to the current workflow commit.

The input-download job precedes the migration job. Dependency installation in the migration job runs before its copy of the input artifact is downloaded and extracted. The ordinary ARM64 Linux container uses the stock beta.2 tarball pinned by SHA-1 752decdb823486435d8884e655ecbe8fffdfa08c and Node 26.12.1 from the previously verified runtime recipe. There is no package instrumentation or ownership bypass. A legacy stage builds only fictional regression fixtures for the restricted schema driver.

Application commands execute as UID 10001 with networking disabled, capabilities dropped, a read-only root filesystem and writable disposable home/temp/output directories. The input mount is read-only. GitHub credentials are outside the application container.

The job creates a minimal canonical config declaring main and openclaw agents with plugins disabled. Its explicit token is the synthetic laboratory token. The real-state input supplies no original configuration or channel authentication.

## Verification gates

Before the real input is downloaded into the migration job, a fictional regression gate runs the same schema driver. It checks refusal without Doctor ownership, both agent schema upgrades, shared schema upgrade, integrity, foreign keys, both cold snapshot records, and all original columns in session nodes, windows and transcript tables. A failed gate skips the real migration and does not consume a real migration attempt.

Before migration, all three input databases must match their recorded logical fingerprints and schema versions 25/25/20. SQLite integrity and foreign-key checks must pass.

The corrective run calls the pinned stock prepareDoctorDatabaseMigrations export under withDoctorSqliteMaintenanceLock, then finishes additive schema admission under the stock agent maintenance lease. It does not run the full Doctor CLI or later session repair contributions. Both the Doctor authority and its live schema-maintenance scope are asserted before and after migration, additive admission and resource closure. All stock migration ownership checks and pre-migration backups remain active. Doctor is never invoked on DSHBox by this workflow. The legacy doctor_exit field records the driver exit for compatibility; migration_exit and doctor_cli_run identify the actual invocation.

The required output versions are agent schema 38 for both agents and shared schema 36. Agent registry versions must agree. All four identity files must retain their input hashes.

Every populated input application table is compared using its original columns, logical record identities and content. Transcript JSON/zstd representations are decoded canonically for comparison. New additive columns do not invalidate existing records. Removed populated tables, removed data columns or altered application records stop verification. Existing audit records must remain; audit additions are reported.

Schema metadata, registry/lease lifecycle, memory revisions, FTS/search indexes and transcript index state are reported separately. Memory revision singleton identity is preserved and revision regression is rejected. These fields can legitimately change under the stock migration and opening lifecycle.

Originally empty tables may acquire generated runtime records. Known authentication/secret tables must remain empty. Unrecognized SQLite verification errors stop the run. The report identifies any verification failure through fixed codes and context without printing record contents.

The SDK must open current session entries with their retained session IDs and read each historical transcript window with stored events. SDK arrays must be nonempty for nonempty stored histories. Separate logical database comparison covers every stored event. The sessions CLI must return JSON for each agent. These checks establish database continuity and application accessibility; they do not establish live WhatsApp/Discord connectivity.

After reopening, verification runs again. SQLite backup creates quiescent final database snapshots for the returned archive. The full before/after file inventories include size, mode and SHA-256. Added, removed and modified files are enumerated.

## Results and rollback

Only the metadata report and a verified successful output archive are retained as Actions artifacts, for seven days. Raw application output and diagnostics stay in the ephemeral private runner directory. Failed output state is excluded from artifacts.

The returned report uses the sanitized candidate as its comparison baseline. Its sanitization_changes ledger records the earlier exclusions and the 14 transcript-event/one memory-chunk redactions. A successful result cannot establish byte identity with original unsanitized conversation content.

Any application/check failure ends the attempt with STOP. Review its exact stage and verification codes before the single corrective attempt. Recovery reconstructs a fresh disposable copy from the phone's verified independent recovery archive. Production, the existing migration trial and both checkpoint archives remain outside this job's filesystem mounts.

After the output archive is retrieved and verified on the phone, review the migration report and clean up the temporary draft input release. A separate explicit approval and current-state plan are required for any future production cutover.

Setup run #43224148902 built the pinned runtime but stopped before migration because its read-only token could not list the draft release. Doctor was skipped and no migration attempt was consumed. The permission repair separates the input-download job from the read-only migration job. The draft asset is already uploaded and its SHA-256 matches. Status is PREPARED for a fresh primary dispatch; the permission repair has static checks but is not yet verified in Actions.

Primary real-state run #43225579792 reached 38/38/36 with integrity and content/identity checks passing, but stopped on three session-table mismatches. Reopening was skipped and no migrated archive was retained. The restricted-driver correction leaves verify.mjs unchanged and is limited to the single corrective real-state attempt. See CORRECTION_v1.md for the evidence and remaining uncertainty.
