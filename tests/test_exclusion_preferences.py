import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import exclusion_preferences as prefs
class ExclusionPreferenceTests(unittest.TestCase):
 def test_saved_entries_states_and_removal_survive_reload(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(prefs,'path',return_value=Path(tmp)/'prefs.json'):
   initial=prefs.load();self.assertEqual(initial['custom'],[]);self.assertTrue(initial['testFolders'])
   prefs.save({**initial,'custom':[{'name':' Low Res ','enabled':False},{'name':'Previews','enabled':True}],'proxyFolders':False})
   self.assertEqual(prefs.load()['custom'],[{'name':'Low Res','enabled':False},{'name':'Previews','enabled':True}]);self.assertFalse(prefs.load()['proxyFolders'])
   prefs.save({**prefs.load(),'custom':[]});self.assertEqual(prefs.load()['custom'],[])
 def test_names_are_validated_and_duplicates_case_insensitive(self):
  for custom in [[{'name':'../bad'}],[{'name':'Proxy'}],[{'name':'Low Res'},{'name':'low res'}],[{'name':'x','enabled':'yes'}],[{'name':'name'+str(i)} for i in range(31)]]:
   with self.subTest(custom=custom),self.assertRaises(ValueError):prefs.validate({'custom':custom,'proxyFolders':True})
 def test_corrupt_preferences_fall_back_to_defaults(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(prefs,'path',return_value=Path(tmp)/'prefs.json'):
   prefs.path().write_text('{bad');self.assertEqual(prefs.load(),prefs.validate({}))

 def test_legacy_proxy_choices_and_custom_names_migrate(self):
  for first,second in [(False,False),(True,False),(False,True),(True,True)]:
   self.assertEqual(prefs.validate({'proxy':first,'proxies':second})['proxyFolders'],first or second)
  migrated=prefs.validate({'proxy':False,'proxies':False,'custom':[{'name':'Proxy Media','enabled':True},{'name':'Low Res','enabled':False}]})
  self.assertTrue(migrated['proxyFolders']);self.assertEqual(migrated['custom'],[{'name':'Low Res','enabled':False}])
  self.assertFalse(prefs.validate({'proxy':False,'proxies':False,'custom':[{'name':'Proxy Media','enabled':False}]})['proxyFolders'])
  self.assertEqual(prefs.validate({'proxyFolderNames':['unsafe']})['proxyFolderNames'],['Proxy','Proxies','Proxy Media','Final Cut Proxy Media'])
