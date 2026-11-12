// Add a second synthetic agent and cold snapshots to the existing fictional session fixture.
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {openOpenClawAgentDatabase} from '/opt/legacy/node_modules/openclaw/dist/plugin-sdk/sqlite-runtime.js';
openOpenClawAgentDatabase({agentId:'openclaw',env:process.env});
const file=path.join(process.env.OPENCLAW_STATE_DIR,'agents/main/agent/openclaw-agent.sqlite');
const db=new DatabaseSync(file);
try {
  const row=db.prepare('SELECT session_key FROM session_nodes ORDER BY session_key LIMIT 1').get();
  if(!row)throw Error('SYNTHETIC_SESSION_MISSING');
  const insert=db.prepare('INSERT INTO session_entry_snapshots(session_key,field,value_json) VALUES(?,?,?)');
  insert.run(row.session_key,'skillsSnapshot',JSON.stringify({prompt:'Fictional skill snapshot',skills:[],version:1}));
  insert.run(row.session_key,'systemPromptReport',JSON.stringify({source:'synthetic-rehearsal',systemPrompt:{chars:17}}));
}finally{db.close();}
process.exit(0);
