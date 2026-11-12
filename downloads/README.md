# DSHBox synthetic rehearsal v1

Verified by [ARM64 run 43154734394](https://github.com/jaqenhghar77777-dev/orion-doctor-lab/actions/runs/43154734394), source commit `bcd245c21677ecafb5d83ea4266bcc3e7fbe19db`.

`orion_dshbox_synthetic_rehearsal_v1.zip` is the exact 72,018-byte Actions artifact 13915736233.

SHA-256 `48044a176f5041593f47f4e3a07dcf17686385cc861759b6d1f9e35e7383c3e5`.

## Completed verification

- Stock beta.2 migrated populated synthetic agent schema v25 to v38 on normal ARM64 Linux.
- A fresh container with the PID link simulated as missing read the two original fictional messages and answered a Gateway health request.
- The executable ZIP passed on beta.1 and beta.2 with the missing link simulated.
- Both SQLite integrity checks and fictional workspace checksums passed.

## Next phone step

Run the ZIP in DSHBox, optionally passing the existing beta package directory as its sole argument. An extracted ZIP directory also works as the Python entry point.

The launcher creates a new temporary home, config, cache and synthetic state. It reads the bundled messages through the selected SDK and lists the fictional session through the CLI. It checks database integrity before and after. Its CLI invocation is `sessions --agent main --json`.

Expected completion is `SYNTHETIC REHEARSAL PASS`. Record the `PACKAGE`, `RUNTIME`, `DATABASES`, `SESSION` and final result lines. If it stops, retain its diagnostic output.

## Remaining verification

- Actual DSHBox/PRoot execution of this ZIP.
- A private migration environment suitable for the eventual real-state copy.
- Backup/restore validation and live continuity checks before any real migration.

The synthetic test establishes neither a completed phone migration nor WhatsApp/Discord connectivity. Production migration requires a separate reviewed plan and explicit approval.
