import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const html=()=>readFileSync(new URL('../index.html',import.meta.url),'utf8');
test('study UI provides labelled dialog, import, sorting, tags, reset and live feedback',()=>{for(const token of ['<dialog','id="detail"','id="import"','id="sort"','id="tag"','id="reset"','id="study"','id="notice"','aria-labelledby="detail-title"'])assert.ok(html().includes(token),token)});
test('answer overlay and route navigation are implemented',()=>{const js=readFileSync(new URL('../app.js',import.meta.url),'utf8');for(const token of ['answers.json','hashchange','validateProgress','showModal','answer.sections'])assert.ok(js.includes(token),token)});
