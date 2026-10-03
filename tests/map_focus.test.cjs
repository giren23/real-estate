const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
function declaration(name){
  const match=new RegExp(`^(?:async )?function ${name}\\(`,'m').exec(source);
  assert.ok(match,name);
  const tail=source.slice(match.index+1);
  const next=/^(?:async )?function /m.exec(tail);
  return source.slice(match.index,next?match.index+1+next.index:source.length);
}
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
const group=name=>({key:name,apt_name:name,lawd_cd:'41135',dong:'정자동',areas:[],hydrated:false,search_names:[name]});
function setup(overrides={}){
  const calls=[],elements={mapState:{textContent:''}};
  const marker={openPopup(){calls.push('popup')},setPopupContent(){}};
  const ctx=vm.createContext({
    mapFocusRunId:0,localityFocusRunId:0,searchSuggestionTimer:null,clearTimeout,
    mapLocalityAnchor:null,markers:new Map(),
    map:{stop(){calls.push('stop')},invalidateSize(o){calls.push(['size',o.pan])},setView(p,z,o){calls.push(['view',...p,z,o.animate])}},
    byId:id=>elements[id],cachedCoordinate:()=>null,
    hydrateGroup:async g=>g,geocodeGroup:async()=>({lat:37.38,lng:127.12}),
    ensureMapMarker:()=>marker,refreshGraphAddButtons(){},renderDetails(){calls.push('details')},
    mapPopupHtml:()=>'',activeBoard:()=>null,setStatus:message=>calls.push(message),
    ...overrides,
  });
  ['normalized','compactName','looseName','nameVariants','isSubsequence','apartmentNameScore','confidentSearchMatch','cancelMapFocus','centerMapOnGroup','focusGroup'].forEach(name=>vm.runInContext(declaration(name),ctx));
  return {ctx,calls,elements};
}
test('resolved coordinates centre immediately while history is still pending',async()=>{
  const slow=deferred(),{ctx,calls}=setup({hydrateGroup:()=>slow.promise});
  const result=await ctx.focusGroup(group('이매촌한신'));
  assert.equal(result.lat,37.38);
  assert.ok(calls.some(c=>Array.isArray(c)&&c.join(',')==='view,37.38,127.12,16,false'));
  assert.ok(!calls.includes('details'));
});
test('a history failure does not prevent map centring',async()=>{
  const {ctx,calls}=setup({hydrateGroup:async()=>{throw new Error('offline')}});
  await ctx.focusGroup(group('단지'));
  assert.ok(calls.includes('popup'));
});
test('cached coordinates need no geocoding',async()=>{
  const {ctx}=setup({geocodeGroup:()=>assert.fail('unnecessary request')});
  const coord={lat:37.4,lng:127.1};
  assert.equal(await ctx.focusGroup(group('단지'),coord),coord);
});
test('a late response from the previous search cannot move the map',async()=>{
  const old=deferred();
  const {ctx,calls}=setup({geocodeGroup:g=>g.key==='old'?old.promise:Promise.resolve({lat:35,lng:129})});
  const first=ctx.focusGroup(group('old'));
  await ctx.focusGroup(group('new'));
  old.resolve({lat:37,lng:127});
  assert.equal(await first,null);
  assert.equal(calls.filter(c=>Array.isArray(c)&&c[0]==='view').length,1);
  assert.equal(ctx.mapLocalityAnchor.group.key,'new');
});
test('reset or another navigation cancels pending focus',async()=>{
  const slow=deferred(),{ctx,calls}=setup({geocodeGroup:()=>slow.promise});
  const pending=ctx.focusGroup(group('단지'));
  ctx.cancelMapFocus();slow.resolve({lat:37,lng:127});
  assert.equal(await pending,null);
  assert.ok(!calls.includes('popup'));
});
test('missing coordinate is an explicit failure, not a dong-centre marker',async()=>{
  const {ctx,calls,elements}=setup({geocodeGroup:async()=>null});
  assert.equal(await ctx.focusGroup(group('단지')),null);
  assert.ok(!calls.includes('popup'));
  assert.match(elements.mapState.textContent,/정확한 위치를 확인하지 못했습니다/);
});
test('address from history may resolve a previously missing coordinate',async()=>{
  const g=group('단지'),{ctx}=setup({hydrateGroup:async g=>{g.jibun='123';return g},geocodeGroup:async(g,withAddress)=>withAddress&&g.jibun?{lat:37,lng:127}:null});
  assert.equal((await ctx.focusGroup(g)).lat,37);
});
test('common aliases match but two numbered phases are not auto-selected',()=>{
  const {ctx}=setup();
  assert.equal(ctx.apartmentNameScore('이매한신','이매촌한신'),1000);
  assert.equal(ctx.apartmentNameScore('상록우성','상록마을(우성)1'),1000);
  const matches=[{group:group('상록우성1'),score:1000},{group:group('상록우성2'),score:1000}];
  assert.equal(ctx.confidentSearchMatch(matches,'상록우성'),null);
  assert.equal(ctx.confidentSearchMatch(matches,'상록우성2'),matches[1]);
});
test('same name in different localities requires choosing a result',()=>{
  const {ctx}=setup(),matches=[{group:group('현대아파트'),score:1000},{group:{...group('현대아파트'),lawd_cd:'11110'},score:1000}];
  assert.equal(ctx.confidentSearchMatch(matches,'현대아파트'),null);
});
