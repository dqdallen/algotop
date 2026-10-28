import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as core from '../core.js';
const items=Array.from({length:105},(_,i)=>({id:`q${i+1}`}));
test('pagination defaults to 20 and slices without changing the ordered input',()=>{
 assert.equal(typeof core.paginateQuestions,'function');
 const result=core.paginateQuestions(items);
 assert.deepEqual(result.items,items.slice(0,20));assert.equal(result.total,105);
 assert.equal(result.pageCount,6);assert.equal(result.start,1);assert.equal(result.end,20);
 assert.deepEqual(core.paginateQuestions(items,2).items,items.slice(20,40));assert.equal(items.length,105);
});
test('pagination supports page sizes and clamps after results shrink',()=>{
 assert.equal(typeof core.paginateQuestions,'function');
 for(const size of [20,50,100]){const r=core.paginateQuestions(items,999,size);assert.equal(r.page,Math.ceil(105/size));assert.equal(r.end,105);assert.equal(r.items.at(-1).id,'q105')}
 assert.equal(core.paginateQuestions(items,-5).page,1);
 assert.equal(core.paginateQuestions(items,NaN,0).pageSize,20);
 const empty=core.paginateQuestions([],7);assert.equal(empty.pageCount,0);assert.equal(empty.start,0);assert.equal(empty.end,0);assert.deepEqual(empty.pages,[]);
});
test('page links stay bounded and always include current and end pages',()=>{
 assert.equal(typeof core.paginateQuestions,'function');
 const r=core.paginateQuestions(Array(10000).fill(0),250);
 assert.ok(r.pages.length<=7);for(const page of [1,249,250,251,500])assert.ok(r.pages.includes(page));
});

test('pagination release uses one cache key for HTML assets and the core module import',async()=>{
 const {readFileSync}=await import('node:fs');
 const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
 const app=readFileSync(new URL('../app.js',import.meta.url),'utf8');
 const key=html.match(/src="\.\/app\.js\?v=([^"]+)"/)?.[1];
 assert.ok(key,'app module must bypass the pre-pagination browser cache');
 assert.ok(html.includes(`href="./style.css?v=${key}"`),'stylesheet uses the same release key');
 assert.ok(app.includes(`from './core.js?v=${key}'`),'core module uses the same release key');
});
