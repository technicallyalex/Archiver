import unittest
import app
class FilenameTemplates(unittest.TestCase):
 def setUp(self):
  self.item=dict(path='C:/Footage/Clip.mov',width=2560,height=1440,fps=60)
  self.settings=dict(naming='template',filenameTemplate='{original}_{resolution}_{codec}',mode='preserve',codec='av1',container='mp4',qualityMode='custom',bitrate='cq',qualityValue='35')
 def test_order_and_quality(self):
  self.assertEqual(app.output_name(self.item,self.settings),'Clip_2560x1440_AV1.mp4')
  self.assertEqual(app.output_name(self.item,{**self.settings,'filenameTemplate':'{codec}_{original}_{quality}_{sequence}'},2),'AV1_Clip_cq-35_002.mp4')
 def test_preserve_guard(self):
  with self.assertRaisesRegex(ValueError,'Original name'):app.output_name(self.item,{**self.settings,'filenameTemplate':'custom'})
 def test_directory_and_custom(self):
  self.assertEqual(app.output_name(self.item,{**self.settings,'mode':'directory','filenameTemplate':'Capture_{sequence}'},3),'Capture_003.mp4')
 def test_invalid(self):
  for template in ['{original}/{codec}','{original}_{unknown}','{original}_bad?','{original}_{','{original}_'+'a'*250]:
   with self.subTest(template=template),self.assertRaises(ValueError):app.output_name(self.item,{**self.settings,'filenameTemplate':template})
 def test_archive(self):
  self.assertEqual(app.output_name(self.item,{**self.settings,'qualityMode':'archive','archiveProfile':'prores'}),'Clip_2560x1440_ProRes.mov')
 def test_archiver_tag_and_preserve_fallback(self):
  self.assertEqual(app.output_name(self.item,{**self.settings,'filenameTemplate':'{original}_{archiver}'}),'Clip_archiver.mp4')
  self.assertEqual(app.output_name(self.item,{**self.settings,'filenameTemplate':'{original}'}),'Clip_archiver.mp4')
  self.assertEqual(app.output_name(self.item,{**self.settings,'filenameTemplate':'{original}_'}),'Clip_archiver.mp4')
  self.assertEqual(app.output_name(self.item,{**self.settings,'filenameTemplate':'{original}_{codec}'}),'Clip_AV1.mp4')
  self.assertEqual(app.output_name(self.item,{**self.settings,'filenameTemplate':'{original}_custom'}),'Clip_custom.mp4')
  self.assertEqual(app.output_name(self.item,{**self.settings,'filenameTemplate':'{original}','mode':'directory'}),'Clip.mp4')
if __name__=='__main__':unittest.main()
