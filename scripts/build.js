#!/usr/bin/env node
import {copyFileSync,existsSync,mkdirSync,rmSync,lstatSync} from 'node:fs';
// Never publish the repository itself: QA snapshots, imports and notes are private.
const required=['index.html','style.css','app.js','core.js','data.json','taxonomy.json'];
const optional=['answers.json','answers-extra.json'];
try {
  for(const name of required)if(!existsSync(name)||!lstatSync(name).isFile())throw Error(`Missing runtime file: ${name}`);
  for(const name of optional)if(existsSync(name)&&!lstatSync(name).isFile())throw Error(`Unsafe runtime file: ${name}`);
  if(existsSync('_site')&&!lstatSync('_site').isDirectory())throw Error('_site must be a directory, not a symlink or file');
  rmSync('_site',{recursive:true,force:true});mkdirSync('_site');
  const files=[...required,...optional.filter(existsSync)];
  for(const name of files)copyFileSync(name,`_site/${name}`);
  console.log(JSON.stringify({directory:'_site',files},null,2));
} catch(error){console.error(error.message);process.exitCode=1;}
