# Restricted schema driver correction

The primary real-state rehearsal, run 43225579792 at e84f2dffbfba0b2b191a0bfbd577daf893dd60c7, ran stock beta.2 Doctor successfully and reached agent versions 38/38 and shared version 36. All databases passed integrity and foreign-key checks. Retained conversation, transcript and memory content passed, as did the four identity files. The post-migration verifier stopped on session_entry_snapshots (4 to 3 records), session_nodes (9 records with changed original content), and session_windows (10 records with changed original content). Reopening was skipped. Only the metadata report survived the failed runner; no migrated database was retained.

The phone's read-only candidate metadata confirmed two skillsSnapshot and two systemPromptReport records. Neither skillsSnapshot contains resolvedSkills or discoverySkills. Thus removal of those runtime catalog fields is not an established explanation for the lost snapshot. The exact changed cells in the failed disposable state remain unknown. This correction does not classify those changes as acceptable.

Pinned beta.2 source c0f42f648144b25b8945b9c56329eb13eb6d7754 separates prepareDoctorDatabaseMigrations in src/commands/doctor-schema-migrations.ts from later session repair contributions. The pinned npm tarball SHA-1 752decdb823486435d8884e655ecbe8fffdfa08c was independently checked during source review. Its compiled exports are used directly, without modifying application modules:

| Operation | Stock export |
| --- | --- |
| Offline exclusive custody | withDoctorSqliteMaintenanceLock |
| Live schema authority assertion | getOpenClawDatabaseMaintenanceScope |
| Verified backups and declared version changes | prepareDoctorDatabaseMigrations |
| Agent-specific maintenance ownership | withAgentDatabaseMaintenanceLease |
| Additive columns and registry admission | ensureOpenClawAgentDatabaseSchema |
| Settle native resources before releasing custody | closeOpenClawAgentDatabasesAsync / closeOpenClawStateDatabaseAsync |

The restricted driver acquires normal Doctor custody for exactly the three disposable paths, validates 25/25/20 before writing, and retains every stock authority assertion. It finishes same-version additive admission under the stock agent lease, closes resources and then releases custody. Full Doctor's later title, routing, snapshot and other session repairs are outside this invocation. No raw SQL repair, forced user_version assignment, application patch or forged authority is introduced.

Before receiving the real input, the workflow runs a single fictional driver regression, including unauthorized-owner refusal, schema gates, integrity, foreign keys and preservation of original session/transcript columns and two cold snapshots. It uses the existing legacy SDK fixture and fictional two-message session, with an additional empty agent. This test is necessary because the migration invocation changed; it does not repeat the previously successful full Doctor experiment.

The real-state verifier is unchanged. Any original session record mismatch still stops the corrective run. If the fictional gate fails, real migration is skipped. If the corrective real migration fails, stop with its exact report; no third migration is authorized. Original production, the migration trial and both checkpoint archives are outside all runner mounts.

Local verification covers pinned export names, constructed Dockerfile, syntax, job ordering and unchanged verifier bytes. The new driver has not yet passed Actions. The next reviewed dispatch is corrective with reviewed_change_commit equal to this correction's commit.
