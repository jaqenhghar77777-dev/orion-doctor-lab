import assert from 'node:assert/strict';
import path from 'node:path';
const seed = process.argv[2] === 'seed';
const prefix = seed ? '/opt/legacy' : '/opt/beta';
const sdk = prefix+'/node_modules/openclaw/dist/plugin-sdk/';
const {upsertSessionEntry,getSessionEntry} = await import(sdk+'session-store-runtime.js');
const {appendSessionTranscriptMessageByIdentity,readSessionTranscriptEvents} = await import(sdk+'session-transcript-runtime.js');
const scope = {agentId:'main',sessionKey:'agent:main:main',sessionId:'5fd080f7-d376-483d-a065-c212db942f93',
  storePath:path.join(process.env.OPENCLAW_STATE_DIR,'agents/main/sessions/sessions.json')};
const messages = [
  {role:'user',content:'Fictional continuity check 7351.'},
  {role:'assistant',content:'Fictional reply 9452.'},
];
if (seed) {
  await upsertSessionEntry({...scope,entry:{sessionId:scope.sessionId,updatedAt:Date.now()}});
  for (const message of messages) {
    assert.ok(await appendSessionTranscriptMessageByIdentity({...scope,message}));
  }
}
assert.equal(getSessionEntry(scope)?.sessionId,scope.sessionId);
const events=await readSessionTranscriptEvents(scope);
const logical=events.flatMap(e=>{
  const m=e?.message;
  if (!m || !['user','assistant'].includes(m.role)) return [];
  const content=typeof m.content==='string' ? m.content : m.content.filter(p=>p.type==='text').map(p=>p.text).join('');
  return [{role:m.role,content}];
});
assert.deepEqual(logical,messages);
console.log('SESSION '+(seed?'legacy-seed':'beta-read')+' same-session=true ordered-messages='+logical.length);
