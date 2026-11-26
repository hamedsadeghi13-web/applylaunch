/* Phase 2.2 - automated checks for the experimental fusion engine (needs: node, playwright, python3 for static servers).
   Compares the default site (engine=rule) with the ORIGINAL index.html taken from git (BASE_REF, default: the commit before Phase 2). */
const {chromium}=require('playwright');const {execSync,spawn}=require('child_process');const fs=require('fs'),path=require('path'),os=require('os');
const ROOT=path.resolve(__dirname,'..'),BASE_REF=process.env.BASE_REF||'HEAD';
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'fus-'));
fs.mkdirSync(path.join(tmp,'base'));for(const f of fs.readdirSync(path.join(ROOT,'docs')))if(f!=='index.html')fs.symlinkSync(path.join(ROOT,'docs',f),path.join(tmp,'base',f));
fs.writeFileSync(path.join(tmp,'base','index.html'),execSync(`git -C ${ROOT} show ${BASE_REF}:docs/index.html`,{maxBuffer:1<<28}));
const serve=(dir,port)=>spawn('python3',['-m','http.server',String(port),'--bind','127.0.0.1','-d',dir],{stdio:'ignore'});
const S1=serve(path.join(ROOT,'docs'),8791),S2=serve(path.join(tmp,'base'),8792);
let fails=0;const ok=(n,c,x='')=>{console.log((c?'ok   ':'FAIL ')+n+(x?'  '+x:''));if(!c)fails++};
const F=['Architecture','Civil Engineering','Mechanical Engineering','Electrical Engineering','Computer Science','Medicine','Law','Psychology','Economics','Environmental Engineering','Chemical Engineering','Urban Planning'];
async function open(b,url,opt={}){const ctx=await b.newContext({viewport:{width:1366,height:1000}});const p=await ctx.newPage();const errs=[],reqs=[];p.on('pageerror',e=>errs.push(e.message));p.on('request',r=>reqs.push(r.url()));
 if(opt.route)await p.route(opt.route.pat,opt.route.fn);
 await p.goto(url,{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>typeof LIVE!=='undefined'&&LIVE&&POSITIONS.length>1000,null,{timeout:60000});
 if(opt.fusion)await p.waitForFunction(()=>window.FUS&&(FUS.ready||FUS.spec===null),null,{timeout:60000}).catch(()=>{});
 await p.waitForTimeout(opt.wait||1500);return {ctx,p,errs,reqs}}
const run=(p,q,o={})=>p.evaluate(([q,o])=>{S.q.text=q;S.q.region=o.region||'all';S.sort=o.sort||'match';S.showIrr=false;S.showNoise=false;const t=performance.now();const l=sorted(searchResults());return {ids:l.map(r=>r.id),sem:l.filter(r=>r.sem).map(r=>r.id),ms:performance.now()-t,chip:l.slice(0,300).filter(r=>r.sem).length}},[q,o]);
(async()=>{const b=await chromium.launch();
 try{
  /* 1. default engine identical to the ORIGINAL index.html */
  const base=await open(b,'http://127.0.0.1:8792/'),cur=await open(b,'http://127.0.0.1:8791/');
  ok('default: fusion.js and affinity files are NOT requested',!cur.reqs.some(u=>/fusion\.js|affinity\./.test(u)));
  ok('default: window.FUS undefined',await cur.p.evaluate(()=>typeof window.FUS==='undefined'));
  let same=0,tot=0;const qs=[...F,'معماری','mimarlık','AI','engineering','Architecture Italy','phd','zzzz'];
  for(const q of qs)for(const o of [{},{region:'eu'},{sort:'dl'}]){const a=await run(base.p,q,o),c=await run(cur.p,q,o);tot++;if(JSON.stringify(a.ids)===JSON.stringify(c.ids))same++;else console.log('  differs:',q,JSON.stringify(o),a.ids.length,c.ids.length)}
  ok(`default engine: identical order/ids to the original site (${tot} queries)`,same===tot,`${same}/${tot}`);
  ok('default: no page errors',cur.errs.length===0,cur.errs.join('|'));await base.ctx.close();await cur.ctx.close();
  /* 2. fusion on */
  const fu=await open(b,'http://127.0.0.1:8791/?engine=fusion',{fusion:true});
  ok('fusion: loaded and ready',await fu.p.evaluate(()=>FUS.ready===true));
  const rb=await open(b,'http://127.0.0.1:8791/');let sup=0,subset=0,addedAll=0,tot2=0,perf=[],perfR=[];const extra={};
  for(const q of F){const a=await run(rb.p,q),c=await run(fu.p,q);tot2++;
   const A=new Set(a.ids),C=new Set(c.ids);const lostA=a.ids.filter(i=>!C.has(i));const added=c.ids.filter(i=>!A.has(i));
   if(!lostA.length)sup++;if(added.every(i=>c.sem.includes(i))&&c.sem.length===added.length)addedAll++;if(c.ids.length===new Set(c.ids).size)subset++;extra[q]=added.length;perf.push(c.ms);perfR.push(a.ms)}
  ok('fusion: no rule result removed (12 fields)',sup===tot2);ok('fusion: every added record is a labelled suggested match',addedAll===tot2);ok('fusion: no duplicates in list',subset===tot2);
  console.log('  suggested matches added per field:',JSON.stringify(extra));
  /* validated-query set differs in ORDER only for the 11 enabled fields; collect the share of top-100 kept */
  let keep=[];for(const q of F){const a=await run(rb.p,q),c=await run(fu.p,q);const t=new Set(c.ids.slice(0,100));keep.push(a.ids.slice(0,100).filter(i=>t.has(i)).length/Math.min(100,a.ids.length||1))}
  console.log('  share of rule top-100 still in fusion top-100 per field:',keep.map(x=>x.toFixed(2)).join(' '));ok('fusion: >=85% of the rule top-100 stays in the top-100 (all fields)',keep.every(x=>x>=.85));
  /* 3. not-eligible queries are identical to rule */
  let ident=0,n3=0;for(const [q,o] of [['Architecture Italy',{}],['engineering',{}],['AI',{}],['data science',{}],['phd',{}],['zzzz',{}],['Architecture',{sort:'dl'}],['Medicine',{sort:'fund'}]]){const a=await run(rb.p,q,o),c=await run(fu.p,q,o);n3++;if(JSON.stringify(a.ids)===JSON.stringify(c.ids))ident++;else console.log('  differs',q,JSON.stringify(o))}
  ok('fusion: free-text, multi-domain, unvalidated-domain and user-chosen sorts equal rule',ident===n3,`${ident}/${n3}`);
  /* 4. label in three languages + chip */
  ok('label key defined',await fu.p.evaluate(()=>typeof T('relSem')==='string'&&T('relSem').length>2));
  const html=await fu.p.evaluate(()=>{S.q.text='Architecture';S.sort='match';S.q.region='all';const l=sorted(searchResults());const r=l.find(x=>x.sem);return r?relChip(r):''});ok('suggested match chip renders',/small/.test(html)&&html.length>20,html.slice(0,80));
  ok('fusion: no page errors',fu.errs.length===0,fu.errs.join('|'));
  console.log('  ms per search (fusion vs rule), median:',perf.sort((a,b)=>a-b)[6].toFixed(0),perfR.sort((a,b)=>a-b)[6].toFixed(0));
  await fu.ctx.close();
  /* 5. fallbacks */
  for(const [name,route] of [['missing affinity.bin',{pat:/affinity\.bin/,fn:r=>r.abort()}],['corrupt affinity.bin',{pat:/affinity\.bin/,fn:r=>r.fulfill({status:200,body:Buffer.from('xx')})}],['version mismatch',{pat:/affinity\.json/,fn:async r=>{const t=await (await r.fetch()).json();t.relevance_version=99;r.fulfill({json:t})}}]]){
   const f=await open(b,'http://127.0.0.1:8791/?engine=fusion',{fusion:true,route});const a=await run(rb.p,'Architecture'),c=await run(f.p,'Architecture');
   ok('fallback: '+name+' -> rule results unchanged',JSON.stringify(a.ids)===JSON.stringify(c.ids)&&await f.p.evaluate(()=>!FUS.active),'');await f.ctx.close()}
  /* 6. kill switch: allowUrl:false */
  const ks=await open(b,'http://127.0.0.1:8791/?engine=fusion',{route:{pat:/flags\.json/,fn:r=>r.fulfill({json:{engine:'rule',allowUrl:false}})}});
  ok('kill switch: allowUrl=false ignores ?engine=fusion',await ks.p.evaluate(()=>typeof window.FUS==='undefined')&&!ks.reqs.some(u=>/fusion\.js/.test(u)));await ks.ctx.close();
  const fl=await open(b,'http://127.0.0.1:8791/',{route:{pat:/flags\.json/,fn:r=>r.fulfill({json:{engine:'fusion'}})},fusion:true});ok('flags.json engine=fusion enables it',await fl.p.evaluate(()=>FUS.ready===true));await fl.ctx.close();
  const er=await open(b,'http://127.0.0.1:8791/?engine=rule',{route:{pat:/flags\.json/,fn:r=>r.fulfill({json:{engine:'fusion'}})}});ok('?engine=rule overrides flags',await er.p.evaluate(()=>typeof window.FUS==='undefined'));await er.ctx.close();
  await rb.ctx.close();
 }catch(e){console.log('EXCEPTION',e);fails++}
 await b.close();S1.kill();S2.kill();console.log(fails?`\n${fails} FAILED`:'\nall passed');process.exit(fails?1:0)})();
