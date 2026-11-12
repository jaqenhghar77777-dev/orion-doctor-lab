"""Run one offline migration against a disposable copy and emit reviewed report data."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
from usability import allow_strict, gateway
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


def record_changes(report, before, doctor_state, runtime_state):
    doctor = inventory(doctor_state)
    final = inventory(runtime_state)
    report["file_changes"] = [
        {"path": name, "before": before.get(name), "doctor": doctor.get(name), "final": final.get(name)}
        for name in sorted(before.keys() | doctor.keys() | final.keys())
        if before.get(name) != doctor.get(name) or doctor.get(name) != final.get(name)
    ]


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
              "migration_driver": "stock Doctor CLI",
              "model_inference": "NOT_TESTED_OFFLINE", "phone_deployment": "PENDING",
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
        if code or report["checks"]["before"].get("result") != "PASS":
            raise ValueError("BEFORE_VERIFICATION_FAILED")
        stage = "doctor"
        code = run(["node", CLI, "doctor", "--fix", "--non-interactive"], "doctor", 600)
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
        report["strict_result"] = report["checks"]["after"]["result"]
        if not allow_strict(report["checks"]["after"], code):
            raise ValueError("AFTER_VERIFICATION_FAILED")
        stage = "session metadata audit"
        snapshot = PRIVATE / "snapshot"
        snapshot.mkdir()
        audit = PRIVATE / "session-audit.json"
        if run(["node", "/opt/real-lab/snapshot.mjs", str(INPUT), str(STATE), str(snapshot), str(audit)], "snapshot-audit", 180):
            raise ValueError("SESSION_AUDIT_OR_SNAPSHOT_FAILED")
        report["session_differences"] = json.loads(audit.read_text())
        for item in manifest["files"]:
            if item["path"].startswith("workspace/"):
                dest = snapshot / item["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(STATE / item["path"], dest)

        def strict_check(label, directory):
            receipt = PRIVATE / (label + ".json")
            rc = run(["node", "/opt/real-lab/verify.mjs", "final", str(INPUT), str(directory), str(receipt)], label, 180)
            data = json.loads(receipt.read_text())
            report["checks"][label] = data
            if data["result"] == "STOP":
                report["strict_result"] = "STOP"
            if not allow_strict(data, rc):
                raise ValueError("FINAL_VERIFICATION_FAILED")
        strict_check("snapshot", snapshot)
        # Exercise precisely the snapshot files that would be returned, under the same canonical state path.
        original = STATE.with_name("doctor-output")
        STATE.rename(original)
        STATE.mkdir()
        for item in manifest["files"]:
            dest = STATE / item["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(snapshot / item["path"], dest)
        shutil.copyfile(original / "openclaw.json", STATE / "openclaw.json")
        stage = "agent loading"
        if run(["node", CLI, "agents", "list", "--json"], "agents", 120):
            raise ValueError("AGENTS_LIST_FAILED")
        agents = json.loads((PRIVATE / "agents.log").read_text())
        main_agent = next((a for a in agents if a.get("id") == "main"), {})
        if (Path(main_agent.get("workspace","")).expanduser().resolve() != STATE / "workspace"
                or main_agent.get("admissionRefusal") or main_agent.get("status") == "degraded"):
            raise ValueError("MAIN_WORKSPACE_FAILED")
        report["checks"]["main_workspace"] = "PASS"
        stage = "main session access"
        if run(["node", CLI, "sessions", "--agent", "main", "--json"], "sessions", 120):
            raise ValueError("SESSIONS_CLI_FAILED")
        reopened = PRIVATE / "reopen.json"
        rc = run(["node", "/opt/real-lab/usability.mjs", str(PRIVATE / "sessions.log"), str(reopened)], "reopen", 180)
        report["checks"]["reopen"] = json.loads(reopened.read_text()) if reopened.exists() else {}
        if rc or report["checks"]["reopen"].get("result") != "PASS":
            raise ValueError("SDK_REOPEN_FAILED")
        stage = "gateway"
        gateway(CLI, PRIVATE, run)
        report["checks"]["gateway"] = {"loopback_live": True, "health_rpc": True, "clean_shutdown": True}
        stage = "final"
        strict_check("final", STATE)
        report["result"] = "USABILITY_PASS"
        report["decision"] = "GO_FOR_ISOLATED_PHONE_CHECK"
        report["data_loss_assessment"] = {
            "session_metadata": report["session_differences"],
            "retained_content": "Original conversation, logical transcript and memory records verified against sanitized input.",
            "identity_files": "All four input hashes matched.",
            "original_report_sha256": "bfc0eb39854cdbb1ca7c47ebcf5cb97d3ea27e3d3c3c8e2bd2f0c3d91cf94ae9"}
        # Snapshot verification can create SQLite sidecars. Only manifest-listed payloads are eligible.
        eligible = {item["path"] for item in manifest["files"]}
        files = {k: v for k, v in inventory(snapshot).items() if k in eligible}
        if set(files) != eligible or len(files) != 7:
            raise ValueError("OUTPUT_ALLOWLIST")
        record_changes(report, before_files, original, STATE)
        output_manifest = {"format": "orion-migrated-rehearsal-v1", "input_sha256": ARCHIVE_SHA, "files": files,
                           "production_approval": False}
        (snapshot / "manifest.json").write_text(json.dumps(output_manifest, indent=2) + "\n")
        (snapshot / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (snapshot / "migration-report.json").write_text(json.dumps(report, indent=2) + "\n")
        archive = PUBLIC / "orion_migrated_rehearsal_v1.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name in sorted(eligible | {"manifest.json", "input-manifest.json", "migration-report.json"}):
                file = snapshot / name
                if file.is_file():
                    info = tar.gettarinfo(file, arcname=file.relative_to(snapshot).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mode = 0o600
                    with file.open("rb") as data:
                        tar.addfile(info, data)
        report["output_sha256"] = digest(archive)
        archive.chmod(0o444)
    except Exception as error:
        if report["result"] == "USABILITY_PASS":
            report["result"] = "STOP"
        report["decision"] = "STOP"
        report["failure_stage"] = stage
        text = str(error)
        report["failure_code"] = text if re.fullmatch(r"[A-Z_]{3,80}", text) else "CHECK_FAILED"
        if report["failure_code"] == "SDK_REOPEN_FAILED" and report["checks"].get("reopen", {}).get("failure_code") in {
                "MAIN_SESSION_LISTING", "SDK_CURRENT_SESSION_IDENTITY", "SDK_CURRENT_MESSAGE_READ"}:
            report["decision"] = "FALLBACK_REVIEW"
        # Keep application logs and raw exception strings in the private runner directory.
    finally:
        if "before_files" in locals() and "file_changes" not in report:
            try:
                record_changes(report, before_files, original if "original" in locals() and original.exists() else STATE, STATE)
            except (OSError, ValueError):
                report["file_inventory_incomplete"] = True
        for archive in PUBLIC.glob("*.tar.gz"):
            if report["result"] != "USABILITY_PASS":
                archive.unlink()
        file = PUBLIC / "migration-report.json"
        file.write_text(json.dumps(report, indent=2) + "\n")
        file.chmod(0o444)
    print(json.dumps({"result": report["result"], "failure_stage": report.get("failure_stage"),
                      "doctor_exit": report.get("doctor_exit"), "output_sha256": report.get("output_sha256")}))
    return 0 if report["result"] == "USABILITY_PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError):
        print('{"result":"STOP","failure_stage":"container preflight"}')
        raise SystemExit(1)
