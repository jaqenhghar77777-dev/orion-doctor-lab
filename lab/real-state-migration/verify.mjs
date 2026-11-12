import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {DatabaseSync,backup} from 'node:sqlite';
import {tables,rows,fingerprint,fingerprintRows} from './compat.mjs';

const [mode,input,working,reportFile,snapshot]=process.argv.slice(2);
const hash=data=>createHash('sha256').update(data).digest('hex');
const DATABASES=['agents/main/agent/openclaw-agent.sqlite','agents/openclaw/agent/openclaw-agent.sqlite','state/openclaw.sqlite'];
const RUNTIME=new Set(['schema_meta','memory_index_state','agent_databases','state_leases','agent_database_leases']);
const CREDENTIALS=new Set(['auth_profile_state','auth_profile_store','device_auth_tokens','device_bootstrap_tokens',
  'device_identities','device_pairing_paired','gateway_origin_device_tokens','config_revision_keys','secret_store_entries',
  'worker_environment_credentials','mcp_oauth_stores']);
let current={stage:mode};
const result={result:'PASS',stage:mode,databases:[],tables:[],failures:[]};
const manifest=JSON.parse(fs.readFileSync(path.join(input,'manifest.json'),'utf8'));
function failure(code,details={}){result.failures.push({...current,code,...details});}
function compare(before,after,allowAdded) {
  const count=new Map();
  for(const row of after)count.set(row,(count.get(row)||0)+1);
  for(const row of before) {
    const n=count.get(row)||0;
    if(!n)return false;
    count.set(row,n-1);
  }
  return allowAdded||before.length===after.length;
}
function recordHashes(entries,table) {
  // Hash separately to compare multisets without emitting record contents.
  return entries.map(row=>fingerprintRows([row],table));
}
try {
  for(const relative of DATABASES) {
    current={stage:mode,database:relative};
    const source=new DatabaseSync(path.join(input,relative),{readOnly:true});
    const target=new DatabaseSync(path.join(working,relative),{readOnly:true});
    try {
      const version=target.prepare('PRAGMA user_version').get().user_version;
      const expected=mode==='before'?(relative.startsWith('agents/')?25:20):(relative.startsWith('agents/')?38:36);
      const integrity=target.prepare('PRAGMA integrity_check').all().map(r=>r.integrity_check);
      const foreignKeys=target.prepare('PRAGMA foreign_key_check').all().length;
      if(version!==expected)failure('SCHEMA_VERSION',{expected,actual:version});
      if(integrity.length!==1||integrity[0]!=='ok')failure('INTEGRITY');
      if(foreignKeys)failure('FOREIGN_KEYS',{violations:foreignKeys});
      result.databases.push({path:relative,user_version:version,integrity:integrity.length===1&&integrity[0]==='ok'?'ok':'FAIL',foreign_key_violations:foreignKeys});
      const existing=new Map(tables(target).map(t=>[t.name,t]));
      for(const table of tables(source)) {
        current={stage:mode,database:relative,table:table.name};
        const prior=rows(source,table),actualTable=existing.get(table.name);
        const baseline=manifest.baselines.find(b=>b.database===relative&&b.table===table.name);
        if(!baseline||baseline.rows!==prior.length||baseline.fingerprint_sha256!==fingerprint(source,table)) {
          failure('INPUT_LOGICAL_BASELINE');continue;
        }
        if(!actualTable) {
          result.tables.push({database:relative,table:table.name,before:prior.length,after:null,change:'removed-table'});
          if(prior.length)failure('POPULATED_TABLE_REMOVED');
          continue;
        }
        const actual=rows(target,actualTable);
        const beforeHash=fingerprint(source,table),afterHash=fingerprint(target,actualTable);
        const meta={database:relative,table:table.name,before:prior.length,after:actual.length,before_hash:beforeHash,after_hash:afterHash};
        const columns=table.columns.filter(c=>c.hidden===0).map(c=>c.name);
        const nextColumns=new Set(actualTable.columns.filter(c=>c.hidden===0).map(c=>c.name));
        const missing=columns.filter(c=>!nextColumns.has(c));
        meta.added_columns=[...nextColumns].filter(c=>!columns.includes(c));
        meta.removed_columns=missing;
        result.tables.push(meta);
        if(CREDENTIALS.has(table.name)&&actual.length)failure('CREDENTIAL_TABLE_POPULATED',{rows:actual.length});
        if(mode==='before') {
          if(beforeHash!==afterHash)failure('BEFORE_CONTENT_MISMATCH');
          continue;
        }
        if(RUNTIME.has(table.name)||table.type==='virtual'||table.name.includes('_fts')||
           table.name==='session_transcript_index_state') {
          if(table.name==='memory_index_state'&&(prior.length!==1||actual.length!==1||
             actual[0].id!==prior[0].id||actual[0].revision<prior[0].revision))
            failure('MEMORY_REVISION_STATE');
          meta.classification='schema-or-runtime-metadata';continue;
        }
        if(!prior.length) {
          meta.classification='new-runtime-or-derived-records';continue;
        }
        if(missing.length) {
          if(prior.length)failure('DATA_COLUMN_REMOVED',{columns:missing});
          continue;
        }
        const projected=actual.map(row=>{
          const entry={};
          if(Object.hasOwn(row,'__orion_rowid__'))entry.__orion_rowid__=row.__orion_rowid__;
          for(const column of columns)entry[column]=row[column];
          return entry;
        });
        if(!compare(recordHashes(prior,table),recordHashes(projected,table),table.name==='audit_events'))
          failure('LOGICAL_RECORD_MISMATCH',{before:prior.length,after:actual.length});
      }
      for(const table of existing.values())if(!manifest.baselines.some(b=>b.database===relative&&b.table===table.name)) {
        const count=rows(target,table).length;
        result.tables.push({database:relative,table:table.name,before:null,after:count,change:'added-table'});
        if(CREDENTIALS.has(table.name)&&count)failure('NEW_CREDENTIAL_TABLE_POPULATED');
      }
      if(relative==='state/openclaw.sqlite'&&mode!=='before') {
        const agents=target.prepare('SELECT agent_id,schema_version FROM agent_databases ORDER BY agent_id').all();
        if(agents.length!==2||agents.some(r=>!['main','openclaw'].includes(r.agent_id)||r.schema_version!==38))
          failure('AGENT_REGISTRY_SCHEMA');
      }
    }finally{source.close();target.close();}
  }
  for(const item of manifest.files.filter(f=>f.path.startsWith('workspace/'))) {
    current={stage:mode,file:item.path};
    if(hash(fs.readFileSync(path.join(working,item.path)))!==item.sha256)failure('IDENTITY_FILE_CHANGED');
  }
  if(!result.failures.length&&snapshot) {
    for(const relative of DATABASES) {
      const source=new DatabaseSync(path.join(working,relative),{readOnly:true});
      const dest=path.join(snapshot,relative);fs.mkdirSync(path.dirname(dest),{recursive:true,mode:0o700});
      try{await backup(source,dest);}finally{source.close();}
    }
  }
}catch(error) {
  failure('VERIFICATION_EXCEPTION',{error_code:/^[A-Z0-9_]+$/.test(error.code||'')?error.code:'SQLITE_OR_PAYLOAD_ERROR'});
}
if(result.failures.length)result.result='STOP';
fs.writeFileSync(reportFile,JSON.stringify(result,null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({result:result.result,stage:mode,databases:result.databases,failures:result.failures}));
if(result.result!=='PASS')process.exitCode=1;
