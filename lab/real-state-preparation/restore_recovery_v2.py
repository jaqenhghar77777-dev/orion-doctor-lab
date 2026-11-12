"""Corrective restore with byte-preserved empty generation-lock companions."""
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time

SOURCE = Path("/root/orion-recovery-n3hz4fpf/checkpoint.tar.gz")
EXPECTED_SHA256 = "daccf87f3dc4173d7ee52e300d33546e82d73d2cdf279a69c57f8f22df06707c"
EXPECTED_COUNTS = {"files": 45923, "directories": 1364, "symlinks": 24, "hardlinks": 0, "special": 0}
CHUNK = 1024 * 1024
GENERATION_LOCK_SUFFIX = ".generation-lock.sqlite"
VERIFY_JS = r"""
const fs = require('node:fs');
const path = require('node:path');
const {DatabaseSync} = require('node:sqlite');
const request = JSON.parse(fs.readFileSync(0,'utf8'));
const results = [];
let current, phase;
try {
  for (const relative of request.databases) {
    current=relative;
    phase='open';
    const file = path.join(request.root,relative);
    const db = new DatabaseSync(file,{readOnly:true});
    try {
      phase='integrity_check';
      const checks = db.prepare('PRAGMA integrity_check').all().map(r=>r.integrity_check);
      if (checks.length!==1 || checks[0]!=='ok')
        throw Object.assign(Error('integrity_check failed'),{code:'INTEGRITY_CHECK_FAILED'});
      phase='schema_version';
      const version = db.prepare('PRAGMA user_version').get().user_version;
      if (relative.endsWith('/agents/main/agent/openclaw-agent.sqlite') ||
          relative==='agents/main/agent/openclaw-agent.sqlite') {
        if(version!==25) throw Object.assign(Error('main agent schema mismatch'),
          {code:'MAIN_SCHEMA_MISMATCH',actualSchema:version,expectedSchema:25});
      }
      results.push({path:relative,user_version:version,integrity:'ok',
        wal:fs.existsSync(file+'-wal'),shm:fs.existsSync(file+'-shm')});
    } finally { db.close(); }
  }
  process.stdout.write(JSON.stringify({databases:results}));
} catch(e) {
  process.stderr.write(String(e.stack||e));
  process.stdout.write(JSON.stringify({failure:'SQLite verification failed',
    database:current,check:phase,error_code:e.code||'SQLITE_CHECK_ERROR',
    actualSchema:e.actualSchema,expectedSchema:e.expectedSchema,completed:results}));
  process.exitCode=1;
}
"""


def fingerprint(file):
    digest = hashlib.sha256()
    for block in iter(lambda: file.read(CHUNK), b""):
        digest.update(block)
    return digest.hexdigest()


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def canonical(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe archive member path.")
    return str(path)


def restore(source, expected_hash, expected_counts, parent):
    started = time.monotonic()
    destination = None
    stage = "archive verification"
    def bounded():
        if time.monotonic() - started > 1800:
            raise ValueError("Restoration exceeded its 30-minute bound.")
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Recovery archive must be a regular file.")
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd,"rb") as raw:
            if stamp(os.fstat(raw.fileno())) != stamp(before):
                raise ValueError("Recovery archive changed before opening.")
            if fingerprint(raw) != expected_hash:
                raise ValueError("Recovery archive SHA-256 mismatch.")
            raw.seek(0)
            counts = dict.fromkeys(expected_counts,0)
            kinds = {}
            with gzip.GzipFile(fileobj=raw,mode="rb") as gz:
                with tarfile.open(fileobj=gz,mode="r|") as archive:
                    for item in archive:
                        bounded()
                        name = canonical(item.name)
                        if name in kinds:
                            raise ValueError("Duplicate archive member path.")
                        kind = ("files" if item.isfile() else "directories" if item.isdir() else
                                "symlinks" if item.issym() else "hardlinks" if item.islnk() else "special")
                        kinds[name] = kind
                        counts[kind] += 1
                        if kind in ("hardlinks","special"):
                            raise ValueError("Hard links or special entries require review.")
                while gz.read(CHUNK):
                    bounded()
            if counts != expected_counts:
                raise ValueError("Archive entry counts differ from the reviewed inventory.")
            for name,kind in kinds.items():
                if name=="." and kind!="directories":
                    raise ValueError("Archive root must be a directory.")
                for ancestor in PurePosixPath(name).parents:
                    if str(ancestor) in kinds and kinds[str(ancestor)]!="directories":
                        raise ValueError("Archive member has a non-directory ancestor.")
            if not shutil.which("node"):
                raise ValueError("Node is unavailable.")
            destination = Path(tempfile.mkdtemp(prefix="orion-real-rehearsal-",dir=parent))
            os.chmod(destination,0o700)
            state = destination/"restored"
            state.mkdir(mode=0o700)
            stage = "regular-file restoration"
            raw.seek(0)
            databases,companions,empty_generation_locks = [],[],[]
            with (destination/"restored-files.jsonl").open("x",encoding="utf8") as ledger:
                os.chmod(ledger.name,0o600)
                with gzip.GzipFile(fileobj=raw,mode="rb") as gz:
                    with tarfile.open(fileobj=gz,mode="r|") as archive:
                        for item in archive:
                            bounded()
                            name = canonical(item.name)
                            if item.issym():
                                continue
                            target = state/name
                            if item.isdir():
                                target.mkdir(parents=True,exist_ok=True,mode=0o700)
                                continue
                            if not item.isfile():
                                raise ValueError("Archive entry type changed.")
                            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                            digest = hashlib.sha256()
                            size = 0
                            header = b""
                            with archive.extractfile(item) as inp, target.open("xb") as out:
                                os.chmod(target,0o600 | (item.mode & 0o100))
                                while True:
                                    bounded()
                                    block = inp.read(CHUNK)
                                    if not block:
                                        break
                                    if not size:
                                        header = block[:16]
                                    out.write(block)
                                    digest.update(block)
                                    size += len(block)
                            if size != item.size:
                                raise ValueError("Restored file size mismatch.")
                            with target.open("rb") as check:
                                if fingerprint(check)!=digest.hexdigest():
                                    raise ValueError("Restored file checksum mismatch.")
                            ledger.write(json.dumps({"path":name,"bytes":size,"sha256":digest.hexdigest()})+"\n")
                            if header==b"SQLite format 3\x00":
                                databases.append(name)
                            elif size==0 and name.endswith(".sqlite"+GENERATION_LOCK_SUFFIX):
                                empty_generation_locks.append(name)
                            elif name.endswith((".sqlite",".sqlite3",".db")):
                                raise ValueError("Named SQLite file has an invalid header.")
                            if name.endswith(("-wal","-shm")):
                                companions.append(name)
                    while gz.read(CHUNK):
                        bounded()
                ledger.flush()
                os.fsync(ledger.fileno())
            if stamp(os.fstat(raw.fileno()))!=stamp(before) or stamp(source.lstat())!=stamp(before):
                raise ValueError("Recovery archive changed during restoration.")
        stage = "SQLite verification"
        candidates = [p for p in databases if p=="agents/main/agent/openclaw-agent.sqlite" or
                      p.endswith("/agents/main/agent/openclaw-agent.sqlite")]
        if len(candidates)!=1:
            raise ValueError("Expected exactly one main agent database.")
        for name in empty_generation_locks:
            if name[:-len(GENERATION_LOCK_SUFFIX)] not in databases:
                raise ValueError("Empty generation-lock companion has no matching SQLite database.")
        for name in companions:
            if name[:-4] not in databases:
                raise ValueError("Orphan SQLite WAL or SHM companion.")
        env = {k:os.environ[k] for k in ("PATH","LD_LIBRARY_PATH","LANG") if k in os.environ}
        result = subprocess.run(["node","--no-warnings","-e",VERIFY_JS],input=json.dumps({
            "root":str(state),"databases":sorted(databases)}),cwd=destination,env=env,
            text=True,capture_output=True,timeout=max(1,int(1800-(time.monotonic()-started))))
        try:
            checked = json.loads(result.stdout)
        except ValueError:
            raise ValueError("Node SQLite checker failed to produce its result.")
        if result.returncode or "failure" in checked:
            diagnostic = destination/"sqlite-private-diagnostic.txt"
            diagnostic.write_text(result.stderr)
            os.chmod(diagnostic,0o600)
            report = {"result":"STOP","stage":stage,"directory":str(destination),**checked}
            (destination/"restore-report.json").write_text(json.dumps(report,indent=2)+"\n")
            os.chmod(destination/"restore-report.json",0o600)
            return report,1
        report = {"result":"RESTORE_PASS","directory":str(destination),"restored_state":str(state),
                  "archive_sha256":expected_hash,"counts":counts,"symlinks_skipped":counts["symlinks"],
                  "wal_shm_files_copied_and_verified":len(companions),**checked,
                  "preserved_empty_generation_lock_companions":empty_generation_locks,
                  "main_agent_schema":25,"upload_ready":False}
        (destination/"restore-report.json").write_text(json.dumps(report,indent=2)+"\n")
        os.chmod(destination/"restore-report.json",0o600)
        return report,0
    except (OSError,ValueError,tarfile.TarError,EOFError,subprocess.SubprocessError) as error:
        # Archive filenames, raw SQLite errors and contents stay out of the terminal.
        return {"result":"STOP","stage":stage,"directory":str(destination) if destination else None,
                "failure_type":type(error).__name__,"reason":str(error) if isinstance(error,ValueError) else
                "Operation failed; retain the disposable directory for diagnosis.","upload_ready":False},1


if __name__=="__main__":
    os.umask(0o077)
    try:
        report,code = restore(SOURCE,EXPECTED_SHA256,EXPECTED_COUNTS,Path("/root"))
    except (OSError,ValueError) as error:
        report,code = {"result":"STOP","stage":"source opening","failure_type":type(error).__name__,
                       "reason":"Recovery archive is unavailable or is not a regular file.","upload_ready":False},1
    print(json.dumps(report,indent=2))
    raise SystemExit(code)
