"""Adaptive ab-av1 searches with independent, source-timed clip validation.

Budgets bound sample work, never elapsed time. A budget cannot turn a failed
quality check into an applicable recommendation. Thresholds are application
heuristics, not perceptual guarantees or statistical confidence intervals.
"""
import json
import math
from pathlib import Path
import ab_av1
import motion_selection
import test_levels
import motion

MAX_ROUNDS = 4
SCORE_SPREAD_DB = 3.
SIZE_SPREAD_RATIO = 2.
ESTIMATE_CHANGE = .10


def window_key(w):
    return (round(w['start'],6),round(w['duration'],6))


def clip_check(analyzer,item,settings,winner,window,directory):
    """Encode the exact lossless reference with the final-output command path."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    reference_dir=directory.parent.parent/'reference-clips';reference_dir.mkdir(exist_ok=True)
    ref=reference_dir/f'{window["start"]:.6f}-{window["duration"]:.6f}.mkv';encoded=directory/'encoded.mkv'
    analyzer.check()
    known_motion=next((m for m in item.get('_motionSelection',{}).get('sampleMotion',[]) if window_key(m)==window_key(window) and math.isfinite(m.get('mean',float('nan')))),None)
    measure_motion=bool(item.get('_motionSelection',{}).get('sampleMotion')) and known_motion is None
    motion_file=directory/'motion.txt'
    motion_filter=',vmafmotion=stats_file=motion.txt' if measure_motion else ''
    if not ref.exists():analyzer.run([analyzer.ffmpeg,'-hide_banner','-v','error','-nostdin','-y','-ss',str(window['start']),
                  '-i',item['path'],'-t',str(window['duration']),'-map','0:v:0','-an','-sn','-dn',
                  '-vf',f'trim=duration={window["duration"]},setpts=PTS-STARTPTS{motion_filter}',
                  '-c:v','ffv1','-level','3','-threads','2','-fps_mode','passthrough','-enc_time_base','1:1000000',str(ref)],cwd=directory)
    if measure_motion:
        if motion_file.exists():known_motion={**motion.summarize(motion_file.read_text(encoding='utf-8')),**window}
        else:
            # Existing references from interrupted work need only a motion pass.
            known_motion={**motion.measure(analyzer,ref,{'start':0.,'duration':window['duration']},directory,0),**window}
    config={**settings,**{k:winner[k] for k in ('codec','encoder','qualityValue','encoderPriority')},
            'qualityMode':'perceptual','autoEngine':'ab-av1','sourceMetadata':item,
            'resolution':'original','fps':'original','bitrate':'crf' if not winner['encoder'].endswith(('_nvenc','_qsv')) else 'cqp',
            'audio':'copy','container':'mkv'}
    command=analyzer.command_for(ref,encoded,config)
    # Validation is video-only; references intentionally contain no audio.
    analyzer.run(command,cwd=directory)
    score=analyzer.score_xpsnr(ref,encoded,directory,item['fps'],0)
    if math.isnan(score) or score == -math.inf:raise ValueError('Invalid validation XPSNR score')
    return {**window,'reference':str(ref.resolve()),'encoded':str(encoded.resolve()),'xpsnr':score if math.isfinite(score) else None,'identical':score==math.inf,
            'bytesPerSecond':encoded.stat().st_size/window['duration'],'qualityValue':winner['qualityValue'],
            'encoder':winner['encoder'],**({'motion':known_motion} if known_motion else {})}


def analyze(item,settings,available,ffmpeg,ffprobe,directory,cancelled,progress,telemetry,analyzer,previews=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    level=settings.get('testLevel') or 'balanced';budget=test_levels.policy(level)
    telemetry=telemetry or (lambda _:None)
    selection=item['_motionSelection'];plan=list(selection['windows']);probes=selection.get('probes',[])
    checked={};history=[];all_attempts=[];previous_size=None;next_settings=dict(settings); focus=None; expansions=0; holdout_plan=[]
    target=ab_av1.target_for(settings);all_used=list(plan);final=None;reserved=None
    use_motion=bool(selection.get('sampleMotion'))
    comparison_clips=[]
    motion_by_key={window_key(m):dict(m) for m in selection.get('sampleMotion',[])}
    def motion_rows(windows):
        return motion.rank_samples([motion_by_key.get(window_key(w),{**w,'error':'Motion measurement pending' if use_motion else 'Motion measurement unavailable'}) for w in windows])
    def emit(data):
        if focus:
            original=plan+holdout_plan
            data={**data,'sampleWindows':original,'sampleTotal':len(original),'combinedSamples':False,'sampleMotion':motion_rows(original)}
            if data.get('activeSampleIndices'):
                data['activeSampleIndices']=[next(i for i,w in enumerate(original) if window_key(w)==window_key(focus))]
        if 'measurements' in data:
            data={**data,'measurements':all_attempts+[{**m,'round':round_index} for m in data['measurements']]}
        # The CLI percentage describes this search, not validation or future rounds.
        if 'searchPercent' in data:data={**data,'searchPercent':min(90,data['searchPercent']*.9)}
        telemetry(data)
    for round_index in range(1,budget['rounds']+1):
        analyzer.check()
        run_dir=directory/f'round-{round_index}'
        if focus:
            # Search the difficult clip itself, rather than raising the mean of an
            # ever-growing concatenation. Reuse its exact validated reference.
            selection={**selection,'windows':[{'start':focus['start'],'duration':focus['duration']}],
                       'path':focus['reference'],'referenceDuration':focus['duration']}
        progress(f'Quality search · Round {round_index} · '+('Difficult clip' if focus else f'{len(plan)} clips'))
        telemetry({'adaptiveRound':round_index,'stage':'search','searchPercent':0,'searchEtaText':'','terminalProgress':''})
        current=next_settings.get('_reuseCandidate') or ab_av1.analyze({**item,'_motionSelection':selection},next_settings,available,ffmpeg,ffprobe,run_dir,cancelled,progress,emit)
        if '_reuseCandidate' not in next_settings:all_attempts.extend({**m,'round':round_index} for m in current.get('measurements',[]))
        winner=current['winner'];quality=winner['qualityValue']
        fresh=[] if focus else motion_selection.holdouts(item['duration'],probes,all_used,count=test_levels.holdout_count(level,len(plan))-(1 if reserved else 0))
        all_used+=fresh
        independent=holdout_plan if focus else sorted(([reserved] if reserved else [])+fresh,key=lambda w:w['start'])
        holdout_plan=list(independent)
        if reserved is None and independent:reserved=independent[-1]
        telemetry({'sampleWindows':plan+independent,'sampleTotal':len(plan)+len(independent),'sampleRoles':['search']*len(plan)+['independent']*len(independent),'sampleMotion':motion_rows(plan+independent),'motionAvailable':use_motion})
        if independent and previews:previews(plan+independent)
        # Retry the known weak clip first. Do not spend another full pass on a
        # candidate that still fails there. Original indices preserve UI positions.
        ordered=list(enumerate(plan+independent))
        if focus:ordered.sort(key=lambda pair:window_key(pair[1])!=window_key(focus))
        checks=[]
        for completed,(index,w) in enumerate(ordered):
            analyzer.check();role='search' if index<len(plan) else 'independent'
            key=(window_key(w),winner['encoder'],quality)
            progress(f'Checking {role} clip {index+1}/{len(plan)+len(independent)} · {w["start"]:.1f}s')
            telemetry({'stage':'validation','activeSampleIndices':[index],
                       'validationCurrent':completed+1,'validationTotal':len(plan)+len(independent),
                       'validationWindow':w,'searchEtaText':'','terminalProgress':''})
            if key not in checked:checked[key]=clip_check(analyzer,item,settings,winner,w,directory/f'checks/{len(checked)+1}')
            if checked[key].get('motion'):motion_by_key[window_key(w)]={**checked[key]['motion'],'start':w['start'],'duration':w['duration']}
            telemetry({'sampleMotion':motion_rows(plan+independent)})
            row={**checked[key],'role':role,'passed':checked[key]['identical'] or checked[key]['xpsnr']>=target}
            checks.append(row)
            if not any(r.get('encoded')==row.get('encoded') for r in comparison_clips):
                comparison_clips.append({**row,'attempt':1+sum(window_key(r)==window_key(row) for r in comparison_clips)})
            telemetry({'validationResults':list(checks),'comparisonClips':list(comparison_clips)})
            if focus and not row['passed']:break
        failed=[r for r in checks if not r['passed']]
        finite=[r['xpsnr'] for r in checks if r['xpsnr'] is not None]
        rates=[r['bytesPerSecond'] for r in checks if r['bytesPerSecond']>0]
        score_spread=max(finite)-min(finite) if finite else 0
        size_spread=max(rates)/min(rates) if rates else 1
        size=sum(r['bytesPerSecond']*r['duration'] for r in checks)/sum(r['duration'] for r in checks)*item['duration']
        current={**current,'estimatedVideoBytes':size}
        change=abs(size-previous_size)/max(1,previous_size) if previous_size is not None else None
        variable=score_spread>SCORE_SPREAD_DB or size_spread>SIZE_SPREAD_RATIO or (change is not None and change>ESTIMATE_CHANGE)
        record={'round':round_index,'qualityValue':quality,'searchClips':list(plan),'independentClips':independent,
                'checks':checks,'scoreSpreadDb':score_spread,'sizeSpreadRatio':size_spread,'estimateChange':change,
                'estimatedVideoBytes':size,'passed':not failed,'variable':variable}
        history.append(record)
        (directory/'validation-history.json').write_text(json.dumps(history,indent=2,allow_nan=False),encoding='utf-8')
        if not failed and (not variable or expansions>=budget['expansions'] or round_index==budget['rounds'] or not independent):
            final=current;break
        if round_index==budget['rounds']:break
        if failed:
            worst=min(failed,key=lambda r:r['xpsnr'])
            # Persistent score plateaus are evidence to stop, not to keep adding
            # unrelated footage. Never relax the user's target to make a pass.
            prior=[r for h in history[:-1] for r in h['checks']
                   if window_key(r)==window_key(worst) and r['qualityValue']>=quality+2]
            if prior and worst['xpsnr']-prior[-1]['xpsnr']<.05:
                progress('Quality plateau on a validation clip · Stopping repeated searches')
                break
            maximum=quality-1
            if maximum < (1 if winner['encoder'].endswith('_qsv') else 0):break
            focus=worst
            if worst['role']=='independent':
                # Once searched, a holdout is training footage. Replace it so the
                # final recommendation still faces genuinely unseen footage.
                plan=sorted(plan+[{'start':worst['start'],'duration':worst['duration']}],key=lambda w:w['start'])
                replacement=motion_selection.holdouts(item['duration'],probes,all_used,count=1)
                all_used+=replacement
                holdout_plan=[w for w in independent if window_key(w)!=window_key(worst)]+replacement
                if reserved and window_key(reserved)==window_key(worst):reserved=holdout_plan[-1] if holdout_plan else None
            next_settings={**settings,'_searchMaxCrf':maximum,'_searchTarget':min(50,target+.2)}
            progress('A clip missed the target · Searching that clip directly')
        else:
            # Variation affects estimate uncertainty, not a passing quality target.
            # One bounded coverage expansion is enough; do not restart CRF-search.
            expansions+=1
            plan=sorted(plan+[w for w in independent if window_key(w)!=window_key(reserved)],key=lambda w:w['start'])
            # Reuse the current candidate; fresh clips below still get checked.
            focus=None
            next_settings={**settings,'_reuseCandidate':current}
            progress('Checking extra coverage · Reusing the measured quality setting')
        previous_size=size
    telemetry({'activeSampleIndices':[],'validationWindow':None,'validationHistory':history})
    if final is None:
        raise ValueError('No setting passed every clip quality check within the adaptive sample budget. Review validation details or choose Manual controls; no settings were applied.')
    record=history[-1]
    rate=record['estimatedVideoBytes']/item['duration']
    scores=[r['xpsnr'] for r in record['checks'] if r['xpsnr'] is not None]
    winner={**final['winner'],'bytesPerSecond':rate,
            'scores':[{'mean':sum(scores)/len(scores) if scores else None,'p05':None,'identical':not scores}]}
    source_bytes=item.get('video_bitrate',0)/8*item['duration'] or item.get('size',1)
    final.update(winner=winner,alternatives=[winner],videoSavings=1-record['estimatedVideoBytes']/max(1,source_bytes))
    final.update(comparisonClips=comparison_clips,testLevel=level,validation=record,validationHistory=history,measurements=all_attempts,trials=len(all_attempts),
                 sampleMotion=motion_rows(plan+record['independentClips']),sampleWindows=list(plan),
                 coverage=f'{len(plan)} search clips; {len(record["independentClips"])} clips held out of the final search. '
                 + ('Full recording checked.' if item['duration']<=30 else 'Sampled coverage, not a full-video guarantee. ')
                 + ('Clip results vary; the output-size estimate has limited reliability.' if record['variable'] else 'No expansion threshold exceeded in the final checks.'))
    return final
