const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
(async()=>{
 const source=fs.readFileSync('web/workflows.js','utf8'),controls={textContent:''};
 const media=[0,1].map(()=>({readyState:2,seeking:false,error:null,paused:true,async play(){this.paused=false;},pause(){this.paused=true;}}));
 const context=vm.createContext({workflowUI:{comparisonGeneration:1,comparisonWantPlay:true,comparisonVisible:true,comparisonPlayRequest:0},document:{hidden:false},activePane:'tests',comparisonVideos:()=>media,$:()=>controls,showComparisonStatus(){}});
 vm.runInContext(source.slice(source.indexOf('function pauseComparison('),source.indexOf('function seekComparison(')),context);
 await vm.runInContext('startComparison()',context);assert(media.every(v=>!v.paused));assert.equal(controls.textContent,'Pause');
 vm.runInContext('pauseComparison()',context);await vm.runInContext('startComparison()',context);assert(media.every(v=>v.paused));assert.equal(context.workflowUI.comparisonWantPlay,false);
 context.workflowUI.comparisonWantPlay=true;context.workflowUI.comparisonVisible=false;await vm.runInContext('startComparison()',context);assert(media.every(v=>v.paused));
 context.workflowUI.comparisonVisible=true;await vm.runInContext('startComparison()',context);assert(media.every(v=>!v.paused));
 context.document.hidden=true;vm.runInContext('pauseComparison(true)',context);assert.equal(context.workflowUI.comparisonWantPlay,true);await vm.runInContext('startComparison()',context);assert(media.every(v=>v.paused));
 context.document.hidden=false;await vm.runInContext('startComparison()',context);assert(media.every(v=>!v.paused));
 console.log('Comparison autoplays when ready/visible, preserves manual pause, and holds playback offscreen or in the background.');
})().catch(e=>{console.error(e);process.exit(1)});
