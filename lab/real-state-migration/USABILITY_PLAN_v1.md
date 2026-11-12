# Saving Private Orion: usability-first plan for review

Status: PLAN ONLY. No migration, deployment, new private-data upload or credential transfer is authorized by publishing this document. The remaining corrective migration is unlaunched. Do not dispatch the current real-state workflow: it still contains the restricted driver that failed on fictional data. After plan review, a new pinned revision will restore the proven stock Doctor invocation and implement the checks below.

## Goal and present decision

GO for the stock Doctor route as the proposed final disposable rehearsal. DSHBox deployment is pending actual functional verification. Success means the main Orion agent runs in DSHBox using the familiar personality and user files, with retained useful knowledge. Perfect retention of historical execution metadata is not required. A real model response, WhatsApp connection and Discord connection are separate checks requiring phone-local credentials.

Current evidence: the stock Doctor primary run 43225579792 exited 0, migrated both agents from 25 to 38 and shared state from 20 to 36, passed all three database integrity/foreign-key checks, preserved three conversations, 652 logical transcript events, 70 memory chunks and all four required identity files. It stopped before SDK reopening or Gateway startup because three session tables differed. Those differences have not been shown to prevent operation, and their exact changed cells are not yet known. The failed migrated state was discarded, so testing usability requires the remaining disposable attempt.

The later restricted-driver experiment failed only on fictional state and will not be extended. It is outside the proposed migration approach.

## Preserve the existing strict evidence first

Preserve the original primary report byte-for-byte. Do not replace its STOP result with a usability verdict.

- Existing artifact: orion_real_state_rehearsal_v1_primary, artifact ID 13947672783, run 43225579792.
- Artifact ZIP SHA-256: 26e9e503c51cc20c997a1d0e867a8a779945f76725f950e71c318a580e3d2700.
- migration-report.json SHA-256: bfc0eb39854cdbb1ca7c47ebcf5cb97d3ea27e3d3c3c8e2bd2f0c3d91cf94ae9.
- GitHub expiry: 19 November 2026, 20:17 WIB. Download into a fresh private phone directory before expiry and verify the JSON hash. This download does not upload private data or modify Orion.
- Keep the existing recovery copy and original checkpoint, production /root/.openclaw and trial /root/orion-beta-trial-20261107/.openclaw untouched.

## One remaining disposable migration, after review

Use the already reviewed eight-file sanitized archive, SHA-256 d991442d8e5175dd2d38eb7402c148507b93d855a5e91d4ffe6038c059bfffd3. No additional real-state export is needed. The input remains read-only, and stock beta.2 runs with networking disabled and ordinary maintenance checks. The command is the previously successful stock Doctor invocation: node /opt/beta/node_modules/openclaw/openclaw.mjs doctor --fix --non-interactive. It runs once, exclusively in GitHub's disposable ARM64 container. Doctor is never run on DSHBox.

Keep verify.mjs unchanged. Run it before migration and save the complete strict result after migration and again after functional checks. Initial corruption, wrong versions, altered identity files, missing conversation/message content, missing useful memory or unexpected credential records stop the process. If the only strict failures are the already identified session_entry_snapshots, session_nodes and session_windows comparisons, preserve them as strict failures and proceed to the bounded usability tests. Do not reinterpret them as strict verification success.

In that same attempt, compare those three tables against input using their original columns and record identities. Report removed/added row counts, changed column names and changed top-level JSON field names. For snapshots, identify the snapshot field type. Keep actual row values, session identifiers and transcript contents out of logs. Preserve the original input on the phone and in its reviewed draft release; historical fields are recoverable there even if Doctor retires them. Record every added, removed or modified output file by path, size and hash.

The review will explicitly cover the returned migrated databases as a new GitHub Actions artifact. No archive containing original credentials, generated client-credential files, channel authentication, complete original configuration or raw application logs will be published. Only the three reviewed database roles, four required identity files and metadata manifests/reports are eligible. Any successful archive is labeled migrated disposable state, pending DSHBox validation; it never grants production cutover approval.

## Bounded functional tests on the migrated copy

1. Reopen the databases through the pinned beta SDK in a fresh process. Require integrity, agent registry agreement and versions 38/38/36. Verify required identity hashes again.
2. Run agents list --json and sessions --agent main --json. Require the main agent to resolve to the migrated workspace, not a newly generated default identity. Confirm the original main/current session identity can be accessed through the SDK and read retained message content. Check other retained histories once and record any failures; do not enter an optional historical-repair loop.
3. Start the stock Gateway bound to loopback with plugins/channels disabled, using a fresh laboratory token. Require the process to stay alive, /healthz to report live and gateway health --json to succeed within 90 seconds. Stop it cleanly and rerun integrity, identity and content checks.
4. Record model inference as NOT TESTED: the rehearsal has no provider credentials and no external networking. Missing API credentials alone is not a storage/startup failure. Actual familiar behavior must be checked on the phone using a locally entered credential after the functional rehearsal and deployment plan are approved.

The runner publishes two separate assessments: the unchanged strict verification result and a usability decision. A strict metadata mismatch is visible in the latter's limitations. No claim of complete historical preservation is permitted when the strict result is STOP.

## Short DSHBox deployment sequence if usable

Prepare an installer only after the final rehearsal result is reviewed. Use the same pinned beta.2 package in DSHBox and a fresh private state directory, for example a uniquely named /root/orion-dshbox-ready-* directory. Set OPENCLAW_STATE_DIR, OPENCLAW_CONFIG_PATH and an explicit Orion workspace path for every command. Do not overwrite /root/.openclaw or the existing trial.

1. Download the verified migrated artifact, check its digest and safely extract only reviewed regular files into the new directory. Preserve the input reports and the four identity file hashes. Never apply filesystem ownership receipts or leftover leases from another runtime as authority.
2. Run read-only integrity/version/identity checks and session access, then start Gateway directly in DSHBox. No Doctor or phone-side schema migration. Validate /healthz and Gateway health under the phone's actual missing-PID-link environment. Any stale absolute-path or ownership refusal stops deployment; do not patch around it.
3. Enter provider authentication locally and ask one short identity/USER.md question plus one known-memory question. Credentials remain on the phone. This confirms an actual response separately from startup.
4. Reconnect channels locally, one at a time, using the pinned version's supported interactive setup. WhatsApp may require a fresh QR/link-device pairing; Discord requires the correct bot token, channel permissions and supported setup. Do not upload old channel sessions or tokens. Before enabling the same accounts, verify that no old Gateway is active. Any required stop of an old production process needs explicit user approval; do not silently stop or reconfigure it. Check one incoming and outgoing message per channel.
5. After those checks, provide a short launcher that always selects the new state directory. Keep old directories and both checkpoints intact. Production cutover or cleanup remains a separate explicit decision.

Rollback is to stop the new isolated Gateway and stop using its launcher. The old installation, trial and backups have not been overwritten. Never run two gateways with the same channel identity while rolling back.

## Decision rules and stopping point

| Decision | Required evidence / action |
| --- | --- |
| GO for DSHBox use | Real phone Gateway and main agent operate, the four original identity files are byte-exact, useful knowledge is available, and the phone can access the current session. Explicitly list any historical metadata loss. Model response and channel readiness are separately labeled until tested. |
| FALLBACK | The remaining stock rehearsal or actual DSHBox startup is unusable, while verified personality/knowledge files remain recoverable. Prepare a clean pinned DSHBox installation in a fresh state directory. Restore the original AGENTS.md, SOUL.md, IDENTITY.md and USER.md; recover useful workspace Markdown and sanitized memory-chunk text into clearly labeled notes. Let the clean runtime build its own databases. Retain old databases and transcripts as archives; do not promise native old-session continuity. Reconnect provider and channel credentials locally. Review this fallback before executing it. |
| STOP | Identity bytes differ, backup verification fails, data corruption appears, unredacted credentials would be transferred, maintenance checks refuse access, or the user pauses. Do not force schema markers, discard the old identity or start another real migration attempt. |

Once the main Orion identity works, stop investigating optional historical session metadata. There is one real corrective migration remaining and no automatic retries. A fallback is a reviewed new-state installation, not another historical migration experiment.
