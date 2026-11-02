"""Explicit stream selection and preservation controls shared by queue and inspector."""
from pathlib import Path
DEFAULTS={'metadata':True,'chapters':True,'dates':True,'color':True,'audioTracks':'all','subtitleTracks':'all','subtitles':'none'}
TEXT={'subrip','ass','ssa','webvtt','mov_text','text'}
def settings(value):
    if value is None:return dict(DEFAULTS)
    if not isinstance(value,dict) or any(k not in DEFAULTS for k in value):raise ValueError('Invalid audio/metadata settings')
    result={**DEFAULTS,**value}
    for key in ('metadata','chapters','dates','color'):
        if type(result[key]) is not bool:raise ValueError('Invalid preservation checkbox')
    for key in ('audioTracks','subtitleTracks'):
        v=result[key]
        if v!='all' and (not isinstance(v,list) or len(v)>128 or any(type(i) is not int or not 0<=i<128 for i in v)):raise ValueError('Invalid track selection')
    if result['subtitles'] not in ('none','copy','text'):raise ValueError('Invalid subtitle handling')
    return result

def selected(item,kind,value):
    rows=[s for s in item.get('streams',[]) if s['type']==kind]
    return rows if value=='all' else [s for i,s in enumerate(rows) if i in value]

def audio_metadata(item,config):
    tracks=settings(config.get('preservation'))['audioTracks'];streams=item.get('audio_streams',[])
    if config.get('audio')=='none':return []
    return streams if tracks=='all' else [s for i,s in enumerate(streams) if i in tracks]

def summary(item,config):
    p=settings(config.get('preservation'));container=config.get('container','mp4');rows=[];issues=[]
    for kind,key in [('audio','audioTracks'),('subtitle','subtitleTracks')]:
        chosen=selected(item,kind,p[key]);count=len([s for s in item.get('streams',[]) if s['type']==kind])
        if p[key]!='all' and (kind!='subtitle' or p['subtitles']!='none') and any(index>=count for index in p[key]):issues.append(f"{item['name']}: a selected {kind} track is missing. Review track selections before queueing.")
        for ordinal,s in enumerate(s for s in item.get('streams',[]) if s['type']==kind):
            include=s in chosen and (kind!='subtitle' or p['subtitles']!='none') and (kind!='audio' or config.get('audio')!='none')
            treatment=('pcm_s24le' if config.get('qualityMode') in ('archive','proxy') else config.get('audio','aac')) if kind=='audio' else p['subtitles'];status='Not included'
            if include:
                status='Copy original' if treatment=='copy' else 'Encode as '+('timed text' if treatment=='text' else treatment.upper())
                if kind=='subtitle':
                    if container=='mp4' and treatment=='copy' and s['codec']!='mov_text':issues.append('MP4 cannot copy '+s['codec']+' subtitles. Choose MKV, convert text subtitles, or exclude them.')
                    if container=='webm' and (treatment!='copy' or s['codec']!='webvtt'):issues.append('WebM subtitle output supports copied WebVTT only. Choose MKV for these subtitles.')
                    if treatment=='text' and (container!='mp4' or s['codec'] not in TEXT):issues.append('Text subtitle conversion requires text subtitles and MP4. Image subtitles require a compatible container.')
                    if treatment=='text' and s['codec'] in ('ass','ssa'):status+=' · Styling will be lost'
                elif treatment=='copy' and container in ('mp4','mov') and s['codec'] in ('flac','opus','vorbis'):issues.append(s['codec'].upper()+' audio cannot be preserved in this output configuration. Choose MKV or an audio encoder.')
            rows.append({**s,'ordinal':ordinal,'included':include,'output':status})
    return {'name':item['name'],'path':item['path'],'streams':rows,'issues':list(dict.fromkeys(issues)),'conversions':conversion_notes(item,config),'color':{k:item.get(k,'') for k in ('pixel_format','color_space','color_transfer','color_primaries','color_range')},'conversions':conversion_notes(item,config),'chapters':len(item.get('chapters',[])),'recordingDate':item.get('metadataTags',{}).get('creation_time','Not reported')}

def command(command,item,config):
    if not config.get('preservation'):return command
    p=settings(config['preservation']);details=summary(item,config)
    if details['issues']:raise ValueError(' '.join(details['issues']))
    result=[];i=0
    while i<len(command):
        if command[i] in ('-map','-map_metadata','-map_metadata:s','-map_chapters','-c:s') or command[i].startswith('-disposition:'):
            i+=2;continue
        result.append(command[i]);i+=1
    output=result.pop();result+=['-map','0:'+str(item['videoIndex']) if type(item.get('videoIndex')) is int else '0:v:0']
    if config.get('audio','aac')!='none':
        if p['audioTracks']=='all':result+=['-map','0:a?']
        else:
            for index in dict.fromkeys(p['audioTracks']):result+=['-map',f'0:a:{index}?']
    if p['subtitles']!='none':
        if p['subtitleTracks']=='all':result+=['-map','0:s?']
        else:
            for index in dict.fromkeys(p['subtitleTracks']):result+=['-map',f'0:s:{index}?']
        result+=['-c:s','mov_text' if p['subtitles']=='text' else 'copy']
    result+=['-map_metadata','0' if p['metadata'] else '-1','-map_chapters','0' if p['chapters'] else '-1']
    if not p['metadata']:result+=['-map_metadata:s','-1']
    if p['metadata']:
        for kind,key,letter in [('audio','audioTracks','a'),('subtitle','subtitleTracks','s')]:
            if kind=='audio' and config.get('audio')=='none':continue
            if kind=='subtitle' and p['subtitles']=='none':continue
            for index,stream in enumerate(selected(item,kind,p[key])):
                allowed={'default','forced','original','comment','dub','hearing_impaired','visual_impaired','clean_effects','lyrics','karaoke'}
                flags='+'.join(k for k,v in stream.get('disposition',{}).items() if v and k in allowed)
                result += [f'-disposition:{letter}:{index}',flags or '0']
    if p['color'] and config.get('codec')!='prores':
        if item.get('color_transfer','') in ('smpte2084','arib-std-b67') and config.get('codec')=='h264':raise ValueError('HDR preservation requires HEVC, AV1 or an appropriate ProRes profile. Automatic HDR-to-SDR conversion is not enabled.')
        for key,flag in [('color_space','-colorspace'),('color_transfer','-color_trc'),('color_primaries','-color_primaries'),('color_range','-color_range')]:
            if item.get(key) not in (None,'','unknown','unspecified'):result += [flag,item[key]]
        if config.get('qualityMode')!='proxy' and any(v in item.get('pixel_format','') for v in ('10','12','16')) and config.get('codec') in ('hevc','av1'):
            if '-pix_fmt' in result:result[result.index('-pix_fmt')+1]='yuv420p10le'
    return result+[output]


def pixel_format(item,config):
    if config.get('mode') in ('copy','move') or config.get('qualityMode')=='original':return item.get('pixel_format')
    if config.get('qualityMode')=='archive' or config.get('codec')=='prores':
        import prores
        result=prores.resolve(item,config)
        return ('yuva444p10le' if result.get('alpha') else 'yuv444p10le') if result['profileNumber']>=4 else 'yuv422p10le'
    if config.get('qualityMode')=='proxy':return 'yuv422p10le' if config.get('proxyCodec','prores')=='prores' else 'yuv420p'
    high=settings(config.get('preservation'))['color'] and any(v in item.get('pixel_format','') for v in ('10','12','16')) and config.get('codec') in ('hevc','av1')
    return 'yuv420p10le' if high else 'yuv420p'


def conversion_notes(item,config):
    before=item.get('pixel_format');after=pixel_format(item,config)
    if not before or not after or before==after:return []
    return [f'Pixel format: {before} → {after}. Bit depth, color sampling or alpha may change. Choose an appropriate ProRes profile to retain supported source precision.']
