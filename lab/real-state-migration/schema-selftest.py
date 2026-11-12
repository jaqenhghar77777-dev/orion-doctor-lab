"""One fictional regression gate before the corrective real-state attempt."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

state=Path('/home/replay/.openclaw')
assert os.getuid()!=0 and os.environ['OPENCLAW_STATE_DIR']==str(state)
assert not state.exists()
shutil.copytree('/fixture',state)
agent=state/'agents/main/agent/openclaw-agent.sqlite'
second=state/'agents/openclaw/agent/openclaw-agent.sqlite'
(state/'openclaw.json').write_text(json.dumps({'gateway':{'mode':'local','auth':{'mode':'token','token':'synthetic-doctor-replay-token'}},'plugins':{'enabled':False},'agents':{'entries':{'main':{'default':True},'openclaw':{}}}}))
tables=['session_nodes','session_windows','session_entry_snapshots','transcript_events','transcript_event_identities']
def records(file,columns=None):
    with sqlite3.connect(f'file:{file}?mode=ro',uri=True) as db:
        selected=columns or {table:[r[1] for r in db.execute(f'PRAGMA table_info("{table}")')] for table in tables}
        values={}
        for table,names in selected.items():
            fields=','.join('"'+name+'"' for name in names)
            values[table]=sorted(repr(row) for row in db.execute(f'SELECT {fields} FROM "{table}"'))
        return selected,values
columns,before=records(agent)
assert len(before['session_entry_snapshots'])==2
assert len(before['transcript_events'])>=2
files=[agent,second,state/'state/openclaw.sqlite']
hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
subprocess.run(['node','/opt/real-lab/schema-only.mjs','--negative-owner-probe'],check=True,timeout=60)
assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
subprocess.run(['node','/opt/real-lab/schema-only.mjs'],check=True,timeout=240)
assert records(agent,columns)[1]==before
for file,version in zip(files,[38,38,36]):
    with sqlite3.connect(f'file:{file}?mode=ro',uri=True) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==version
        assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
print('SCHEMA_DRIVER_SYNTHETIC_PASS owner refusal, both agents 25-to-38, shared 20-to-36, cold snapshots and original session/transcript columns preserved')
