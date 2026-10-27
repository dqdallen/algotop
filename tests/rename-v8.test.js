import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// Reverting the visible name or export filename makes these tests fail.
test('public page identifies AlgoWen and 算问集 without the retired brand',()=>{
 const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
 assert.match(html,/<title>AlgoWen · 算问集/);
 assert.match(html,/class="brand"[^>]*>.*AlgoWen/);
 assert.doesNotMatch(html,/AlgoTop/);
});

test('renamed app reads legacy storage, opens old hash links, and round-trips old backups',async()=>{
 const db=JSON.parse(readFileSync(new URL('../data.json',import.meta.url)));
 const [oldId,targetId]=Object.entries(db.questionAliases)[0];
 const legacy={ [oldId]:{saved:true,status:'review',note:'旧笔记不丢失'},retired_question:{note:'已移出题库仍保留'} };
 const storage=new Map([['algotop-v1',JSON.stringify(legacy)]]),reads=[],writes=[];
 const nodes=new Map(); const node=id=>{if(!nodes.has(id))nodes.set(id,{value:({'#scope':'all','#mode':'all','#sort':'posts'})[id]||'',innerHTML:'',textContent:'',children:[],showModal(){this.open=true},add(x){this.children.push(x)},append(x){this.children.push(x)},addEventListener(type,cb){this[type]=cb},querySelector(){return null}});return nodes.get(id)};
 let download,blob;
 globalThis.document={querySelector:node,createElement:tag=>({children:[],append(x){this.children.push(x)},click(){if(tag==='a')download=this.download}}),addEventListener(){},activeElement:{tagName:'BODY'}};
 globalThis.localStorage={getItem(key){reads.push(key);return storage.get(key)},setItem(key,value){writes.push(key);storage.set(key,value)}};
 globalThis.window={addEventListener(){}};
 globalThis.location={hash:'#question='+encodeURIComponent(oldId),pathname:'/algowen/',search:''};
 globalThis.Option=function(text,value){this.text=text;this.value=value};
 globalThis.fetch=async url=>({ok:true,json:async()=>JSON.parse(readFileSync(new URL('../'+url.replace('./',''),import.meta.url),'utf8'))});
 globalThis.confirm=()=>true;
 const originalCreate=URL.createObjectURL,originalRevoke=URL.revokeObjectURL;
 URL.createObjectURL=value=>{blob=value;return 'blob:test'};URL.revokeObjectURL=()=>{};
 try {
  await import('../app.js?rename-v8');
  assert.deepEqual(reads,['algotop-v1']);
  assert.equal(node('#detail').open,true);
  assert.ok(node('#detail-body').innerHTML.includes(targetId));
  assert.ok(node('#detail-body').innerHTML.includes('旧笔记不丢失'));
  node('#export').onclick();
  assert.match(download,/^algowen-progress-\d{4}-\d{2}-\d{2}\.json$/);
  const backup=JSON.parse(await blob.text());
  assert.equal(backup.version,1);
  assert.deepEqual(backup.progress[targetId],legacy[oldId]);
  assert.deepEqual(backup.progress.retired_question,legacy.retired_question);
  const oldBackup=JSON.stringify({version:1,progress:{[oldId]:{saved:true,status:'done',note:'旧版备份导入'}}});
  await node('#import').onchange({target:{files:[{name:'algotop-progress-2026-01-01.json',size:oldBackup.length,text:async()=>oldBackup}],value:'chosen'}});
  const saved=JSON.parse(storage.get('algotop-v1'));
  assert.equal(saved[targetId].note,'旧版备份导入');
  assert.equal(saved[targetId].status,'done');
  assert.deepEqual(saved.retired_question,legacy.retired_question);
  assert.ok(writes.length>0);assert.ok(writes.every(key=>key==='algotop-v1'));
 }finally{URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;}
});
