const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const script=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const start=script.indexOf('function testLoadingHTML('),end=script.indexOf('function renderAnalysis()',start);
const context=vm.createContext({esc:v=>String(v??''),duration:v=>String(v),qualityResultHTML:()=>'<div>result</div>',sampleTimelineHTML:()=>'<div>timeline</div>',motionResultHTML:()=>'',crfMeasurementsHTML:()=>'',validationResultHTML:()=>''});vm.runInContext(script.slice(script.indexOf('const esc ='),script.indexOf('function duration(')),context);vm.runInContext(script.slice(start,end),context);
for(const status of ['queued','waiting','running','completed','failed','cancelled']){const job={id:'test-'+status,name:'Source.mp4',status,settings:{autoEngine:'ab-av1',xpsnrTarget:38},progress:{},activity:[],outputDirectory:'C:/test',result:status==='completed'?{}:null};context.job=job;const html=vm.runInContext('testJobHTML(job)',context);assert(html.includes('data-test-id="'+job.id+'"'));assert(html.includes(job.name));assert(!html.includes('/api/thumbnail?job='));}
console.log('Test Queue templates render every job state without Encoding queue thumbnail references.');
const codecNodes=Object.fromEntries(['outputCodec','codec','abCodec','sourceCodec','qualityMode','qualityModeWrap','archiveProfile'].map(id=>[id,{value:'h264',closest:()=>({hidden:false})}]));
context.$=id=>codecNodes[id];
vm.runInContext(script.slice(script.indexOf('function syncPrimaryCodec(){'),script.indexOf("$('outputCodec').addEventListener",script.indexOf('function syncPrimaryCodec(){'))),context);
for(const codec of ['h264','hevc','av1'])for(const mode of ['auto','source','custom']){codecNodes.outputCodec.value=codec;codecNodes.qualityMode.value=mode;codecNodes.codec.value='h264';codecNodes.abCodec.value='av1';codecNodes.sourceCodec.value='hevc';vm.runInContext('syncPrimaryCodec()',context);for(const id of ['outputCodec','codec','abCodec','sourceCodec'])assert.equal(codecNodes[id].value,codec);}
console.log('Primary codec remains authoritative across all quality workflows.');

context.settings={qualityMode:'source',resolution:'1080',fps:'30',bitrate:'crf'};
assert.equal(vm.runInContext("estimateHint('Use Automated (Test) or Manual',settings,'missing_video_bitrate')",context),'Reported video bitrate unavailable');
assert.equal(vm.runInContext("estimateHint('test footage.mp4: unavailable',settings)",context),'Review the estimate details');
context.settings={qualityMode:'custom',resolution:'original',fps:'original'};
assert.equal(vm.runInContext("estimateHint('Size requires a matching test for each selected file',settings,'test_required')",context),'Run a test for a size estimate');
console.log('Estimate errors preserve their actual cause instead of treating any mention of test as a test requirement.');

const terminal=vm.runInContext('terminalWindow("Encoding log", "<script>alert(1)</script>\\nERROR: failed\\nEncoding crf 22\\nCompleted")',context);
assert(!terminal.includes('<script>'));
assert(terminal.includes('Terminal output'));
assert(terminal.includes('terminal-error'));
assert(terminal.includes('terminal-operation'));
assert(terminal.includes('terminal-success'));
console.log('Shared terminal windows escape tool output and distinguish operations, errors and success.');

assert(script.includes("card.querySelector('.test-details-region .queue-terminal pre')"),'Test terminal must retain scroll position across refreshes');

vm.runInContext(script.slice(script.indexOf('function explainDisabledOption('),script.indexOf('function updateAudioOptions(')),context);
let selectedText='Automated (Test)',writes=0;
const clonedLabel={get textContent(){return selectedText},set textContent(value){selectedText=value;writes++;}};
const option={dataset:{},textContent:'Automated (Test)',disabled:true,selected:true,title:'',closest:()=>({querySelector:()=>clonedLabel})};
context.option=option;
vm.runInContext("explainDisabledOption(option,'Choose H.264, H.265 or AV1')",context);
assert(selectedText.includes('Choose H.264'));
option.disabled=false;
vm.runInContext("explainDisabledOption(option,'Choose H.264, H.265 or AV1')",context);
assert.equal(selectedText,'Automated (Test)');assert.equal(option.title,'');
const before=writes;
for(let i=0;i<10;i++)vm.runInContext("explainDisabledOption(option,'Choose H.264, H.265 or AV1')",context);
assert.equal(writes,before,'Unchanged polling must not rewrite selected content');
option.selected=false;option.disabled=true;
vm.runInContext("explainDisabledOption(option,'Unavailable')",context);
assert.equal(selectedText,'Automated (Test)','Unselected options must not overwrite the displayed selection');
console.log('Disabled reasons clear from the displayed selected label without rewriting unchanged dropdown content.');

const queueControls=script.slice(script.indexOf(" $('startTests').disabled="),script.indexOf(' // Completed cards remain intact'));
const controls={startTests:{},pauseTests:{}};
const queueContext=vm.createContext({$:id=>controls[id],jobs:[{status:'queued'}],state:{test_queue_running:false,test_queue_paused:false}});
vm.runInContext(queueControls,queueContext);assert.equal(controls.startTests.disabled,false);assert.equal(controls.pauseTests.disabled,true);
queueContext.state.test_queue_running=true;vm.runInContext(queueControls,queueContext);assert.equal(controls.startTests.disabled,true);assert.equal(controls.pauseTests.disabled,false);
const html=fs.readFileSync(require('node:path').join(__dirname,'../web/index.html'),'utf8');
assert(!html.match(/<input[^>]*id="autoStartTests"[^>]*>/)[0].includes('checked'));
console.log('Test Queue offers manual start while idle; automatic start is unchecked by default.');

context.job={id:'timing',name:'Video.mp4',status:'running',settings:{},started:Date.now()/1000-500,progress:{stage:'search-scoring',searchEtaText:'6m'},activity:[]};
const timing=vm.runInContext('testJobHTML(job)',context);assert(timing.includes('Test progress ·'));assert(timing.includes('ETA · 6m'));assert(!timing.includes('Search remaining'));assert(!timing.includes('Estimated full-video encoding time'));
context.job.progress={stage:'validation'};assert(vm.runInContext('testJobHTML(job)',context).includes('ETA · —'));
console.log('Test progress labels elapsed time on the left and ETA on the right, with unavailable estimates shown as a dash.');

for(const status of ['queued','waiting','running','completed','failed','cancelled']){
 context.job={id:'slots',name:'Video.mp4',status,settings:{},progress:{},activity:[],result:null};
 const html=vm.runInContext('testJobHTML(job)',context);
 assert(html.includes('test-result-primary'));assert(html.includes('test-comparison-slot'));assert(html.includes('test-details-region'));assert(html.includes('Test details'));
 if(status==='running')assert(html.includes('is-working'));
}
console.log('Results, Comparison and Test details reserve dedicated fields in every queue state.');

context.job={id:'order',name:'Video.mp4',status:'running',settings:{},progress:{},activity:[]};
const ordered=vm.runInContext('testJobHTML(job)',context);
assert(ordered.indexOf('<div>timeline</div>')<ordered.indexOf('test-progress-area'));
assert(ordered.indexOf('test-progress-area')<ordered.indexOf('test-comparison-slot'));
assert(ordered.indexOf('test-comparison-slot')<ordered.indexOf('test-result-primary'));
assert(ordered.indexOf('test-result-primary')<ordered.indexOf('test-details-region'));
assert(ordered.indexOf('test-details-region')<ordered.indexOf('queue-terminal'));
console.log('Queue order is timeline, progress, comparison, results and detailed data; terminal output is inside Test details.');
