// Pinned stock beta.2 exports. No application modules or ownership checks are patched.
import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {prepareDoctorDatabaseMigrations} from '/opt/beta/node_modules/openclaw/dist/doctor-schema-migrations-DewXbdCD.mjs';
import {i as withDoctorSqliteMaintenanceLock} from '/opt/beta/node_modules/openclaw/dist/doctor-sqlite-maintenance-lock-Dz-0AYA9.mjs';
import {t as withAgentDatabaseMaintenanceLease} from '/opt/beta/node_modules/openclaw/dist/openclaw-agent-db-maintenance-lease-CaPUEsBM.mjs';
import {r as ensureOpenClawAgentDatabaseSchema} from '/opt/beta/node_modules/openclaw/dist/openclaw-agent-db-schema-C46e22DW.mjs';
import {a as getOpenClawDatabaseMaintenanceScope} from '/opt/beta/node_modules/openclaw/dist/openclaw-state-maintenance-context-BOBtF7pF.mjs';
import {n as openNodeSqliteDatabase} from '/opt/beta/node_modules/openclaw/dist/node-sqlite-CbOS7zgX.mjs';
import {s as closeOpenClawAgentDatabasesAsync} from '/opt/beta/node_modules/openclaw/dist/openclaw-agent-db-lifecycle-B6f6neQT.mjs';
import {s as closeOpenClawStateDatabaseAsync} from '/opt/beta/node_modules/openclaw/dist/openclaw-state-db-cache-Dg4SKEty.mjs';

const state='/home/replay/.openclaw';
const agents=['main','openclaw'].map(agentId=>({agentId,path:path.join(state,'agents',agentId,'agent/openclaw-agent.sqlite')}));
const shared=path.join(state,'state/openclaw.sqlite');
const paths=[shared,...agents.map(a=>a.path)];
function parameters() {
  if(process.getuid()===0||process.env.OPENCLAW_STATE_DIR!==state)throw Error('SCHEMA_DRIVER_ISOLATION');
  for(const file of paths)if(!fs.lstatSync(file).isFile()||fs.lstatSync(file).isSymbolicLink())throw Error('SCHEMA_DRIVER_PATH');
  const pendingMigrations=paths.map(file=>{
    const db=new DatabaseSync(file,{readOnly:true});
    try {
      const foundVersion=db.prepare('PRAGMA user_version').get().user_version;
      const kind=file===shared?'state':'agent';
      if(foundVersion!==(kind==='state'?20:25))throw Error('SCHEMA_DRIVER_INPUT_VERSION');
      return {kind,path:file,foundVersion,supportedVersion:kind==='state'?36:38};
    }finally{db.close();}
  });
  return {env:process.env,pendingDatabasePaths:paths,databasePaths:paths,pendingMigrations,agentDatabaseTargets:agents,check:'full'};
}
function assertOwned(authority) {
  authority.assertCurrent();
  const scope=getOpenClawDatabaseMaintenanceScope();
  if(!scope?.ownsSchemaMaintenance)throw Error('SCHEMA_DRIVER_CUSTODY');
  scope.assertAdmission();
}

try {
  const params=parameters();
  if(process.argv.includes('--negative-owner-probe')) {
    let refused=false;
    try {await prepareDoctorDatabaseMigrations(params);}
    catch(error){if(error.message==='Pre-migration SQLite backups require Doctor maintenance ownership.')refused=true;else throw error;}
    if(!refused)throw Error('SCHEMA_DRIVER_OWNER_GUARD_FAILED');
    console.log('SCHEMA_DRIVER_OWNER_REFUSAL_PASS');
  }else {
    await withDoctorSqliteMaintenanceLock({env:process.env,operation:'Orion disposable schema migration',protectedPaths:paths,
      run:async authority=>{
        assertOwned(authority);
        const result=await prepareDoctorDatabaseMigrations(params);
        assertOwned(authority);
        if(result.warnings.length)throw Error('SCHEMA_DRIVER_MIGRATION_WARNING');
        // Version-only publication deliberately leaves ordinary additive columns pending.
        // Use the stock schema owner and agent lease to finish admission, without session repairs.
        await withAgentDatabaseMaintenanceLease({env:process.env,processBound:true},async lease=>{
          for(const target of agents) {
            assertOwned(authority);lease.assertOwned();
            const db=openNodeSqliteDatabase(target.path);
            try {ensureOpenClawAgentDatabaseSchema(db,{...target,env:process.env,register:true,integrityCheck:'full'});}
            finally{db.close();}
            lease.assertOwned();assertOwned(authority);
          }
        });
        assertOwned(authority);
        await closeOpenClawAgentDatabasesAsync(state);
        await closeOpenClawStateDatabaseAsync();
        assertOwned(authority);
      }});
    console.log('SCHEMA_ONLY_DRIVER_PASS');
  }
}catch(error){
  console.error(JSON.stringify({result:'STOP',code:/^[A-Z_]{3,80}$/.test(error.message)?error.message:'SCHEMA_DRIVER_FAILED',error_type:error.name}));
  process.exitCode=1;
}
