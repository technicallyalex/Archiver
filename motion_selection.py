"""Bounded motion sampling and a lossless, source-timed search reference."""
import random
import json
import math
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import motion
import test_levels


def probes(duration, rng=None, level="balanced"):
    policy=test_levels.policy(level)
    rng = rng or random.SystemRandom()
    length = min(2., duration)
    if duration <= 24:
        return [{'start': 0., 'duration': length}]
    count = 12 if duration < 300 else 20 if duration < 1800 else 32 if duration < 7200 else 40 if duration < 14400 else 48
    count=max(policy['probeMin'],min(policy['probeMax'],round(count*policy['probeScale'])))
    span = (duration - length) / count
    return [{'start': rng.uniform(i * span, (i + 1) * span), 'duration': length} for i in range(count)]


def select(duration, measurements, level="balanced"):
    policy=test_levels.policy(level)
    if duration <= 30:
        return [{'start': 0., 'duration': duration}]
    valid = [m for m in measurements if math.isfinite(m.get('mean',float('nan')))]
    if len(valid) < 3:
        raise ValueError('Not enough valid motion probes')
    values = sorted(m['mean'] for m in valid)
    count = min(policy['longSamples'] if duration >= 3600 else policy['samples'], max(1,int(duration//16)))
    # Always retain the most active probe, then cover time strata at varied ranks.
    chosen = [max(valid,key=lambda m:m['mean'])]
    def start(m):
        return max(0., min(duration-8, m['start']-3))
    for i in range(count):
        if len(chosen)>=count:break
        quantile=[.5,.75,.25,.9,.5,.75,.5,.9][i%8]
        target=values[round((len(values)-1)*quantile)]
        candidates = [m for m in valid if all(abs(start(m) - start(c)) >= 8 for c in chosen)]
        if not candidates:
            break
        local=[m for m in candidates if i*duration/count<=m['start']<(i+1)*duration/count]
        chosen.append(min(local or candidates, key=lambda m: abs(m['mean']-target)))
    return sorted([{'start': start(m), 'duration':8.} for m in chosen], key=lambda w:w['start'])


def holdouts(duration, measurements, used, count=3):
    """Unused, nonoverlapping windows, favoring activity then temporal coverage."""
    if duration<=30:return []
    candidates=[{'start':max(0.,min(duration-8,m['start']-3)), 'duration':8.,'motion':m.get('mean',0)} for m in measurements]
    chosen=[]
    for _ in range(count):
        available=[w for w in candidates if all(w['start']+w['duration']<=u['start'] or u['start']+u['duration']<=w['start'] for u in used+chosen)]
        if not available:
            # Fill the largest uncovered interval if random candidates are crowded.
            occupied=sorted(used+chosen,key=lambda w:w['start']);edge=0.;gaps=[]
            for w in occupied:
                if w['start']-edge>=8:gaps.append((edge,w['start']))
                edge=max(edge,w['start']+w['duration'])
            if duration-edge>=8:gaps.append((edge,duration))
            if not gaps:break
            a,b=max(gaps,key=lambda p:p[1]-p[0]);chosen.append({'start':(a+b-8)/2,'duration':8.});continue
        w=max(available,key=lambda w:w['motion']) if not chosen else max(available,key=lambda w:min(abs(w['start']-u['start']) for u in used+chosen))
        chosen.append({'start':w['start'],'duration':w['duration']})
    return sorted(chosen,key=lambda w:w['start'])


def prepare(analyzer, item, directory, progress, telemetry, previews=None, probe_factory=None, use_motion=True, level="balanced"):
    directory = Path(directory)
    candidates=probes(item['duration'],level=level)
    probe_lock=threading.Lock()
    states=[{**w,'index':i,'status':'planned'} for i,w in enumerate(candidates)]
    def publish_probe(index,status,summary=None):
        with probe_lock:
            states[index].update(status=status)
            if summary and math.isfinite(summary.get('mean',float('nan'))):states[index]['mean']=summary['mean']
            telemetry({'stage':'motion-scout','motionProbes':[dict(s) for s in states],'motionProbesCompleted':sum(s['status']=='completed' for s in states),'sourceDuration':item['duration']})
    if use_motion:telemetry({'stage':'motion-scout','motionProbes':[dict(s) for s in states],'motionProbesCompleted':0,'sourceDuration':item['duration']})
    def probe(task):
        i,window=task
        if probe_factory and analyzer.cancelled():raise InterruptedError('Motion selection cancelled')
        progress(f'Choosing representative footage · Motion probe {i+1}/{len(candidates)}')
        publish_probe(i,'active')
        try:
            result=motion.measure(probe_factory() if probe_factory else analyzer,item['path'],window,directory,100+i)
        except BaseException:
            publish_probe(i,'failed');raise
        publish_probe(i,'completed',result)
        return result
    if not use_motion:
        measured=[{**w,'mean':0.} for w in candidates]
    elif probe_factory:
        with ThreadPoolExecutor(max_workers=2) as pool:
            measured=list(pool.map(probe,enumerate(candidates)))
    else:
        measured=[probe(task) for task in enumerate(candidates)]
    plan = select(item['duration'], measured,level=level)
    telemetry({'stage':'sample-previews','sampleWindows':plan, 'sourceDuration':item['duration'], 'sampleTotal':len(plan)})
    if previews:previews(plan)
    result=reference(analyzer,item,plan,directory,progress,use_motion=use_motion)
    manifest = {**result,'testLevel':level,'windows':plan,'probes':measured,'method':f'{len(candidates)} stratified two-second probes; varied motion and time coverage; not a whole-file average' if use_motion else 'Distributed time coverage; motion filter unavailable'}
    (directory/'motion-selection.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def reference(analyzer,item,plan,directory,progress,use_motion=True):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    inputs, filters = [], []
    for i, window in enumerate(plan):
        inputs += ['-threads','1','-ss',str(window['start']),'-t',str(window['duration']),'-i',item['path']]
        motion_filter=f'vmafmotion=stats_file=selected-{i}-motion.txt,' if use_motion else ''
        filters.append(f'[{i}:v:0]trim=duration={window["duration"]},setpts=PTS-STARTPTS,{motion_filter}settb=AVTB[v{i}]')
    filters.append(''.join(f'[v{i}]' for i in range(len(plan)))+f'concat=n={len(plan)}:v=1:a=0[out]')
    reference = directory/'motion-reference.mkv'
    progress('Preparing selected footage for quality search')
    analyzer.run([analyzer.ffmpeg,'-v','error','-nostdin','-y',*inputs,'-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[out]','-c:v','ffv1','-level','3','-threads','2','-fps_mode','passthrough','-enc_time_base','1:1000000',str(reference)],cwd=directory)
    summaries=[]
    for i,window in enumerate(plan):
        stats=directory/f'selected-{i}-motion.txt'
        if stats.exists():summaries.append({**motion.summarize(stats.read_text()),**window,'statsFile':stats.name})
    metadata = json.loads(analyzer.run([analyzer.ffprobe,'-v','error','-show_format','-of','json',str(reference)]))
    duration = float(metadata['format']['duration'])
    return {'sampleMotion':motion.rank_samples(summaries),'referenceDuration':duration,'path':str(reference)}
