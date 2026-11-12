"""Run one offline migration against a disposable copy and emit reviewed report data."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile

INPUT = Path("/input")
STATE = Path("/home/replay/.openclaw")
PUBLIC = Path("/output/public")
PRIVATE = Path("/tmp/orion-private")
CLI = "/opt/beta/node_modules/openclaw/openclaw.mjs"
ARCHIVE_SHA = "d991442d8e5175dd2d38eb7402c148507b93d855a5e91d4ffe6038c059bfffd3"


def digest(file):
    h = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inventory(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ValueError("OUTPUT_SYMLINK")
        for name in files:
            file = Path(directory) / name
            if file.is_symlink() or not file.is_file():
                raise ValueError("OUTPUT_FILE_TYPE")
            result[file.relative_to(root).as_posix()] = {"bytes": file.stat().st_size,
                "mode": format(file.stat().st_mode & 0o777, "04o"), "sha256": digest(file)}
    return result


def run(command, label, timeout):
    with (PRIVATE / (label + ".log")).open("wb") as log, (PRIVATE / (label + ".stderr")).open("wb") as errors:
        process = subprocess.Popen(command, stdout=log, stderr=errors,
                                   start_new_session=True, env=os.environ.copy())
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise ValueError("COMMAND_TIMEOUT")


def main():
    os.umask(0o077)
    if os.getuid() == 0 or str(STATE) != os.environ.get("OPENCLAW_STATE_DIR"):
        raise ValueError("RUNTIME_ISOLATION")
    PUBLIC.mkdir(mode=0o755)
    PUBLIC.chmod(0o755)
    PRIVATE.mkdir(mode=0o700)
    manifest = json.loads((INPUT / "manifest.json").read_text())
    report = {"result": "STOP", "input_sha256": ARCHIVE_SHA, "migrator": "2026.11.5-beta.2",
              "attempt": os.environ.get("ORION_ATTEMPT"), "correction_reason": os.environ.get("ORION_REASON", ""),
              "migration_driver": "stock schema phase and additive admission under stock Doctor/agent maintenance ownership",
              "doctor_cli_run": False,
              "comparison_baseline": "reviewed sanitized candidate after 14 transcript-event and 1 memory-chunk redactions",
              "sanitization_changes": manifest["changes"], "checks": {}}
    stage = "copy"
    try:
        STATE.mkdir(mode=0o700)
        for item in manifest["files"]:
            file = STATE / item["path"]
            file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(INPUT / item["path"], file)
            file.chmod(0o600)
        config = {"gateway": {"mode": "local", "auth": {"mode": "token", "token": "synthetic-doctor-replay-token"}},
                  "plugins": {"enabled": False},
                  "agents": {"entries": {"main": {"default": True}, "openclaw": {}}}}
        (STATE / "openclaw.json").write_text(json.dumps(config))
        before_files = inventory(STATE)
        stage = "before"
        before = PRIVATE / "before.json"
        code = run(["node", "/opt/real-lab/verify.mjs", "before", str(INPUT), str(STATE), str(before)], "before", 180)
        report["checks"]["before"] = json.loads(before.read_text()) if before.exists() else {"result": "STOP"}
        if code:
            raise ValueError("BEFORE_VERIFICATION_FAILED")
        stage = "doctor"
        code = run(["node", "/opt/real-lab/schema-only.mjs"], "doctor", 600)
        report["migration_exit"] = code
        report["doctor_exit"] = code
        report["doctor_log_sha256"] = digest(PRIVATE / "doctor.log")
        report["doctor_error_log_sha256"] = digest(PRIVATE / "doctor.stderr")
        if code:
            diagnostic = (PRIVATE / "doctor.log").read_text(errors="replace") + (PRIVATE / "doctor.stderr").read_text(errors="replace")
            known_errors = ["StateDatabaseAccessError", "StateDatabaseOfflineMaintenanceError",
                            "StateDatabaseAdmissionPendingError", "OpenClawStateLeaseError",
                            "DoctorStateMigrationRefusalError", "SqliteWorkerError",
                            "StateDatabaseSchemaVersionError", "StateDatabaseRecoveryRequiredError"]
            report["doctor_error_types"] = [name for name in known_errors if name in diagnostic]
            raise ValueError("DOCTOR_EXIT_NONZERO")
        stage = "after"
        after = PRIVATE / "after.json"
        code = run(["node", "/opt/real-lab/verify.mjs", "after", str(INPUT), str(STATE), str(after)], "after", 180)
        report["checks"]["after"] = json.loads(after.read_text()) if after.exists() else {"result": "STOP"}
        if code:
            raise ValueError("AFTER_VERIFICATION_FAILED")
        stage = "reopen"
        reopened = PRIVATE / "reopen.json"
        code = run(["node", "/opt/real-lab/reopen.mjs", str(reopened)], "reopen", 180)
        report["checks"]["reopen"] = json.loads(reopened.read_text()) if reopened.exists() else {"result": "STOP"}
        if code:
            raise ValueError("SDK_REOPEN_FAILED")
        for agent in ["main", "openclaw"]:
            code = run(["node", CLI, "sessions", "--agent", agent, "--json"], "sessions-" + agent, 120)
            if code:
                raise ValueError("SESSIONS_CLI_FAILED")
            listing = json.loads((PRIVATE / ("sessions-" + agent + ".log")).read_text())
            if not isinstance(listing.get("sessions"), list):
                raise ValueError("SESSIONS_CLI_FORMAT")
            report["checks"]["sessions_" + agent] = {"result": "PASS", "listed": len(listing["sessions"])}
        stage = "final"
        snapshot = PRIVATE / "snapshot"
        snapshot.mkdir(mode=0o700)
        final = PRIVATE / "final.json"
        code = run(["node", "/opt/real-lab/verify.mjs", "final", str(INPUT), str(STATE), str(final), str(snapshot)], "final", 180)
        report["checks"]["final"] = json.loads(final.read_text()) if final.exists() else {"result": "STOP"}
        if code:
            raise ValueError("FINAL_VERIFICATION_FAILED")
        after_files = inventory(STATE)
        report["file_changes"] = [
            {"path": name, "before": before_files.get(name), "after": after_files.get(name)}
            for name in sorted(before_files.keys() | after_files.keys())
            if before_files.get(name) != after_files.get(name)
        ]
        report["files_before"] = before_files
        report["files_after"] = after_files
        report["result"] = "REHEARSAL_PASS"
        report["data_loss_assessment"] = {
            "comparison": "All retained nonempty application tables matched their pre-migration columns and logical records.",
            "intentional_input_changes": "Exclusions and redactions are enumerated in sanitization_changes.",
            "metadata_changes": "Schema, search-index, registry and runtime-lease changes are reported separately.",
            "production_migration": False,
        }
        for item in manifest["files"]:
            if item["path"].startswith("workspace/"):
                dest = snapshot / item["path"]
                dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(STATE / item["path"], dest)
        files = inventory(snapshot)
        output_manifest = {"format": "orion-migrated-rehearsal-v1", "input_sha256": ARCHIVE_SHA, "files": files,
                           "production_approval": False}
        (snapshot / "manifest.json").write_text(json.dumps(output_manifest, indent=2) + "\n")
        (snapshot / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (snapshot / "migration-report.json").write_text(json.dumps(report, indent=2) + "\n")
        archive = PUBLIC / "orion_migrated_rehearsal_v1.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for file in sorted(snapshot.rglob("*")):
                if file.is_file():
                    info = tar.gettarinfo(file, arcname=file.relative_to(snapshot).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mode = 0o600
                    with file.open("rb") as data:
                        tar.addfile(info, data)
        report["output_sha256"] = digest(archive)
        archive.chmod(0o444)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as error:
        if report["result"] == "REHEARSAL_PASS":
            report["result"] = "STOP"
        report["failure_stage"] = stage
        text = str(error)
        report["failure_code"] = text if re.fullmatch(r"[A-Z_]{3,80}", text) else "CHECK_FAILED"
        # Keep application logs and raw exception strings in the private runner directory.
    finally:
        for archive in PUBLIC.glob("*.tar.gz"):
            if report["result"] != "REHEARSAL_PASS":
                archive.unlink()
        file = PUBLIC / "migration-report.json"
        file.write_text(json.dumps(report, indent=2) + "\n")
        file.chmod(0o444)
    print(json.dumps({"result": report["result"], "failure_stage": report.get("failure_stage"),
                      "doctor_exit": report.get("doctor_exit"), "output_sha256": report.get("output_sha256")}))
    return 0 if report["result"] == "REHEARSAL_PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError):
        print('{"result":"STOP","failure_stage":"container preflight"}')
        raise SystemExit(1)
