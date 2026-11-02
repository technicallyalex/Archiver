"""Escaped human-readable sidecars and machine-readable encode provenance."""
import html,json,time
from pathlib import Path
import workflow_store,tool_config

def document(job,version,tools):
    source=job.get('settings',{}).get('sourceMetadata',{});size=job.get('source_size',0);output=job.get('output_size',0)
    return workflow_store.clean({'schema':'archiver.encode-report','version':1,'jobId':job['id'],'created':time.time(),
        'source':{'path':job['source'],'bytes':size,'modifiedNs':source.get('sourceMtimeNs'),'identity':'Path, size and modification time; not a content checksum'},
        'output':{'path':job['output'],'bytes':output,'reductionPercent':(1-output/size)*100 if size else None},
        'settings':{k:v for k,v in job['settings'].items() if k!='sourceMetadata'},'elapsedSeconds':job.get('finished',time.time())-job.get('started',time.time()),
        'verification':job.get('verification',{'status':'not requested'}),'qualityTest':job.get('qualityResult') or job.get('testedAnalysis'),
        'command':job.get('command',[]),'tools':{'Archiver':version,**tools}})

def render(data):
    e=lambda value:html.escape(str(value))
    rows=''.join('<tr><th>'+e(k)+'</th><td><pre>'+e(json.dumps(v,indent=2,ensure_ascii=False) if isinstance(v,(list,dict)) else v)+'</pre></td></tr>' for k,v in data.items())
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Archiver encode report</title><style>body{font:14px/1.6 system-ui;margin:32px;max-width:1200px;color:#202d27;background:#f6f7f5}h1{font-size:24px}table{border-collapse:collapse;width:100%}th,td{padding:12px;border-bottom:1px solid #ccd6ce;vertical-align:top;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:inherit}</style><h1>Archiver encode report</h1><p>Quality measurements describe the tested clips, not every frame.</p><table>'+rows+'</table></html>'

def save(job,version,tools):
    data=document(job,version,tools);base=Path(job['output']);json_path=base.with_name(base.name+'.archiver-report.json');html_path=base.with_name(base.name+'.archiver-report.html')
    # Do not overwrite an unrelated sidecar left by another application or job.
    for n in range(1,10000):
        suffix='' if n==1 else '-'+str(n)
        jp=json_path.with_stem(json_path.stem+suffix);hp=html_path.with_stem(html_path.stem+suffix)
        if jp.exists() or hp.exists():continue
        try:
            with jp.open('x',encoding='utf-8') as stream:json.dump(data,stream,indent=2,ensure_ascii=False,allow_nan=False)
        except FileExistsError:continue
        try:
            with hp.open('x',encoding='utf-8') as stream:stream.write(render(data))
        except Exception:
            jp.unlink(missing_ok=True);raise
        return {'json':str(jp),'html':str(hp)}
    raise ValueError('No free report filename was available')
