import {readFileSync,existsSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {runCase} from '../src/runner.ts';
const v2e=process.argv.includes('--v2e');
const v2d=v2e||process.argv.includes('--v2d');
const root=resolve(import.meta.dirname,'../../..');
const fixtureOnly=process.argv.includes('--fixture-only');
const reports:any[]=[];
for(const name of fixtureOnly ? ['fixture'] : ['fixture','t1a','t1b']) {
  const stem=name==='fixture' ? resolve(root,`packages/kernel-ts/test/fixtures/${v2d?'v2d':'v2c'}-runner`) : resolve(root,'data/compiled/v2',name+(v2e?'-v2e-runner':v2d?'-v2d-runner':'-runner'));
  if(!existsSync(stem+'.json')) {if(fixtureOnly)throw new Error('fixture absent');reports.push({name,status:'UNAVAILABLE'});continue;}
  const log=JSON.parse(readFileSync(stem+'.json','utf8'));
  const bytes=readFileSync(name==='fixture' ? resolve(root,'packages/kernel-ts/test/fixtures/escape.webbin') : stem+'.webbin');
  const result=await runCase(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),log);
  const mismatches=result.digests.flatMap((v,i)=>v===log.intervals[i].expected_state_sha256?[]:[i+1]);
  reports.push({name,status:mismatches.length?'FAIL':'PASS',mismatches,intervals:log.intervals.length,...result});
  if(mismatches.length)throw new Error(`${name} parity mismatch at ${mismatches[0]}`);
}
const report={schema:'flybench.v2c.node-runner-parity',status:reports.every(r=>r.status==='PASS')?'PASS':'INCOMPLETE',cases:reports};
if(!fixtureOnly){const out=resolve(root,process.env.FLYBENCH_EVIDENCE_OUT ? process.env.FLYBENCH_EVIDENCE_OUT+'/kernel-ts-parity.json' : v2d?'evidence/V2D/browser/kernel-ts-parity.json':'evidence/V2C/p3/kernel-ts-parity.json');mkdirSync(dirname(out),{recursive:true});writeFileSync(out,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({status:report.status,cases:reports.map(({digests,...r})=>r)}));
