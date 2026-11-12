# Fictional-only schema driver diagnosis

## Result

The original failure was reproduced once on fictional data in [Actions run 43230350280](https://github.com/jaqenhghar77777-dev/orion-doctor-lab/actions/runs/43230350280), diagnostic commit 9bd85cc70392b180aa00c864e706f0760a2bbf39. The run used stock beta.2, Node 26.12.1, ARM64 Linux and the existing legacy fictional fixture with two messages, two cold snapshots and an empty second agent. It did not retrieve the real sanitized archive or invoke the real-state workflow.

| Captured field | Value |
| --- | --- |
| Driver operation | acquire stock agent maintenance lease |
| Exception type | Error |
| Exception code | null; no code property supplied |
| Sanitized message | Client credentials require backed-up migration custody; stop the app and run openclaw doctor --fix. |
| Exact throwing function | prepareClientCredentialMigration |
| Compiled location | client-credential-migration-EUv7uHDA.mjs:223:117 |
| Calling operation | shared-state schema migration transaction during agent lease acquisition |
| Process result | exit 1, as expected for the reproduced refusal |

The quoted message is diagnostic evidence, not an instruction to run Doctor on DSHBox.

## Cause and call sequence

1. The negative ownership probe passed: the stock migration helper refused execution without Doctor maintenance ownership. The fixture database bytes remained unchanged by this probe.
2. The positive path acquired the normal Doctor maintenance owner and passed the driver's live schema-authority assertions.
3. The driver called prepareDoctorDatabaseMigrations with shared schema 20 to 36 and agent schema 25 to 38 descriptors. This internal helper depends on the complete Doctor orchestration; it is not a general schema-only migration API.
4. In backupDoctorMigrationDatabases, the native version-only fast path requires resolveSchemaMigrationBackupTables to return a complete scope for every requested destination version. The pinned declarations omit shared versions 21, 22, 24 and 25, and agent version 26. The resolver therefore returns undefined for these upgrade ranges. The migrationTables map is cleared, and the native backup result has no versionMigrations list.
5. prepareDoctorDatabaseMigrations sees no version migrations and returns from its early branch. The optional additive preparation in that branch also returns immediately because this standalone driver has no updater migration capture. Consequently that helper call did not complete the declared version upgrade.
6. The driver's next operation, withAgentDatabaseMaintenanceLease, initializes shared state. That initialization enters the shared schema migration transaction and calls prepareClientCredentialMigration for the old schema.
7. The client-credential guard requires live schema-maintenance ownership and a current, generation-bound backup capture for the exact database path. That compound guard refused the call, yielding the captured Error. The diagnostic did not serialize the private capture object, so it does not identify the individual failed operand of that guard.

The actionable integration defect is the restricted driver's use of an internal migration helper outside the complete stock Doctor migration orchestration, followed by ordinary agent-lease acquisition. This is not evidence of corrupt Orion data or a failure of maintenance ownership protection. No guard should be disabled to work around it.

## Evidence sources

All stock source references are pinned to beta.2 commit c0f42f648144b25b8945b9c56329eb13eb6d7754:

- [Version migration helper](https://github.com/openclaw/openclaw/blob/c0f42f648144b25b8945b9c56329eb13eb6d7754/src/commands/doctor-schema-migrations.ts)
- [Backup orchestration and versionMigrations publication](https://github.com/openclaw/openclaw/blob/c0f42f648144b25b8945b9c56329eb13eb6d7754/src/commands/doctor-migration-backup.ts)
- [Complete-scope resolver](https://github.com/openclaw/openclaw/blob/c0f42f648144b25b8945b9c56329eb13eb6d7754/src/state/schema-migration-backup-scope.ts)
- [Declared per-version scopes](https://github.com/openclaw/openclaw/blob/c0f42f648144b25b8945b9c56329eb13eb6d7754/src/state/schema-migration-backup-tables.ts)
- Client-credential guard in the checksum-verified npm tarball, SHA-1 752decdb823486435d8884e655ecbe8fffdfa08c, compiled location above; source region src/infra/client-credential-migration.ts.

## Boundaries and remaining uncertainty

Only the separate diagnostic workflow, its build-context instrumentation script and this report were added. The original migration driver, real-state workflow and preservation verifier were not changed by this diagnosis. Instrumentation changed only a temporary driver copy; stock package modules and checks were untouched. Error messages, causes and stack traces are sanitized for token/password/secret patterns, private-key blocks and URLs.

The one diagnostic run had no real-state archive download, filesystem bind mounts or application networking. Production, the existing migration trial, both checkpoints and the phone's export candidate were not accessed. No new real migration attempt was started. The remaining real corrective attempt remains unused.

This diagnosis explains SCHEMA_DRIVER_FAILED in the fictional restricted driver. It does not explain or accept the three session-table differences from the earlier full Doctor real-state rehearsal. No repair was applied, no preservation check was relaxed, and no further diagnostic or migration run was dispatched.
