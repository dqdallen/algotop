import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('real app paginates, resets filters, preserves deep links and studies the whole selection',async()=>{
 const nodes=new Map(),events={};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:({'#scope':'all','#mode':'all','#sort':'posts','#page-size':'20'})[id]||'',innerHTML:'',textContent:'',children:[],focus(){document.activeElement=this},scrollIntoView(){},showModal(){this.open=true},close(){this.open=false;this.closeEvent?.()},add(x){this.children.push(x)},append(x){this.children.push(x)},addEventListener(type,cb){this[type==='close'?'closeEvent':type]=cb},querySelector(){return null}});return nodes.get(id)};
 globalThis.document={querySelector:node,createElement:()=>({append(){}}),addEventListener(){},activeElement:{tagName:'BODY',focus(){}}};
 globalThis.localStorage={getItem(){return '{}'},setItem(){}};
 globalThis.window={addEventListener(type,cb){events[type]=cb}};
 let hash='';globalThis.location={get hash(){return hash},set hash(value){hash=value.startsWith('#')?value:'#'+value},pathname:'/',search:''};globalThis.history={replaceState(){location.hash='#workspace'}};
 globalThis.CSS={escape:x=>x};globalThis.Option=function(text,value){this.text=text;this.value=value};
 globalThis.fetch=async url=>({ok:true,json:async()=>{const data=JSON.parse(readFileSync(new URL('../'+url.replace('./',''),import.meta.url),'utf8'));if(url==='./data.json')for(const source of data.sources)source.notes='INTERNAL_INGESTION_NOTE';return data}});
 await import('../app.js?pagination-runtime');
 const ids=()=>[...node('#list').innerHTML.matchAll(/data-open="([^"]+)"/g)].map(m=>m[1]);
 const clickPage=page=>node('#pagination').onclick({target:{closest:()=>({dataset:{page:String(page)},disabled:false})}});
 const first=ids();assert.equal(first.length,20);assert.match(node('#count').innerHTML,/第 1–20 道/);assert.match(node('#pagination').innerHTML,/aria-current="page"/);
 clickPage(2);const second=ids();assert.equal(document.activeElement,node('.list-head'));assert.equal(second.length,20);assert.ok(second.every(id=>!first.includes(id)));
 node('#study').onclick();events.hashchange();assert.match(node('#detail-body').innerHTML,/练习 1 \/ (?:[2-9]\d|\d{3,})/);node('#close-detail').onclick();
 location.hash='#question='+first[0];events.hashchange();assert.match(node('#detail-body').innerHTML,new RegExp(first[0]));assert.doesNotMatch(node('#detail-body').innerHTML,/INTERNAL_INGESTION_NOTE/);assert.deepEqual(ids(),second);document.activeElement={tagName:'BUTTON',isConnected:false,focus(){throw Error('detached card must not receive focus')}};node('#detail').open=false;events.hashchange();node('#close-detail').onclick();assert.equal(document.activeElement,node(`[data-open="${first[0]}"]`));
 for(const id of ['company','job-direction','answer-status','tag','year','mode','sort']){clickPage(2);node('#'+id).change();assert.deepEqual(ids(),first,id+' must reset page')}
 clickPage(2);node('#search').input();assert.deepEqual(ids(),first);
 clickPage(2);node('#tracks').onclick({target:{closest:()=>({dataset:{track:''}})}});assert.deepEqual(ids(),first);
 for(const size of [50,100,20]){node('#page-size').value=String(size);node('#page-size').change();assert.equal(ids().length,size);assert.equal(ids()[0],first[0])}
 node('#search').value='no-matching-question-xyz';node('#search').input();assert.equal(ids().length,0);assert.equal(node('#pagination').innerHTML,'');assert.equal(node('#pagination').hidden,true);
 node('#reset').onclick();assert.deepEqual(ids(),first);
 // Removing the last saved item on page 2 must clamp the result back to page 1.
 for(const id of [...first,second[0]])node('#list').onclick({target:{closest:s=>s==='[data-save]'?{dataset:{save:id}}:null}});
 node('#mode').value='saved';node('#mode').change();clickPage(2);assert.equal(ids().length,1);
 const last=ids()[0];node('#list').onclick({target:{closest:s=>s==='[data-save]'?{dataset:{save:last}}:null}});assert.equal(ids().length,20);assert.match(node('#count').innerHTML,/第 1–20 道/);
});
