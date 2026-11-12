import fs from 'node:fs';
import path from 'node:path';
import {isDeepStrictEqual as equal} from 'node:util';
import {DatabaseSync, backup} from 'node:sqlite';

const [input,state,destination,receipt] = process.argv.slice(2);
const main = 'agents/main/agent/openclaw-agent.sqlite';
const definitions = {session_entry_snapshots:['session_key','field'],session_nodes:['session_key'],session_windows:['session_id']};
const report = {};
const increment = (counts,key)=>{counts[key]=(counts[key]??0)+1;};
function indexed(db, table, keys) {
  const rows = db.prepare('SELECT * FROM '+table).all();
  const result = new Map(rows.map(row=>[JSON.stringify(keys.map(k=>row[k])),row]));
  if (result.size!==rows.length) throw Error('AMBIGUOUS_ROW_KEY');
  return result;
}
const before = new DatabaseSync(path.join(input,main),{readOnly:true});
const after = new DatabaseSync(path.join(state,main),{readOnly:true});
try {
  for (const [table,keys] of Object.entries(definitions)) {
    const left=indexed(before,table,keys), right=indexed(after,table,keys);
    const delta={removed:0,added:0,changed_columns:Object.create(null),changed_json_fields:Object.create(null),snapshot_types:Object.create(null)};
    for (const [id,row] of left) {
      const next=right.get(id);
      if (!next) {
        delta.removed++;
        if (table==='session_entry_snapshots') increment(delta.snapshot_types,'removed.'+row.field);
        continue;
      }
      for (const col of Object.keys(row)) {
        if (equal(row[col],next[col])) continue;
        increment(delta.changed_columns,col);
        if (!col.endsWith('_json')) continue;
        const a=JSON.parse(row[col]??'null'), b=JSON.parse(next[col]??'null');
        const keysOf = v=>v && typeof v==='object' && !Array.isArray(v) ? Object.keys(v) : [];
        for (const name of new Set([...keysOf(a),...keysOf(b)]))
          if (!equal(a?.[name],b?.[name])) increment(delta.changed_json_fields,name);
      }
    }
    for (const [id,row] of right) if (!left.has(id)) {
      delta.added++;
      if (table==='session_entry_snapshots') increment(delta.snapshot_types,'added.'+row.field);
    }
    report[table]=delta;
  }
} finally {before.close();after.close();}
fs.writeFileSync(receipt,JSON.stringify(report));
for (const file of [main,'agents/openclaw/agent/openclaw-agent.sqlite','state/openclaw.sqlite']) {
  const db=new DatabaseSync(path.join(state,file),{readOnly:true});
  const dest=path.join(destination,file);
  fs.mkdirSync(path.dirname(dest),{recursive:true});
  try {await backup(db,dest);} finally {db.close();}
}
