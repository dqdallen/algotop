import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
const workflow=()=>readFileSync(new URL('../.github/workflows/pages.yml',import.meta.url),'utf8');
test('Pages uses verified Node24 action pins with no credentials persistence or package cache',()=>{
 const text=workflow();
 assert.match(text,/runs-on: ubuntu-24\.04/);
 assert.match(text,/node-version: ['"]?24['"]?\s/);
 assert.match(text,/package-manager-cache: false/);
 assert.match(text,/persist-credentials: false/);
 assert.deepEqual([...text.matchAll(/uses: (\S+)/g)].map(m=>m[1]),[
  'actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd',
  'actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444',
  'actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d',
  'actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9',
  'actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346'
 ]);
});
test('Pages retains validation gates and publishes only public artifact without scheduling collectors',()=>{
 const text=workflow();
 assert.match(text,/contents: read\s+pages: write\s+id-token: write/);
 assert.match(text,/group: pages\s+cancel-in-progress: true/);
 assert.match(text,/name: github-pages/);
 assert.deepEqual([...text.matchAll(/- run: ([^\n]+)/g)].map(m=>m[1]),['npm test','node scripts/data-pipeline.js','node scripts/build.js']);
 assert.match(text,/path: _site\s+include-hidden-files: false/);
 assert.match(text,/branches: \[main\]/);assert.match(text,/workflow_dispatch:/);
 for(const file of readdirSync(new URL('../.github/workflows/',import.meta.url))){
  const source=readFileSync(new URL('../.github/workflows/'+file,import.meta.url),'utf8');
  assert.doesNotMatch(source,/^\s*(?:schedule|cron):/m);
 }
 assert.doesNotMatch(text,/pull_request_target|secrets\.|enablement: true|continue-on-error|tools\/collection/);
});
