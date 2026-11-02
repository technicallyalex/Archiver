from pathlib import Path
import tempfile,shutil,unittest
import app,prores

class ProresProfileTests(unittest.TestCase):
 def item(self,pixel):return dict(pixel_format=pixel,width=1920,height=1080,duration=60,fps=30)
 def test_auto_and_preference(self):
  for pixel,expected in [('yuv420p','standard'),('yuv422p10le','hq'),('yuv420p10le','hq'),('yuv444p','4444'),('rgba','4444'),('yuva444p10le','4444')]:
   self.assertEqual(prores.resolve(self.item(pixel),{})['profile'],expected)
  self.assertEqual(prores.resolve(self.item('yuv420p'),{'proresPreferFidelity':True})['profile'],'hq')
 def test_explicit_profiles_and_unsupported_sources(self):
  for profile in prores.PROFILES:self.assertEqual(prores.resolve(self.item('yuv420p'),{'proresProfile':profile})['profile'],profile)
  for item,settings in [(self.item('yuv444p12le'),{}),({**self.item('yuv420p10le'),'color_transfer':'smpte2084'},{}),(self.item('rgba'),{'proresProfile':'hq'}),(self.item('yuv420p'),{'proresProfile':'bad'})]:
   with self.assertRaises(ValueError):prores.resolve(item,settings)
 @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
 def test_native_profiles_alpha_and_rgb(self):
  app.configure(shutil.which('ffmpeg'),shutil.which('ffprobe'))
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for pixel,profile in [('yuv420p','proxy'),('yuv420p','lt'),('yuv420p','standard'),('yuv422p10le','hq'),('yuv444p10le','4444'),('yuva444p10le','4444xq'),('gbrp','auto')]:
    source=root/(pixel+'-'+profile+'.mkv');target=source.with_suffix('.mov')
    source_filter=f'color=c=red@0.35:size=96x64:rate=12:duration=1,format={pixel}' if pixel.startswith('yuva') else f'testsrc2=size=96x64:rate=12:duration=1,format={pixel}'
    result=app.run([app.STATE['ffmpeg'],'-v','error','-f','lavfi','-i',source_filter,'-c:v','ffv1',str(source)])
    self.assertEqual(result.returncode,0,result.stderr)
    item=app.probe(source);settings=dict(qualityMode='archive',archiveProfile='prores',proresProfile=profile,sourceMetadata=item)
    result=app.run(app.archive_command(source,target,settings));self.assertEqual(result.returncode,0,result.stderr)
    output=app.probe(target);resolved=prores.resolve(item,settings)
    self.assertEqual('444' in output['pixel_format'],resolved['profileNumber']>=4)
    if resolved['alpha']:
     self.assertTrue(output['pixel_format'].startswith('yuva'))
     alpha=root/'alpha.raw';r=app.run([app.STATE['ffmpeg'],'-v','error','-y','-i',str(target),'-vf','alphaextract','-frames:v','1','-pix_fmt','gray','-f','rawvideo',str(alpha)])
     self.assertEqual(r.returncode,0,r.stderr);values=alpha.read_bytes();self.assertGreater(min(values),70);self.assertLess(max(values),110)
    app.verify_archive({'settings':settings,'cancel':False},target)
