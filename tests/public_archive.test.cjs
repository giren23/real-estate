const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),zlib=require('node:zlib');
const {webcrypto}=require('node:crypto');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
function declaration(name){const start=new RegExp(`^(?:async )?function ${name}\\(`,'m').exec(source).index;const next=/^(?:async )?function /m.exec(source.slice(start+1));return source.slice(start,start+1+next.index);}
function setup(fetch){
  const ctx=vm.createContext({fetch,Blob,Response,DecompressionStream,TextDecoder,TextEncoder,Uint8Array,crypto:webcrypto,
    publicShardManifest:{generated_at:'test',districts:[]},publicDistrictCache:new Map(),publicTradeBucketCache:new Map()});
  ['fetchPublicArchiveFile','publicDistrictPayload','publicGroupTrades'].forEach(n=>vm.runInContext(declaration(n),ctx));
  return ctx;
}
test('loads gzip files as JSON without requiring a running server',async()=>{
  const payload={history:{rows:[[0,84.9,'2026-09',15,6000000]]}};
  const ctx=setup(async()=>new Response(zlib.gzipSync(JSON.stringify(payload))));
  assert.equal((await ctx.fetchPublicArchiveFile({file:'41135.json.gz'})).history.rows[0][4],6000000);
});
test('old plain JSON shards are still supported',async()=>{
  const ctx=setup(async()=>new Response('{"lawd_cd":"41135"}'));
  assert.equal((await ctx.fetchPublicArchiveFile({file:'41135.json'})).lawd_cd,'41135');
});
test('uses manifest file names and retries a failed download',async()=>{
  let requests=0;
  const ctx=setup(async url=>{assert.match(url,/41135.json.gz\?v=abc/);return ++requests===1?new Response('',{status:503}):new Response('{}')});
  ctx.publicShardManifest.districts=[{lawd_cd:'41135',file:'41135.json.gz',sha256:'abc'}];
  await assert.rejects(ctx.publicDistrictPayload('41135'));
  await ctx.publicDistrictPayload('41135');
  assert.equal(requests,2);
});
test('selected complex loads only its deterministic detail bucket',async()=>{
  const calls=[],ctx=setup(async url=>{calls.push(url);return new Response('{"rows":[{"apt_name":"이매촌한신"}]}')});
  const group={dong:'이매동',data_apt_name:'이매촌한신'};
  const parts=Array.from({length:16},(_,i)=>({file:i+'.json.gz'}));
  const hash=new Uint8Array(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode('이매동\0이매촌한신')));
  assert.equal((await ctx.publicGroupTrades(group,{trade_buckets:parts}))[0].apt_name,'이매촌한신');
  await ctx.publicGroupTrades(group,{trade_buckets:parts});
  assert.equal(calls.length,1);
  assert.ok(calls[0].includes('/'+hash[0]%16+'.json.gz'));
});
