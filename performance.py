"""On-demand system telemetry. Unavailable counters remain null."""
import csv
from io import StringIO
import shutil
import subprocess
import threading
import time

try:
    import psutil
except ImportError:
    psutil = None


class Monitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_request = 0
        self.sample = {'available': False, 'message': 'Waiting for the first sample', 'history': []}
        self.history = []
        self.started = False

    def read(self):
        with self.lock:
            self.last_request = time.monotonic()
            if not self.started:
                self.started = True
                threading.Thread(target=self.loop, daemon=True).start()
            return dict(self.sample)

    def loop(self):
        previous = None
        if psutil:
            psutil.cpu_percent()
        while True:
            if time.monotonic() - self.last_request > 6:
                previous = None
                time.sleep(1)
                continue
            try:
                if not psutil:
                    data = {'available': False, 'message': 'Install dependencies with: python -m pip install -r requirements.txt'}
                else:
                    now = time.monotonic()
                    disk = psutil.disk_io_counters()
                    net = psutil.net_io_counters()
                    memory = psutil.virtual_memory()
                    data = {'available': True, 'timestamp': time.time(), 'cpu': psutil.cpu_percent(), 'cores': psutil.cpu_count(), 'ram_percent': memory.percent, 'ram_used': memory.total-memory.available, 'ram_total': memory.total, 'read_rate': None, 'write_rate': None, 'disk_active': None, 'network_receive': None, 'network_send': None, 'gpus': []}
                    if previous:
                        stamp, old_disk, old_net = previous
                        elapsed = now-stamp
                        if disk and old_disk:
                            data.update(read_rate=max(0,(disk.read_bytes-old_disk.read_bytes)/elapsed), write_rate=max(0,(disk.write_bytes-old_disk.write_bytes)/elapsed))
                            if hasattr(disk, 'busy_time') and hasattr(old_disk, 'busy_time'):
                                data['disk_active'] = min(100,max(0,(disk.busy_time-old_disk.busy_time)/(elapsed*10)))
                        if net and old_net:
                            data.update(network_receive=max(0,(net.bytes_recv-old_net.bytes_recv)/elapsed), network_send=max(0,(net.bytes_sent-old_net.bytes_sent)/elapsed))
                    previous = now, disk, net
                    utility = shutil.which('nvidia-smi')
                    if utility:
                        result = subprocess.run([utility,'--query-gpu=name,utilization.gpu,utilization.encoder,utilization.decoder,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        if result.returncode == 0:
                            for row in csv.reader(StringIO(result.stdout)):
                                if len(row)!=6:
                                    continue
                                def number(text):
                                    try:
                                        return float(text.strip())
                                    except ValueError:
                                        return None
                                data['gpus'].append(dict(zip(['name','usage','encode','decode','memory_used','memory_total'],[row[0].strip(),*[number(value) for value in row[1:]]])))
                    self.history = [point for point in self.history if point['time'] > time.time()-120]
                    self.history.append({'time':time.time(),'cpu':data['cpu'],'ram':data['ram_percent'],'gpu':data['gpus'][0]['usage'] if data['gpus'] else None,'read':data['read_rate'],'write':data['write_rate']})
                    data['history'] = list(self.history)
                with self.lock:
                    self.sample = data
            except Exception as error:
                with self.lock:
                    self.sample = {'available':False,'message':str(error),'history':list(self.history)}
            time.sleep(2)


MONITOR = Monitor()
