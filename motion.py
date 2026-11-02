"""Native-resolution, source-timed FFmpeg vmafmotion summaries."""
import math
import re
from pathlib import Path


def summarize(text):
    frames=[]
    for line in text.splitlines():
        if not line.strip():continue
        match=re.fullmatch(r'n:(\d+)\s+motion:([^\s]+)\s*',line)
        if not match:raise ValueError('Unexpected vmafmotion frame data')
        number,value=int(match[1]),float(match[2])
        if number!=len(frames)+1 or not math.isfinite(value) or value<0:
            raise ValueError('Invalid vmafmotion frame sequence or score')
        frames.append(value)
    if not frames:raise ValueError('vmafmotion returned no frames')
    ordered=sorted(frames)
    return {'mean':sum(frames)/len(frames),'peak':max(frames),'p95':ordered[max(0,math.ceil(.95*len(frames))-1)],
            'frames':len(frames),'metric':'vmafmotion','units':'raw score','version':1}


def measure(analyzer, source, window, directory, index):
    directory=Path(directory)
    name=f'sample-{index+1}-vmafmotion.txt'
    output=directory/name
    analyzer.run([analyzer.ffmpeg,'-v','error','-nostdin','-y','-threads','1','-ss',str(window['start']),
                  '-i',str(source),'-t',str(window['duration']),'-map','0:v:0','-an','-sn','-dn',
                  '-filter_threads','1','-vf',f"trim=duration={window['duration']},setpts=PTS-STARTPTS,vmafmotion=stats_file={name}",'-fps_mode','passthrough','-f','null','-'],cwd=directory)
    result=summarize(output.read_text(encoding='utf-8'))
    return {**result,'start':window['start'],'duration':window['duration'],'statsFile':name}


def rank_samples(samples):
    """Relative labels, never universal motion thresholds."""
    values=sorted(set(round(s['mean'],6) for s in samples if 'mean' in s))
    for sample in samples:
        if 'mean' not in sample:continue
        if len(values)==1:
            sample['relative']='Similar within test' if sum('mean' in s for s in samples)>1 else 'Single sample'
        else:
            value=round(sample['mean'],6)
            sample['relative']='Lower within test' if value==values[0] else 'Higher within test' if value==values[-1] else 'Middle within test'
    return samples
