# Bounded beta.1 Gateway diagnostic

The phone's stock TUI conversation remains blocked. This laboratory experiment did not identify the failing ownership branch.

## Existing phone evidence

- Gateway health and TUI connection pass.
- One explicit session creation passes.
- The first send in that session reports “Live input changed its captured database owner”.
- The isolated shipped live-input reader passes on DSHBox.
- In that isolated test, SQLite's native filename equals both the requested path and Node's realpath and identifies the same file.
- External observation found a stable inode and canonical path.
- Existing Gateway logs contain the live-input and submitted-input errors without stack frames.

## Executed laboratory work

Pinned OpenClaw 2026.11.5-beta.1 npm tarball, SHA-1 cc6d3b105b938acaf9301f17daa3985acd29fce0, Node 24.19.0, Linux ARM64.

Instrumentation adds trace statements at capture, resolution, both guard throws, and active transcript-reader selection. The original throw statements and ownership assertions remain. Fictional local fixtures exercised both refusals and a matching-target success.

The first build stopped before Gateway startup because compact published JavaScript differed from a source formatting anchor. Correcting that anchor allowed the build in run 43377305466 to succeed.

Run 43377305466 executed the disposable networkless Gateway experiment with a local mock provider. The runner was configured for one session creation and at most one chat.send. No private input or phone credentials were supplied.

The finalizer failed before emitting its in-memory report, with:

    sqlite3.OperationalError: unknown function: octet_length()

Debian's Python SQLite could not evaluate the application schema during PRAGMA integrity_check. The container was removed, so the captured trace and request counters are unavailable. Session creation, actual send count, model request count, reader selection, path comparisons and guard branch cannot be asserted from this run.

## Diagnosis and proposed change

The confirmed new failure is in the diagnostic finalizer. It is not evidence of an OpenClaw or PRoot ownership defect.

The diagnostic is corrected to print collected evidence before inspection and use Node's SQLite implementation for optional integrity checking. That correction is syntax-checked and its Node inspection expression is tested locally. It has not been executed against another Gateway.

No OpenClaw runtime fix is justified yet. If future evidence establishes a producer passing a different database locator than the admitted transcript reader, the minimal repair should correct that producer handoff while preserving the ownership guard. The exact producer and repair remain unknown.

Automatic push execution is disabled. No second Gateway experiment was launched after the report failure. Production state, phone Gateway state, v2 chat, memories, credentials and backups were outside the lab.
