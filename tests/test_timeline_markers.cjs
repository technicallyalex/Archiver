const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8'),start=source.indexOf('function sampleTimelineHTML(job)'),end=source.indexOf('const visibleSampleVideos',start);
const context=vm.createContext({token:'test',encodeURIComponent,esc:x=>String(x),duration:x=>String(x)});vm.runInContext(source.slice(start,end),context);
for(const count of [1,3,12]){
 context.job={id:'test',status:'running',progress:{sourceDuration:14000,sampleWindows:Array.from({length:count},(_,i)=>({start:i*1000,duration:8})),activeSampleIndices:[0]}};
 const html=vm.runInContext('sampleTimelineHTML(job)',context);
 assert.equal((html.match(/class="sample-range-marker"/g)||[]).length,count);assert(html.includes('data-start="0"'));assert(html.includes('Short ranges are enlarged for visibility'));assert(!html.includes('sample-pin'));assert(html.includes('sample-time-range'));assert(html.includes('Testing'));
}
context.job={id:'pending',status:'running',progress:{}};const pending=vm.runInContext('sampleTimelineHTML(job)',context);assert(pending.includes('preview-skeleton'));assert(!pending.includes('class="sample-range-marker"'));
console.log('Timeline templates retain skeletons and exact sample metadata, with endpoint bars and no upper dots.');

context.job={id:'scout',status:'running',progress:{sourceDuration:300,stage:'motion-scout',motionProbes:[{index:0,start:10,duration:2,status:'completed',mean:2},{index:1,start:80,duration:2,status:'active'},{index:2,start:170,duration:2,status:'planned'}]}};
const scout=vm.runInContext('sampleTimelineHTML(job)',context);assert(scout.includes('Motion probes'));assert(scout.includes('1 / 3 measured'));assert(scout.includes('Checking 80–82'));assert.equal((scout.match(/data-probe-index=/g)||[]).length,3);assert(!scout.includes('sample-anchor'));assert(!scout.includes('<video'));assert(!scout.includes('Sample 1'));
context.job.progress.sampleWindows=[{start:80,duration:8}];const selected=vm.runInContext('sampleTimelineHTML(job)',context);assert(selected.includes('Test samples'));assert(!selected.includes('data-probe-index='));
console.log('Motion scouting shows actual probe positions/states before switching to selected samples.');

context.job={id:'motion',status:'running',progress:{sourceDuration:100,sampleWindows:[{start:10,duration:8},{start:30,duration:8},{start:50,duration:8}],sampleMotion:[{start:30,duration:8,mean:7.25},{start:10,duration:8,mean:0}]}};
const motionHTML=vm.runInContext('sampleTimelineHTML(job)',context);
assert(motionHTML.indexOf('Motion 0.00')<motionHTML.indexOf('Motion 7.25'));
assert(motionHTML.includes('Motion · Pending'));
context.job.status='completed';assert(vm.runInContext('sampleTimelineHTML(job)',context).includes('Motion · Not measured'));
context.job.progress.motionAvailable=false;assert(vm.runInContext('sampleTimelineHTML(job)',context).includes('Motion · Unavailable'));
console.log('Motion values match timestamps rather than array positions; zero and unmeasured statuses render correctly.');
