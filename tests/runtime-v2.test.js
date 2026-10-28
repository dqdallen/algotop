import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
test('real app ignores removed filter axes and retains user filters',async()=>{
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{value:({'#scope':'archive','#source-type':'not-a-type','#date-basis':'not-a-date','#mode':'all','#sort':'posts'})[id]||'',innerHTML:'',textContent:'',children:[],showModal(){this.open=true},add(x){this.children.push(x)},append(x){this.children.push(x)},addEventListener(type,cb){this[type]=cb},querySelector(){return null}});return nodes.get(id)};
 globalThis.document={querySelector:node,createElement:()=>({children:[],append(x){this.children.push(x)}}),addEventListener(){},activeElement:{tagName:'BODY'}};
 globalThis.localStorage={getItem(){return '{}'},setItem(){}};globalThis.window={addEventListener(){}};globalThis.location={hash:''};globalThis.Option=function(text,value){this.text=text;this.value=value};
 globalThis.fetch=async url=>({ok:true,json:async()=>JSON.parse(readFileSync(new URL('../'+url.replace('./',''),import.meta.url),'utf8'))});
 await import('../app.js?runtime-test');
 assert.match(node('#count').innerHTML,/找到 <b>323<\/b> 道题/);assert.ok(node('#list').innerHTML.includes('收录来源数'));assert.ok(node('#job-direction').children.length>1);assert.ok(!node('#list').innerHTML.includes('undefined'));
 node('#answer-status').value='answered';node('#answer-status').change();assert.ok(!node('#list').innerHTML.includes('答案待补充'));node('#answer-status').value='missing';node('#answer-status').change();assert.ok(!node('#list').innerHTML.includes('含参考答案'));
 node('#company').value='a-company-with-no-records';node('#company').change();assert.match(node('#list').innerHTML,/暂时没有匹配/);
 node('#reset').onclick();assert.equal(node('#answer-status').value,'all');assert.ok(node('#list').innerHTML.includes('收录来源数'));
 node('#job-direction').value='computer-vision';node('#job-direction').change();assert.match(node('#count').innerHTML,/找到 <b>6<\/b> 道题/);
});
