const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');const source=fs.readFileSync('web/app.js','utf8');
const context=vm.createContext({});
for(const [start,end] of [['function matchesNotificationFilters','function renderNotifications'],['function groupQueueSuccess','function showQueueNotificationToast']])vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end)),context);
context.items=[{level:'error',category:'encoding'},{level:'success',category:'encoding'},{level:'error',category:'test'},{level:'info',category:'import'},{level:'info',category:'app'}];
assert.equal(vm.runInContext("items.filter(i=>matchesNotificationFilters(i,'error','all')).length",context),2);
assert.equal(vm.runInContext("items.filter(i=>matchesNotificationFilters(i,'error','encoding')).length",context),1);
assert.equal(vm.runInContext("items.filter(i=>matchesNotificationFilters(i,'all','queue')).length",context),3);
assert.equal(vm.runInContext("items.filter(i=>matchesNotificationFilters(i,'info','app')).length",context),1);
context.item={level:'success',category:'encoding',jobId:'a',time:104};context.group={firstTime:100,lastTime:101};
assert(vm.runInContext('groupQueueSuccess(item,group,true)',context));
for(const change of [{level:'error'},{category:'app'},{jobId:''},{time:107},{time:99}]){context.changed={...context.item,...change};assert(!vm.runInContext('groupQueueSuccess(changed,group,true)',context));}
context.group={firstTime:60,lastTime:103};assert(!vm.runInContext('groupQueueSuccess(item,group,true)',context));assert(!vm.runInContext('groupQueueSuccess(item,group,false)',context));
console.log('Notification filters combine severity/source; only nearby successful queue events group, with bounded duration and visible-card checks.');
