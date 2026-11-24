from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
class Logos(HTMLParser):
 def __init__(self):super().__init__();self.depth=0;self.current=[];self.items=[]
 def handle_starttag(self,tag,attrs):
  if tag=='svg' and (self.depth or any(k=='class' and v in ('brand-wordmark','brand-monogram') for k,v in attrs)):self.depth+=1
  if self.depth:self.current.append(self.get_starttag_text())
 def handle_endtag(self,tag):
  if self.depth:self.current.append('</'+tag+'>')
  if tag=='svg' and self.depth:
   self.depth-=1
   if not self.depth:self.items.append(''.join(self.current));self.current=[]
 def handle_startendtag(self,tag,attrs):
  if self.depth:self.current.append(self.get_starttag_text())

def signature(node):return (node.tag.split('}')[-1],tuple(sorted(node.attrib.items())),tuple(signature(child) for child in node))
def pair(root):return next(e for e in root.iter() if e.get('data-brand-pair')=='ar')

class BrandAssetsTests(unittest.TestCase):
 def test_wordmark_compact_and_icon_share_identical_pair(self):
  canonical=ET.parse(ROOT/'web/assets/wordmark.svg').getroot();expected=signature(pair(canonical))
  parser=Logos();parser.feed((ROOT/'web/index.html').read_text(encoding='utf-8'));self.assertEqual(len(parser.items),3)
  for markup in parser.items:self.assertEqual(signature(pair(ET.fromstring(markup))),expected)
  self.assertEqual(signature(pair(ET.parse(ROOT/'web/assets/icon.svg').getroot())),expected)
  # Outlined standard lettering needs no platform font download/fallback.
  self.assertFalse(any(e.tag.split('}')[-1]=='text' for e in canonical.iter()))
 def test_windows_icon_includes_small_and_hidpi_png_images(self):
  data=(ROOT/'web/assets/archiver.ico').read_bytes();reserved,kind,count=struct.unpack_from('<HHH',data);self.assertEqual((reserved,kind),(0,1));sizes=[]
  for i in range(count):
   w,h,_,_,planes,bits,length,offset=struct.unpack_from('<BBBBHHII',data,6+i*16);w=w or 256;h=h or 256;sizes.append(w);self.assertEqual(w,h);self.assertEqual((planes,bits),(1,32));self.assertEqual(data[offset:offset+8],b'\x89PNG\r\n\x1a\n');self.assertLessEqual(offset+length,len(data))
  self.assertEqual(sizes,[16,24,32,48,64,128,256])
