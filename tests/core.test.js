import {test} from 'node:test';
import assert from 'node:assert/strict';
import {filterQuestions,countSources} from '../core.js';
test('cross-posts count once',()=>assert.equal(countSources([{event:'a'},{event:'a'},{event:'b'}]),2));
test('direction and keyword filters compose',()=>assert.deepEqual(filterQuestions([{title:'PLE',tracks:['推荐'],records:[]},{title:'DPO',tracks:['LLM'],records:[]}],{track:'推荐',query:'ple'}).map(q=>q.title),['PLE']));
test('company filter matches provenance',()=>assert.equal(filterQuestions([{title:'PLE',tracks:['推荐'],records:[{company:'字节'}]}],{company:'百度'}).length,0));
