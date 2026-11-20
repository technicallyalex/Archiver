"""Saved output configurations without source or test-report references."""
import secrets,threading,json
import tool_config
import preservation
LOCK=threading.RLock()
FIELDS=set('outputCodec codec abCodec sourceCodec encodingMode hardwareBackend encoder container audio audioBitrate resolution fps bitrate qualityValue customBitrate mode destination replacementTempDirectory filenameTemplate qualityMode proresProfile archiveProfile encoderPriority testedEncoder xpsnrTarget sourcePreset outputPreset proxyCodec proxyScale proxyLocation naming nameSuffix batchName'.split())
def path():return tool_config.user_config().with_name('output-presets.json')
def settings(value):
 if not isinstance(value,dict):raise ValueError('Invalid output settings')
 result={}
 for key,item in value.items():
  if key=='preservation':result[key]=preservation.settings(item)
  elif key=='proresPreferFidelity':
   if not isinstance(item,bool):raise ValueError('Invalid preset checkbox')
   result[key]=item
  elif key in FIELDS:
   if not isinstance(item,str) or len(item)>(4096 if key=='destination' else 1024):raise ValueError('Invalid preset setting: '+key)
   result[key]=item
 if result.get('qualityMode') not in ('auto','source','custom','archive','proxy'):raise ValueError('Choose a quality mode before saving')
 if result.get('outputCodec') not in ('h264','hevc','av1','prores'):raise ValueError('Choose an output codec before saving')
 if result.get('proxyLocation','subfolder') not in ('subfolder','next-to','custom'):raise ValueError('Invalid proxy output location')
 if result.get('mode','preserve') not in ('preserve','directory','overwrite'):raise ValueError('Invalid save-output action')
 return result
def load():
 with LOCK:
  try:data=json.loads(path().read_text(encoding='utf-8-sig')) if path().exists() else {}
  except (OSError,ValueError):raise ValueError('Saved presets could not be read; the file was not changed') from None
  if not isinstance(data,dict):raise ValueError('Saved presets could not be read')
  rows=data.get('presets',[])
  if not isinstance(rows,list):raise ValueError('Saved presets could not be read')
  result=[]
  for row in rows:
   if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not isinstance(row.get('name'),str):raise ValueError('Saved presets could not be read')
   result.append({'id':row['id'],'name':row['name'],'settings':settings(row.get('settings'))})
  default=data.get('defaultId','')
  if not isinstance(default,str) or default not in {r['id'] for r in result}:default=''
  return {'version':1,'presets':result,'defaultId':default}
def change(data):
 if not isinstance(data,dict):raise ValueError('Invalid preset request')
 with LOCK:
  current=load();rows=current['presets'];action=data.get('action');preset_id=data.get('id')
  existing=next((r for r in rows if r['id']==preset_id),None)
  if preset_id not in (None,'') and existing is None:raise ValueError('This preset no longer exists. Reload the presets.')
  if action not in ('save','rename','delete','set-default'):raise ValueError('Unknown preset action')
  if action in ('rename','delete') and existing is None:raise ValueError('Select a preset first')
  if action=='set-default':current['defaultId']=preset_id or ''
  elif action=='delete':
   rows.remove(existing)
   if current['defaultId']==preset_id:current['defaultId']=''
  else:
   name=data.get('name',existing['name'] if existing else '')
   if not isinstance(name,str) or not name.strip() or len(name.strip())>80:raise ValueError('Enter a preset name from 1 to 80 characters')
   name=name.strip()
   if any(r is not existing and r['name'].casefold()==name.casefold() for r in rows):raise ValueError('A preset with this name already exists')
   if action=='rename':existing['name']=name
   else:
    value=settings(data.get('settings'))
    if existing:existing.update(name=name,settings=value)
    else:
     if len(rows)>=100:raise ValueError('Save up to 100 output presets')
     existing={'id':secrets.token_hex(8),'name':name,'settings':value};rows.append(existing)
  tool_config.write_json(path(),current)
  return {**current,'selectedId':existing['id'] if existing and action!='delete' else ''}

def portable_export(preset_id):
 row=next((r for r in load()['presets'] if r['id']==preset_id),None)
 if not row:raise ValueError('Select a saved preset to export')
 value=dict(row['settings']);value.pop('destination',None);value.pop('replacementTempDirectory',None)
 if value.get('proxyLocation')=='custom':value['proxyLocation']='subfolder'
 notes=[]
 if value.get('mode') in ('directory','overwrite'):value['mode']='preserve';notes.append('Output location and replacement action reset to Keep originals.')
 if value.get('testedEncoder'):
  value.update(qualityMode='auto',testedEncoder='');value.pop('qualityValue',None);notes.append('Measured CQ/CRF result removed. Run a new quality test.')
 return {'schema':'archiver.output-preset','version':1,'name':row['name'],'settings':value,'notes':notes}

def portable_import(document):
 if not isinstance(document,dict) or document.get('schema')!='archiver.output-preset' or document.get('version')!=1:raise ValueError('Choose an Archiver preset file with a supported version')
 if not isinstance(document.get('name'),str) or not 1<=len(document['name'].strip())<=80:raise ValueError('Invalid preset name')
 raw=document.get('settings')
 if not isinstance(raw,dict):raise ValueError('Invalid preset settings')
 raw={**raw,'mode':'preserve','destination':''};raw.pop('testedEncoder',None);raw.pop('replacementTempDirectory',None)
 if raw.get('proxyLocation')=='custom':raw['proxyLocation']='subfolder'
 if raw.get('bitrate') in ('cq','icq'):raw.update(qualityMode='auto');raw.pop('qualityValue',None)
 return {'name':document['name'].strip(),'settings':settings(raw)}


def override_encoder(config,encoder):
 software=encoder.startswith(('lib','prores'))
 previous=config.get('encoder')
 config.update(encoder=encoder,encodingMode='software' if software else 'hardware',hardwareBackend=next((v for v in ('nvenc','qsv','amf') if encoder.endswith('_'+v)),'nvenc'),testedEncoder='')
 if previous!=encoder:
  # Quality numbers and speed presets are encoder-specific; never translate them silently.
  config.pop('qualityValue',None);config.pop('encoderPriority',None)
  if config.get('outputCodec')=='prores':config.update(qualityMode='archive',archiveProfile='prores')
  elif config.get('qualityMode')=='custom' and config.get('bitrate') not in ('custom','source'):
   config.update(qualityMode='auto',bitrate='crf' if software else 'cqp')
 return config
