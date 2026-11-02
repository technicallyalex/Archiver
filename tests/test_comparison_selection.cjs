const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/workflows.js','utf8'),start=source.indexOf('function comparisonRows('),end=source.indexOf('const wfBaseAnalysis=',start);
const context=vm.createContext({});vm.runInContext(source.slice(start,end),context);
context.job={progress:{comparisonClips:[{start:0,duration:8,encoded:'a',passed:false},{start:0,duration:8,encoded:'b',passed:false},{start:0,duration:8,encoded:'c',passed:true},{start:0,duration:8,encoded:'d',passed:true}]},result:{validation:{checks:[{encoded:'d'}]}}};
assert.equal(JSON.stringify(vm.runInContext("comparisonChoices(job,'sample')",context)),'[2]');
assert.equal(JSON.stringify(vm.runInContext("comparisonChoices(job,'recommendation')",context)),'[3]');
context.job.progress.comparisonClips[0].passed=true;assert.equal(JSON.stringify(vm.runInContext("comparisonChoices(job,'sample')",context)),'[0]');
assert(!source.includes('720p H.264 comparison proxies'));
console.log('First target-meeting attempt is distinct from the final recommendation; comparisons do not substitute proxies.');

const nodes={comparisonStatus:{},comparisonEmpty:{},comparisonSkeleton:{},comparisonStage:{setAttribute(){}},comparisonPlay:{},comparisonPosition:{}};
const videos=[0,1].map(()=>({readyState:0,seeking:false,error:null,canPlayType:()=>'',load(){this.loaded=true;}}));
const playback=vm.createContext({workflowUI:{comparisonId:'job',comparisonKey:'key',comparisonSignature:'',comparisonFailure:''},state:{workflows:{comparison:{key:{status:'ready',sourceStart:10,duration:8,message:'Original video'}}}},$:id=>nodes[id],document:{addEventListener(){}},comparisonVideos:()=>videos,startComparison:()=>{},encodeURIComponent,token:'test'});
vm.runInContext(source.slice(source.indexOf('function showComparisonStatus('),source.indexOf('const wfBasePane=')),playback);
vm.runInContext('updateComparisonState()',playback);assert(videos.every(v=>v.loaded&&v.src));assert.equal(nodes.comparisonEmpty.hidden,false);
videos.forEach(v=>v.readyState=2);vm.runInContext('updateComparisonState()',playback);assert.equal(nodes.comparisonEmpty.hidden,true);assert.equal(nodes.comparisonPlay.disabled,false);
playback.workflowUI.comparisonFailure='Codec unavailable';vm.runInContext('updateComparisonState()',playback);vm.runInContext('updateComparisonState()',playback);assert.equal(nodes.comparisonEmpty.textContent,'Codec unavailable');assert.equal(nodes.comparisonEmpty.hidden,false);
assert(!source.includes('id="comparisonDownloads"'));
console.log('Actual media loads despite inconclusive codec hints; loading/errors stay visible and save controls are absent.');
