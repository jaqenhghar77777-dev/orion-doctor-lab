'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const acorn = require('acorn');
const dist = process.argv[2] || '/opt/beta/node_modules/openclaw/dist';
const parseOptions = {ecmaVersion:'latest', sourceType:'module', allowHashBang:true};
const worker = 'process.getBuiltinModule("node:module").createRequire(process.execPath)("/opt/lab/custody-worker.cjs")';
const stats = {guards:0, readWorker:0, readBroker:0};
const apiNames = ['captureGatewayStateOwner','resolveGatewayStateOwnerPath','acquireGatewayStateOwner',
  'getOpenClawDatabaseMaintenanceScope','createOpenClawDatabaseMaintenanceScope','assertStateDatabaseAccessAllowed'];
const providers = new Map();
function* filenames(dir) {
  for (const e of fs.readdirSync(dir,{withFileTypes:true})) {
    const f = path.join(dir,e.name);
    if(e.isDirectory() && e.name !== 'node_modules') yield* filenames(f);
    else if(e.isFile() && /\.(?:js|mjs|cjs)$/.test(e.name)) yield f;
  }
}
function* walk(n) {
  if (!n?.type) return;
  yield n;
  for (const val of Object.values(n)) {
    if (Array.isArray(val)) { for (const item of val) if (item?.type) yield* walk(item); }
    else if (val?.type) yield* walk(val);
  }
}
const propName = n => n?.key?.name || n?.key?.value;
function unique(values,label) {
  if(values.length !== 1) throw Error(label + ': expected one match, got ' + values.length);
  return values[0];
}
const files=[...filenames(dist)];
for (const name of apiNames) {
  const top=files.filter(f=>path.dirname(f)===dist && f.endsWith('.mjs'));
  top.sort((a,b)=>Number(!a.endsWith('/gateway-state-owner-DQ8gMS4R.mjs'))-Number(!b.endsWith('/gateway-state-owner-DQ8gMS4R.mjs')));
  for (const f of top) {
    const source=fs.readFileSync(f,'utf8');
    const hit=new RegExp('^(?:export\\s+)?function\\s+('+name+'(?:\\$\\d+)?)\\s*\\(','m').exec(source);
    if (!hit) continue;
    fs.appendFileSync(f,'\nexport { '+hit[1]+' as orionLab_'+name+' };\n');
    providers.set(name,f); break;
  }
  if(!providers.has(name)) throw Error('No pinned host provider for '+name);
}
fs.writeFileSync(path.join(__dirname,'custody-api.mjs'), [...providers].map(([n,f]) =>
  'export { orionLab_'+n+' as '+n+' } from '+JSON.stringify(pathToFileURL(f).href)+';').join('\n')+'\n');

for (const file of files) {
  const code=fs.readFileSync(file,'utf8'), bundle=path.relative(dist,file), edits=[];
  const slice=n=>code.slice(n.start,n.end);
  const insert=(p,s)=>edits.push([p,p,s]);
  if (code.includes(' + orionReplayCaller(') && code.includes(' is undergoing offline maintenance by ')) {
    const anchor=/^([ \t]*)(?:const|let|var) maintenancePending(?:\$\d+)? = \x60OpenClaw state at /gm;
    for (const hit of code.matchAll(anchor)) {
      insert(hit.index,hit[1]+'if ('+worker+'.admit(namespace, databasePath, ownerPath, raw, owner)) return;\n');
      stats.guards++;
    }
  }
  if (code.includes('checkFreshAdmission') &&
      (code.includes('Shared-state read transport is closed') || code.includes('assertOpenClawStateDatabaseFreshOpenAllowedAtPath'))) {
    const tree=acorn.parse(code,parseOptions);
    const nodes=[...walk(tree)];
    for (const n of nodes) {
      if (n.type !== 'IfStatement' || n.test.type !== 'MemberExpression' ||
          n.test.property?.name !== 'checkFreshAdmission' || n.consequent.type!=='BlockStatement' ||
          !slice(n.consequent).includes('assertOpenClawStateDatabaseFreshOpenAllowedAtPath')) continue;
      const input=slice(n.test.object);
      insert(n.consequent.start+1,'\n'+worker+'.run('+input+'.orionReadTicket, () => {\n');
      insert(n.consequent.end-1,'\n});\n');
      stats.readWorker++;
    }
    for (const method of nodes.filter(n=>n.type==='MethodDefinition' && propName(n)==='startRun')) {
      const body=method.value.body;
      if(!slice(body).includes('Shared-state read transport is closed')) continue;
      const [context,,fresh,,authority]=method.value.params.map(n=>n.name);
      if(!context || !authority || !fresh) throw Error('Unrecognized read transport parameters');
      const inside=[...walk(body)];
      const request=unique(inside.filter(n=>n.type==='VariableDeclarator' && n.init?.type==='ObjectExpression' &&
        n.init.properties.some(p=>propName(p)==='checkFreshAdmission') && n.init.properties.some(p=>propName(p)==='command')),'read request').id.name;
      const send=unique(inside.filter(n=>n.type==='ReturnStatement' && n.argument?.type==='Identifier' && n.argument.name===request),'read dispatch');
      const ret=unique(inside.filter(n=>n.type==='ReturnStatement' && n.argument?.type==='ObjectExpression' &&
        n.argument.properties.some(p=>propName(p)==='task') && n.argument.properties.some(p=>propName(p)==='result')),'read result');
      const result=ret.argument.properties.find(p=>propName(p)==='result');
      const original=slice(result.value);
      insert(0,'import { issue as orionLabIssue } from "file:///opt/lab/custody-host.mjs";\n');
      insert(body.start+1,'\nlet orionGrant; let orionFinished = false;\n');
      insert(send.start,'if ('+fresh+' && !orionFinished && !orionGrant) {\n' +
        'orionGrant = orionLabIssue('+context+'.admission.databasePath, '+context+'.maintenanceScope, '+authority+'.assertCurrent, '+authority+'.signal, "read");\n' +
        'if (orionGrant) '+request+'.orionReadTicket = orionGrant.ticket;\n}\n');
      edits.push([result.start,result.end,'result: '+original+'.finally(() => { orionFinished = true; orionGrant?.close(); })']);
      stats.readBroker++;
    }
  }
  if (edits.length) {
    let out=code;
    for(const [a,b,s] of edits.sort((x,y)=>y[0]-x[0])) out=out.slice(0,a)+s+out.slice(b);
    fs.writeFileSync(file,out);
    console.log('CANDIDATE_PATCH',bundle,edits.length);
  }
}
if(stats.guards<2 || !stats.readWorker || !stats.readBroker) throw Error('Incomplete candidate '+JSON.stringify(stats));
console.log('CANDIDATE_READY',JSON.stringify(stats),JSON.stringify(Object.fromEntries([...providers].map(([k,v])=>[k,path.basename(v)]))));
