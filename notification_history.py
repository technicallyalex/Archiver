"""Bounded local notification history, shared by worker threads and the UI."""
import json,os,secrets,threading,time,math
from pathlib import Path
import tool_config
LOCK=threading.RLock()
LIMIT=500
def path():return Path(os.environ['ARCHIVER_NOTIFICATION_FILE']) if os.environ.get('ARCHIVER_NOTIFICATION_FILE') else tool_config.user_config().with_name('notifications.json')
def _load():
 if not path().exists():return []
 try:data=json.loads(path().read_text(encoding='utf-8-sig'))
 except (OSError,ValueError):raise ValueError('Notification history could not be read') from None
 rows=data.get('items') if isinstance(data,dict) else None
 if not isinstance(rows,list):raise ValueError('Notification history could not be read')
 if any(not isinstance(r,dict) or not isinstance(r.get('id'),str) or not isinstance(r.get('title'),str) or not isinstance(r.get('message'),str) or r.get('level') not in ('info','success','error') or not isinstance(r.get('time'),(int,float)) or not math.isfinite(r['time']) for r in rows):raise ValueError('Notification history contains invalid entries')
 return rows[-LIMIT:]
def snapshot(revision=None):
 with LOCK:
  stamp=str(path().stat().st_mtime_ns) if path().exists() else 'empty'
  if revision==stamp:return {'unchanged':True,'revision':stamp}
  rows=_load();return {'items':list(reversed(rows)),'unread':sum(not r.get('read',False) for r in rows),'revision':stamp}
def add(title,message='',level='info',category='app',job_id='',key=''):
 if not isinstance(title,str) or not title.strip() or len(title)>200:raise ValueError('Invalid notification title')
 if not isinstance(message,str) or len(message)>4000 or level not in ('info','success','error'):raise ValueError('Invalid notification')
 with LOCK:
  rows=_load()
  old=next((r for r in rows if key and r.get('key')==key),None)
  if old:return old
  row={'id':secrets.token_hex(10),'title':title,'message':message,'level':level,'category':category,'jobId':job_id,'time':time.time(),'read':False,'key':key}
  rows.append(row);tool_config.write_json(path(),{'version':1,'items':rows[-LIMIT:]});return row
def change(action):
 with LOCK:
  rows=_load()
  if action=='read':
   for row in rows:row['read']=True
  elif action=='clear':rows=[]
  else:raise ValueError('Unknown notification action')
  tool_config.write_json(path(),{'version':1,'items':rows});return snapshot()
def queue_result(job,category):
 status=job.get('status')
 if status not in ('completed','failed','cancelled','skipped'):return
 label='Quality test' if category=='test' else 'Encoding'
 error=job.get('queueError') or job.get('error','')
 level='error' if status=='failed' or job.get('queueError') else 'success' if status=='completed' else 'info'
 title=label+({'completed':' complete','failed':' failed','cancelled':' cancelled','skipped':' skipped'}[status])
 if job.get('queueError'):title='Test complete · Encoding not queued'
 message=job.get('name') or Path(job.get('source','Video')).name
 if error:message+='\n'+str(error)[:3000]
 return add(title,message,level,category,job.get('id',''),category+':'+job.get('id','')+':'+status)
