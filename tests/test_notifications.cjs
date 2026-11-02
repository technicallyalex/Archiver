const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');const s=fs.readFileSync('web/app.js','utf8');
const context=vm.createContext({esc:x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),notificationTime:()=> 'Nov 1, 12:00'});
vm.runInContext(s.slice(s.indexOf('function notificationItemHTML('),s.indexOf('function renderNotifications()')),context);
context.item={id:'test',title:'Encoding failed',message:'<script>Bad input</script>',level:'error',category:'encoding',jobId:'job',time:1793534400};
const html=vm.runInContext('notificationItemHTML(item)',context);assert(html.includes('&lt;script&gt;'));assert(!html.includes('<script>'));assert(html.includes('View in Encoding Queue'));assert(html.includes('<time'));
const toast=vm.runInContext('notificationItemHTML({...item,category:"test"},true)',context);assert(toast.includes('View in Test Queue'));assert(toast.includes('Dismiss notification'));assert(!toast.includes('<time'));
console.log('Notification rendering escapes content and provides history timestamps, dismiss controls and queue links.');
