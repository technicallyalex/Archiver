"""Quality subprocesses must not inherit invalid handles from the tray launcher."""
import ctypes,json,os,subprocess,sys,unittest
from pathlib import Path

@unittest.skipUnless(os.name=='nt','Windows standard handles')
class WindowlessQualityTests(unittest.TestCase):
 def test_invalid_inherited_input_does_not_break_validation(self):
  code=r"""
import ctypes,json,sys
from quality import Analyzer
k=ctypes.windll.kernel32;k.GetStdHandle.restype=ctypes.c_void_p;k.SetStdHandle.argtypes=[ctypes.c_ulong,ctypes.c_void_p]
old=k.GetStdHandle(-10);k.SetStdHandle(ctypes.c_ulong(-10),ctypes.c_void_p(-1))
try:
 output=Analyzer('','',None,lambda:False,lambda _:None).run([sys.executable,'-c','print("validation child ready")'])
 print(json.dumps({'output':output.strip()}))
finally:k.SetStdHandle(ctypes.c_ulong(-10),old)
"""
  p=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],stdin=subprocess.DEVNULL,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
  self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['output'],'validation child ready')
