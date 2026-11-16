const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name=token]').content;
var samplePlaybackReady=false,presetStatusReady=false,notificationUIReady=false,dependencyUIReady=false;
var initialOutputValues=Object.fromEntries([...document.querySelectorAll('.encode-panel input[id],.encode-panel select[id]')].map(e=>[e.id,e.type==='checkbox'?e.checked:e.value]));
let state = {files:[],jobs:[],scan:{}}, selected = new Set(), fileSignature = '', scanning = false;
var outputSizeTimer,outputSizeSignature='',outputSizeRequest=0;
var proxyUIActive=false,proxyStandardState=null,proxyTaskState=null,lastStandardQuality='auto';
var proxyFolderNames=['Proxy','Proxies','Proxy Media','Final Cut Proxy Media'],customFolderExclusions=[],exclusionPreferencesPromise,exclusionSavePromise=Promise.resolve();
const encoderGroups = {h264:['libx264','h264_nvenc','h264_qsv','h264_amf'],hevc:['libx265','hevc_nvenc','hevc_qsv','hevc_amf'],av1:['libsvtav1','libaom-av1','av1_nvenc','av1_qsv','av1_amf']};
const encoderNames = {libx264:'Software · x264',libx265:'Software · x265',libsvtav1:'Software · SVT-AV1','libaom-av1':'Software · AOM AV1'};
const esc = text => String(text ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function bytes(n){if(n==null||!Number.isFinite(Number(n)))return 'Not estimated';if(!n)return '0 B';const i=Math.min(4,Math.floor(Math.log(Math.max(1,n))/Math.log(1024)));return `${(n/1024**i).toFixed(i?1:0)} ${['B','KiB','MiB','GiB','TiB'][i]}`;}
// Presentation helpers keep machine states, parameters and raw diagnostics intact.
function uiStatus(value,testing=false){return ({queued:'Queued',waiting:'Waiting',running:testing?'Testing':'Encoding',completed:'Completed',failed:'Failed',cancelled:'Canceled',skipped:'Skipped'})[value]||value;}
function estimateHint(reason,settings,code=''){
 const labels={missing_video_bitrate:'Reported video bitrate unavailable',source_format:'Source format is not supported by this estimate',source_timing:'Source timing or dimensions unavailable',unsupported_codec:'No estimate model for the source codec',encoder_unavailable:'Encoder unavailable for this method',bitrate_range:'Estimated bitrate is outside the supported range',missing_audio_metadata:'Audio metadata unavailable',audio_size_unavailable:'Audio size cannot be estimated'};
 if(labels[code])return labels[code];
 if(code==='test_required')return settings.qualityMode==='source'?'Review the estimate details':'Run a test for a size estimate';
 // Older servers may not return a code. Never interpret a filename or a suggested
 // action containing “test” as proof that this workflow requires quality testing.
 if(/(?:video(?:-stream average)? bitrate)(?: is)? unavailable/i.test(reason||''))return 'Reported video bitrate unavailable';
 if(settings.qualityMode==='source')return 'Review the estimate details';
 if(settings.resolution!=='original'||settings.fps!=='original')return 'Use Target bitrate for a size estimate';
 if(/^Size requires a matching test|^Recorded quality needs a test|^Test this output size/i.test(reason||''))return 'Run a test for a size estimate';
 return reason||'Estimate unavailable';
}
function codecName(value){return ({h264:'H.264 (AVC)',hevc:'H.265 (HEVC)',av1:'AV1',prores:'ProRes'})[value]||value;}
function encoderName(value){return ({libx264:'x264',libx265:'x265',libsvtav1:'SVT-AV1','libaom-av1':'AOM AV1',prores_ks:'ProRes'})[value]||(value?.endsWith('_nvenc')?'NVIDIA NVENC':value?.endsWith('_qsv')?'Intel Quick Sync':value?.endsWith('_amf')?'AMD AMF':value||'Not available');}
function exactEncoder(value){return value?`${encoderName(value)} (${value})`:'No encoder available';}
function presetName(encoder,priority='balanced'){const i=({fast:0,balanced:1,smallest:2})[priority]??1;return ({libx264:['veryfast','medium','slow'],libx265:['fast','medium','slow'],libsvtav1:['10','8','6'],'libaom-av1':['CPU-used 6','CPU-used 4','CPU-used 2']})[encoder]?.[i]||(encoder?.endsWith('_nvenc')?['p3','p5','p7'][i]:encoder?.endsWith('_qsv')?['fast','medium','slow'][i]:encoder?.endsWith('_amf')?['speed','balanced','quality'][i]:'Encoder default');}
function taskErrorHTML(job,error,task='encode'){
 if(!error)return '';
 const raw=String(error),diagnostics=[raw,...(job.log||job.activity||[])].join('\n');
 let cause=raw.length<300&&!/\[WinError|Traceback|Error initializing|Invalid data found|FFmpeg failed/i.test(raw)?raw:'Check the selected settings, source file and output folder. Open Technical details for the encoder or system error.';
 if(/not found|No such file/i.test(raw))cause='A required file or tool was not found. Check its path and try again.';
 const label=task==='test'?'Could not test':task==='queue'?'Could not queue':'Could not encode';
 return `<div class="job-error"><strong>${label} ${esc(job.name||'this video')}.</strong><p>${esc(cause)}</p><details><summary>Technical details</summary>${job.command?terminalWindow('Command',JSON.stringify(job.command,null,2)):''}${terminalWindow('Diagnostic log',diagnostics)}</details></div>`;
}
function terminalLines(text){
 return String(text).replace(/\x1b\[[0-9;]*[A-Za-z]/g,'').split('\n').map(line=>{
  const kind=/\b(error|failed|failure|panic)\b/i.test(line)?'error':/\b(warn|retry|plateau)\b/i.test(line)?'warning':/\b(successful|completed|passed|target reached)\b/i.test(line)?'success':/\b(encoding|checking|preparing|search|xpsnr|cq |crf )/i.test(line)?'operation':'output';
  return `<span class="terminal-line terminal-${kind}">${esc(line)||' '}</span>`;
 }).join('');
}
function terminalWindow(title,text,attrs=''){
 return `<section class="queue-terminal"><div class="terminal-header"><span aria-hidden="true">&gt;_</span><strong>${esc(title)}</strong><span class="terminal-label">Terminal output</span></div><pre ${attrs}>${terminalLines(text)}</pre></section>`;
}
// End of presentation helpers.
function duration(n){n=Math.max(0,Math.round(n||0));return n>=3600?`${Math.floor(n/3600)}:${String(Math.floor(n%3600/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`:`${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`;}
function toast(message,level='info'){recordNotification(String(message),level);}
async function api(path,body){const response=await fetch('/api/'+path,{method:body?'POST':'GET',headers:{'X-Token':token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw Error(data.error||'Request failed');return data;}
function previewURL(f,t=0){if(f.metadataPending)return 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22/%3E';return `/api/thumbnail?id=${f.id}&t=${Math.floor(t)}&token=${encodeURIComponent(token)}`;}
function updateEncoders(){const previous=$('encoder').value;const available=encoderGroups[$('codec').value].filter(e=>state.encoders?.includes(e)).filter(e=>$('encodingMode').value==='hardware'?e.endsWith('_'+$('hardwareBackend').value):!e.endsWith('_nvenc')&&!e.endsWith('_qsv')&&!e.endsWith('_amf'));$('encoder').innerHTML=available.map(e=>`<option value="${e}">${encoderNames[e]|| (e.includes('nvenc')?'NVIDIA NVENC':e.includes('qsv')?'Intel Quick Sync':'AMD AMF')}</option>`).join('')||'<option value="">No encoder available</option>';styleSelectButtons();if(available.includes(previous))$('encoder').value=previous;$('encoderNote').hidden=available.length>0;$('encoderNote').textContent=available.length?'':'No encoder is available for this codec and encoding method. Choose another method or configure FFmpeg.';updateSelection();updateBitrateNote();}
const poolFilterDefinitions=[['filterCodec','codecs',f=>f.codec||'unknown',v=>({h264:'H.264',hevc:'H.265',av1:'AV1',prores:'ProRes',vp9:'VP9',ffv1:'FFV1',unknown:'Unknown'})[v]||v],['filterResolution','resolutions',f=>f.width&&f.height?`${f.width}x${f.height}`:'unknown',v=>v==='unknown'?'Unknown':`${v.split('x')[1]}p · ${v.replace('x',' × ')}`],['filterFps','frame rates',f=>f.fps>0?String(Number(Number(f.fps).toFixed(3))):'unknown',v=>v==='unknown'?'Unknown':v+' fps'],['filterFormat','file types',f=>f.name?.includes('.')?f.name.split('.').pop().toLowerCase():'unknown',v=>v==='unknown'?'Unknown':v.toUpperCase()]];
const poolFilterPickers=new Map();
function poolFilterChoices(){return new Map(poolFilterDefinitions.map(([id])=>[id,[...$(id).selectedOptions].map(o=>o.value).filter(Boolean)]));}
function matchesPoolFilters(file,choices){return poolFilterDefinitions.every(([id,,key])=>!choices.get(id)?.length||choices.get(id).includes(key(file)));}
function populatePoolFilters(){
 for(const [id,,key,display] of poolFilterDefinitions){
  const select=$(id),previous=new Set([...select.selectedOptions].map(o=>o.value)),values=[...new Set(state.files.map(key))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})),signature=JSON.stringify(values);
  if(select.dataset.values!==signature){select.dataset.values=signature;select.innerHTML=values.map(value=>`<option value="${esc(value)}" ${previous.has(value)?'selected':''}>${esc(display(value))}</option>`).join('');}
  syncPoolFilterPicker(id);
 }
}
function visibleFiles(){const query=$('search').value.toLowerCase(),choices=poolFilterChoices();return state.files.filter(f=>f.name.toLowerCase().includes(query)&&matchesPoolFilters(f,choices)).sort((a,b)=>$('sort').value==='name'?a.name.localeCompare(b.name):b[$('sort').value]-a[$('sort').value]);}
function closePoolFilter(picker,restoreFocus=false){if(picker.native){if(picker.panel.matches(':popover-open'))picker.panel.hidePopover();}else picker.panel.hidden=true;picker.button.setAttribute('aria-expanded','false');if(restoreFocus)picker.button.focus();}
function poolFilterOpen(picker){return picker.native?picker.panel.matches(':popover-open'):!picker.panel.hidden;}
function positionPoolFilter(picker){
 if(!poolFilterOpen(picker))return;
 const rect=picker.button.getBoundingClientRect();if(rect.bottom<0||rect.top>innerHeight||rect.right<0||rect.left>innerWidth){closePoolFilter(picker);return;}const bounds=picker.boundary?.getBoundingClientRect(),leftBound=Math.max(12,bounds?bounds.left+12:12),rightBound=Math.min(innerWidth-12,bounds?bounds.right-12:innerWidth-12),maxHeight=picker.maxHeight||320;const width=Math.min(picker.width||Math.max(rect.width,240),rightBound-leftBound),height=Math.min(picker.panel.scrollHeight,maxHeight,innerHeight-24),below=innerHeight-rect.bottom-12,above=rect.top-12;
 const top=below>=height||below>=above?Math.max(12,Math.min(rect.bottom+6,innerHeight-height-12)):Math.max(12,rect.top-height-6);
 Object.assign(picker.panel.style,{width:width+'px',left:Math.max(leftBound,Math.min(rect.left,rightBound-width))+'px',top:top+'px',maxHeight:Math.max(80,Math.min(maxHeight,innerHeight-top-12))+'px'});
}
function openPoolFilter(picker,focusFirst=false){
 for(const other of poolFilterPickers.values())if(other!==picker)closePoolFilter(other);
 if(picker.native)picker.panel.showPopover();else picker.panel.hidden=false;
 picker.button.setAttribute('aria-expanded','true');positionPoolFilter(picker);
 if(focusFirst)picker.panel.querySelector('input,button')?.focus();
}
function initializePoolFilters(){
 for(const [id,label] of poolFilterDefinitions){
  const select=$(id),button=document.createElement('button'),panel=document.createElement('div');
  button.type='button';button.className='pool-filter-button';button.id=id+'Button';button.innerHTML='<span></span><svg aria-hidden="true" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m4 6 4 4 4-4"/></svg>';
  button.setAttribute('aria-label',$(id+'Label').textContent+' filter');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',id+'Options');button.setAttribute('aria-haspopup','dialog');
  panel.id=id+'Options';panel.className='pool-filter-popover';panel.setAttribute('role','dialog');panel.setAttribute('aria-labelledby',id+'Label');
  panel.innerHTML=`<button type="button" class="pool-filter-reset">All ${label}</button><div class="pool-filter-options"></div>`;
  const picker={select,button,panel,native:typeof panel.showPopover==='function'};poolFilterPickers.set(id,picker);
  if(picker.native){panel.setAttribute('popover','auto');panel.addEventListener('beforetoggle',e=>button.setAttribute('aria-expanded',String(e.newState==='open')));}else panel.hidden=true;
  select.after(button);document.body.append(panel);
  button.onclick=()=>button.disabled?undefined:poolFilterOpen(picker)?closePoolFilter(picker):openPoolFilter(picker);
  button.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();openPoolFilter(picker,true);}});
  panel.querySelector('button').onclick=()=>{for(const option of select.options)option.selected=false;select.dispatchEvent(new Event('change',{bubbles:true}));};
  panel.addEventListener('change',e=>{if(e.target.type!=='checkbox')return;const option=[...select.options].find(o=>o.value===e.target.value);if(option)option.selected=e.target.checked;select.dispatchEvent(new Event('change',{bubbles:true}));});
  panel.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const nodes=[...panel.querySelectorAll('input,button')],index=nodes.indexOf(document.activeElement);nodes[(index+(e.key==='ArrowDown'?1:-1)+nodes.length)%nodes.length]?.focus();}});
  syncPoolFilterPicker(id);
 }
 document.addEventListener('keydown',e=>{if(e.key==='Escape')for(const picker of poolFilterPickers.values())if(poolFilterOpen(picker)){e.preventDefault();closePoolFilter(picker,true);}});
 document.addEventListener('pointerdown',e=>{for(const picker of poolFilterPickers.values())if(!picker.native&&!picker.panel.contains(e.target)&&!picker.button.contains(e.target))closePoolFilter(picker);});
 const reposition=()=>{for(const picker of poolFilterPickers.values())positionPoolFilter(picker);};window.addEventListener('resize',reposition);window.addEventListener('scroll',reposition,true);
}
function syncPoolFilterPicker(id){
 const picker=poolFilterPickers.get(id);if(!picker)return;
 const options=[...picker.select.options].filter(o=>o.value),chosen=options.filter(o=>o.selected),label=poolFilterDefinitions.find(d=>d[0]===id)[1],signature=JSON.stringify(options.map(o=>[o.value,o.textContent]));
 const caption=chosen.length===0?'All '+label:chosen.length<=2?chosen.map(o=>o.textContent).join(', '):chosen.length+' '+label;
 picker.button.querySelector('span').textContent=caption;picker.button.setAttribute('aria-label',$(id+'Label').textContent+' filter: '+caption);picker.button.title=chosen.length?chosen.map(o=>o.textContent).join(', '):'All '+label;picker.button.classList.toggle('has-selection',chosen.length>0);
 if(picker.panel.dataset.values!==signature){
  const focused=picker.panel.contains(document.activeElement)?document.activeElement.value:null;
  picker.panel.querySelector('.pool-filter-options').innerHTML=options.map(o=>`<label><input type="checkbox" value="${esc(o.value)}"> <span>${esc(o.textContent)}</span></label>`).join('');picker.panel.dataset.values=signature;
  if(focused!=null&&poolFilterOpen(picker))[...picker.panel.querySelectorAll('input')].find(input=>input.value===focused)?.focus();
 }
 for(const input of picker.panel.querySelectorAll('input'))input.checked=chosen.some(o=>o.value===input.value);
 picker.panel.querySelector('.pool-filter-reset').setAttribute('aria-pressed',String(!chosen.length));positionPoolFilter(picker);
}
initializePoolFilters();
function updateSelection(){if($('analyzeSelected'))$('analyzeSelected').disabled=!!state.scan?.running||!state.files.some(f=>selected.has(f.id)&&f.metadataPending);updateProxyPresetUI();updateEncodingSummary();scheduleEncodingDetails();scheduleOutputSize();updateAutoPresets();updateAnalysisSelection();updateProresRecommendation();scheduleNamingPreview();selected=new Set([...selected].filter(id=>state.files.some(f=>f.id===id)));$('statSelected').innerHTML=`${selected.size} <small>files</small>`;const shown=visibleFiles();$('selectAll').checked=shown.length>0&&shown.every(f=>selected.has(f.id));$('selectAll').indeterminate=shown.some(f=>selected.has(f.id))&&!$('selectAll').checked;$('deleteConfirmWrap').hidden=$('mode').value!=='overwrite'||!$('deleteOriginal').checked;$('enqueue').disabled=($('mode').value==='overwrite'&&$('deleteOriginal').checked&&!$('confirmDelete').checked)||!selected.size||(isProxyPreset()?!proxyEncoderAvailable():($('qualityMode').value==='auto'&&(!validXpsnrTarget()||!autoReady()))||($('qualityMode').value==='archive'&&(proresPending||proresHasErrors))||($('qualityMode').value==='custom'&&!['copy','move'].includes($('mode').value)&&!$('encoder').value));$('queueHint').textContent=!selected.size?'Select videos to add to the encoding queue.':isProxyPreset()&&!proxyEncoderAvailable()?'No encoder is available for this proxy codec and method. Choose another method or configure FFmpeg.':!isProxyPreset()&&$('qualityMode').value==='auto'&&!autoReady()?'Complete a matching test, then apply its settings.':$('mode').value==='overwrite'&&$('deleteOriginal').checked&&!$('confirmDelete').checked?'Confirm permanent deletion before queueing.':`${selected.size} video${selected.size===1?'':'s'} selected`;document.querySelectorAll('.file-card').forEach(card=>{const checked=selected.has(card.dataset.id);card.classList.toggle('chosen',checked);card.querySelector('input').checked=checked;});if(presetStatusReady)updateSavedPresetStatus();if(dependencyUIReady)applyDependencyGates();}
function renderFiles(){populatePoolFilters();$('clearPoolFilters').hidden=!$('search').value&&!poolFilterDefinitions.some(([id])=>[...$(id).selectedOptions].some(o=>o.value));const files=visibleFiles();$('visibleCount').textContent=`${files.length} shown · ${state.files.length} total`;$('empty').hidden=!!files.length;if(!files.length){$('empty').querySelector('h2').textContent=state.files.length?'No matching videos':'No videos loaded';$('empty').querySelector('p').textContent=state.files.length?'Change or clear the filters to see videos in this pool.':'Choose a source folder, then select Import videos.';}
 $('files').innerHTML=files.map(f=>`<article class="file-card ${selected.has(f.id)?'chosen':''}" data-id="${f.id}" title="${esc(f.path)}"><div class="preview"><span>▻</span><img loading="lazy" src="${previewURL(f)}" alt="Preview of ${esc(f.name)}"><input type="checkbox" aria-label="Select ${esc(f.name)}" ${selected.has(f.id)?'checked':''}><div class="duration">${f.metadataPending?'Not analyzed':duration(f.duration)}</div><div class="scrub-hint">${f.metadataPending?'Analyze selected to load previews':'MOVE POINTER TO PREVIEW'}</div><div class="scrub-line"></div></div><div class="file-info"><h3>${esc(f.name)}</h3><div class="file-meta"><span class="codec-tag">${esc(f.codec)}</span><span>${f.metadataPending?'Metadata not read':`${f.width} × ${f.height}`}</span><span>${f.metadataPending?'':f.fps.toFixed(2)+' fps'}</span></div><div class="file-detail"><span>${bytes(f.size)}</span><span>${f.metadataPending?'—':(f.bitrate/1e6).toFixed(1)+' Mbps'}</span><span>${f.metadataPending?'—':esc(f.audio||'No audio')}</span></div></div></article>`).join('');
 document.querySelectorAll('.file-card').forEach(card=>{const f=state.files.find(x=>x.id===card.dataset.id);const preview=card.querySelector('.preview'),img=card.querySelector('img');img.onerror=()=>{img.style.opacity='0';};img.onload=()=>img.style.opacity='1';card.onclick=e=>{if(e.target.tagName==='INPUT'){e.target.checked?selected.add(f.id):selected.delete(f.id);}else{selected.has(f.id)?selected.delete(f.id):selected.add(f.id);}updateSelection();};let last=0,pending=false,target=0;preview.onpointermove=e=>{if(f.metadataPending)return;const fraction=Math.min(1,Math.max(0,(e.clientX-preview.getBoundingClientRect().left)/preview.clientWidth));card.querySelector('.scrub-line').style.width=`${fraction*100}%`;target=fraction*f.duration;if(Date.now()-last<300||pending)return;last=Date.now();pending=true;const frame=new Image();frame.onload=()=>{if(preview.matches(':hover'))img.src=frame.src;pending=false;};frame.onerror=()=>pending=false;frame.src=previewURL(f,target);};preview.onpointerleave=()=>{img.src=previewURL(f);card.querySelector('.scrub-line').style.width='0';};});updateSelection();}
function queueOutputSettingsHTML(job){
 const s=job.settings||{},meta=s.sourceMetadata||{},detail=job.encodingDetails||{},command=detail.command||[];
 const arg=(...keys)=>{for(const key of keys){const i=command.indexOf(key);if(i>=0)return command[i+1];}return null;};
 const codec=({h264:'H.264 (AVC)',hevc:'H.265 (HEVC)',av1:'AV1',prores:'ProRes'})[s.codec]||s.codec||'Not recorded';
 let quality=detail.control&&detail.value!=null?`${detail.control} ${detail.value}`:s.bitrate==='custom'?`${s.customBitrate} Mbps`:['crf','cq','cqp','icq'].includes(s.bitrate)?`${s.bitrate.toUpperCase()} ${s.qualityValue}`:s.bitrate==='proxy'?'Proxy preset':s.bitrate==='auto'?'Source metadata':s.bitrate||'Not recorded';
 const resolution=s.qualityMode==='proxy'||s.requestedQualityMode==='proxy'?`${String(s.proxyScale)==='4'?'Quarter':'Half'} resolution`:s.resolution&&s.resolution!=='original'?`Fit within ${s.resolution}p`:meta.width&&meta.height?`${meta.width} × ${meta.height}`:'Same as source';
 const fps=s.fps&&s.fps!=='original'?`${s.fps} fps`:meta.fps?`${Number(meta.fps.toFixed(3))} fps · Source`:'Same as source';
 const audioCodec=arg('-c:a','-c:a:0')||s.audio;
 const audio=Array.isArray(meta.audio_streams)&&!meta.audio_streams.length&&!meta.audio?'No audio':audioCodec==='copy'?'Copy original audio':audioCodec?`${({pcm_s24le:'PCM 24-bit',aac:'AAC',mp3:'MP3',libmp3lame:'MP3',libopus:'Opus',opus:'Opus',flac:'FLAC'})[audioCodec]||audioCodec}${arg('-b:a')?' · '+String(arg('-b:a')).replace('k',' kbps'):s.audioBitrate?.endsWith('k')?' · '+s.audioBitrate.replace('k',' kbps'):''}`:'Not recorded';
 const rows=[['Video',codec],['Encoder',detail.encoder||s.encoder||s.testedEncoder||'Not recorded'],['Quality',quality],['Resolution',resolution],['Frame rate',fps],['Audio',audio],['Container',(job.output?.split('.').pop()||s.container||'—').toUpperCase()]];
 if(detail.preset&&detail.preset!=='Encoder default')rows.splice(2,0,['Speed preset',detail.preset]);
 return `<div class="queue-output-settings"><dl aria-label="Output settings">${rows.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl></div>`;
}
function renderJobs(){const oldFrames=new Map([...$('jobs').querySelectorAll('[data-encode-id]')].map(card=>[card.dataset.encodeId,card.querySelector('.queue-thumbnail')]));$('clearQueue').disabled=!state.jobs.some(j=>j.status==='queued');$('pauseQueue').disabled=!state.queue_running;$('stopQueue').disabled=!state.queue_running&&!state.jobs.some(j=>j.status==='running');$('startQueue').disabled=state.queue_running||!state.jobs.some(j=>j.status==='queued');$('startQueue').textContent=state.queue_running?'Encoding':state.queue_paused?'Resume encoding':'Start encoding';const view=$('progressView').value;const logsScroll={};document.querySelectorAll('.job pre[data-job]').forEach(el=>logsScroll[el.dataset.job]={top:el.scrollTop,bottom:el.scrollHeight-el.scrollTop-el.clientHeight<30});$('jobCount').textContent=state.jobs.length;$('queueCount').textContent=state.jobs.filter(j=>['running','queued'].includes(j.status)).length;$('jobs').innerHTML=state.jobs.length?state.jobs.map(j=>`<article class="job ${j.status}" data-encode-id="${j.id}"><div class="job-top"><div class="queue-thumbnail" title="Source frame near the current encoding position"><span aria-hidden="true">▻</span><img loading="lazy" decoding="async" src="/api/thumbnail?job=${encodeURIComponent(j.id)}&token=${encodeURIComponent(token)}" alt="Preview of ${esc(j.name)}"></div><div class="job-name">${esc(j.name)}</div><span class="job-status">${uiStatus(j.status)}</span>${j.status==='completed'?`<button class="button secondary open-directory" data-open-directory="${j.id}">Open output folder</button>`:''}${['running','queued'].includes(j.status)?`<button class="cancel" data-cancel="${j.id}" aria-label="${j.status==='queued'?'Remove from queue':'Cancel encode'}: ${esc(j.name)}">${j.status==='queued'?'Remove from queue':'Cancel encode'}</button>`:''}</div>${queueOutputSettingsHTML(j)}${view==='bar'?`<progress value="${j.percent}" max="100" aria-label="Progress for ${esc(j.name)}"></progress>`:''}<div class="job-metrics"><span title="Encoding throughput: 1× is real time. This is not the output frame rate.">${j.status==='running'?`${j.percent.toFixed(1)}% · Speed ${esc((j.speed||'—').replace('x','×'))} · ${esc(j.fps||'—')} fps`:j.status==='queued'?'Waiting to encode':j.status==='completed'?'100% · Complete':esc(uiStatus(j.status))}</span><span>${j.status==='running'?'Remaining '+(j.eta==null?'Not estimated':duration(j.eta)):''}</span></div><div class="job-path">→ ${esc(j.output)}</div>${j.status==='completed'&&j.output_size!=null?`<div class="job-comparison">Source: ${bytes(j.source_size)} · Output: ${bytes(j.output_size)} · ${j.source_size?(Math.abs(j.source_size-j.output_size)/j.source_size*100).toFixed(1):0}% ${j.output_size<=j.source_size?'smaller':'larger'}</div>`:''}${j.phase?`<div class="field-note">${esc(j.phase)}</div>`:''}${taskErrorHTML(j,j.error)}${view==='verbose'?`${terminalWindow('Encoding log',j.log.join('\n')||'Waiting for output…',`data-job="${j.id}"`)}`:''}</article>`).join(''):'<div class="queue-empty">No files queued. Select videos in the Media Pool, choose output settings, then select Add to encoding queue.</div>';for(const card of $('jobs').querySelectorAll('[data-encode-id]')){const previous=oldFrames.get(card.dataset.encodeId);if(previous)card.querySelector('.queue-thumbnail').replaceWith(previous);}syncEncodingFrames();document.querySelectorAll('.queue-thumbnail img').forEach(img=>img.onerror=()=>{img.hidden=true;});document.querySelectorAll('[data-open-directory]').forEach(b=>b.onclick=async()=>{try{await api('open-directory',{id:b.dataset.openDirectory});}catch(e){toast(e.message,'error');}});document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=async()=>{try{await api('cancel',{id:b.dataset.cancel});await refresh();}catch(e){toast(e.message,'error');}});document.querySelectorAll('.job pre[data-job]').forEach(el=>{const prev=logsScroll[el.dataset.job];el.scrollTop=!prev||prev.bottom?el.scrollHeight:prev.top;});}
function syncEncodingFrames(){
 if(document.hidden||activePane!=='queue')return;
 for(const job of state.jobs){
   const card=[...$('jobs').querySelectorAll('[data-encode-id]')].find(el=>el.dataset.encodeId===job.id),holder=card?.querySelector('.queue-thumbnail');
   if(!holder||!job.framePreview||job.encodedSeconds==null)continue;
   const rect=holder.getBoundingClientRect();if(rect.bottom<0||rect.top>innerHeight)continue;
   const tick=Math.floor(job.encodedSeconds/2),key=job.id+':'+tick;
   if(holder.dataset.frameKey===key||holder.dataset.framePending)continue;
   holder.dataset.framePending='true';const image=new Image();image.decoding='async';
   image.onload=()=>{delete holder.dataset.framePending;if(!holder.isConnected)return;image.alt='Source frame near '+duration(job.encodedSeconds);holder.querySelector('img')?.replaceWith(image);holder.dataset.frameKey=key;let stamp=holder.querySelector('small');if(!stamp){stamp=document.createElement('small');holder.append(stamp);}stamp.textContent=duration(job.encodedSeconds);};
   image.onerror=()=>{delete holder.dataset.framePending;};
   image.src='/api/encoding-frame?id='+encodeURIComponent(job.id)+'&v='+tick+'&token='+encodeURIComponent(token);
 }
}
document.addEventListener('visibilitychange',syncEncodingFrames);window.addEventListener('scroll',syncEncodingFrames,{passive:true});
function feedbackURL(version,agent=navigator.userAgent){
 const body=`## Type
- [ ] Bug report
- [ ] Feedback or suggestion

## Description
What happened, or what would you like changed?

## Steps to reproduce (if applicable)
1.

## Expected behavior

## Environment
- Archiver: ${version}
- Browser: ${agent}

## Screenshots or relevant logs (optional)
`;
 return 'https://github.com/technicallyalex/Archiver/issues/new?'+new URLSearchParams({title:`[${version}] `,body});
}
function updateFeedbackLink(){const link=$('feedbackOpen'),version=state.version||'Unknown';if(link.dataset.version!==version){link.href=feedbackURL(version);link.dataset.version=version;}}
async function refresh(){let next;try{next=await api('state');}catch(e){$('toolStatus').textContent='Connection lost';$('toolStatus').classList.remove('ready');$('settingsOpen').classList.remove('tools-ready');state.dependencies={ready:false,missing:['Connection to Archiver']};applyDependencyGates();$('toolStatus').title='Check that Archiver is still running.';return;}try{const encodersChanged=JSON.stringify(next.encoders)!==JSON.stringify(state.encoders);state=next;if(notificationUIReady)refreshNotifications();$('parallelHardware').checked=state.parallel_hardware!==false;renderAnalysis();$('appVersion').textContent='v'+state.version;updateFeedbackLink();updateDependencyStatus();if(encodersChanged){updateEncoders();updateTestMethod();}$('statFiles').textContent=state.files.length;$('statSize').textContent=bytes(state.files.reduce((n,f)=>n+f.size,0));$('statTime').textContent=state.files.some(f=>f.metadataPending)?'Not fully analyzed':duration(state.files.reduce((n,f)=>n+f.duration,0));renderScan();$('scan').disabled=state.scan.running;$('scan').textContent=state.scan.running?'Importing…':'Import videos';$('scanErrors').hidden=!state.scan.errors?.length;$('scanErrorText').textContent=state.scan.errors?.join('\n')||'';const signature=state.files.map(f=>f.id+':'+!!f.metadataPending).join();if(signature!==fileSignature){fileSignature=signature;renderFiles();}renderJobs();applyDependencyGates();}catch(e){console.error('Unable to render application state',e);$('toolStatus').textContent='Interface could not refresh';$('settingsOpen').classList.remove('tools-ready');}}
$('scan').onclick=async()=>{try{await exclusionPreferencesPromise;await exclusionSavePromise;await api('scan',{directory:$('directory').value,recursive:$('recursive').checked,files_only:$('importMode').value==='files',parallel:$('parallelScan').checked,workers:$('scanWorkers').value==='auto'?'auto':Number($('scanWorkers').value),excluded_folders:$('recursive').checked?excludedImportFolders():[],exclude_test_folders:$('excludeTestFolders').checked});selected.clear();await refresh();}catch(e){toast(e.message,'error');}};
$('directory').onkeydown=e=>{if(e.key==='Enter')$('scan').click();};
$('browseDirectory').onclick=async()=>{const button=$('browseDirectory');button.disabled=true;button.textContent='Choosing folder…';try{const result=await api('browse',{initial:$('directory').value,kind:'source'});if(result.directory){$('directory').value=result.directory;$('directory').focus();}}catch(e){toast(e.message,'error');}finally{button.disabled=false;button.textContent='Browse…';}};
function settingsOpen(){updateDependencyStatus(); $('ffmpegPath').value=state.ffmpeg||'';$('ffprobePath').value=state.ffprobe||'';$('settingsDialog').showModal();}
$('settingsOpen').onclick=settingsOpen;$('closeSettings').onclick=()=>$('settingsDialog').close();
$('settingsForm').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{await api('config',{ffmpeg:$('ffmpegPath').value,ffprobe:$('ffprobePath').value});await refresh();if(state.dependencies?.ready)$('settingsDialog').close();else updateDependencyStatus();toast(state.dependencies?.ready?'All video tools are ready':'FFmpeg verified. Finish the remaining Video tools setup.',state.dependencies?.ready?'success':'info');}catch(error){toast(error.message,'error');}finally{button.disabled=false;}};
$('codec').onchange=updateEncoders;
$('selectAll').onchange=()=>{visibleFiles().forEach(f=>$('selectAll').checked?selected.add(f.id):selected.delete(f.id));updateSelection();};
$('search').oninput=renderFiles;$('sort').onchange=renderFiles;for(const [id] of poolFilterDefinitions)$(id).onchange=renderFiles;$('clearPoolFilters').onclick=()=>{$('search').value='';for(const [id] of poolFilterDefinitions)for(const option of $(id).options)option.selected=false;renderFiles();};
$('gridView').onclick=()=>{$('files').classList.remove('list');$('gridView').classList.add('selected');$('listView').classList.remove('selected');$('thumbSize').disabled=false;};
$('listView').onclick=()=>{$('files').classList.add('list');$('listView').classList.add('selected');$('gridView').classList.remove('selected');$('thumbSize').disabled=true;};
$('thumbSize').oninput=()=>document.documentElement.style.setProperty('--thumb-size',$('thumbSize').value+'px');
$('mode').onchange=()=>{const mode=$('mode').value;$('destinationWrap').hidden=mode!=='directory';$('overwriteWarning').hidden=mode!=='overwrite';$('recycleOriginal').checked=true;$('confirmDelete').checked=false;syncFilenameParts();$('actionNote').textContent=({preserve:'Saves encoded files in the source folder and keeps the originals.',overwrite:'Saves the encoded file in place of the original. Original files are handled as selected below.',directory:'Saves encoded files in the output folder and keeps the originals.'})[mode];updateSelection();};
$('enqueue').onclick=async()=>{const settings=encodingPreferences();try{await api('queue',{ids:[...selected],settings:{...settings,deleteOriginal:$('deleteOriginal').checked,confirmDelete:$('confirmDelete').checked},auto_start:$('autoStart').checked});toast(`${selected.size} video${selected.size===1?'':'s'} added to queue`);selected.clear();updateSelection();await refresh();showPane('queue');}catch(e){toast(e.message,'error');}};
$('parallelHardware').onchange=async()=>{try{await api('queue-parallel',{enabled:$('parallelHardware').checked});}catch(e){toast(e.message,'error');}};$('progressView').onchange=renderJobs;$('clearJobs').onclick=async()=>{try{await api('clear',{});await refresh();}catch(e){toast(e.message,'error');}};
$('queueNav').onclick=()=>showPane('queue');$('libraryNav').onclick=()=>showPane('library');document.querySelector('.brand').onclick=e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();showPane('library');workspaceScroller().scrollTo({top:0,behavior:'instant'});};
document.documentElement.dataset.theme=localStorage.getItem('archiver-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');$('theme').onclick=()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;localStorage.setItem('archiver-theme',theme);updateThemeLabel();};updateThemeLabel();
updateSelection();refresh();setInterval(refresh,1200);

$('browseDestination').onclick=async()=>{const button=$('browseDestination');button.disabled=true;button.textContent='Choosing folder…';try{const result=await api('browse',{initial:$('destination').value,kind:'destination',fallback:state.scan?.directory||$('directory').value});if(result.directory){$('destination').value=result.directory;$('destination').focus();scheduleNamingPreview();}}catch(e){toast(e.message,'error');}finally{button.disabled=false;button.textContent='Browse…';}};

function updateBitrateNote(){updateQualityControls();const mode=$('bitrate').value;const notes={crf:'Lower values generally retain more detail and produce larger files.',cqp:'Uses fixed quantization (QP), not a target bitrate. Lower values generally retain more detail.',cq:'NVENC target quality with variable bitrate. Lower values generally retain more detail.',icq:'Intel intelligent constant quality. Valid values: 1–51; lower values retain more detail.',custom:'Sets the target video bitrate in Mbps. This is not a constant-bitrate guarantee.',auto:'Reuses a recorded CRF or CQP value when compatible; otherwise uses the reported average video bitrate. Missing values are not inferred.'};$('bitrateNote').textContent=notes[mode]||'';updateEncodingSummary();scheduleEncodingDetails();}

$('bitrate').onchange=updateBitrateNote;
$('encoder').addEventListener('change',updateBitrateNote);
$('codec').addEventListener('change',updateBitrateNote);
updateBitrateNote();

$('startQueue').onclick=async()=>{try{await api('start',{});await refresh();}catch(e){toast(e.message,'error');}};

let activePane='library';
const paneScroll={library:0,queue:0,tests:0};
function workspaceScroller(){return matchMedia('(min-width:1100px)').matches?document.querySelector('.workspace>main'):document.scrollingElement;}
function showPane(name){const previousScroll=workspaceScroller().scrollTop;if(name!=='library')for(const picker of poolFilterPickers.values())closePoolFilter(picker);$('paneTitle').textContent=({library:'Media Pool',tests:'Test Queue',queue:'Encoding Queue'})[name];$('jobCount').hidden=name!=='queue';$('testJobCount').hidden=name!=='tests';document.body.dataset.pane=name;if(name===activePane)return;paneScroll[activePane]=previousScroll;activePane=name;for(const [key,pane,nav] of [['library','libraryPane','libraryNav'],['queue','queueSection','queueNav'],['tests','testsPane','testsNav']]){const active=key===name;$(pane).hidden=!active;$(nav).classList.toggle('active',active);$(nav).setAttribute('aria-selected',String(active));$(nav).tabIndex=active?0:-1;}workspaceScroller().scrollTo({top:paneScroll[name]||0,behavior:'instant'});document.querySelector('.workspace>main').setAttribute('aria-label',$('paneTitle').textContent+' viewer');if(samplePlaybackReady)syncSamplePlayback();syncEncodingFrames();}
for(const id of ['libraryNav','testsNav','queueNav']){$(id).addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const names=['library','tests','queue'];const delta=['ArrowUp','ArrowLeft'].includes(e.key)?-1:1;const name=e.key==='Home'?names[0]:e.key==='End'?names[2]:names[(names.indexOf(activePane)+delta+names.length)%names.length];showPane(name);$({library:'libraryNav',queue:'queueNav',tests:'testsNav'}[name]).focus();}});}

function explainDisabledOption(option,reason){
 if(!option.dataset.baseLabel)option.dataset.baseLabel=option.textContent;
 const label=option.dataset.baseLabel+(option.disabled&&reason?' · '+reason:'');
 if(option.textContent!==label)option.textContent=label;
 const title=option.disabled?reason:'';if(option.title!==title)option.title=title;
 // Customizable selects clone the selected option. Updating its text can leave
 // Chromium's displayed clone stale after a programmatic codec/mode change.
 // Refresh only changed content so polling never disturbs an open picker.
 if(option.selected){const content=option.closest?.('select')?.querySelector('selectedcontent');if(content&&content.textContent!==label)content.textContent=label;}

}
function updateAudioOptions(){const container=$('container').value;const allowed=container==='source'?['aac','mp3','opus','flac','copy']:container==='webm'?['opus','copy']:container==='mp4'?['aac','mp3','copy']:['aac','mp3','opus','flac','copy'];for(const option of $('audio').options){option.disabled=!allowed.includes(option.value);explainDisabledOption(option,({opus:'Choose MKV or WebM',flac:'Choose MKV',aac:'Choose MP4 or MKV',mp3:'Choose MP4 or MKV',copy:'Choose MP4 or MKV'})[option.value]||'Unavailable for this container');}if(!allowed.includes($('audio').value))$('audio').value=allowed[0];const audio=$('audio').value,rate=$('audioBitrate');if(!rate.disabled&&rate.value.endsWith('k'))rate.dataset.encodingBitrate=rate.value;rate.disabled=!['aac','mp3','opus'].includes(audio);if(audio==='copy')rate.value='source';else if(audio==='flac')rate.value='auto';else if(!rate.value.endsWith('k'))rate.value=rate.dataset.encodingBitrate||'192k';$('audioBitrate').title=audio==='copy'?'Original bitrate is retained when copying audio':audio==='flac'?'FLAC sets bitrate automatically':'';$('audioNote').textContent=audio==='copy'?'Copies all original audio tracks without re-encoding, retaining their codecs and channels. The audio must be supported by the selected container; choose MKV for broader compatibility.':audio==='flac'?'Lossless audio in MKV. Bitrate is determined by the audio content.':audio==='mp3'?'Encodes audio at the selected bitrate. Multichannel audio is mixed to stereo.':audio==='opus'?'Opus: Uses the selected audio bitrate. Requires an FFmpeg build with libopus.':'AAC: Uses the selected audio bitrate.';}
$('audio').onchange=updateAudioOptions;
$('container').addEventListener('change',updateAudioOptions);
updateAudioOptions();

var namingTimer, namingRequest=0;
function filenameHasAlternative(template){return template.replace(/\{(?:original|archiver)\}/g,'').replace(/[\s_.-]+/g,'').length>0;}
function syncFilenameParts(){
 const field=$('filenameTemplate'),locked=$('mode').value==='preserve';
 // Recognize the literal suffix used by older versions and saved presets.
 field.value=field.value.replace(/(^|_)archiver(?=_|$)/gi,'$1{archiver}');
 if(locked&&!field.value.includes('{original}'))field.value='{original}'+(field.value?'_'+field.value:'');
 const alternative=filenameHasAlternative(field.value);
 if(locked&&!alternative&&!field.value.includes('{archiver}'))field.value+=(field.value&&!field.value.endsWith('_')?'_':'')+'{archiver}';
 $('filenameLockNote').hidden=!locked;$('filenameLockNote').textContent=locked&&!alternative?'Original name is locked. Add another filename part to make the Archiver tag optional.':'Original name is locked while Keep originals is selected.';
 document.querySelectorAll('[data-filename-part]').forEach(button=>{
  const key=button.dataset.filenamePart,order=[...field.value.matchAll(/\{([^{}]+)\}/g)].map(m=>m[1]).indexOf(key),required=locked&&(key==='original'||(key==='archiver'&&!alternative));
  button.disabled=required;button.setAttribute('aria-pressed',String(order>=0));button.querySelector('.part-order').textContent=order>=0?order+1:'';button.title=required?(key==='original'?'Locked while Keep originals is selected':'Add another filename part before removing the Archiver tag'):'';
 });
}

function scheduleNamingPreview(){syncFilenameParts();clearTimeout(namingTimer);const request=++namingRequest;namingTimer=setTimeout(async()=>{const settings=encodingPreferences();$('namingControls').hidden=settings.mode==='overwrite'||isProxyPreset();if($('namingSection'))$('namingSection').hidden=settings.mode==='overwrite'||isProxyPreset();try{const result=await api('naming-preview',{ids:[...selected],settings});if(request!==namingRequest)return;$('namingPreview').hidden=settings.mode==='overwrite';$('namingPreview').textContent=settings.mode==='overwrite'?'':(result.example?'Example: ':'Preview: ')+result.names.join(' · ');}catch(e){if(request===namingRequest)$('namingPreview').textContent=e.message;}},180);}
document.querySelectorAll('[data-filename-part]').forEach(button=>button.onclick=()=>{const token='{'+button.dataset.filenamePart+'}',field=$('filenameTemplate');if(field.value.includes(token)){field.value=field.value.replace(token,'').replace(/_{2,}/g,'_').replace(/^_|_$/g,'');}else field.value+=(field.value&&!field.value.endsWith('_')?'_':'')+token;scheduleNamingPreview();});
$('clearFilename').onclick=()=>{$('filenameTemplate').value=$('mode').value==='preserve'?'{original}_{archiver}':'';scheduleNamingPreview();};

for(const id of ['archiveProfile','qualityMode','autoPreset','sourcePreset','mode','container','destination','resolution','fps','bitrate','qualityValue','customBitrate','naming','nameSuffix','batchName','filenameTemplate']){$(id).addEventListener('input',scheduleNamingPreview);$(id).addEventListener('change',scheduleNamingPreview);}
scheduleNamingPreview();

for(const id of ['recycleOriginal','deleteOriginal'])$(id).addEventListener('change',()=>{$('confirmDelete').checked=false;updateSelection();});
$('confirmDelete').onchange=updateSelection;

function updateQualityControls(){const hardware=/_nvenc$|_qsv$|_amf$/.test($('encoder').value);const crf=$('bitrate').querySelector('[value=crf]'),cqp=$('bitrate').querySelector('[value=cqp]');crf.disabled=hardware;cqp.disabled=!hardware;explainDisabledOption(crf,'Requires a software encoder');explainDisabledOption(cqp,'Requires a hardware encoder');if(hardware&&$('bitrate').value==='crf')$('bitrate').value='cqp';if(!hardware&&$('bitrate').value==='cqp')$('bitrate').value='crf';for(const [value,suffix] of [['cq','_nvenc'],['icq','_qsv']]){const option=$('bitrate').querySelector('[value='+value+']'),matches=$('encoder').value.endsWith(suffix);option.disabled=!matches||$('testedEncoder').value!==$('encoder').value;explainDisabledOption(option,!matches?(value==='cq'?'Requires NVIDIA NVENC':'Requires Intel Quick Sync'):'Apply a completed test result first');}if(['cq','icq'].includes($('bitrate').value)&&$('bitrate').selectedOptions[0].disabled)$('bitrate').value=hardware?'cqp':'crf';const mode=$('bitrate').value;$('qualityValueLabel').textContent=({crf:'CRF value',cq:'CQ value',icq:'ICQ value',cqp:'QP value'})[mode]||'Quality value';$('qualityValue').min=mode==='icq'?1:0;$('qualityControls').hidden=!['crf','cqp','cq','icq'].includes(mode);$('customBitrateWrap').hidden=mode!=='custom';$('qualityValue').max=hardware||['h264','hevc'].includes($('codec').value)?51:63;$('qualityValue').title='Valid range: '+$('qualityValue').min+'–'+$('qualityValue').max;if(Number($('qualityValue').value)>Number($('qualityValue').max))$('qualityValue').value=$('qualityValue').max;}
$('recommendQuality').onclick=async()=>{try{const r=await api('recommend-quality',{ids:[...selected],settings:{codec:$('codec').value,encoder:$('encoder').value}});$('bitrate').value=r.mode;$('qualityValue').value=r.value;$('qualityRecommendation').textContent=`Suggested ${r.mode.toUpperCase()} ${r.value}. ${r.note} ${r.warnings.join(' ')}`;updateBitrateNote();scheduleNamingPreview();}catch(e){toast(e.message,'error');}};
for(const id of ['qualityValue','customBitrate'])$(id).addEventListener('input',scheduleNamingPreview);
for(const id of ['codec','encoder','resolution','fps'])$(id).addEventListener('change',()=>{$('qualityRecommendation').textContent='';});

function styleSelectButtons(){if(!CSS.supports('appearance','base-select'))return;document.querySelectorAll('select:not([multiple])').forEach((select,index)=>{select.style.setProperty('--select-anchor','--archiver-select-'+index);if(select.querySelector('button'))return;const button=document.createElement('button');button.type='button';button.innerHTML='<selectedcontent></selectedcontent>';select.prepend(button);});}
styleSelectButtons();

function measurePickerSpace(select){const bottom=select.getBoundingClientRect().bottom;const viewport=window.visualViewport?window.visualViewport.height:window.innerHeight;select.style.setProperty('--picker-space',Math.max(48,Math.floor(viewport-bottom-14))+'px');}
document.addEventListener('pointerdown',event=>{const select=event.target.closest('select');if(select)measurePickerSpace(select);},true);
document.addEventListener('keydown',event=>{const select=event.target.closest('select');if(select)measurePickerSpace(select);},true);

let scanToastInitialized=false,scanToastRun=null,scanToastDismissed=false,scanToastTimer,scanToastHideTimer,scanToastFinished=false;
function resetScanToastFade(){clearTimeout(scanToastTimer);clearTimeout(scanToastHideTimer);$('scanToast').classList.remove('fading');scanToastFinished=false;}
function finishScanToast(){if(scanToastFinished||scanToastDismissed)return;scanToastFinished=true;scanToastTimer=setTimeout(()=>{$('scanToast').classList.add('fading');scanToastHideTimer=setTimeout(()=>{scanToastDismissed=true;$('scanToast').hidden=true;},350);},4000);}
function renderScan(){
 const scan=state.scan;
 if(!scanToastInitialized||scan.started!==scanToastRun){resetScanToastFade();scanToastRun=scan.started;scanToastDismissed=!scanToastInitialized&&!scan.running;scanToastInitialized=true;}
 $('scanToast').hidden=!scan.started||scanToastDismissed;
 if(scan.started&&!scan.running&&['complete','stopped'].includes(scan.phase))finishScanToast();
 $('stopScan').hidden=!scan.running;$('stopScan').disabled=!!scan.stopping;$('stopScan').textContent=scan.stopping?'Stopping…':'Stop importing';
 const elapsed=scan.started?Math.max(0,((scan.finished||Date.now()/1000)-scan.started)):0,discovering=scan.phase==='discovering',errors=scan.errors?.length||0;
 $('scanStatus').textContent=scan.running?(discovering?'Finding videos…':scan.phase==='listing'?'Adding files…':'Reading video metadata…'):['complete','stopped'].includes(scan.phase)?`Import ${scan.phase==='stopped'?'stopped':'complete'} · ${state.files.length} videos added · ${duration(elapsed)}`:'Choose a source folder, then select Import videos.';
 const progress=$('scanProgress');if(discovering&&scan.running)progress.removeAttribute('value');else{progress.max=Math.max(1,scan.total||0);progress.value=scan.running||scan.phase==='stopped'?(scan.done||0):progress.max;}
 $('scanMetrics').textContent=discovering?`${scan.folders||0} folders searched · ${scan.total||0} videos found`:`${scan.done||0} / ${scan.total||0} videos processed${scan.cached?' · '+scan.cached+' cached':''}${scan.inspected?' · '+scan.inspected+' inspected':''}${errors?' · '+errors+' errors':''}${scan.excludedFolders?' · '+scan.excludedFolders+' folders excluded':''}`;
 $('scanErrors').querySelector('summary').textContent=errors+` video${errors===1?'':'s'} could not be imported`;
 const active=Object.entries(scan.active||{}),slow=active.filter(([,started])=>Date.now()/1000-started>=10),names=active.slice(0,2).map(([path])=>path.split(/[\\/]/).pop());
 $('scanReadStatus').textContent=scan.running&&!discovering?`${active.length} active · ${scan.adaptive?'Auto limit':'Limit'} ${scan.workerLimit||scan.workers||1}${scan.adaptive?' / '+scan.workers:''}${slow.length?' · '+slow.length+' slow read'+(slow.length===1?'':'s'):''}`:scan.timeouts?`${scan.timeouts} inspection${scan.timeouts===1?'':'s'} timed out`:'';
 $('scanCurrent').textContent=scan.running?(discovering?'Searching: '+(scan.current||'Preparing…'):names.length?'Reading: '+names.join(' · ')+(active.length>2?` · ${active.length-2} more`:''):'Preparing…'):'';
 $('scanActivity').textContent=[...(scan.recent||[]),...(scan.fallbacks?[`${scan.fallbacks} files needed a normal inspection after the fast pass.`]:[]),...(scan.cachePath?['Metadata cache: '+scan.cachePath]:[]),...(scan.cacheWarning?[scan.cacheWarning]:[])].join('\n');
}


$('dismissScanProgress').onclick=()=>{resetScanToastFade();scanToastDismissed=true;$('scanToast').hidden=true;};
$('stopScan').onclick=async()=>{try{await api('stop-scan',{});await refresh();}catch(e){toast(e.message,'error');}};

$('pauseQueue').onclick=async()=>{try{await api('pause-queue',{});toast('Queue paused. Active files will finish.');await refresh();}catch(e){toast(e.message,'error');}};
$('stopQueue').onclick=async()=>{try{await api('stop-queue',{});toast('Active encodes cancelled. Waiting files are held.');await refresh();}catch(e){toast(e.message,'error');}};

$('clearQueue').onclick=async()=>{try{await api('clear-queue',{});await refresh();toast('Waiting files removed from the queue.');}catch(e){toast(e.message,'error');}};

function automaticPreferences(){$('autoEngine').value='ab-av1';return {...Object.fromEntries(['qualityMode','encodingMode','hardwareBackend','container','autoEngine','abTarget','abCodec'].map(id=>[id,$(id).value])),xpsnrTarget:currentXpsnrTarget(),testLevel:document.querySelector('input[name=testDepth]:checked')?.value||'balanced',priority:'balanced'};}
function testPreferences(){if(isProxyPreset())throw Error('Choose Automated (Test) to set up a quality test.');return {...automaticPreferences(),qualityMode:'auto'};}
function updateAnalysisSelection(){
 const select=$('analysisSource'),old=select.value,library=state.files.filter(f=>selected.has(f.id)),files=library.length?library:state.files;
 const signature=files.map(f=>f.id).join();
 const manual=select.dataset.manual==='true'&&files.some(f=>f.id===old);
 const pool=files,supported=pool.filter(f=>f.pixel_format==='yuv420p'&&!['smpte2084','arib-std-b67'].includes(f.color_transfer)&&f.duration>0&&f.fps>0&&f.width%2===0&&f.height%2===0);
 const automatic=[...(supported.length?supported:pool)].sort((a,b)=>(Number(b.duration)||0)-(Number(a.duration)||0))[0];
 const chosen=manual?old:automatic?.id||'';
 if(select.dataset.signature!==signature){select.dataset.signature=signature;select.innerHTML=files.map(f=>`<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('');}
 select.value=chosen;select.dataset.manual=String(manual);
 const source=files.find(f=>f.id===chosen),summary=$('testFilePickerSummary'),options=$('testFileOptions');
 const thumb=f=>previewURL(f,Math.min(f.duration*.1,Math.max(0,f.duration-.1)));
 if(options.dataset.signature!==signature){options.dataset.signature=signature;options.innerHTML=files.map(f=>`<button type="button" role="option" data-test-source="${esc(f.id)}" title="${esc(f.name)}" aria-selected="false"><img loading="lazy" src="${thumb(f)}" alt=""><span>${esc(f.name)}</span></button>`).join('')||'<p class="field-note">Import videos into the Media Pool to choose a test file.</p>';}
 for(const option of options.querySelectorAll('[data-test-source]'))option.setAttribute('aria-selected',String(option.dataset.testSource===chosen));
 if(summary.dataset.source!==chosen){summary.dataset.source=chosen;summary.innerHTML=source?`<img src="${thumb(source)}" alt=""><span>${esc(source.name)}</span><span class="picker-chevron" aria-hidden="true">▾</span>`:'No videos in the Media Pool';}
 $('testFileSelectionHelp').textContent=library.length?'The longest supported selected video is chosen automatically. Choose another below if you prefer.':files.length?'Choose any loaded Media Pool video below. The longest supported video is selected automatically.':'Import videos into the Media Pool to choose a test file.';
 $('testFileSelectionStatus').textContent=source?manual?'Selected by you':supported.length?`Automatically selected · Longest of ${supported.length} supported ${library.length?'selected':'Media Pool'} videos`:'Automatically selected · Longest loaded video':'';
 const batch=$('testScope').value==='each';
 const location=$('testOutputDirectory').value.trim()||state.scan?.directory||$('directory').value.trim();
 $('testStorageNote').title='Each test gets its own folder, named with its local start date and time, for clips, cache and results.';$('testStorageNote').textContent=location?`Test files and results are saved in a separate folder inside ${location}.`:'Test files and results are saved in a separate folder inside the Media Pool source folder.';
 $('singleTestSource').hidden=batch;$('testEncodingStart').hidden=!batch;$('testEncodingStart').textContent=state.queue_paused?'Encoding Queue is paused. Successful results will wait.':state.queue_running?'Encoding Queue is running. Successful results can start when a slot is available.':$('autoStart').checked?'Encoding starts automatically after each successful test.':'Successful results are queued. Start encoding from the Encoding Queue.';
 $('testScopeNote').textContent=batch?`Tests ${library.length} selected videos separately, then queues each successful result for encoding. Files that fail testing are not queued.`:'For similar recordings, test one representative video and apply its settings to the group. For different scenes, lighting or motion, choose Each selected video.';
 $('analyzeQuality').textContent=batch?`Add ${library.length} tests and queue successful results`:'Add to test queue';
 $('analyzeQuality').disabled=isProxyPreset()||(batch?!library.length:!select.value)||$('qualityMode').value!=='auto'||!validXpsnrTarget()||!state.xpsnr||($('encodingMode').value==='hardware'&&$('hardwareBackend').value==='amf');
}
function autoReady(){return !!$('autoPreset').value&&!!$('autoTestId').value;}
function updateAutoPresets(){
 const preferences=automaticPreferences(),selector=$('autoPreset'),old=selector.value;
 const jobs=(state.preset_reports||state.test_jobs||[]).filter(j=>j.status==='completed'&&j.result?.profiles&&j.usableProfiles?.length&&['encodingMode','hardwareBackend','container','autoEngine','abTarget','abCodec'].every(k=>j.settings[k]===preferences[k])&&Number(j.settings.xpsnrTarget??38)===preferences.xpsnrTarget);
 const report=jobs.find(j=>j.id===$('autoTestId').value)||jobs.at(-1);
 const names={perceptual:`Tested · XPSNR ${preferences.xpsnrTarget} dB`};
 const signature=JSON.stringify([report?.id,report?.usableProfiles]);
 if(selector.dataset.signature!==signature){selector.dataset.signature=signature;selector.innerHTML=report?['perceptual'].filter(key=>report.usableProfiles.includes(key)).map(key=>{const r=report.result.profiles[key],w=r.winner;return `<option value="${key}">${names[key]} · ${r.keepOriginal?'Keep original':esc(w.codec.toUpperCase())}</option>`;}).join(''):'<option value="">Complete a quality test</option>';if(report?.usableProfiles.includes(old))selector.value=old;}
 if(report?.usableProfiles.includes($('abTarget').value))selector.value=$('abTarget').value;selector.disabled=!report;$('autoTestId').value=report?.id||'';
 $('testReadiness').hidden=true;$('testReadiness').textContent=report?'Ready to encode · Tested with '+report.name:state.xpsnr?`Auto searches for XPSNR ${preferences.xpsnrTarget} dB. Output size is informational; originals are retained if quality verification fails.`:'Configure FFmpeg with XPSNR to run Auto tests.'; $('openTests').textContent='Set up quality test…';
 $('autoPresetNote').textContent=report?`Tested with ${report.name}. Results may not suit other videos.`:'Complete a matching quality test, then apply its settings.';
 $('testedQualityWrap').hidden=true;$('autoPresetNote').hidden=true;
 updateSourceEstimate();
}
function updateSourceEstimate(){
 $('sourceCodecWrap').hidden=true;
 if($('qualityMode').value!=='source')return;
 $('sourcePresetNote').textContent='Estimates a bitrate from each file’s reported video bitrate, adjusted for codec, resolution and frame rate. The percentage scales this estimate.';
}

function updateQualityMode(){
 transitionProxyMode();
 const mode=$('qualityMode').value,custom=mode==='custom',archive=mode==='archive';updateXpsnrGuidance();
 syncPrimaryCodec();
 $('mode').closest('label').firstChild.textContent='4. Save output';$('proresProfile').closest('label').firstChild.textContent='3. ProRes profile';$('archiveControls').hidden=!archive;$('container').closest('label').hidden=archive;$('audio').closest('.field-row').hidden=archive;$('audioNote').hidden=archive;
 $('mode').querySelector('option[value=overwrite]').disabled=archive;explainDisabledOption($('mode').querySelector('option[value=overwrite]'),'ProRes requires Keep originals or Save to another folder');
 if(archive){if($('mode').value==='overwrite'){$('mode').value='preserve';$('mode').dispatchEvent(new Event('change'));}$('container').value=$('archiveProfile').value==='prores'?'mov':'mkv';}
 $('archiveNote').textContent='MOV container · 24-bit PCM audio · Original resolution and frame rate';$('abTargetWrap').hidden=true;$('abCodecWrap').hidden=true;
 $('manualVideoControls').hidden=!custom;$('automaticControls').hidden=custom||archive;
 $('autoPresetControls').hidden=mode!=='auto';$('sourcePresetControls').hidden=mode!=='source';
 $('autoPresetExplanation').hidden=true;$('openTests').hidden=mode!=='auto';$('qualityToolStatus').hidden=true;
 $('qualityModeNote').hidden=true;
 $('qualityModeNote').textContent=({auto:'Set up a quality test, then apply its settings before encoding.',source:'Estimates bitrate from source metadata, codec, resolution and frame rate. Percentages scale bitrate, not quality.',custom:'Choose the codec, encoder, bitrate or quality setting, resolution, and frame rate yourself.'})[mode]||(archive?'ProRes profiles prioritize high fidelity. Originals are kept.':'');
 $('outputSizeControls').hidden=!custom&&mode!=='source';if(!custom&&mode!=='source'){$('resolution').value='original';$('fps').value='original';}if(!custom)$('audio').value='copy';
 updateAudioOptions();$('hardwareBackendWrap').hidden=$('encodingMode').value!=='hardware';
 updateAutoPresets();updateSelection();renderAnalysis();scheduleNamingPreview();
}
function testedQualityLabel(result, setting){
 return result.engine==='ab-av1'&&setting.encoder?.endsWith('_nvenc')?'CQ':result.engine==='ab-av1'&&setting.encoder?.endsWith('_qsv')?'ICQ':setting.bitrate.toUpperCase();
}
function estimatedSizeChange(saving,comparison='source'){
 if(saving==null||!Number.isFinite(saving))return 'Size change not estimated';
 if(saving===0)return 'About the same size as '+comparison;
 const percent=Math.abs(saving*100),amount=percent<1?'less than 1':percent.toFixed(0);
 return `About ${amount}% ${saving<0?'larger':'smaller'} than the ${comparison}`;
}
function qualityResultHTML(job){
 const r=job.result;if(!r)return '';
 if(r.profiles?.perceptual&&Object.keys(r.profiles).length===1)return qualityResultHTML({...job,result:{...r.profiles.perceptual,preview:r.preview,sampleMotion:r.sampleMotion||r.profiles.perceptual.sampleMotion}});
 if(r.profiles||r.metric!=='xpsnr')return '<p>Run a new XPSNR test to generate current settings.</p>';

 const w=r.winner,sizeChange=estimatedSizeChange(r.videoSavings,r.sizeComparison==='source-file'?'source file':r.sizeComparison==='source-video'?'source video':'source'),sourceDuration=r.sourceDuration||job.progress?.sourceDuration||state.files?.find(f=>f.path===job.source)?.duration,estimatedVideoBytes=r.estimatedVideoBytes??(sourceDuration?w.bytesPerSecond*sourceDuration:null);
 const preview=kind=>`/api/quality-preview?id=${job.id}&kind=${kind}&token=${encodeURIComponent(token)}`;
 return `<div class="quality-result"><strong>${r.keepOriginal?'Keep original recommended':'Test complete · Target reached on samples'}</strong><p><strong>Sample XPSNR: ${scoreSummary(w.scores)} dB</strong> · Quality setting: ${esc(testedQualityLabel(r,w))} ${w.qualityValue}</p><p><strong>Estimated video size: ${estimatedVideoBytes!=null?bytes(estimatedVideoBytes):'Unavailable'}</strong> · ${esc(sizeChange)}</p><p class="field-note">Based on test samples. Audio not included.${r.validation?` Lowest checked clip: ${r.validation.checks.filter(c=>c.xpsnr!=null).length?Math.min(...r.validation.checks.filter(c=>c.xpsnr!=null).map(c=>c.xpsnr)).toFixed(2)+' dB':'Identical'}. ${r.validation.variable?'Clip results vary; the size estimate is less reliable.':''}`:''}</p>${job.queuedForEncoding?'<p class="field-note">Added to Encoding Queue with this file’s tested settings.</p>':''}${job.hideApply||job.queuedForEncoding?'':`<button class="button primary apply-test" data-apply-test="${job.id}">Apply settings and review</button><p class="field-note">Opens Manual controls in the Media Pool. Encoding does not start.</p>`}</div>`;
}
function testLoadingHTML(title,message,active){return `<section class="test-detail-section test-loading ${active?'is-working':''}">${title?`<h4>${esc(title)}</h4>`:''}<p class="field-note" role="status">${esc(message)}</p><div class="test-skeleton-lines" aria-hidden="true"><span></span><span></span><span></span></div></section>`;}
function testLogHTML(job){const p=job.progress||{},active=['queued','waiting','running'].includes(job.status);return terminalWindow(`Search log · ${job.settings.autoEngine==='ab-av1'?'ab-av1':'test'}${job.settings.xpsnrTarget!=null?' · Target '+job.settings.xpsnrTarget+' dB XPSNR':''}`,(job.activity||[]).join('\n')+(p.terminalProgress&&active?'\n'+p.terminalProgress:''));}
function testDetailsHTML(job){
 const r=job.result?.profiles?.perceptual||job.result;
 const preview=kind=>`/api/quality-preview?id=${job.id}&kind=${kind}&token=${encodeURIComponent(token)}`;
 if(r?.metric==='xpsnr'&&r.winner)return `<details class="test-details" open><summary>Test details</summary>${testLogHTML(job)}<section class="test-detail-section"><h4>Encoding settings</h4><p class="field-note">Search engine: ab-av1 crf-search · Encoder preset: ${esc(r.encoderPreset||'Not recorded')} · ${esc(job.settings?.container?.toUpperCase()||'')} · ${r.sourceWidth&&r.sourceHeight?`${r.sourceWidth} × ${r.sourceHeight} · ${r.sourceFps} fps`:'Source resolution and frame rate'}</p><div class="quality-table"><table><thead><tr><th>Encoder</th><th>Quality setting</th><th>Sample XPSNR (dB)</th><th>Estimated video bitrate (Mbps)</th></tr></thead><tbody>${r.alternatives.map(x=>`<tr><td>${esc(exactEncoder(x.encoder))}</td><td>${esc(testedQualityLabel(r,x))} ${x.qualityValue}</td><td>${scoreSummary(x.scores)}</td><td>${(x.bytesPerSecond*8/1e6).toFixed(2)}</td></tr>`).join('')}</tbody></table></div></section>${motionResultHTML(job)}${validationResultHTML(job)}${crfMeasurementsHTML(job)}<section class="test-detail-section"><h4>Sampling coverage</h4><p class="field-note">${esc(r.coverage)}</p></section>${r.failures?.length?`<p>${esc(r.failures.join(' | '))}</p>`:''}${r.preview?`<details><summary>Compare sample videos</summary><div class="test-preview-pair"><label>Original<video controls preload="none" src="${preview('source')}"></video></label><label>Recommended<video controls preload="none" src="${preview('candidate')}"></video></label></div><p>Playback depends on browser codec support. The original preview uses lossless H.264.</p></details>`:''}</details>`;
 const working=job.status==='running',pending=['queued','waiting','running'].includes(job.status);
 const message=working?'Waiting for measurements…':pending?'Waiting for the test to start.':'No measurements available.';
 return `<details class="test-details" open><summary>Test details</summary>${testLogHTML(job)}${motionResultHTML(job)||testLoadingHTML('Motion analysis',working?'Selecting representative footage…':message,working)}${validationResultHTML(job)||testLoadingHTML('Sample checks',working?'Checks appear after a sample is evaluated.':message,working)}${crfMeasurementsHTML(job)||testLoadingHTML('Quality settings',working?'Measured settings will appear here.':message,working)}</details>`;
}
function testComparisonSlotHTML(job){
 const r=job.result?.profiles?.perceptual||job.result,rows=job.progress?.comparisonClips||r?.comparisonClips||r?.validation?.checks||[],working=job.status==='running',pending=['queued','waiting','running'].includes(job.status);
 const message=rows.length?'A measured sample is ready to compare.':working?'Comparison appears after a sample finishes evaluation.':pending?'Waiting for the test to start.':'No evaluated sample is available for comparison.';
 return `<section class="test-comparison-slot" aria-label="Comparison"><div class="comparison-placeholder test-loading ${working?'is-working':''}"><div class="workflow-line"><h3>Comparison</h3>${rows.length?`<button type="button" class="button secondary" data-view-comparison="${esc(job.id)}">View comparison</button>`:''}</div><div class="test-skeleton-lines comparison-control-skeleton" aria-hidden="true"><span></span><span></span></div><div class="comparison-placeholder-stage"><p role="status">${esc(message)}</p></div><div class="test-skeleton-lines comparison-bar-skeleton" aria-hidden="true"><span></span></div></div></section>`;
}
function testJobHTML(job){
 const p=job.progress||{},active=['queued','waiting','running'].includes(job.status),elapsed=job.started?duration((job.finished||Date.now()/1000)-job.started):'—';
 const known=p.searchPercent!=null||!active;
 return `<article class="job test-job ${esc(job.status)}" data-test-id="${job.id}"><div class="job-top"><div class="job-name">${esc(job.name)}</div><span class="test-depth-badge">${({fast:'Fast',balanced:'Balanced',extensive:'Extensive'})[job.settings.testLevel||'balanced']||'Balanced'} test</span><span class="job-status">${esc(uiStatus(job.status,true))}</span>${active?`<button class="cancel" data-cancel-test="${job.id}" aria-label="${job.status==='queued'?'Remove test':'Cancel test'}: ${esc(job.name)}">${job.status==='queued'?'Remove test':'Cancel test'}</button>`:''}</div>${sampleTimelineHTML(job)||'<section class="sample-timeline"><strong>Test samples</strong><p class="field-note">No samples were prepared.</p></section>'}<section class="test-progress-area"><div class="job-metrics"><span>Test progress · ${elapsed}</span><span title="Estimated remaining time for the current search">ETA · ${active&&p.stage?.startsWith('search')&&p.searchEtaText?esc(p.searchEtaText):'—'}</span></div><progress ${known?`value="${job.percent}"`:''} max="100" aria-label="Estimated quality test progress"></progress></section>${testComparisonSlotHTML(job)}<div class="test-result test-result-primary"><h3 class="test-region-heading">Results</h3>${job.result?qualityResultHTML(job):testLoadingHTML('',job.status==='running'?'Testing samples… Results will appear here.':['queued','waiting'].includes(job.status)?'Waiting for the test to start.':'No recommendation was produced.',job.status==='running')}</div><section class="test-details-region">${testDetailsHTML(job)}</section>${taskErrorHTML(job,job.queueError,'queue')}${taskErrorHTML(job,job.error,'test')}<div class="job-path">Test folder: ${esc(job.outputDirectory)}</div></article>`;
}
function preserveTestDisclosures(previous,next){
 const counts=new Map(),open=new Map();
 const key=detail=>{const name=detail.querySelector(':scope > summary')?.textContent.trim()||'';const count=counts.get(name)||0;counts.set(name,count+1);return name+':'+count;};
 for(const detail of previous.querySelectorAll('details'))open.set(key(detail),detail.open);
 counts.clear();for(const detail of next.querySelectorAll('details')){const name=key(detail);if(open.has(name))detail.open=open.get(name);}
}
function renderAnalysis(){
 updateAutoPresets();updateSelection();
 $('qualityToolStatus').textContent=state.xpsnr?'Tests short samples to find a quality setting for the selected encoder.':'Automated (Test) needs an FFmpeg build with XPSNR. Automated (Estimate) and Manual remain available.';
 updateAnalysisSelection();
 const jobs=state.test_jobs||[];
 $('testJobCount').textContent=jobs.length;
 $('testCount').textContent=jobs.filter(j=>['queued','waiting','running'].includes(j.status)).length;
 $('startTests').disabled=!!state.test_queue_running||!jobs.some(j=>j.status==='queued');
 $('startTests').textContent=state.test_queue_running?'Testing':state.test_queue_paused?'Resume tests':'Start tests';
 $('pauseTests').disabled=!state.test_queue_running;
 // Completed cards remain intact so refreshing progress never resets playing previews.
 for(const card of $('testJobs').querySelectorAll('[data-test-id]'))if(!jobs.some(j=>j.id===card.dataset.testId))card.remove();
 if(jobs.length)$('testJobs').querySelector('.queue-empty')?.remove();
 for(const job of jobs){
   let card=$('testJobs').querySelector(`[data-test-id="${job.id}"]`);
   const finalSignature=[job.status,!!job.queuedForEncoding,job.queueError||''].join('|');
   if(card?.dataset.final===finalSignature&&['completed','failed','cancelled'].includes(job.status))continue;
   const holder=document.createElement('div');holder.innerHTML=testJobHTML(job);const next=holder.firstElementChild;
   if(card)preserveTestDisclosures(card,next);
   if(['completed','failed','cancelled'].includes(job.status))next.dataset.final=finalSignature;
   if(card){
     const previousLog=card.querySelector('.test-details-region .queue-terminal pre'),previousScroll=previousLog?.scrollTop||0,atBottom=!previousLog||previousLog.scrollHeight-previousLog.scrollTop-previousLog.clientHeight<30;
     const oldTimeline=card.querySelector('.sample-timeline'),current=next.querySelector('.sample-timeline');
     if(oldTimeline&&current&&oldTimeline.dataset.signature===current.dataset.signature){
       if(current.classList.contains('motion-scout-timeline')){
         oldTimeline.querySelector('strong').textContent=current.querySelector('strong').textContent;
         oldTimeline.querySelector('.motion-probe-status').textContent=current.querySelector('.motion-probe-status').textContent;
         oldTimeline.querySelector('.motion-probe-markers').innerHTML=current.querySelector('.motion-probe-markers').innerHTML;
       }
       const updated=[...current.querySelectorAll('.sample-thumb')];
       oldTimeline.querySelectorAll('.sample-thumb').forEach((tile,i)=>{
         const change=updated[i];if(!change)return;tile.className=change.className;tile.querySelector('span').innerHTML=change.querySelector('span').innerHTML;
         const media=tile.querySelector('img,video'),desired=change.querySelector('img,video');if(!media||!desired)return;
         if(media.tagName!==desired.tagName&&!(desired.tagName==='VIDEO'&&tile.dataset.previewFailed===desired.dataset.previewSrc)){if(media.tagName==='VIDEO')media.pause();media.closest('.preview-frame')?.classList.add('is-loading');media.closest('.preview-frame')?.setAttribute('aria-busy','true');media.replaceWith(desired);}
         else if(media.tagName==='IMG'&&desired.tagName==='IMG'&&media.getAttribute('src')!==desired.getAttribute('src'))media.src=desired.getAttribute('src');
       });
       // Keep the playing media attached; moving it to a replacement card can reset playback.
       const previousComparisonSlot=card.querySelector(':scope > .test-comparison-slot'),comparisonPanel=previousComparisonSlot?.querySelector('.workflow-comparison')?previousComparisonSlot:null;
       for(const child of [...card.children])if(child!==oldTimeline&&child!==comparisonPanel)child.remove();
       let afterTimeline=false,afterComparison=false;for(const child of [...next.children]){if(child===current){afterTimeline=true;continue;}if(comparisonPanel&&child.matches('.test-comparison-slot')){afterComparison=true;continue;}if(!afterTimeline)card.insertBefore(child,oldTimeline);else if(comparisonPanel&&!afterComparison)card.insertBefore(child,comparisonPanel);else card.append(child);}
       card.className=next.className;if(next.dataset.final)card.dataset.final=next.dataset.final;
     }else {card.replaceWith(next);card=next;}
     const newLog=card.querySelector('.test-details-region .queue-terminal pre');if(newLog)newLog.scrollTop=atBottom?newLog.scrollHeight:previousScroll;
   }else { $('testJobs').append(next);const log=next.querySelector('.test-details-region .queue-terminal pre');if(log)log.scrollTop=log.scrollHeight; }


 }
 layoutSampleCards();
 settleCachedPreviews();
 if(samplePlaybackReady)syncSamplePlayback();
 if(!jobs.length)$('testJobs').innerHTML='<div class="queue-empty">No tests queued. Choose a video above, then select Add to test queue.</div>';
}
function updateTestMethod(){if(isProxyPreset()){$('testSettingsSummary').textContent=($('proxyCodec').value==='h264'?'H.264 proxy':'ProRes 422 Proxy')+' · '+($('outputPreset').value==='proxy-half'?'1/2':'1/4')+' resolution';$('testMethodNote').textContent='Proxy presets do not need a quality test. Choose Automated (Test) in Quality mode to test.';$('testMethodNote').hidden=false;return;}
 const p=automaticPreferences(),available=state.encoders||[],hardware=p.encodingMode==='hardware',backend=p.hardwareBackend;
 $('abTargetWrap').hidden=true;$('abCodecWrap').hidden=true;
 const quality={auto:'Automated (Test)',source:'Automated (Estimate) · Switch to Automated (Test) to test',custom:'Manual · Switch to Automated (Test) to test'}[p.qualityMode];
 $('testSettingsSummary').textContent=`${codecName(p.abCodec)} · ${hardware?({nvenc:'NVIDIA NVENC',qsv:'Intel Quick Sync',amf:'AMD AMF'})[backend]:'Software (CPU)'} · Target ${p.xpsnrTarget} dB XPSNR · ${p.container.toUpperCase()}`;
 const codecs=['h264','hevc','av1'].filter(codec=>hardware?available.includes(`${codec}_${backend}`):available.includes({h264:'libx264',hevc:'libx265',av1:'libsvtav1'}[codec])||(codec==='av1'&&available.includes('libaom-av1'))).filter(codec=>p.container!=='webm'||codec==='av1');
 $('testMethodNote').textContent=p.qualityMode!=='auto'?'Choose Automated (Test) in the Media Pool to set up a quality test.':hardware&&backend==='amf'?'Automated (Test) is not available for AMD AMF. Choose Software, NVIDIA NVENC or Intel Quick Sync.':!state.xpsnr?'This FFmpeg build does not provide XPSNR. Choose another installation in FFmpeg settings.':'';$('testMethodNote').hidden=!$('testMethodNote').textContent;
}
$('qualityMode').onchange=()=>{updateQualityMode();updateEncoders();};
$('encodingMode').onchange=()=>{$('hardwareBackendWrap').hidden=$('encodingMode').value!=='hardware';};
$('openTests').onclick=()=>{updateTestMethod();updateAnalysisSelection();showPane('tests');};
$('testsNav').onclick=()=>{updateTestMethod();showPane('tests');};
$('editTestSettings').onclick=()=>showPane('library');
for(const id of ['archiveProfile','autoEngine','abTarget','abCodec','xpsnrTarget','qualityMode','encodingMode','hardwareBackend','container','sourcePreset','sourceCodec','autoPreset'])$(id).addEventListener('change',()=>{updateAutoPresets();updateSelection();updateTestMethod();});
$('analysisSource').addEventListener('input',()=>{$('analysisSource').dataset.manual='true';updateAnalysisSelection();});
$('browseTestOutput').onclick=async()=>{try{const r=await api('browse',{initial:$('testOutputDirectory').value,kind:'test-output',fallback:state.scan?.directory||$('directory').value});if(r.directory){$('testOutputDirectory').value=r.directory;updateAnalysisSelection();}}catch(e){toast(e.message,'error');}};
$('resetTestOutput').onclick=()=>{$('testOutputDirectory').value='';updateAnalysisSelection();};
$('testOutputDirectory').addEventListener('input',updateAnalysisSelection);
function updateTestDepth(){
 const level=automaticPreferences().testLevel;
 const descriptions={fast:'Less coverage · Up to 3 initial clips and 1 independent check. A quick starting point for similar recordings.',balanced:'Recommended · 6–8 initial clips and 3–4 independent checks. A balance of coverage and testing time.',extensive:'Broader coverage · 10–12 initial clips and 4 independent checks, with more scouting and extra coverage when results vary. Takes longer.'};
 $('testDepthDescription').textContent=descriptions[level];
 updateAutoPresets();updateSelection();updateTestMethod();
}
for(const radio of document.querySelectorAll('input[name=testDepth]'))radio.addEventListener('change',updateTestDepth);
$('testDepthDescription').textContent='Recommended · 6–8 initial clips and 3–4 independent checks. A balance of coverage and testing time.';
$('testScope').addEventListener('change',updateAnalysisSelection);
$('analyzeQuality').onclick=async()=>{const batch=$('testScope').value==='each';try{await api('test-queue',{ids:batch?[...selected]:[$('analysisSource').value],settings:testPreferences(),auto_start:$('autoStartTests').checked,directory:$('testOutputDirectory').value.trim()||state.scan?.directory||$('directory').value.trim(),...(batch?{encode_settings:{...encodingPreferences(),deleteOriginal:$('deleteOriginal').checked,confirmDelete:$('confirmDelete').checked},encode_auto_start:$('autoStart').checked}:{})});await refresh();toast(batch?'Per-file tests queued. Successful files will be added to the Encoding Queue.':'Quality test added to the queue');}catch(e){toast(e.message,'error');}};
for(const [id,action] of [['startTests','start-tests'],['pauseTests','pause-tests'],['clearTests','clear-tests']])$(id).onclick=async()=>{try{await api(action,{});await refresh();}catch(e){toast(e.message,'error');}};
$('testJobs').onclick=async event=>{const cancel=event.target.closest('[data-cancel-test]'),apply=event.target.closest('[data-apply-test]');try{if(cancel){await api('cancel-test',{id:cancel.dataset.cancelTest});await refresh();}if(apply){
 const job=state.test_jobs.find(j=>j.id===apply.dataset.applyTest);
 const r=job.result.profiles?.[apply.dataset.profile||'perceptual']||job.result,w=r.winner;
 if(!w)throw Error('This test has no usable encoder settings.');
 for(const id of ['encodingMode','hardwareBackend','container','autoEngine','abTarget','abCodec'])$(id).value=job.settings[id];
 $('qualityMode').value='custom';transitionProxyMode();updateProxyPresetUI();$('qualityMode').value='custom';$('codec').value=w.codec;$('outputCodec').value=w.codec;
 $('testedEncoder').value=w.encoder;$('encoderPriority').value=w.encoderPriority||'balanced';
 $('resolution').value='original';$('fps').value='original';$('autoTestId').value='';
 updateQualityMode();updateEncoders();$('encoder').value=w.encoder;
 if($('encoder').value!==w.encoder)throw Error('The tested encoder is no longer available.');
 $('bitrate').value=w.encoder.endsWith('_nvenc')?'cq':w.encoder.endsWith('_qsv')?'icq':w.bitrate;
 $('qualityValue').value=w.qualityValue;updateBitrateNote();syncPrimaryCodec();updateSelection();showPane('library');
 $('qualityRecommendation').textContent='Tested settings applied. Review the encoder and quality setting before adding files to the encoding queue. Changing settings can change quality.';
 $('manualVideoControls').scrollIntoView({block:'center'});
 toast('Tested settings applied to Manual controls. Review, then add to encoding queue.');
}}catch(e){toast(e.message,'error');}};
updateQualityMode();

function sampleTimelineHTML(job){
 const p=job.progress||{},windows=p.sampleWindows;
 if(!windows)return motionProbeTimelineHTML(job);


 const url=t=>`/api/test-thumbnail?id=${job.id}&t=${Math.max(0,Math.min(t,p.sourceDuration-.1))}&token=${encodeURIComponent(token)}`;
 return `<section class="sample-timeline" data-signature="${JSON.stringify(windows).replaceAll('"','&quot;')}"><strong>Test samples</strong><div class="sample-thumbnails">${windows.map((w,i)=>{const active=job.status==='running'&&(p.activeSampleIndices||[]).slice(0,1).includes(i),position=(w.start+w.duration/2)/p.sourceDuration*100,fallback=url(w.start+w.duration/2),motion=(p.sampleMotion||job.result?.sampleMotion||[]).find(m=>Math.abs(m.start-w.start)<.00001&&Math.abs(m.duration-w.duration)<.00001);return `<div class="sample-anchor" data-position="${position}" style="left:${position}%"><div class="sample-thumb ${active?'active':''}"><div class="preview-frame is-loading" aria-busy="true"><i class="preview-skeleton" aria-hidden="true"></i>${`<video class="sample-video" data-native-src="/api/test-source-preview?id=${job.id}&token=${encodeURIComponent(token)}" data-native-mime="${esc(p.nativePreview?.mime||'')}" data-sample-fps="${p.nativePreview?.fps||30}" data-sample-start="${w.start}" data-sample-duration="${w.duration}" data-preview-src="/api/test-sample-preview?id=${job.id}&sample=${i}&start=${w.start}&token=${encodeURIComponent(token)}" poster="${fallback}" data-fallback="${fallback}" muted loop playsinline preload="none" aria-label="Sample ${i+1} preview"></video>`}</div><span>Sample ${i+1} · ${active?'Testing':`${Number(w.duration.toFixed(2))} seconds`}<small class="sample-time-range">${duration(w.start)}–${duration(w.start+w.duration)}</small><small class="sample-motion">${Number.isFinite(motion?.mean)?'Motion '+motion.mean.toFixed(2):p.motionAvailable===false?'Motion · Unavailable':job.status==='running'?'Motion · Pending':'Motion · Not measured'}</small></span></div><div class="sample-connector"></div></div>`;}).join('')}</div><div class="sample-filmstrip"><div class="filmstrip-images">${Array.from({length:18},(_,i)=>`<div class="preview-frame is-loading" aria-busy="true"><i class="preview-skeleton" aria-hidden="true"></i><img loading="lazy" src="${url(p.sourceDuration*i/18)}" alt="Recording at ${duration(p.sourceDuration*i/18)}"></div>`).join('')}</div>${windows.map((w,i)=>`<span class="sample-window" data-sample-index="${i}" style="left:${w.start/p.sourceDuration*100}%;width:${w.duration/p.sourceDuration*100}%"></span>`).join('')}</div><div class="sample-range-markers" aria-label="Sample ranges">${windows.map((w,i)=>`<span class="sample-range-marker" data-sample-index="${i}" data-start="${w.start/p.sourceDuration*100}" data-end="${(w.start+w.duration)/p.sourceDuration*100}" role="img" aria-label="Sample ${i+1}: ${duration(w.start)} to ${duration(w.start+w.duration)}, ${w.duration} seconds" title="Sample ${i+1} · ${duration(w.start)}–${duration(w.start+w.duration)} · ${w.duration} seconds. Short ranges are enlarged for visibility."></span>`).join('')}</div><div class="sample-axis"><span>0:00</span><span>${duration(p.sourceDuration)}</span></div></section>`;
}
function motionProbeTimelineHTML(job){
 const p=job.progress||{},probes=p.motionProbes||[],total=p.sourceDuration||0;
 if(!probes.length&&!['queued','waiting','running'].includes(job.status))return '';
 const active=probes.filter(w=>w.status==='active'),done=probes.filter(w=>w.status==='completed').length;
 const checking=active.map(w=>`${duration(w.start)}–${duration(w.start+w.duration)}`).join(' · ');
 const status=probes.length?`${done} / ${probes.length} measured${checking?' · Checking '+checking:''}`:total?'Preparing timeline…':'Waiting for source information…';
 const markers=probes.map(w=>`<span class="motion-probe ${esc(w.status)}" data-probe-index="${w.index}" style="left:clamp(4px, ${(w.start+w.duration/2)/total*100}%, calc(100% - 4px));width:max(8px,${w.duration/total*100}%)" role="img" aria-label="Probe ${w.index+1}: ${duration(w.start)}–${duration(w.start+w.duration)}, ${esc(w.status)}" title="Probe ${w.index+1} · ${duration(w.start)}–${duration(w.start+w.duration)} · ${esc(w.status)}${Number.isFinite(w.mean)?' · Motion '+w.mean.toFixed(2):''}"></span>`).join('');
 return `<section class="sample-timeline motion-scout-timeline" data-signature="probes-${total}"><strong>${probes.length?'Motion probes':'Preparing timeline'}</strong><p class="field-note motion-probe-status" role="status">${esc(status)}</p><div class="sample-filmstrip"><div class="filmstrip-images">${Array.from({length:18},(_,i)=>`<div class="preview-frame is-loading" aria-busy="true"><i class="preview-skeleton" aria-hidden="true"></i>${total?`<img loading="lazy" src="/api/test-thumbnail?id=${job.id}&t=${Math.floor(total*i/18)}&token=${encodeURIComponent(token)}" alt="Recording at ${duration(total*i/18)}">`:''}</div>`).join('')}</div><div class="motion-probe-markers">${markers}</div></div><div class="sample-axis"><span>0:00</span><span>${total?duration(total):''}</span></div></section>`;
}
const visibleSampleVideos=new Set(),observedSampleVideos=new Set();
const sampleObserver=new IntersectionObserver(entries=>{for(const entry of entries){entry.isIntersecting?visibleSampleVideos.add(entry.target):visibleSampleVideos.delete(entry.target);}syncSamplePlayback();},{threshold:.1});
function sampleShouldPlay(video){return video.isConnected&&!document.hidden&&activePane==='tests'&&visibleSampleVideos.has(video)&&video.closest('.sample-thumb')?.classList.contains('active');}
function stopSampleClock(video){if(video._sampleFrameRequest!=null&&video.cancelVideoFrameCallback)video.cancelVideoFrameCallback(video._sampleFrameRequest);video._sampleFrameRequest=null;}
function seekNativeSample(video){
 if(video.seeking||video._sampleSeekPending)return;
 video._sampleSeekPending=true;video._nativeSeekDone=false;
 try{video.currentTime=Number(video.dataset.sampleStart);}catch(_){video._sampleSeekPending=false;}
}
function sampleFramePresented(video,time){
 if(!sampleShouldPlay(video))return;
 const native=video.dataset.sourceKind==='native',start=Number(video.dataset.sampleStart),end=start+Number(video.dataset.sampleDuration);
 if(native&&(time<start-.05||time>=end)){
  if(time>=end)seekNativeSample(video);
  return; // Pre-roll is not evidence that the requested sample is playing.
 }
 const now=performance.now();video._lastSampleFrame=now;
 if(native){
  video._nativeFrameReady=true;video._samplePresented=(video._samplePresented||0)+1;settlePreview(video);
  const elapsed=now-video._sampleRateStart;
  if(elapsed>2500){
   const fps=video._samplePresented*1000/elapsed;
   if(fps<Math.min(12,(Number(video.dataset.sampleFps)||30)*.5)){fallbackSampleProxy(video);return;}
   video._sampleRateStart=now;video._samplePresented=0;
  }
  if(time>=end-1/Math.max(1,Number(video.dataset.sampleFps)||30))seekNativeSample(video);
 }else settlePreview(video);
}
function watchSampleFrame(video){
 if(!video.requestVideoFrameCallback||video._sampleFrameRequest!=null||!sampleShouldPlay(video))return;
 video._sampleFrameRequest=video.requestVideoFrameCallback((_,frame)=>{video._sampleFrameRequest=null;sampleFramePresented(video,frame.mediaTime);watchSampleFrame(video);});
}
function resetSampleSource(video){
 stopSampleClock(video);video._sampleGeneration=(video._sampleGeneration||0)+1;delete video.dataset.playPending;
 video.pause();video.removeAttribute('src');video.load();
 video._sampleSeekPending=false;video._nativeSeekDone=false;video._nativeFrameReady=false;
 video._lastSampleFrame=performance.now();video._sampleRateStart=performance.now();video._samplePresented=0;
}
function fallbackSampleProxy(video){
 if(video.dataset.sourceKind==='proxy'){retrySamplePreview(video);return;}
 video.dataset.sourceKind='proxy';video.dataset.retryCount='0';delete video.dataset.retryPending;delete video.dataset.previewFailed;
 resetSampleSource(video);syncSamplePlayback();
}
// A single low-priority warm-up request prepares unsupported-codec fallbacks.
// It never plays inactive videos or holds up the analysis worker.
const warmedSampleProxies=new Set(),sampleWarmFailures=new Map();let sampleWarmPending=false;
function warmSampleProxies(videos){
 if(sampleWarmPending||document.hidden||activePane!=='tests')return;
 const now=performance.now(),candidates=videos.filter(v=>v.isConnected&&v.closest('.test-job')?.classList.contains('running')&&!v.dataset.previewFailed&&
  (v.dataset.sourceKind==='proxy'||!v.dataset.nativeMime||!v.canPlayType(v.dataset.nativeMime))&&
  !warmedSampleProxies.has(v.dataset.previewSrc)&&now-(sampleWarmFailures.get(v.dataset.previewSrc)||-Infinity)>15000);
 const next=candidates.find(v=>sampleShouldPlay(v))||candidates[0];if(!next)return;
 const url=next.dataset.previewSrc;
 if(next.getAttribute('src')===url){if(next.readyState>=2)warmedSampleProxies.add(url);return;}
 sampleWarmPending=true;
 fetch(url,{cache:'force-cache'}).then(r=>{if(!r.ok)throw Error('Preview not ready');return r.arrayBuffer();})
 .then(()=>warmedSampleProxies.add(url)).catch(()=>sampleWarmFailures.set(url,performance.now()))
 .finally(()=>{sampleWarmPending=false;});
}
function syncSamplePlayback(){
 for(const video of observedSampleVideos)if(!video.isConnected){video.pause();stopSampleClock(video);sampleObserver.unobserve(video);visibleSampleVideos.delete(video);observedSampleVideos.delete(video);}
 const videos=[...$('testJobs').querySelectorAll('video.sample-video')];
 for(const video of videos){
  if(!observedSampleVideos.has(video)){observedSampleVideos.add(video);sampleObserver.observe(video);}
  if(!sampleShouldPlay(video)){
   const wasActive=video._sampleWasActive;video._sampleWasActive=false;video.pause();stopSampleClock(video);
   if(wasActive){video._sampleGeneration=(video._sampleGeneration||0)+1;delete video.dataset.playPending;if(video.dataset.sourceKind==='native')resetSampleSource(video);}
   if(video.poster)settlePreview(video);continue;
  }
  const now=performance.now();
  if(!video._sampleWasActive){
   video._sampleWasActive=true;video._lastSampleFrame=now;video._sampleRateStart=now;video._samplePresented=0;
   video._nativeSeekDone=false;video._sampleSeekPending=false;delete video.dataset.previewFailed;video.dataset.retryCount='0';
  }
  if(video.dataset.retryPending||video.dataset.previewFailed)continue;
  if(!video.dataset.sourceKind)video.dataset.sourceKind=video.dataset.nativeSrc&&video.dataset.nativeMime&&video.canPlayType(video.dataset.nativeMime)?'native':'proxy';
  const native=video.dataset.sourceKind==='native';
  if(!video.getAttribute('src')){
   video._lastSampleFrame=now;video._sampleRateStart=now;video._samplePresented=0;video.loop=!native;
   video.src=native?video.dataset.nativeSrc:video.dataset.previewSrc;video.load();
  }
  const stalled=now-video._lastSampleFrame;
  if(native&&stalled>4000){fallbackSampleProxy(video);continue;}
  if(!native&&stalled>(video.readyState>=2?5000:30000)){retrySamplePreview(video);continue;}
  if(native){
   if(video.readyState<1)continue;
   if(!video._nativeSeekDone||video.ended){seekNativeSample(video);continue;}
   if(video.seeking)continue;
  }
  video.muted=true;
  if(video.paused&&!video.dataset.playPending){
   const generation=video._sampleGeneration||0;video.dataset.playPending='true';
   video.play().then(()=>{if(generation!==(video._sampleGeneration||0)||!sampleShouldPlay(video)){if(!sampleShouldPlay(video))video.pause();return;}watchSampleFrame(video);})
   .catch(error=>{if(generation===(video._sampleGeneration||0)&&sampleShouldPlay(video)&&error.name!=='AbortError'&&error.name!=='NotAllowedError')native?fallbackSampleProxy(video):retrySamplePreview(video);})
   .finally(()=>{if(generation===(video._sampleGeneration||0))delete video.dataset.playPending;});
  }
  watchSampleFrame(video);
 }
 warmSampleProxies(videos);
}
samplePlaybackReady=true;
setInterval(()=>{if(activePane==='tests'&&!document.hidden)syncSamplePlayback();},500);
document.addEventListener('visibilitychange',syncSamplePlayback);
function retrySamplePreview(video){
 if(!video.isConnected||video.dataset.retryPending)return;
 if(video.dataset.sourceKind==='native'){fallbackSampleProxy(video);return;}
 const count=Number(video.dataset.retryCount||0);
 if(count>=4){video.dataset.previewFailed='true';resetSampleSource(video);settlePreview(video,true);return;}
 video.dataset.retryPending='true';video.dataset.retryCount=String(count+1);resetSampleSource(video);
 setTimeout(()=>{delete video.dataset.retryPending;if(video.isConnected)syncSamplePlayback();},Math.min(4000,500*2**count));
}
for(const type of ['loadedmetadata','seeked','ended','pause','canplay','playing'])$('testJobs').addEventListener(type,event=>{
 const video=event.target;if(!video.matches('video.sample-video'))return;
 if(type==='seeked'){video._sampleSeekPending=false;video._nativeSeekDone=true;}
 syncSamplePlayback();
},true);
$('testJobs').addEventListener('timeupdate',event=>{const video=event.target;if(video.matches('video.sample-video')&&!video.requestVideoFrameCallback)sampleFramePresented(video,video.currentTime);},true);
$('testJobs').addEventListener('error',event=>{const video=event.target;if(video.tagName==='VIDEO'&&video.classList.contains('sample-video')){settlePreview(video);retrySamplePreview(video);}},true);



$('archiveProfile').addEventListener('change',updateQualityMode);


function syncPrimaryCodec(){
 const mode=$('qualityMode').value;
 const value=$('outputCodec').value;
 if(value!=='prores')for(const id of ['codec','abCodec','sourceCodec'])$(id).value=value;
 $('codec').closest('label').hidden=true;$('archiveProfile').closest('label').hidden=true;
 $('qualityModeWrap').hidden=false;
 if($('formatDetails'))$('formatDetails').hidden=mode==='archive';if($('encodingMethodControls'))$('encodingMethodControls').hidden=mode==='archive';
}
$('outputCodec').addEventListener('change',()=>{
 const codec=$('outputCodec').value;
 if(isProxyPreset()){$('proxyCodec').value=codec;updateQualityMode();updateEncoders();updateTestMethod();return;}
 if(codec==='prores'){$('qualityMode').value='archive';$('archiveProfile').value='prores';}
 else{
   $('codec').value=codec;$('abCodec').value=codec;$('sourceCodec').value=codec;
   if($('qualityMode').value==='archive')$('qualityMode').value='auto';
   updateEncoders();
 }
 updateQualityMode();updateTestMethod();
});
function organizeOutputSettings(){
 $('sourcePresetControls').after($('outputSizeControls'));
 const method=document.createElement('div');method.id='encodingMethodControls';$('qualityModeWrap').before(method);method.append($('encodingMode').closest('label'),$('hardwareBackendWrap'));const summary=document.createElement('p');summary.id='encoderSummary';summary.className='field-note';method.append(summary);$('manualVideoControls').after($('encodingDetails'));updateEncodingSummary();

 const format=document.createElement('section');format.id='formatDetails';format.className='output-section';format.innerHTML='<h3>File format and audio</h3>';
 const container=$('container').closest('label'),audio=$('audio').closest('.field-row'),note=$('audioNote');
 container.before(format);format.append(container,audio,note);
 const naming=document.createElement('section');naming.id='namingSection';naming.className='output-section';naming.innerHTML='<h3>Output naming</h3><p class="field-note">Duplicate output names receive a sequence number.</p>';
 const controls=$('namingControls'),preview=$('namingPreview');controls.before(naming);naming.append(controls,preview);
 $('autoPresetExplanation').hidden=true;$('qualityToolStatus').hidden=true;
 syncPrimaryCodec();
}
organizeOutputSettings();
organizeProxyPresets();

for(const id of ['encodingMode','hardwareBackend'])$(id).addEventListener('change',updateEncoders);

function validationResultHTML(job){
 const result=job.result?.profiles?.perceptual||job.result,rows=result?.validation?.checks||job.progress?.validationResults;if(!rows?.length)return '';
 return `<section class="test-detail-section"><h4>Clip quality checks</h4><p class="field-note">Each clip is encoded and measured separately at the suggested setting. Independent clips were held out of that round’s search. Every checked clip must reach the target before settings can be applied.</p><div class="quality-table"><table><thead><tr><th>Clip</th><th>Used for</th><th>XPSNR (dB)</th><th>Result</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${i+1}<small class="sample-time-range">${duration(r.start)}–${duration(r.start+r.duration)}</small></td><td>${r.role==='independent'?'Independent check':'Search + check'}</td><td>${r.identical?'Identical':Number(r.xpsnr).toFixed(2)}</td><td>${r.passed?'Meets target':'Below target'}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function motionResultHTML(job){
 const original=job.progress?.sampleMotion||job.result?.sampleMotion;const samples=original?.map((s,index)=>({...s,index})).sort((a,b)=>(a.start??a.index)-(b.start??b.index));if(!samples?.length)return '';
 return `<section class="motion-details test-detail-section"><h4>Motion analysis</h4><p class="field-note">${(job.progress?.sourceDuration||job.result?.sourceDuration)<=30?'This short video is used as the test sample.':'Short motion checks help select representative clips.'} FFmpeg’s vmafmotion filter estimates picture change. Cuts, noise and camera movement affect the score; higher numbers mean more change, not a percentage.</p><div class="quality-table"><table><thead><tr><th>Sample</th><th>Average change</th><th title="95% of measured frame scores are at or below this value">95th percentile</th><th>Peak change</th><th>Frames measured</th><th>Relative level</th></tr></thead><tbody>${samples.map(s=>`<tr><td>Sample ${s.index+1}${s.start!=null?`<small class="sample-time-range">${duration(s.start)}–${duration(s.start+s.duration)}</small>`:''}</td>${s.error?`<td colspan="5">${esc(s.error)}</td>`:`<td>${s.mean.toFixed(3)}</td><td>${s.p95.toFixed(3)}</td><td>${s.peak.toFixed(3)}</td><td>${s.frames}</td><td>${esc((s.relative||'').replace('Middle','Typical'))}</td>`}</tr>`).join('')}</tbody></table></div></section>`;
}
function crfMeasurementsHTML(job){
 const raw=job.progress?.measurements||job.result?.measurements;if(!raw?.length)return '';const values=[...raw].sort((a,b)=>Number(a.crf)-Number(b.crf));const result=job.result?.profiles?.perceptual||job.result,winner=result?.winner,target=Number(result?.targetScore??result?.policy?.mean??job.settings?.xpsnrTarget);const selected=m=>winner&&Number(m.crf)===Number(winner.qualityValue);
 return `<section class="crf-measurements test-detail-section"><h4>Quality search attempts (${values.length})</h4><p class="field-note">Each row is a quality setting tested on the same footage. Size and time are full-video estimates.${winner?' The selected setting meets your target.':''}</p><div class="quality-table"><table><thead><tr><th title="Lower values generally retain more detail. Values are not comparable between encoders.">Quality setting (${result?.winner?testedQualityLabel(result,result.winner):job.settings?.encodingMode==='hardware'?(job.settings.hardwareBackend==='qsv'?'ICQ':'CQ'):'CRF'})</th><th>Sample XPSNR (dB)</th><th>Estimated video size</th><th>Estimated encoding time</th><th>Result</th></tr></thead><tbody>${values.map(m=>`<tr class="${selected(m)?'selected-crf':''}"><td>${m.crf}</td><td>${m.identical?'Identical':m.xpsnr==null?'Unavailable':Number(m.xpsnr).toFixed(2)}</td><td>${bytes(m.predicted_encode_size)} (${Number(m.predicted_encode_percent).toFixed(1)}% of ${result?.sizeComparison==='source-file'?'source file':result?.sizeComparison==='source-video'?'source video':'source'})</td><td>${duration(m.predicted_encode_seconds)}</td><td>${selected(m)?'<strong>Selected</strong>':Number.isFinite(target)?(m.identical||m.xpsnr!=null&&Number(m.xpsnr)>=target)?'Meets target':'Below target':'Measured'}</td></tr>`).join('')}</tbody></table></div></section>`;
}

function currentXpsnrTarget(){const n=Number($('xpsnrTarget').value);return Number.isFinite(n)&&$('xpsnrTarget').value!==''?n:38;}
function validXpsnrTarget(){return $('xpsnrTarget').value!==''&&$('xpsnrTarget').checkValidity();}
function updateXpsnrGuidance(){
 const n=currentXpsnrTarget(),valid=validXpsnrTarget();
 $('xpsnrTargetRange').setAttribute('aria-valuetext',`${n} dB`);
 $('xpsnrGuidance').textContent=valid?'':'Enter a target from 30 to 50 dB.';
 $('xpsnrGuidance').hidden=valid;
}
function refreshXpsnrTarget(){updateXpsnrGuidance();updateAutoPresets();updateTestMethod();updateSelection();}
if($('xpsnrTargetRange')){
 $('xpsnrTargetRange').addEventListener('input',()=>{$('xpsnrTarget').value=$('xpsnrTargetRange').value;refreshXpsnrTarget();});
 $('xpsnrTarget').addEventListener('input',()=>{if(validXpsnrTarget())$('xpsnrTargetRange').value=$('xpsnrTarget').value;refreshXpsnrTarget();});
 $('resetXpsnrTarget').addEventListener('click',()=>{$('xpsnrTarget').value='38';$('xpsnrTargetRange').value='38';refreshXpsnrTarget();});
 updateXpsnrGuidance();
}

function settlePreview(media,failed=false){
 if(media.dataset?.sourceKind==='native'&&!media._nativeFrameReady&&!failed&&sampleShouldPlay(media))return;
 const frame=media.closest('.preview-frame');if(!frame)return;
 frame.classList.remove('is-loading');frame.classList.toggle('preview-unavailable',failed);frame.setAttribute('aria-busy','false');
 if(failed)frame.setAttribute('data-message','Preview unavailable');else frame.removeAttribute('data-message');
}
function settleCachedPreviews(){
 for(const media of $('testJobs').querySelectorAll('.preview-frame img,.preview-frame video')){
  if(media.tagName==='IMG'&&media.complete&&media.getAttribute('src'))settlePreview(media,!media.naturalWidth);
  else if(media.tagName==='VIDEO'&&media.readyState>=2)settlePreview(media);
 }
}
for(const type of ['load','loadeddata'])$('testJobs').addEventListener(type,e=>settlePreview(e.target),true);
$('testJobs').addEventListener('error',e=>{if(e.target.tagName==='IMG')settlePreview(e.target,true);},true);

function layoutSampleCards(){
 for(const row of $('testJobs').querySelectorAll('.sample-thumbnails')){
  const width=row.clientWidth,anchors=[...row.querySelectorAll('.sample-anchor')];
  if(!width||!anchors.length)continue;
  const gap=12,columns=Math.max(1,Math.floor((width+gap)/152)),lanes=Math.ceil(anchors.length/columns),cardWidth=Math.min(220,(width-gap*(Math.min(columns,anchors.length)-1))/Math.min(columns,anchors.length));
  const ordered=anchors.map(anchor=>({anchor,wanted:Number(anchor.dataset.position??parseFloat(anchor.style.left))/100*width})).sort((a,b)=>a.wanted-b.wanted);
  for(const entry of ordered)entry.anchor.style.width=cardWidth+'px';
  const laneHeight=Math.max(...ordered.map(e=>e.anchor.querySelector('.sample-thumb').getBoundingClientRect().height))+16;
  row.style.height=(lanes*laneHeight+24)+'px';
  for(let lane=0;lane<lanes;lane++){
   const entries=ordered.slice(lane*columns,(lane+1)*columns);let edge=0;
   for(const entry of entries){entry.left=Math.max(edge,Math.min(width-cardWidth,entry.wanted-cardWidth/2));edge=entry.left+cardWidth+gap;}
   let limit=width;for(const entry of [...entries].reverse()){entry.left=Math.min(entry.left,limit-cardWidth);limit=entry.left-gap;}
   for(const {anchor,left,wanted} of entries){
    anchor.style.left=(left+cardWidth/2)+'px';anchor.style.top=(lane*laneHeight)+'px';

   }
  }
  const timeline=row.closest('.sample-timeline'),svgNS='http://www.w3.org/2000/svg';let connectors=row.querySelector('.sample-connectors');
  if(!connectors){connectors=document.createElementNS(svgNS,'svg');connectors.classList.add('sample-connectors');connectors.setAttribute('aria-hidden','true');row.prepend(connectors);}
  connectors.setAttribute('viewBox',`0 0 ${width} ${row.clientHeight}`);connectors.replaceChildren();const rowRect=row.getBoundingClientRect();
  for(const {anchor,wanted} of ordered){
   const card=anchor.querySelector('.sample-thumb'),rect=card.getBoundingClientRect(),x=rect.left+rect.width/2-rowRect.left,y=rect.bottom-rowRect.top,path=document.createElementNS(svgNS,'path'),active=card.classList.contains('active');
   path.setAttribute('d',`M ${x} ${y} C ${x} ${y+16}, ${wanted} ${row.clientHeight-16}, ${wanted} ${row.clientHeight}`);path.classList.toggle('active',active);connectors.append(path);
  }
  const markerRows=[];
  for(const marker of [...timeline.querySelectorAll('.sample-range-marker')].sort((a,b)=>Number(a.dataset.start)-Number(b.dataset.start))){
   const start=Number(marker.dataset.start)/100*width,end=Number(marker.dataset.end)/100*width,barWidth=Math.min(width,Math.max(24,end-start)),left=Math.max(0,Math.min(width-barWidth,(start+end-barWidth)/2));
   let lane=markerRows.findIndex(edge=>edge+6<=left);if(lane<0)lane=markerRows.length;markerRows[lane]=left+barWidth;
   Object.assign(marker.style,{left:left+'px',width:barWidth+'px',top:(4+lane*16)+'px'});
   const active=anchors[Number(marker.dataset.sampleIndex)]?.querySelector('.sample-thumb').classList.contains('active');marker.classList.toggle('active',!!active);
   timeline.querySelector(`.sample-window[data-sample-index="${marker.dataset.sampleIndex}"]`)?.classList.toggle('active',!!active);
  }
  const markers=timeline.querySelector('.sample-range-markers');if(markers)markers.style.height=(Math.max(1,markerRows.length)*16)+'px';
 }
}
window.addEventListener('resize',layoutSampleCards);
const sampleLayoutObserver=new ResizeObserver(()=>layoutSampleCards());sampleLayoutObserver.observe($('testJobs'));

$('testFileOptions').addEventListener('click',e=>{
 const option=e.target.closest('[data-test-source]');if(!option)return;
 $('analysisSource').value=option.dataset.testSource;$('analysisSource').dataset.manual='true';
 updateAnalysisSelection();$('testFilePicker').open=false;$('testFilePickerSummary').focus();
});
$('testFilePicker').addEventListener('keydown',e=>{
 const options=[...$('testFileOptions').querySelectorAll('[data-test-source]')];
 if(e.key==='Escape'){$('testFilePicker').open=false;$('testFilePickerSummary').focus();e.preventDefault();return;}
 if(!['ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End'].includes(e.key)||!options.length)return;
 e.preventDefault();$('testFilePicker').open=true;
 const index=options.indexOf(document.activeElement);
 const columns=getComputedStyle($('testFileOptions')).gridTemplateColumns.split(' ').length;
 const delta={ArrowDown:columns,ArrowUp:-columns,ArrowLeft:-1,ArrowRight:1}[e.key]||0;
 const next=e.key==='Home'?0:e.key==='End'?options.length-1:index<0?Math.max(0,options.findIndex(o=>o.getAttribute('aria-selected')==='true')):Math.max(0,Math.min(options.length-1,index+delta));
 options[next].focus();options[next].scrollIntoView({block:'nearest'});
});
document.addEventListener('click',e=>{if(!$('testFilePicker').contains(e.target))$('testFilePicker').open=false;});
$('testFilePicker').addEventListener('error',e=>{if(e.target.tagName==='IMG')e.target.classList.add('thumbnail-unavailable');},true);

function encodingPreferences(){const settings={...Object.fromEntries(['proresProfile','testedEncoder','encoderPriority','archiveProfile','autoEngine','abTarget','abCodec','xpsnrTarget','qualityMode','autoPreset','autoTestId','sourcePreset','sourceCodec','encodingMode','hardwareBackend','codec','encoder','resolution','fps','bitrate','qualityValue','customBitrate','container','audio','audioBitrate','mode','destination','naming','nameSuffix','batchName','filenameTemplate'].map(id=>[id,$(id).value])),proresPreferFidelity:$('proresPreferFidelity').checked};return isProxyPreset()?{...settings,qualityMode:'proxy',proxyScale:$('outputPreset').value==='proxy-half'?'2':'4',proxyCodec:$('proxyCodec').value,proxyLocation:$('proxyLocation').value,codec:$('proxyCodec').value,encoder:proxyEncoder(),container:$('proxyCodec').value==='av1'?'mp4':'mov',resolution:'original',fps:'original',audio:'pcm_s24le',bitrate:'proxy',testedEncoder:''}:settings;}

$('parallelScan').addEventListener('change',()=>{$('scanWorkers').disabled=!$('parallelScan').checked;});

function excludedImportFolders(){return [...($('excludeProxyFolders').checked?proxyFolderNames:[]),...customFolderExclusions.filter(entry=>entry.enabled).map(entry=>entry.name)];}
function exclusionPreferences(){return {custom:customFolderExclusions.map(entry=>({...entry})),proxyFolders:$('excludeProxyFolders').checked,testFolders:$('excludeTestFolders').checked};}
function saveExclusionPreferences(){const snapshot=exclusionPreferences();exclusionSavePromise=exclusionSavePromise.catch(()=>{}).then(()=>api('import-exclusions',snapshot));return exclusionSavePromise;}
function renderCustomExclusions(){
 $('customExclusionOptions').innerHTML=customFolderExclusions.map((entry,index)=>`<span class="custom-exclusion"><label class="check-label"><input type="checkbox" data-custom-exclusion="${index}" ${entry.enabled?'checked':''}> ${esc(entry.name)}</label><button type="button" class="remove-exclusion" data-remove-exclusion="${index}" aria-label="Remove ${esc(entry.name)} exclusion" title="Remove exclusion">×</button></span>`).join('');
}
async function addFolderExclusion(){
 const name=$('customExcludedFolders').value.trim();
 if(!name||name.length>100||['.','..'].includes(name)||/[\/\\:*?"<>|]/.test(name)){toast('Enter a folder name without paths or wildcards.');return;}
 if([...proxyFolderNames.map(name=>name.toLowerCase()),'archiver test folders',...customFolderExclusions.map(entry=>entry.name.toLowerCase())].includes(name.toLowerCase())){toast('This folder exclusion already exists.');return;}
 if(customFolderExclusions.length>=30){toast('Add up to 30 custom folder exclusions.');return;}
 customFolderExclusions.push({name,enabled:true});$('customExcludedFolders').value='';renderCustomExclusions();
 try{await saveExclusionPreferences();}catch(e){toast('Could not save exclusions: '+e.message);}
}
$('addExcludedFolder').onclick=addFolderExclusion;
$('customExcludedFolders').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();addFolderExclusion();}});
$('customExclusionOptions').addEventListener('change',async e=>{if(!e.target.matches('[data-custom-exclusion]'))return;customFolderExclusions[Number(e.target.dataset.customExclusion)].enabled=e.target.checked;try{await saveExclusionPreferences();}catch(error){toast('Could not save exclusions: '+error.message);}});
$('customExclusionOptions').onclick=async e=>{const button=e.target.closest('[data-remove-exclusion]');if(!button)return;customFolderExclusions.splice(Number(button.dataset.removeExclusion),1);renderCustomExclusions();try{await saveExclusionPreferences();}catch(error){toast('Could not save exclusions: '+error.message);}};
for(const id of ['excludeProxyFolders','excludeTestFolders'])$(id).addEventListener('change',()=>saveExclusionPreferences().catch(e=>toast('Could not save exclusions: '+e.message)));
async function loadExclusionPreferences(){
 const ids=['excludeProxyFolders','excludeTestFolders','addExcludedFolder','customExcludedFolders'];ids.forEach(id=>$(id).disabled=true);
 try{const prefs=await api('import-exclusions');customFolderExclusions=prefs.custom;proxyFolderNames=prefs.proxyFolderNames||proxyFolderNames;updateProxyFolderHelp();for(const [id,key] of [['excludeProxyFolders','proxyFolders'],['excludeTestFolders','testFolders']])$(id).checked=prefs[key];renderCustomExclusions();}
 catch(e){toast('Could not load saved exclusions: '+e.message);}finally{ids.forEach(id=>$(id).disabled=false);}
}
exclusionPreferencesPromise=loadExclusionPreferences();

function updateProxyFolderHelp(){
 const help='Skips common proxy folders used by DaVinci Resolve (Proxy), Premiere Pro (Proxies), and Final Cut Pro (Proxy Media and Final Cut Proxy Media), including all nested contents. Custom proxy locations can be added below.';
 $('proxyFolderOption').title=help;$('proxyFolderHelp').textContent=help;
}
function initializeSubfolderFlyout(){
 const panel=$('subfolderFilters'),button=$('subfolderExclusions'),picker={panel,button,native:typeof panel.showPopover==='function',width:360,maxHeight:420,boundary:document.querySelector('.workspace>main')};
 document.body.append(panel);poolFilterPickers.set('subfolders',picker);
 if(picker.native){panel.hidden=false;panel.setAttribute('popover','auto');panel.addEventListener('beforetoggle',e=>button.setAttribute('aria-expanded',String(e.newState==='open')));}
 button.onclick=()=>button.disabled?undefined:poolFilterOpen(picker)?closePoolFilter(picker):openPoolFilter(picker,true);
 button.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();openPoolFilter(picker,true);}});
 $('closeSubfolderFilters').onclick=()=>closePoolFilter(picker,true);updateProxyFolderHelp();updateSubfolderFilters();
}
function updateSubfolderFilters(){const enabled=$('recursive').checked;$('subfolderExclusions').hidden=false;$('subfolderExclusions').disabled=!enabled;$('subfolderExclusions').title=enabled?'Choose subfolders to exclude':'Enable Include subfolders to edit exclusions';const picker=poolFilterPickers.get('subfolders');if(!enabled&&picker)closePoolFilter(picker);}
$('recursive').addEventListener('change',()=>{updateSubfolderFilters();if($('recursive').checked)openPoolFilter(poolFilterPickers.get('subfolders'),true);});
initializeSubfolderFlyout();

function organizeWorkspaceLayout(){
 const source=document.querySelector('.test-source');
 source.querySelector('h2').textContent='Test setup';
 const footage=document.createElement('section');footage.className='test-footage-group';footage.innerHTML='<h3>Test video</h3>';
 footage.append($('testScope').closest('label'),$('testScopeNote'),$('singleTestSource'));
 footage.append($('testDepthGroup'));
 const output=document.createElement('section');output.className='test-output-group';output.innerHTML='<h3>Settings and storage</h3>';
 output.append(document.querySelector('.test-settings-summary'),$('testStorageNote'),document.querySelector('.test-storage-options'));
 source.append(footage,output,$('analyzeQuality'));
 const controls=$('queueSection').querySelector('.queue-controls');
 for(const [name,elements] of [['queue-run-controls',[$('startQueue'),$('pauseQueue'),$('stopQueue')]],['queue-view-controls',[$('autoStart').closest('label'),$('progressView')]],['queue-cleanup-controls',[$('clearQueue'),$('clearJobs')]]]){
  const group=document.createElement('div');group.className=name;group.append(...elements);controls.append(group);
 }
}
organizeWorkspaceLayout();

$('aboutOpen').onclick=()=>{$('aboutVersion').textContent='Version '+(state.version||'Loading…');$('aboutDialog').showModal();};
$('aboutClose').onclick=()=>$('aboutDialog').close();

var proresRequest=0,proresSignature='',proresPending=false,proresHasErrors=false;
function updateProresRecommendation(){
 if(!$('proresProfile')||$('qualityMode').value!=='archive')return;
 $('proresFidelityWrap').hidden=$('proresProfile').value!=='auto';
 const ids=state.files.filter(f=>selected.has(f.id)).map(f=>f.id),settings={proresProfile:$('proresProfile').value,proresPreferFidelity:$('proresPreferFidelity').checked};
 const signature=JSON.stringify([ids,settings]);if(signature===proresSignature)return;proresSignature=signature;const request=++proresRequest;proresPending=false;proresHasErrors=false;
 if(!ids.length){$('proresRecommendation').textContent='Select files to see per-file profile recommendations.';return;}
 proresPending=true;$('proresRecommendation').textContent='Reading source formats…';
 api('prores-preview',{ids,settings}).then(r=>{if(request!==proresRequest)return;const valid=r.recommendations.filter(p=>!p.error),errors=r.recommendations.filter(p=>p.error),counts={};for(const p of valid)counts[p.label]=(counts[p.label]||0)+1;
 proresPending=false;proresHasErrors=errors.length>0;
 $('proresRecommendation').textContent=(valid.length?Object.entries(counts).map(([name,n])=>`${n} file${n===1?'':'s'} → ${name}`).join(' · ')+'. '+valid.slice(0,3).map(p=>`${p.name}: ${p.reason}`).join(' · ')+`. Estimated video size: ${bytes(valid.reduce((sum,p)=>sum+p.estimatedVideoBytes,0))}. Planning estimate; audio not included.`:'')+(errors.length?' Cannot queue this selection: '+errors.slice(0,3).map(p=>`${p.name}: ${p.error}`).join(' · '):'');
 updateSelection();
 }).catch(e=>{if(request===proresRequest){proresPending=false;proresHasErrors=true;$('proresRecommendation').textContent=e.message;updateSelection();}});
}
for(const id of ['proresProfile','proresPreferFidelity'])$(id).addEventListener('change',()=>{proresSignature='';updateProresRecommendation();});

document.body.dataset.pane=activePane;

function scheduleOutputSize(){
 if(!$('statOutputSize'))return;
 const ids=[...selected],settings=encodingPreferences(),signature=JSON.stringify([ids,settings,(state.test_jobs||[]).map(j=>[j.id,j.status,!!j.result])]);
 if(signature===outputSizeSignature)return;outputSizeSignature=signature;clearTimeout(outputSizeTimer);const request=++outputSizeRequest;
 $('statOutputSize').textContent=ids.length?'…':'—';$('statOutputReduction').textContent=ids.length?'Calculating…':'Select files';
 if(!ids.length)return;
 outputSizeTimer=setTimeout(async()=>{try{const result=await api('output-size-preview',{ids,settings});if(request!==outputSizeRequest)return;
 const partial=result.bytes==null&&result.partialBytes!=null&&result.estimatedCount>0;
 $('statOutputSize').textContent=partial?bytes(result.partialBytes):result.bytes==null?'Not estimated':bytes(result.bytes);
 $('statOutputReduction').textContent=partial?`Partial · ${result.estimatedCount} of ${result.count} files`:result.bytes==null?estimateHint(result.reason,settings,result.reasonCode):'About '+Math.abs((result.reduction||0)*100).toFixed(1)+'% '+(result.reduction>=0?'smaller':'larger');
 document.querySelector('.output-size-stat').title=(partial?'Partial estimate only; excludes files listed below.\n':'')+(result.issues?.length?result.issues.slice(0,8).map(i=>i.message.startsWith(i.name+':')?i.message:i.name+': '+i.message).join('\n')+(result.issues.length>8?`\n${result.issues.length-8} more files could not be estimated.`:''):result.reason||result.note);
 }catch(e){if(request===outputSizeRequest){$('statOutputSize').textContent='—';$('statOutputReduction').textContent='Estimate unavailable';document.querySelector('.output-size-stat').title=e.message;}}},200);
}
document.querySelector('.encode-panel').addEventListener('input',scheduleOutputSize);
document.querySelector('.encode-panel').addEventListener('change',scheduleOutputSize);

function updateThemeLabel(){const label=document.documentElement.dataset.theme==='dark'?'Switch to light theme':'Switch to dark theme';$('theme').title=label;$('theme').setAttribute('aria-label',label);}
$('autoStart').addEventListener('change',updateAnalysisSelection);

var encodingDetailsTimer,encodingDetailsSignature='',encodingDetailsRequest=0;
function selectedEncoder(){
 if(isProxyPreset())return proxyEncoder();
 if($('outputCodec').value==='prores')return 'prores_ks';
 const available=state.encoders||[],codec=$('outputCodec').value;
 if($('qualityMode').value==='auto')return $('encodingMode').value==='hardware'?`${codec}_${$('hardwareBackend').value}`:available.includes({h264:'libx264',hevc:'libx265',av1:'libsvtav1'}[codec])?{h264:'libx264',hevc:'libx265',av1:'libsvtav1'}[codec]:codec==='av1'?'libaom-av1':'';
 return $('encoder').value;
}
function updateEncodingSummary(){
 if(!$('encoderSummary'))return;
 const encoder=selectedEncoder(),available=(state.encoders||[]).includes(encoder)||encoder==='prores_ks';
 $('encoderSummary').textContent=available?`Encoder: ${exactEncoder(encoder)} · ${isProxyPreset()?'Proxy tuning':`${encoder==='libaom-av1'?'Tuning':'Preset'}: ${presetName(encoder,$('encoderPriority').value)}`}`:'No encoder is available. Check FFmpeg settings or choose another encoding method.';
 $('encodingMode').title=$('encodingMode').value==='hardware'?'Uses dedicated video-encoding hardware when supported.':'Uses a software encoder on the CPU.';$('outputCodec').title=({h264:'H.264 (AVC): Broad playback support.',hevc:'H.265 (HEVC): Higher compression efficiency.',av1:'AV1: Typically the most efficient of these three delivery codecs.',prores:'ProRes: Intraframe codec with selectable profiles.'})[$('outputCodec').value]+' Results depend on the encoder, settings and footage.';
 $('resolution').title='Keeps aspect ratio. Smaller videos are not upscaled.';$('fps').title='Changing the frame rate adds or drops frames; it does not use motion interpolation.';
}
function scheduleEncodingDetails(force=false){
 if(!$('encodingDetails')?.open)return;
 const ids=[...selected],settings=encodingPreferences(),signature=JSON.stringify([ids,settings]);
 if(!force&&signature===encodingDetailsSignature)return;encodingDetailsSignature=signature;clearTimeout(encodingDetailsTimer);const request=++encodingDetailsRequest;
 $('resolvedEncoding').textContent=ids.length?'Resolving settings…':'Select videos to see their resolved settings.';
 if(!ids.length)return;
 encodingDetailsTimer=setTimeout(async()=>{try{const result=await api('encoding-details',{ids,settings});if(request!==encodingDetailsRequest)return;
 $('resolvedEncoding').innerHTML='<table><thead><tr><th>Video</th><th>Encoder / preset</th><th>Rate control</th><th>Source of setting</th></tr></thead><tbody>'+result.files.map(f=>`<tr><td>${esc(f.name)}</td>${f.error||f.pending?`<td colspan="3">${esc(f.error||f.note)}</td>`:`<td>${esc(exactEncoder(f.encoder))}<small>${esc(f.preset)} ${esc(f.presetFlag)}</small></td><td>${esc(f.control)} ${esc(f.value??'')}${f.lookahead?'<small>Look-ahead ICQ (LA_ICQ)</small>':''}</td><td>${esc(f.provenance)}${(f.conversions||[]).map(v=>`<small>${esc(v)}</small>`).join('')}</td>`}</tr>`).join('')+'</tbody></table>';
 }catch(error){if(request===encodingDetailsRequest)$('resolvedEncoding').textContent=error.message;}},200);
}
$('encodingDetails').addEventListener('toggle',()=>{if($('encodingDetails').open)scheduleEncodingDetails(true);});
for(const event of ['input','change'])document.querySelector('.encode-panel').addEventListener(event,()=>{updateEncodingSummary();scheduleEncodingDetails();});

function isProxyPreset(){return $('qualityMode')?.value==='proxy';}
const proxyRememberedFields=['outputCodec','codec','abCodec','sourceCodec','encodingMode','hardwareBackend','encoder','container','audio','audioBitrate','resolution','fps','bitrate','qualityValue','customBitrate','mode','destination','filenameTemplate','proxyLocation'];
function proxySnapshot(){return Object.fromEntries(proxyRememberedFields.map(id=>[id,$(id).value]));}
function restoreProxySnapshot(saved){if(saved)for(const [id,value] of Object.entries(saved))if($(id))$(id).value=value;}
function transitionProxyMode(){
 const proxy=isProxyPreset(),leaving=!proxy&&proxyUIActive;
 if(proxy&&!proxyUIActive){
  proxyStandardState={...proxySnapshot(),qualityMode:lastStandardQuality};
  restoreProxySnapshot(proxyTaskState||{outputCodec:'prores',encodingMode:'software',container:'mov',mode:'preserve'});
  $('proxyCodec').value=$('outputCodec').value;$('outputCodec').value=$('proxyCodec').value;
 }else if(!proxy&&proxyUIActive){
  proxyTaskState=proxySnapshot();const requested=$('qualityMode').value;restoreProxySnapshot(proxyStandardState);$('qualityMode').value=$('outputCodec').value==='prores'?'archive':requested;
 }
 proxyUIActive=proxy;if(!proxy)lastStandardQuality=$('qualityMode').value;if(leaving)$('mode').dispatchEvent(new Event('change'));
}
function organizeProxyPresets(){
 $('qualityModeWrap').after($('proxyPresetInfo'));updateProxyPresetUI();
}
function updateProxyPresetUI(){
 if(!$('proxyPresetInfo')||!$('formatDetails'))return;
 const proxy=isProxyPreset(),codec=$('outputCodec').value,prores=codec==='prores',labels={h264:'H.264',hevc:'H.265',av1:'AV1',prores:'ProRes 422 Proxy'};
 const codecLabel=$('outputCodec').closest('label'),method=$('encodingMethodControls'),modeLabel=$('mode').closest('label');
 document.querySelector('.encode-panel .panel-heading h2').textContent=proxy?'Proxy settings':'Output settings';
 $('proxyPresetInfo').hidden=!proxy;$('proxyCodec').value=codec;
 for(const option of $('outputCodec').options){option.disabled=false;option.dataset.baseLabel=option.value==='prores'?(proxy?'ProRes 422 Proxy':'ProRes'):option.value==='h264'?'H.264 (AVC)':option.value==='hevc'?'H.265 (HEVC)':'AV1';explainDisabledOption(option,'');}
 for(const option of $('qualityMode').options){option.hidden=option.value==='archive'&&!prores;option.disabled=!proxy&&prores&&['auto','source','custom'].includes(option.value);if(option.value==='archive')option.dataset.baseLabel='Manual · ProRes profiles';explainDisabledOption(option,'Choose H.264, H.265 or AV1 for this quality mode');}
 $('qualityModeWrap').hidden=false;method.hidden=prores;$('formatDetails').hidden=proxy||prores;$('archiveControls').hidden=proxy||!prores;
 $('proxySaveControls').hidden=!proxy;modeLabel.hidden=proxy;
 // Do not detach controls during polling: moving an open native select closes it.
 const quality=$('qualityModeWrap'),info=$('proxyPresetInfo');
 if(quality.nextElementSibling!==codecLabel)codecLabel.before(quality);
 if(codecLabel.nextElementSibling!==info)codecLabel.after(info);
 if(info.nextElementSibling!==method)info.after(method);
 codecLabel.firstChild.textContent='2. Video codec';quality.firstChild.textContent='1. Quality mode';$('encodingMode').closest('label').firstChild.textContent='3. Encoding method';
 if(!proxy)return;
 $('manualVideoControls').hidden=true;$('automaticControls').hidden=true;$('autoPresetControls').hidden=true;$('sourcePresetControls').hidden=true;$('outputSizeControls').hidden=true;$('openTests').hidden=true;
 document.querySelectorAll('[data-proxy-scale]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.proxyScale===($('outputPreset').value==='proxy-quarter'?'4':'2'))));
 $('proxyFormatTitle').textContent=labels[codec]+(codec==='av1'?' · MP4':' · MOV');
 $('proxyRateNote').textContent=prores?'Profile-controlled bitrate. About 45 Mbps at 1080p30, scaled for size and frame rate.':'Target bitrate: 8 Mbps at 1080p30, scaled for size and frame rate. Short GOPs for seeking.';
 $('proxyPlaybackNote').hidden=prores;$('proxyPlaybackNote').textContent=codec==='h264'?'H.264 offers broader editor support.':labels[codec]+' proxy playback depends on editor and hardware support; H.264 or ProRes is usually easier to edit.';
 const half=$('outputPreset').value==='proxy-half';$('proxyScaleNote').textContent=half?'Half width and height. 4K becomes 1080p.':'Quarter width and height. 4K becomes 960 × 540.';
 const location=$('proxyLocation').value||'subfolder';$('mode').value=location==='custom'?'directory':'preserve';$('destinationWrap').hidden=location!=='custom';$('overwriteWarning').hidden=true;$('deleteConfirmWrap').hidden=true;
 $('actionNote').textContent=location==='subfolder'?`Creates Proxies/${half?'Half':'Quarter'}${prores?'':'/'+({h264:'H264',hevc:'HEVC',av1:'AV1'}[codec])} beside each source.`:location==='next-to'?'Adds _proxy to the filename beside each source.':'Saves proxies in the folder you choose. Adds _proxy to each filename.';
 if($('namingSection'))$('namingSection').hidden=true;
}
$('proxyLocation').onchange=()=>{updateProxyPresetUI();updateSelection();scheduleNamingPreview();scheduleOutputSize();};

for(const button of document.querySelectorAll('[data-proxy-scale]'))button.onclick=()=>{$('outputPreset').value=button.dataset.proxyScale==='2'?'proxy-half':'proxy-quarter';updateProxyPresetUI();updateSelection();updateTestMethod();scheduleEncodingDetails(true);scheduleOutputSize();scheduleNamingPreview();};

function proxyEncoder(){const codec=$('proxyCodec').value;if(codec==='prores')return 'prores_ks';if($('encodingMode').value==='hardware')return codec+'_'+$('hardwareBackend').value;return codec==='h264'?'libx264':codec==='hevc'?'libx265':(state.encoders||[]).includes('libsvtav1')?'libsvtav1':'libaom-av1';}
function proxyEncoderAvailable(){return [...(state.encoders||[]),...(state.archive_encoders||[])].includes(proxyEncoder());}
$('proxyCodec').addEventListener('change',()=>{updateProxyPresetUI();updateEncodingSummary();updateSelection();updateTestMethod();scheduleEncodingDetails(true);scheduleOutputSize();scheduleNamingPreview();});
// Named presets store controls, not source metadata, selected files or test reports.
var savedOutputPresets=[],presetBaseline='',presetBusy=false,presetDialogId='',startupPresetId='';
const userPresetFields=[...new Set([...proxyRememberedFields,'qualityMode','proresProfile','archiveProfile','encoderPriority','testedEncoder','xpsnrTarget','sourcePreset','outputPreset','naming','nameSuffix','batchName'])];
const builtinPresetSettings={...Object.fromEntries(userPresetFields.map(id=>[id,initialOutputValues[id]??''])),proresPreferFidelity:false,encoder:''};
function captureOutputPreset(){return {...Object.fromEntries(userPresetFields.map(id=>[id,$(id).value])),proresPreferFidelity:$('proresPreferFidelity').checked};}
function presetSignature(settings){return JSON.stringify(Object.fromEntries(Object.keys(settings).sort().map(key=>[key,settings[key]])));}
function renderSavedOutputPresets(selectedId=''){
 const select=$('savedOutputPreset');select.innerHTML='<option value="">Default settings</option>'+[...savedOutputPresets].sort((a,b)=>a.name.localeCompare(b.name)).map(p=>`<option value="${esc(p.id)}">${esc(p.name)}${p.id===startupPresetId?' · Startup default':''}</option>`).join('');select.value=selectedId;styleSelectButtons();updateSavedPresetStatus();
}
function updateSavedPresetStatus(){
 const id=$('savedOutputPreset').value,current=savedOutputPresets.find(p=>p.id===id),status=$('outputPresetStatus'),modified=presetSignature(captureOutputPreset())!==presetBaseline,name=current?.name||'Default settings';
 $('presetButtonName').textContent=name;$('presetButtonModified').hidden=!modified;$('presetsButton').title='Presets: '+name+(modified?' · Modified; saved preset unchanged':'');$('presetsButton').setAttribute('aria-label',$('presetsButton').title);$('manageOutputPreset').disabled=!current||presetBusy;
 $('startupOutputPreset').checked=id===startupPresetId;$('startupOutputPreset').disabled=presetBusy||(!id&&!startupPresetId);$('startupOutputPreset').title=!id&&!startupPresetId?'Default settings are already used on startup':'';
 status.hidden=false;status.textContent=!modified?(current?'Preset applied':'Default settings'):('Modified · '+(current?'Saved preset unchanged':'Default settings unchanged'));
}
function resetOutputDefaults(silent=false){
 applyOutputPreset({settings:builtinPresetSettings},true);proxyTaskState=null;proxyStandardState=null;$('savedOutputPreset').value='';updateSavedPresetStatus();if(!silent)toast('Default output settings restored');
}

function applyOutputPreset(preset,silent=false){
 const value=preset.settings;
 if(isProxyPreset()){$('qualityMode').value='custom';transitionProxyMode();}
 const assign=()=>{for(const [id,v] of Object.entries(value))if($(id)){if(typeof v==='boolean')$(id).checked=v;else $(id).value=v;}};
 if(value.qualityMode==='proxy'){
  // Enter the proxy flow first, then overlay every saved control value.
  $('qualityMode').value='proxy';transitionProxyMode();assign();$('proxyLocation').value=value.proxyLocation||(value.mode==='directory'?'custom':'subfolder');
 }else{assign();proxyUIActive=false;}
 $('xpsnrTargetRange').value=$('xpsnrTarget').value;
 $('autoTestId').value='';$('autoPreset').value='';$('qualityRecommendation').textContent='';$('confirmDelete').checked=false;$('deleteOriginal').checked=false;
 updateQualityMode();updateEncoders();
 if(value.encoder&&[...$('encoder').options].some(o=>o.value===value.encoder))$('encoder').value=value.encoder;
 // Audio controls are refreshed by the container; restore the saved audio afterwards.
 if(!isProxyPreset()&&value.qualityMode==='custom'&&value.audio)$('audio').value=value.audio;
 updateAudioOptions();$('mode').dispatchEvent(new Event('change'));updateBitrateNote();syncFilenameParts();
 updateProxyPresetUI();updateSelection();updateTestMethod();scheduleEncodingDetails(true);scheduleOutputSize();scheduleNamingPreview();
 presetBaseline=presetSignature(captureOutputPreset());updateSavedPresetStatus();
 if(value.qualityMode==='auto'){$('outputPresetStatus').textContent='Preset applied · Run a quality test for the selected footage';}
 if(!silent)toast('Output preset applied');
}
function openOutputPresetDialog(manage){
 closePoolFilter(poolFilterPickers.get('outputPresets'));
 presetDialogId=manage?$('savedOutputPreset').value:'';const preset=savedOutputPresets.find(p=>p.id===presetDialogId);
 $('outputPresetName').value=preset?.name||'';$('outputPresetDialogTitle').textContent=preset?'Manage output preset':'Save output preset';$('outputPresetError').hidden=true;
 $('confirmSavePreset').hidden=!!preset;for(const id of ['updateOutputPreset','renameOutputPreset','deleteOutputPreset'])$(id).hidden=!preset;
 $('outputPresetDialogNote').textContent=preset?'Update settings replaces this preset with the current output settings. Rename changes only its name.':'Saves output controls and the output folder. Files and quality-test results are not saved.';
 $('outputPresetDialog').showModal();$('outputPresetName').focus();
}
async function changeOutputPreset(action){
 if(presetBusy)return;presetBusy=true;for(const b of $('outputPresetDialog').querySelectorAll('button'))b.disabled=true;
 try{
  const response=await api('output-presets',{action,...(presetDialogId?{id:presetDialogId}:{}),name:$('outputPresetName').value,...(action==='save'?{settings:captureOutputPreset()}: {})});
  savedOutputPresets=response.presets;startupPresetId=response.defaultId||'';if(action==='save')presetBaseline=presetSignature(captureOutputPreset());
  renderSavedOutputPresets(response.selectedId);if(action==='delete')resetOutputDefaults(true);$('outputPresetDialog').close();toast(action==='delete'?'Output preset deleted':action==='rename'?'Output preset renamed':'Output preset saved');
 }catch(error){$('outputPresetError').hidden=false;$('outputPresetError').textContent=error.message;}
 finally{presetBusy=false;for(const b of $('outputPresetDialog').querySelectorAll('button'))b.disabled=false;updateSavedPresetStatus();}
}
$('savedOutputPreset').onchange=()=>{const preset=savedOutputPresets.find(p=>p.id===$('savedOutputPreset').value);if(preset)applyOutputPreset(preset);else resetOutputDefaults();};
$('saveOutputPreset').onclick=()=>openOutputPresetDialog(false);$('manageOutputPreset').onclick=()=>openOutputPresetDialog(true);
$('confirmSavePreset').onclick=()=>changeOutputPreset('save');$('updateOutputPreset').onclick=()=>changeOutputPreset('save');$('renameOutputPreset').onclick=()=>changeOutputPreset('rename');$('deleteOutputPreset').onclick=()=>changeOutputPreset('delete');
$('outputPresetDialog').querySelector('form').onsubmit=event=>{event.preventDefault();changeOutputPreset(presetDialogId?'rename':'save');};
$('closeOutputPresetDialog').onclick=()=>{$('outputPresetDialog').close();$('presetsButton').focus();};
for(const event of ['input','change','click'])document.querySelector('.encode-panel').addEventListener(event,e=>{if(!e.target.closest('.user-output-presets'))requestAnimationFrame(updateSavedPresetStatus);});
function initializeOutputPresetsPanel(){
 const panel=$('outputPresetsPanel'),button=$('presetsButton'),picker={panel,button,native:typeof panel.showPopover==='function',width:360,maxHeight:460,boundary:document.querySelector('.encode-panel')};
 document.body.append(panel);poolFilterPickers.set('outputPresets',picker);if(picker.native){panel.hidden=false;panel.setAttribute('popover','auto');panel.addEventListener('beforetoggle',event=>button.setAttribute('aria-expanded',String(event.newState==='open')));}
 button.onclick=()=>button.disabled?undefined:poolFilterOpen(picker)?closePoolFilter(picker):openPoolFilter(picker,true);$('closeOutputPresetsPanel').onclick=()=>closePoolFilter(picker,true);
 $('applySelectedOutputPreset').onclick=()=>{$('savedOutputPreset').onchange();closePoolFilter(picker,true);};
 $('startupOutputPreset').onchange=async()=>{presetBusy=true;$('startupOutputPreset').disabled=true;const selectedId=$('savedOutputPreset').value;try{const response=await api('output-presets',{action:'set-default',id:$('startupOutputPreset').checked?selectedId:''});startupPresetId=response.defaultId||'';savedOutputPresets=response.presets;renderSavedOutputPresets(selectedId);toast(startupPresetId?'Startup preset saved':'Archiver will start with default settings');}catch(error){toast(error.message,'error');}finally{presetBusy=false;updateSavedPresetStatus();}};
}
initializeOutputPresetsPanel();presetStatusReady=true;
var workflowControlsReady=new Promise(resolve=>document.addEventListener('archiver-workflows-ready',resolve,{once:true}));
(async()=>{try{await workflowControlsReady;const response=await api('output-presets');savedOutputPresets=response.presets;startupPresetId=response.defaultId||'';await refresh();const preset=savedOutputPresets.find(p=>p.id===startupPresetId);if(preset){renderSavedOutputPresets(preset.id);applyOutputPreset(preset,true);}else resetOutputDefaults(true);renderSavedOutputPresets(preset?.id||'');$('saveOutputPreset').disabled=false;$('presetsButton').disabled=false;}catch(error){$('saveOutputPreset').disabled=true;$('presetsButton').disabled=false;$('outputPresetStatus').hidden=false;$('outputPresetStatus').textContent='Could not load saved presets: '+error.message;}})();
var notificationRevision='',notificationItems=[],notificationSeen=new Set(),notificationDisplayed=new Set(),notificationInitialized=false,notificationRequest=false,localNotificationCounter=0;
function notificationTime(value){return new Date(value*1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}
function notificationItemHTML(item,toastView=false){
 const title=esc(item.title),message=esc(item.message||''),action=item.jobId?`<button type="button" class="notification-view" data-notification-view="${esc(item.id)}">View ${item.category==='test'?'in Test Queue':'in Encoding Queue'}</button>`:'';
 return `<article class="notification-item ${esc(item.level)}" data-notification="${esc(item.id)}"><div class="notification-item-heading"><strong>${title}</strong>${toastView?`<button class="icon-button" type="button" data-dismiss-notification="${esc(item.id)}" aria-label="Dismiss notification">×</button>`:`<time datetime="${new Date(item.time*1000).toISOString()}">${notificationTime(item.time)}</time>`}</div>${message?`<p>${message}</p>`:''}${action}</article>`;
}
function matchesNotificationFilters(item,level,source){return (level==='all'||item.level===level)&&(source==='all'||(source==='queue'?['encoding','test'].includes(item.category):(item.category||'app')===source));}
function renderNotifications(){
 const level=$('notificationLevelFilter').value,source=$('notificationSourceFilter').value,filtered=notificationItems.filter(item=>matchesNotificationFilters(item,level,source));
 $('notificationHistory').innerHTML=filtered.length?filtered.map(item=>notificationItemHTML(item)).join(''):`<p class="notification-empty">${notificationItems.length?'No notifications match these filters.':'No notifications yet.'}</p>`;
 $('notificationFilterCount').textContent=`${filtered.length} of ${notificationItems.length} notifications`;$('resetNotificationFilters').hidden=level==='all'&&source==='all';
 const unread=notificationItems.filter(item=>!item.read).length;$('notificationUnread').hidden=!unread;$('notificationUnread').textContent=unread>99?'99+':unread;
 $('notificationsButton').setAttribute('aria-label','Notifications'+(unread?`, ${unread} unread`:''));$('clearNotifications').disabled=!notificationItems.length;
}
const successToastGroups=new Map();
function groupQueueSuccess(item,group,visible){return !!(item.level==='success'&&['encoding','test'].includes(item.category)&&item.jobId&&group&&visible&&item.time>=group.lastTime&&item.time-group.lastTime<=5&&item.time-group.firstTime<=30);}
function showQueueNotificationToast(item){
 if(notificationDisplayed.has(item.id))return;
 const group=successToastGroups.get(item.category);
 if(groupQueueSuccess(item,group,group?.card.isConnected)){
  notificationDisplayed.add(item.id);group.items.push(item);group.lastTime=item.time;
  const card=group.card,count=group.items.length;card.querySelector('strong').textContent=`${count} ${item.category==='test'?'tests':'encodes'} completed`;
  let message=card.querySelector('p');if(!message){message=document.createElement('p');card.querySelector('.notification-item-heading').after(message);}
  message.textContent=group.items.slice(-2).map(row=>(row.message||'').split('\n')[0]).join('\n')+(count>2?`\n+${count-2} more · Every result is in history`:'');
  const action=card.querySelector('.notification-view');if(action){delete action.dataset.notificationView;action.dataset.notificationGroup=item.category;action.textContent='View results';}
  card._restart?.();return;
 }
 const card=showNotificationToast(item);
 if(card&&item.level==='success'&&['encoding','test'].includes(item.category)&&item.jobId)successToastGroups.set(item.category,{card,items:[item],firstTime:item.time,lastTime:item.time});
}

function showNotificationToast(item){
 if(notificationDisplayed.has(item.id))return;notificationDisplayed.add(item.id);
 const holder=document.createElement('div');holder.innerHTML=notificationItemHTML(item,true);const card=holder.firstElementChild;
 $('toast').append(card);while($('toast').children.length>3){const candidates=[...$('toast').children].filter(row=>!row.contains(document.activeElement)&&!row.matches(':hover')),victim=candidates.find(row=>!row.classList.contains('error'))||candidates[0]||card;if(victim._dismiss)victim._dismiss();else victim.remove();}
 let timer;const dismiss=()=>{clearTimeout(timer);card.remove();},start=()=>{clearTimeout(timer);if(card.matches(':hover')||card.contains(document.activeElement))return;timer=setTimeout(()=>{if(card.matches(':hover')||card.contains(document.activeElement)){start();return;}dismiss();},item.level==='error'?12000:7000);};
 card.onpointerenter=()=>clearTimeout(timer);card.onpointerleave=start;card.addEventListener('focus',()=>clearTimeout(timer),true);card.addEventListener('blur',()=>setTimeout(start,0),true);card._dismiss=dismiss;card._restart=start;start();return card;
}
async function recordNotification(message,level){
 try{const item=await api('notifications',{title:message.slice(0,200),message:message.length>200?message:'',level});notificationSeen.add(item.id);notificationItems=[item,...notificationItems.filter(n=>n.id!==item.id)].slice(0,500);renderNotifications();showNotificationToast(item);}
 catch(error){const item={id:'local-'+(++localNotificationCounter),title:message.slice(0,200),message:message.length>200?message:'',level,time:Date.now()/1000,read:false};notificationItems.unshift(item);renderNotifications();showNotificationToast(item);$('notificationHistoryError').hidden=false;$('notificationHistoryError').textContent='Notification history could not be saved.';}
}
async function refreshNotifications(){
 if(notificationRequest)return;notificationRequest=true;
 try{
  const response=await api('notifications'+(notificationRevision?'?revision='+encodeURIComponent(notificationRevision):''));
  if(response.unchanged){if(poolFilterOpen(poolFilterPickers.get('notifications'))&&notificationItems.some(item=>!item.read)){const read=await api('notifications',{action:'read'});notificationRevision=read.revision;notificationItems=read.items;renderNotifications();}return;}
  notificationRevision=response.revision||'';const fresh=response.items.filter(item=>!notificationSeen.has(item.id));
  notificationItems=response.items;for(const item of response.items)notificationSeen.add(item.id);
  if(notificationInitialized&&!poolFilterOpen(poolFilterPickers.get('notifications')))for(const item of fresh.reverse())if(item.category!=='import')showQueueNotificationToast(item);
  notificationInitialized=true;$('notificationHistoryError').hidden=true;renderNotifications();
  if(poolFilterOpen(poolFilterPickers.get('notifications'))&&response.unread){const read=await api('notifications',{action:'read'});notificationRevision=read.revision;notificationItems=read.items;for(const item of read.items)notificationSeen.add(item.id);renderNotifications();}
 }catch(error){$('notificationHistoryError').hidden=false;$('notificationHistoryError').textContent='Could not load notification history: '+error.message;}
 finally{notificationRequest=false;}
}
function openNotificationItem(id){
 const item=notificationItems.find(row=>row.id===id);if(!item?.jobId)return;
 const test=item.category==='test',exists=(test?state.test_jobs:state.jobs)?.some(job=>job.id===item.jobId);closePoolFilter(poolFilterPickers.get('notifications'));
 if(!exists){toast('This item is no longer in the queue. Its notification remains in history.');return;}
 showPane(test?'tests':'queue');const card=[...document.querySelectorAll(test?'[data-test-id]':'[data-encode-id]')].find(e=>(test?e.dataset.testId:e.dataset.encodeId)===item.jobId);card?.scrollIntoView({block:'center',behavior:'smooth'});
}
function initializeNotifications(){
 const panel=$('notificationsPanel'),button=$('notificationsButton'),picker={panel,button,native:typeof panel.showPopover==='function',width:420,maxHeight:620,boundary:document.querySelector('.workspace')};
 document.body.append(panel);poolFilterPickers.set('notifications',picker);
 if(picker.native){
  panel.hidden=false;panel.setAttribute('popover','auto');button.setAttribute('popovertarget',panel.id);button.setAttribute('popovertargetaction','toggle');
  panel.addEventListener('beforetoggle',event=>{button.setAttribute('aria-expanded',String(event.newState==='open'));if(event.newState==='open'){$('toast').replaceChildren();successToastGroups.clear();requestAnimationFrame(async()=>{positionPoolFilter(picker);await refreshNotifications();if(poolFilterOpen(picker))positionPoolFilter(picker);});}});
 }
 button.onclick=async()=>{if(picker.native)return;if(poolFilterOpen(picker)){closePoolFilter(picker,true);return;}$('toast').replaceChildren();successToastGroups.clear();openPoolFilter(picker,true);await refreshNotifications();positionPoolFilter(picker);};
 $('closeNotifications').onclick=()=>closePoolFilter(picker,true);
 for(const id of ['notificationLevelFilter','notificationSourceFilter'])$(id).onchange=()=>{renderNotifications();$('notificationHistory').scrollTop=0;positionPoolFilter(picker);};
 $('resetNotificationFilters').onclick=()=>{$('notificationLevelFilter').value='all';$('notificationSourceFilter').value='all';renderNotifications();positionPoolFilter(picker);};
 $('clearNotifications').onclick=async()=>{try{const result=await api('notifications',{action:'clear'});notificationItems=result.items;$('toast').replaceChildren();successToastGroups.clear();renderNotifications();}catch(error){$('notificationHistoryError').hidden=false;$('notificationHistoryError').textContent=error.message;}};
 for(const host of [$('notificationHistory'),$('toast')])host.onclick=event=>{const dismiss=event.target.closest('[data-dismiss-notification]'),view=event.target.closest('[data-notification-view]'),group=event.target.closest('[data-notification-group]');if(dismiss)dismiss.closest('.notification-item')._dismiss?.();if(view)openNotificationItem(view.dataset.notificationView);if(group){$('notificationLevelFilter').value='success';$('notificationSourceFilter').value=group.dataset.notificationGroup;renderNotifications();if(!poolFilterOpen(picker))button.click();}};
 // Import progress and ordinary toasts share one left-hand stack rather than overlap.
 $('notificationToastHost').prepend($('scanToast'));
 notificationUIReady=true;renderNotifications();refreshNotifications();
}
initializeNotifications();

function applyDependencyGates(){
 if(!dependencyUIReady)return;const ready=state.dependencies?.ready===true;
 if(!ready)for(const id of ['scan','enqueue','analyzeQuality','startTests','startQueue']){$(id).disabled=true;$(id).dataset.dependencyBlocked='true';$(id).title='Finish Video tools setup before starting media work';}
 else for(const id of ['scan','enqueue','analyzeQuality','startTests','startQueue'])if($(id).dataset.dependencyBlocked){delete $(id).dataset.dependencyBlocked;$(id).title='';}
 if(!ready)$('queueHint').textContent='Open Video tools to finish setup before importing, testing or encoding.';
}
var toolSetupSeenRevision=0;
function updateDependencyStatus(){
 const setup=state.dependencies?.setup||{};
 if($('installVideoTools')){
 $('installVideoTools').disabled=!!setup.running||!!state.dependencies?.ready;
 $('installVideoTools').textContent=setup.running?'Installing…':'Install missing tools';
 $('toolSetupProgress').hidden=!setup.message;
 $('toolSetupProgress').querySelector('progress').hidden=!setup.running;
 $('toolSetupMessage').textContent=setup.message||'';
 $('toolSetupMessage').classList.toggle('requires-setup',setup.status==='error');
 $('settingsForm').querySelector('button[type=submit]').disabled=!!setup.running;
 if(setup.running){toolSetupSeenRevision=setup.revision;}
 else if(setup.revision&&toolSetupSeenRevision===setup.revision){toolSetupSeenRevision=0;if(setup.status==='success'){$('ffmpegPath').value=state.ffmpeg||'';$('ffprobePath').value=state.ffprobe||'';}toast(setup.message,setup.status==='success'?'success':'error');}
 }

 const status=state.dependencies||{ready:false,missing:['Tool verification']},info=status.ab_av1||state.ab_av1||{},ready=!!status.ready;
 $('toolStatus').textContent=ready?'Ready':'Setup required';$('toolStatus').classList.toggle('ready',ready);$('settingsOpen').classList.toggle('tools-ready',ready);$('settingsOpen').title=ready?'Video tools · All required tools are ready':'Video tools · Setup required: '+status.missing.join(', ');$('settingsOpen').setAttribute('aria-label',$('settingsOpen').title);
 $('dependencySummary').textContent=ready?'All required video tools are ready.':'Setup required: '+status.missing.join(', ')+'. Importing, testing and encoding are unavailable until setup is complete.';
 $('dependencySummary').classList.toggle('requires-setup',!ready);
 $('abAv1DetailStatus').textContent=info.available?'Ready':'Not available';$('abAv1Version').textContent=info.version||'Not detected';$('abAv1Source').textContent=info.bundled?'Included with Archiver':info.path?'Found on PATH':'Not found';$('abAv1Path').textContent=info.path||'No executable found';$('abAv1Error').hidden=!info.error;$('abAv1Error').textContent=info.error||'';applyDependencyGates();
}
$('recheckAbAv1').onclick=async()=>{const button=$('recheckAbAv1');button.disabled=true;try{state.ab_av1=await api('ab-av1-check',{});await refresh();updateDependencyStatus();toast(state.dependencies?.ready?'All video tools are ready':state.ab_av1.available?'ab-av1 verified. Finish the remaining Video tools setup.':state.ab_av1.error,state.dependencies?.ready?'success':'info');}catch(error){toast(error.message,'error');}finally{button.disabled=false;}};
dependencyUIReady=true;applyDependencyGates();

$('installVideoTools').onclick=async()=>{const button=$('installVideoTools');button.disabled=true;try{const setup=await api('setup-tools',{});toolSetupSeenRevision=setup.revision;await refresh();}catch(error){toast(error.message,'error');button.disabled=false;}};

function scoreSummary(scores){const finite=scores.filter(s=>Number.isFinite(s.mean)).map(s=>s.mean);return finite.length?Math.min(...finite).toFixed(2):scores.length&&scores.every(s=>s.identical)?'Identical':'Unavailable';}

$('analyzeSelected').onclick=async()=>{try{await api('analyze-files',{ids:[...selected]});scanToastDismissed=false;await refresh();}catch(e){toast(e.message,'error');}};

$('importMode').title='Files only lists filenames and sizes without reading video metadata or generating previews. Analyze selected files when needed.';

let importCacheSettings=null;
function renderImportCache(info){importCacheSettings=info;$('importCacheDirectory').value=info.directory;$('importCacheInfo').textContent=`${info.entries} cached files · ${bytes(info.bytes)}${info.error?' · '+info.error:''}`;$('importCacheDirectory').disabled=info.override;$('importCacheSave').disabled=info.override;$('importCacheDefault').disabled=info.override;$('importCacheBrowse').disabled=info.override;}
$('importCacheOpen').onclick=async()=>{try{renderImportCache(await api('import-cache'));$('importCacheDialog').showModal();}catch(e){toast(e.message,'error');}};
$('importCacheClose').onclick=()=>$('importCacheDialog').close();
$('importCacheDefault').onclick=()=>{$('importCacheDirectory').value=importCacheSettings.defaultDirectory;};
$('importCacheBrowse').onclick=async()=>{try{const r=await api('browse',{initial:$('importCacheDirectory').value,kind:'destination'});if(r.directory)$('importCacheDirectory').value=r.directory;}catch(e){toast(e.message,'error');}};
$('importCacheSave').onclick=async()=>{const button=$('importCacheSave');button.disabled=true;try{renderImportCache(await api('import-cache',{directory:$('importCacheDirectory').value}));toast('Import cache folder saved','success');}catch(e){toast(e.message,'error');}finally{button.disabled=!!importCacheSettings?.override;}};
