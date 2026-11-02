import io,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import app,sample_preview


class NativePreviewTests(unittest.TestCase):
    def test_expanded_selection_does_not_reuse_old_index_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'thumbnails').mkdir();(root/'thumbnails/sample-0-source-timing.mp4').write_bytes(b'old clip')
            job={'id':'known','source':'source.mp4','outputDirectory':directory,'status':'running','cancel':False,'progress':{'sampleWindows':[{'start':40.,'duration':8.}]}}
            h=object.__new__(app.Handler);h.path='/api/test-sample-preview?id=known&sample=0&start=40';h.server=SimpleNamespace(server_port=9900);h.headers={'Host':'127.0.0.1:9900','X-Token':app.TOKEN};h.send_preview=Mock();h.send=Mock()
            def create(ffmpeg,source,target,start,length,*args):Path(target).write_bytes(b'new clip')
            with patch.object(app,'TEST_JOBS',[job]),patch.object(sample_preview,'create',side_effect=create) as encode:
                h.do_GET();encode.assert_called_once();self.assertEqual(h.send_preview.call_args.args[0].read_bytes(),b'new clip')
                h.path='/api/test-sample-preview?id=known&sample=0&start=10';h.do_GET();self.assertEqual(h.send.call_args.args[1],409)
    def test_source_route_supports_range_and_requires_known_job(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.mp4';source.write_bytes(b'0123456789')
            job={'id':'known','source':str(source),'progress':{'nativePreview':{'mime':'video/mp4; codecs="avc1"'}}}
            h=object.__new__(app.Handler);h.path='/api/test-source-preview?id=known';h.server=SimpleNamespace(server_port=9900);h.headers={'Host':'127.0.0.1:9900','X-Token':app.TOKEN,'Range':'bytes=2-5'};h.wfile=io.BytesIO();codes=[];headers={}
            h.send_response=codes.append;h.send_header=lambda k,v:headers.update({k:v});h.end_headers=lambda:None
            with patch.object(app,'TEST_JOBS',[job]),patch.object(sample_preview,'create') as encode:
                h.do_GET();self.assertEqual(h.wfile.getvalue(),b'2345');self.assertEqual(codes,[206]);self.assertEqual(headers['Content-Type'],'video/mp4');encode.assert_not_called()
                h.path='/api/test-source-preview?id=missing';h.send=Mock();h.do_GET();self.assertEqual(h.send.call_args.args[1],404)

    def test_preparing_stills_never_encodes_loop_proxies(self):
        with tempfile.TemporaryDirectory() as directory:
            job={'outputDirectory':directory,'cancel':False}
            def run(args,**kwargs):Path(args[-1]).write_bytes(b'jpeg')
            with patch.object(app.Analyzer,'run',side_effect=run),patch.object(sample_preview,'create') as encode:
                app.prepare_test_previews(job,{'path':'source','duration':60},[{'start':10,'duration':8}])
                encode.assert_not_called()
                self.assertTrue((Path(directory)/'thumbnails/14.jpg').exists())

    def test_mime_and_frame_branch_leave_primary_output_untouched(self):
        self.assertEqual(sample_preview.native_mime({'path':'a.mp4','codec':'h264'}),'video/mp4; codecs="avc1"')
        self.assertIn('webm',sample_preview.native_mime({'path':'a.webm','codec':'av1'}))
        cmd=['ffmpeg','-i','in','-vf','scale=1920:1080','-c:v','av1_nvenc','out.mp4']
        result=app.encoding_preview_command(cmd,'preview.jpg')
        self.assertEqual(result[:len(cmd)],cmd);self.assertEqual(result.count('-i'),1)
        self.assertIn('-atomic_writing',result)

    def test_selected_preview_preparation_can_use_idle_hardware(self):
        for stage,expected in [('sample-previews',['h264_nvenc']),('search-scoring',())]:
            with tempfile.TemporaryDirectory() as directory:
                job={'id':'known','source':'source.mp4','outputDirectory':directory,'status':'running','cancel':False,'progress':{'stage':stage,'sampleWindows':[{'start':0.,'duration':2.}]}}
                h=object.__new__(app.Handler);h.path='/api/test-sample-preview?id=known&sample=0&start=0';h.server=SimpleNamespace(server_port=9900);h.headers={'Host':'127.0.0.1:9900','X-Token':app.TOKEN};h.send_preview=Mock();h.send=Mock()
                def create(ffmpeg,source,target,*args):Path(target).write_bytes(b'preview')
                with patch.object(app,'TEST_JOBS',[job]),patch.object(app,'PROCESSES',{}),patch.dict(app.STATE,{'encoders':['h264_nvenc']}),patch.object(sample_preview,'create',side_effect=create) as encode:
                    h.do_GET();self.assertEqual(encode.call_args.args[-1],expected)
