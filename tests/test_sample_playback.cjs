const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8');let videos=[],clock=10000,timers=[],fetches=[];
const context=vm.createContext({performance:{now:()=>clock},document:{hidden:false},activePane:'tests',observedSampleVideos:new Set(),visibleSampleVideos:new Set(),sampleObserver:{observe(){},unobserve(){}},$ :()=>({querySelectorAll:()=>videos}),sampleShouldPlay:v=>v.active&&v.isConnected,settlePreview(){},setTimeout:f=>timers.push(f),fetch:url=>{fetches.push(url);return new Promise(()=>{});}});
vm.runInContext(source.slice(source.indexOf('function stopSampleClock('),source.indexOf('samplePlaybackReady=true;',source.indexOf('function stopSampleClock('))),context);
vm.runInContext(source.slice(source.indexOf('function retrySamplePreview('),source.indexOf("for(const type of ['loadedmetadata'",source.indexOf('function retrySamplePreview('))),context);
function video(kind='proxy'){
 const attrs={src:kind==='native'?'/source':'/clip'};
 const v={active:true,isConnected:true,paused:true,readyState:4,seeking:false,ended:false,poster:'still.jpg',currentTime:11,dataset:{sourceKind:kind,nativeSrc:'/source',nativeMime:'video/mp4',previewSrc:'/clip',sampleStart:'10',sampleDuration:'8',sampleFps:'60'},getAttribute:k=>attrs[k],removeAttribute:k=>delete attrs[k],pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()},load(){this.readyState=0},canPlayType:()=>'',closest:()=>({classList:{contains:()=>false}})};
 Object.defineProperty(v,'src',{get:()=>attrs.src,set:s=>attrs.src=s});return v;
}
(async()=>{
 let v=video();videos=[v];let finish;
 v.play=()=>new Promise(resolve=>{finish=()=>{v.paused=false;resolve()}});
 vm.runInContext('syncSamplePlayback()',context);v.active=false;vm.runInContext('syncSamplePlayback()',context);finish();await new Promise(r=>setImmediate(r));assert(v.paused,'A late play request restarted an inactive sample');
 v=video('native');v._sampleWasActive=true;v._lastSampleFrame=0;videos=[v];vm.runInContext('syncSamplePlayback()',context);assert.equal(v.dataset.sourceKind,'proxy','Stalled native preview did not fall back');assert(!v.src.includes('#t='));
 v=video();v._sampleWasActive=true;v._lastSampleFrame=0;videos=[v];timers=[];vm.runInContext('syncSamplePlayback()',context);assert.equal(v.dataset.retryPending,'true');assert.equal(v.dataset.retryCount,'1');assert(v.paused);assert.equal(timers.length,1);
 v=video('native');v._sampleWasActive=true;v._sampleRateStart=7000;v._samplePresented=0;videos=[v];context.v=v;vm.runInContext('sampleFramePresented(v,11)',context);assert.equal(v.dataset.sourceKind,'proxy','Low native frame rate did not fall back');
 const a=video(),b=video();a.active=b.active=false;a.dataset.previewSrc='/next-a';b.dataset.previewSrc='/next-b';for(const x of [a,b]){x.removeAttribute('src');x.closest=()=>({classList:{contains:()=>true}})}context.warm=[a,b];vm.runInContext('warmSampleProxies(warm);warmSampleProxies(warm)',context);assert.deepEqual(fetches,['/next-a']);assert(a.paused&&b.paused,'Warming played inactive previews');
 console.log('Playback recovers stalled/slow sources, ignores stale play requests and warms at most one inactive proxy without playing it.');
})().catch(e=>{console.error(e);process.exit(1)});
