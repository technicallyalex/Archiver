const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const text=fs.readFileSync('web/app.js','utf8');const context=vm.createContext({esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')});
vm.runInContext(text.slice(text.indexOf('function queueOutputSettingsHTML('),text.indexOf('function renderJobs()')),context);
context.job={output:'out.mkv',settings:{codec:'av1',encoder:'av1_nvenc',resolution:'1080',fps:'30',bitrate:'cq',qualityValue:22,audio:'copy'},encodingDetails:{encoder:'av1_nvenc',preset:'p5',control:'CQ',value:22}};
let html=vm.runInContext('queueOutputSettingsHTML(job)',context);for(const label of ['AV1','av1_nvenc','CQ 22','p5','Fit within 1080p','30 fps','Copy original audio','MKV'])assert(html.includes(label),label);
context.job={output:'proxy.mov',settings:{qualityMode:'proxy',codec:'prores',proxyScale:'4',sourceMetadata:{width:3840,height:2160,fps:59.94,audio_streams:[],audio:''}},encodingDetails:{control:'ProRes profile',value:'422 Proxy'}};
html=vm.runInContext('queueOutputSettingsHTML(job)',context);for(const label of ['Quarter resolution','59.94 fps','No audio','422 Proxy','MOV'])assert(html.includes(label),label);
context.job={settings:{codec:'<script>bad</script>',bitrate:'auto'}};html=vm.runInContext('queueOutputSettingsHTML(job)',context);assert(!html.includes('<script>'));assert(html.includes('Source metadata'));assert(html.includes('Not recorded'));
console.log('Queue summaries use saved job settings and resolved rate controls, support proxies/old jobs and escape text.');
