import assert from 'node:assert/strict';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
const root = process.env.OPENCLAW_STATE_DIR;
const findings = {};
for (const [kind, name] of [['agent','agents/main/agent/openclaw-agent.sqlite'],['shared','state/openclaw.sqlite']]) {
  const db = new DatabaseSync(path.join(root,name),{readOnly:true});
  try {
    const integrity = db.prepare('PRAGMA integrity_check').all().map(row=>row.integrity_check);
    assert.deepEqual(integrity,['ok'],kind+' integrity');
    if (kind === 'agent') assert.equal(db.prepare('PRAGMA user_version').get().user_version,38);
    else assert.equal(db.prepare('SELECT schema_version FROM agent_databases WHERE agent_id=?').get('main')?.schema_version,38);
    findings[kind]='ok';
  } finally { db.close(); }
}
console.log('DATABASES '+process.argv[2]+' '+JSON.stringify({...findings,agentSchema:38,registeredSchema:38}));
