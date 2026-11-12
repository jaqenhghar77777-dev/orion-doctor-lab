import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { DatabaseSync, backup } from 'node:sqlite';
const root=process.env.OPENCLAW_STATE_DIR;
assert.equal(root,'/home/replay/.openclaw');
const out='/handoff/phone-v1';
fs.mkdirSync(out);
const hashes={};
for (const name of ['state/openclaw.sqlite','agents/main/agent/openclaw-agent.sqlite','workspace/IDENTITY.md','workspace/USER.md']) {
  const src=path.join(root,name), dest=path.join(out,'fixture',name);
  fs.mkdirSync(path.dirname(dest),{recursive:true});
  if (name.endsWith('.sqlite')) {
    const db=new DatabaseSync(src,{readOnly:true});
    try { await backup(db,dest); } finally { db.close(); }
  } else fs.copyFileSync(src,dest);
  hashes[name]=createHash('sha256').update(fs.readFileSync(dest)).digest('hex');
}
fs.writeFileSync(path.join(out,'hashes.json'),JSON.stringify(hashes,null,2)+'\n');
