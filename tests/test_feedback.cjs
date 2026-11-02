const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8'),start=source.indexOf('function feedbackURL('),end=source.indexOf('async function refresh()',start);
const link={dataset:{}},context=vm.createContext({URLSearchParams,navigator:{userAgent:'Test browser'},state:{version:'0.3.0-rc.1'},$:()=>link});vm.runInContext(source.slice(start,end),context);vm.runInContext('updateFeedbackLink()',context);
const url=new URL(link.href);assert.equal(url.origin,'https://github.com');assert.equal(url.pathname,'/technicallyalex/Archiver/issues/new');assert(url.searchParams.get('body').includes('Archiver: 0.3.0-rc.1'));assert(url.searchParams.get('body').includes('Test browser'));assert(url.searchParams.get('body').includes('Feedback or suggestion'));
assert(!url.searchParams.get('body').includes('token'));console.log('Feedback opens a user-reviewed repository issue with the correct version and browser.');
