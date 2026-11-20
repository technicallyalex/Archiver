// Browser integration regression. Run against an isolated Archiver QA server and headless Chromium CDP.
// ARCHIVER_QA_URL and ARCHIVER_CDP_URL override the default local endpoints.
const fs=require('fs'),assert=require('node:assert/strict');
(async()=>{const tab=await(await fetch((process.env.ARCHIVER_CDP_URL||'http://127.0.0.1:9261')+'/json/new?about:blank',{method:'PUT'})).json();const ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);let id=0;const pending=new Map(),errors=[];ws.onmessage=e=>{const v=JSON.parse(e.data);if(v.id){pending.get(v.id)?.(v);pending.delete(v.id);}if(v.method==='Runtime.exceptionThrown')errors.push(v.params.exceptionDetails);};const send=(method,params={})=>new Promise((r,j)=>{pending.set(++id,v=>v.error?j(v.error):r(v.result));ws.send(JSON.stringify({id,method,params}));});const ev=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};const until=async expr=>{for(let i=0;i<150;i++){if(await ev(expr))return;await new Promise(r=>setTimeout(r,50));}throw Error('Timeout '+expr)};

await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.env.ARCHIVER_QA_URL||'http://127.0.0.1:18925'});await until("typeof workflowUIReady!=='undefined'&&workflowUIReady&&!$('presetsButton').disabled");

await ev("window.scrollQAOriginalAPI=api;api=async(name,...args)=>name==='state'?structuredClone(state):scrollQAOriginalAPI(name,...args);const template={id:'qa',name:'QA.mp4',output:'QA-output.mp4',source_size:1000,output_size:800,settings:{codec:'h264',encoder:'libx264',bitrate:'crf',qualityValue:22,container:'mp4',audio:'copy'},duration:60,speed:'1x',fps:'30',eta:30};state.jobs=Array.from({length:16},(_,i)=>({...structuredClone(template),id:'scroll-'+i,name:'Queue item '+i+'.mp4',status:i<3?'running':'queued',percent:20,phase:'Encoding',verification:i<3?{status:'passed',checks:[]}:null,log:Array.from({length:100},(_,n)=>'Frame '+n)}));showPane('queue');$('progressView').value='bar';renderJobs();");
await new Promise(r=>setTimeout(r,300));

const result=await ev(`(async()=>{const e=document.querySelector('.workspace>main'),results=[];for(const theme of ['dark','light'])for(const view of ['bar','verbose'])for(const offset of [180,450,900,1400,2500]){ document.documentElement.dataset.theme=theme;$('progressView').value=view;workflowUI.openChecks.add('scroll-0');renderJobs();await new Promise(r=>setTimeout(r,100));e.scrollTop=offset;await new Promise(r=>setTimeout(r,100));const initial=e.scrollTop,samples=[];for(let i=0;i<10;i++){state.jobs[0].percent+=.1;state.jobs[0].log.push('New frame '+i);renderJobs();await new Promise(r=>setTimeout(r,80));samples.push(e.scrollTop);}results.push({theme,view,offset,initial,samples});}return results;})()`);

for(const scenario of result)for(const position of scenario.samples)assert(Math.abs(position-scenario.initial)<1,JSON.stringify(scenario));
await ev("$('progressView').value='verbose';renderJobs();window.scrollQALog=document.querySelector('pre[data-job]');scrollQALog.scrollTop=50");
const before=await ev("document.querySelector('pre[data-job]').scrollTop");
await ev("state.jobs[0].log.push('New output while reading old lines');renderJobs()");
assert.equal(await ev("document.querySelector('pre[data-job]').scrollTop"),before);
await ev("const log=document.querySelector('pre[data-job]');log.scrollTop=log.scrollHeight;state.jobs[0].log.push('New output while following');renderJobs()");
assert(await ev("(()=>{const log=document.querySelector('pre[data-job]');return log.scrollHeight-log.scrollTop-log.clientHeight<2})()"));
assert.equal(errors.length,0,JSON.stringify(errors));
console.log('Queue scroll regression: zero drift in 20 theme/view/offset scenarios; terminal scrollback preserved and following output still works.');
ws.close();})().catch(e=>{console.error(e);process.exit(1)});
