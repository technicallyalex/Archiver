"""Conservative hardware admission, with measured aggregate-throughput feedback.

Session ceilings are not throughput targets. Drivers remain authoritative when
other applications race us for a session. No telemetry is sent off the machine.
"""
import ctypes
import os
import re
import shutil
import subprocess
import time


def hardware_key(job):
    s=job['settings'];encoder=s.get('encoder','')
    ready=job.get('testedAnalysis') or {}
    if ready.get('winner'):
        s={**s,**ready['winner']};encoder=s.get('encoder','')
    if not encoder.endswith(('_nvenc','_qsv','_amf')) or s.get('mode') in ('copy','move') or (s.get('qualityMode') not in ('custom','source','proxy') and not ready.get('winner')):
        return None
    m=s.get('sourceMetadata',{})
    if s.get('qualityMode')=='proxy':return (encoder,m.get('width'),m.get('height'),round(m.get('fps',0),2),'proxy',s.get('proxyScale','2'))
    return (encoder,m.get('width'),m.get('height'),round(m.get('fps',0),2),s.get('resolution','original'),s.get('fps','original'),s.get('bitrate'),s.get('encoderPriority'))


class Resources:
    def __init__(self):
        self.previous_cpu=None;self.cached={};self.updated=-100

    def cpu(self):
        if os.name!='nt':
            try:return min(100,os.getloadavg()[0]/max(1,os.cpu_count())*100)
            except OSError:return None
        values=[ctypes.c_ulonglong() for _ in range(3)]
        if not ctypes.windll.kernel32.GetSystemTimes(*(ctypes.byref(v) for v in values)):return None
        idle,kernel,user=(v.value for v in values);current=(idle,kernel+user);old=self.previous_cpu;self.previous_cpu=current
        if not old or current[1]<=old[1]:return None
        return max(0,min(100,100*(1-(current[0]-old[0])/(current[1]-old[1]))))

    def sample(self):
        if time.monotonic()-self.updated<2:return self.cached
        result={'cpu':self.cpu(),'sessionLimit':2,'sessions':None,'encoder':None,'decoder':None,'gpu':None,'freeMiB':None,'device':'Hardware encoder'}
        executable=shutil.which('nvidia-smi')
        if executable:
            try:
                p=subprocess.run([executable,'--query-gpu=name,driver_version,encoder.stats.sessionCount,utilization.encoder,utilization.decoder,utilization.gpu,memory.free','--format=csv,noheader,nounits'],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=2,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                devices=[]
                for line in p.stdout.splitlines():
                    parts=[s.strip() for s in line.split(',')]
                    if len(parts)==7:
                        devices.append((parts[0],parts[1],*[float(v) for v in parts[2:]]))
                if p.returncode==0 and devices:
                    # Stay below current published consumer ceilings. Older or
                    # unidentified drivers use two and can back off at runtime.
                    modern=all(int(d[1].split('.')[0])>=550 and re.search(r'RTX\s*[2345]\d{3}',d[0],re.I) for d in devices)
                    current=modern and all(int(d[1].split('.')[0])>=600 for d in devices)
                    result.update(device=devices[0][0],sessionLimit=12 if current else 8 if modern else 2,sessions=sum(d[2] for d in devices),encoder=max(d[3] for d in devices),decoder=max(d[4] for d in devices),gpu=max(d[5] for d in devices),freeMiB=min(d[6] for d in devices))
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
        self.cached=result;self.updated=time.monotonic();return result


def session_exhausted(log):
    text='\n'.join(log).lower()
    return any(s in text for s in ('too many concurrent','openencodesessionex failed','no encode device available','mfx_err_device_busy','amf_out_of_memory','encoder initialization failed: resource','cannot allocate memory','out of memory'))


class Admission:
    """One optional probing step at a time; never cancel useful work to downshift."""
    def __init__(self,resources=None,clock=time.monotonic):
        self.resources=resources or Resources();self.clock=clock;self.key=None;self.target=1;self.points=[];self.count=0;self.baseline=None;self.probing=False;self.blocked=set();self.blocked_resources=set()

    def busy(self,key):
        self.blocked_resources.add(key[0] if key else None);self.target=1

    def desired(self,active,candidate,parallel=True):
        key=hardware_key(candidate) if candidate else (hardware_key(active[0]) if active else None)
        if not key:return 1
        if self.key!=key:
            self.key=key;self.target=1;self.points=[];self.count=0;self.baseline=None;self.probing=False
        serial=not parallel or key in self.blocked or key[0] in self.blocked_resources
        if any(hardware_key(j)!=key for j in active):return 1
        now=self.clock();count=len(active)
        total=sum(j.get('encodedSeconds',0) for j in active)
        if count!=self.count:
            self.points=[];self.count=count
        self.points.append((now,total));self.points=[p for p in self.points if now-p[0]<=18]
        data=self.resources.sample()
        # Intel/AMD do not have a portable, reliable session-count query. Probe
        # at most two and rely on throughput plus driver-error backoff there.
        cap=data['sessionLimit'] if key[0].endswith('_nvenc') else 2
        if count==0:
            return 0 if key[0].endswith('_nvenc') and data.get('sessions') is not None and data['sessions']>=cap else 1
        if serial:return 1
        available=cap
        if key[0].endswith('_nvenc') and data.get('sessions') is not None:
            available=max(count,cap-max(0,int(data['sessions'])-count))
        self.target=min(self.target,max(1,available))
        enough=len(self.points)>1 and now-self.points[0][0]>=10
        if not enough:return self.target
        elapsed=now-self.points[0][0];rate=(total-self.points[0][1])/elapsed
        if rate<=0:return self.target
        if self.probing:
            if rate < self.baseline*1.08:
                self.target=max(1,count-1);self.blocked.add(key);self.probing=False
                return self.target
            self.baseline=rate;self.probing=False
        if count==self.target and candidate and count<available:
            headroom=all(data.get(k) is None or data[k]<80 for k in ('cpu','encoder','decoder','gpu')) and (data.get('freeMiB') is None or data['freeMiB']>768)
            if headroom and key[0] not in self.blocked_resources:
                self.baseline=rate;self.target=count+1;self.probing=True;self.points=[]
        return self.target
