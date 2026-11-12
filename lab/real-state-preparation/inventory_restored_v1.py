"""Inventory the successful disposable restore without emitting record contents."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

RESTORE = Path("/root/orion-real-rehearsal-9a_4zlyq")
ARCHIVE_HASH = "daccf87f3dc4173d7ee52e300d33546e82d73d2cdf279a69c57f8f22df06707c"
IDENTITY_NAMES = {"SOUL.md","IDENTITY.md","AGENTS.md","USER.md"}
SKIP_PARTS = {"node_modules",".git","extensions","plugins","tmp","credentials","cache"}
JS = r"""
const fs=require('node:fs'), path=require('node:path');
const {DatabaseSync}=require('node:sqlite');
const input=JSON.parse(fs.readFileSync(0,'utf8')), output=[];
const quote=s=>'"'+s.replaceAll('"','""')+'"';
let current, table;
try {
  for(const item of input.databases) {
    current=item.path;table=undefined;
    const db=new DatabaseSync(path.join(input.root,item.path),{readOnly:true});
    try {
      db.exec('BEGIN');
      const version=db.prepare('PRAGMA user_version').get().user_version;
      if(version!==item.user_version) throw Object.assign(Error('schema changed'),{code:'SCHEMA_CHANGED'});
      const tables=[];
      for(const row of db.prepare("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name").all()) {
        table=row.name;
        const columns=db.prepare('PRAGMA table_xinfo('+quote(table)+')').all().map(c=>({
          name:c.name,type:c.type,primary_key:c.pk,hidden:c.hidden
        }));
        const rows=db.prepare('SELECT count(*) AS n FROM '+quote(table)).get().n;
        tables.push({name:table,rows,columns});
      }
      db.exec('ROLLBACK');
      output.push({path:current,user_version:version,tables});
    } finally {db.close();}
  }
  process.stdout.write(JSON.stringify({databases:output}));
} catch(e) {
  process.stderr.write(String(e.stack||e));
  process.stdout.write(JSON.stringify({failure:'INVENTORY_STOP',database:current,
    table,error_code:e.code||'SQLITE_INVENTORY_ERROR'}));
  process.exitCode=1;
}
"""


def sha(file):
    h=hashlib.sha256()
    with file.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def inventory(directory, allowed_parent=Path("/root")):
    directory=directory.resolve(strict=True)
    if directory.parent!=allowed_parent or not directory.name.startswith("orion-real-rehearsal-"):
        raise ValueError("Expected a disposable restoration directory.")
    report=json.loads((directory/"restore-report.json").read_text())
    if report.get("result")!="RESTORE_PASS" or report.get("archive_sha256")!=ARCHIVE_HASH:
        raise ValueError("Successful matching restoration report required.")
    root=(directory/"restored").resolve(strict=True)
    if root.parent!=directory or report["restored_state"]!=str(root):
        raise ValueError("Unexpected restored-state path.")

    def member(name):
        p=(root/name).resolve(strict=True)
        if not p.is_relative_to(root) or not p.is_file():
            raise ValueError("Restored member escapes the disposable tree.")
        return p

    before={r["path"]:sha(member(r["path"])) for r in report["databases"]}
    environment={k:os.environ[k] for k in ("PATH","LD_LIBRARY_PATH","LANG") if k in os.environ}
    r=subprocess.run(["node","--no-warnings","-e",JS],input=json.dumps({
        "root":str(root),"databases":report["databases"]}),cwd=directory,env=environment,
        capture_output=True,text=True,timeout=600)
    try:
        result=json.loads(r.stdout)
    except ValueError:
        raise ValueError("SQLite metadata checker returned no result.")
    if r.returncode or "failure" in result:
        diagnostic=directory/"inventory-private-diagnostic.txt"
        diagnostic.write_text(r.stderr);diagnostic.chmod(0o600)
        return result,1
    for name,h in before.items():
        if sha(member(name))!=h:
            raise ValueError("A restored database file changed during inventory.")
    identities=[]
    with (directory/"restored-files.jsonl").open() as ledger:
        for line in ledger:
            row=json.loads(line);name=Path(row["path"])
            if name.name not in IDENTITY_NAMES or SKIP_PARTS.intersection(name.parts):
                continue
            p=member(row["path"]);actual=sha(p)
            if actual!=row["sha256"]:
                raise ValueError("Restored identity file differs from its archive fingerprint.")
            identities.append({"path":row["path"],"bytes":p.stat().st_size,"sha256":actual})
    result.update(result="INVENTORY_PASS",archive_sha256=ARCHIVE_HASH,
                  database_file_sha256=before,identity_files=identities,
                  missing_identity_names=sorted(IDENTITY_NAMES-{Path(i["path"]).name for i in identities}),
                  upload_ready=False)
    # Exclusive creation prevents replacing an earlier inventory baseline.
    with (directory/"inventory-v1.json").open("x") as out:
        os.chmod(out.name,0o600)
        json.dump(result,out,indent=2);out.write("\n")
    return result,0


if __name__=="__main__":
    os.umask(0o077)
    try:
        result,code=inventory(RESTORE)
        if not code:
            for database in result["databases"]:
                print("DATABASE "+json.dumps({"path":database["path"],"schema":database["user_version"],
                    "tables":{t["name"]:t["rows"] for t in database["tables"]}}))
            print("IDENTITY "+json.dumps({"files":result["identity_files"],
                                         "missing":result["missing_identity_names"]}))
            print("INVENTORY_PASS "+str(RESTORE/"inventory-v1.json"))
        else:
            print(json.dumps(result,indent=2))
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print(json.dumps({"result":"STOP","failure_type":type(error).__name__,
                         "reason":str(error) if isinstance(error,ValueError) else
                         "Inventory failed; retain the disposable restore.","upload_ready":False}))
        code=1
    sys.exit(code)
