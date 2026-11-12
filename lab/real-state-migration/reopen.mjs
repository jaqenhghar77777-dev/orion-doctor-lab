import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {DatabaseSync} from 'node:sqlite';

const state=process.env.OPENCLAW_STATE_DIR;
const sdk='/opt/beta/node_modules/openclaw/dist/plugin-sdk/';
const report={result:'PASS',agents:[]};
let current={stage:'SDK import'};
try {
  const {getSessionEntry}=await import(pathToFileURL(sdk+'session-store-runtime.js'));
  const {readSessionTranscriptEvents}=await import(pathToFileURL(sdk+'session-transcript-runtime.js'));
  for(const agentId of ['main','openclaw']) {
    current={stage:'SDK history read',agentId};
    const db=new DatabaseSync(path.join(state,'agents',agentId,'agent/openclaw-agent.sqlite'),{readOnly:true});
    let windows,nodes,total;
    try {
      windows=db.prepare('SELECT w.session_id,w.session_key,count(e.seq) AS events FROM session_windows w JOIN transcript_events e ON e.session_id=w.session_id GROUP BY w.session_id,w.session_key ORDER BY w.session_id').all();
      nodes=db.prepare("SELECT session_key,current_session_id FROM session_nodes WHERE entry_valid=1 AND current_session_id IS NOT NULL").all();
      total=db.prepare('SELECT count(*) AS n FROM transcript_events').get().n;
    }finally{db.close();}
    if(windows.reduce((n,w)=>n+w.events,0)!==total)throw Error('HISTORY_WINDOW_COVERAGE');
    const storePath=path.join(state,'agents',agentId,'sessions/sessions.json');
    for(const node of nodes) {
      const entry=await getSessionEntry({agentId,sessionKey:node.session_key,storePath});
      if(!entry||entry.sessionId!==node.current_session_id)throw Error('SDK_SESSION_IDENTITY');
    }
    let returned=0;
    for(const window of windows) {
      const events=await readSessionTranscriptEvents({agentId,sessionKey:window.session_key,
        sessionId:window.session_id,storePath});
      if(!Array.isArray(events)||!events.length)throw Error('SDK_HISTORY_EMPTY');
      returned+=events.length;
    }
    report.agents.push({agentId,current_entries_opened:nodes.length,historical_windows_opened:windows.length,
      database_events:total,sdk_returned_events:returned});
  }
}catch(error) {
  report.result='STOP';
  report.failure={...current,code:['HISTORY_WINDOW_COVERAGE','SDK_SESSION_IDENTITY','SDK_HISTORY_EMPTY'].includes(error.message)?
    error.message:'SDK_REOPEN_FAILED'};
}
fs.writeFileSync(process.argv[2],JSON.stringify(report,null,2)+'\n',{mode:0o600});
console.log(JSON.stringify(report));
if(report.result!=='PASS')process.exitCode=1;
