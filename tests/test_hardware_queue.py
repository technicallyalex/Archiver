import unittest
from unittest.mock import Mock
from hardware_queue import Admission,hardware_key,session_exhausted


def job(encoder='av1_nvenc'):
    return {'encodedSeconds':0,'settings':{'encoder':encoder,'qualityMode':'custom','mode':'preserve','sourceMetadata':{'width':1920,'height':1080,'fps':60},'bitrate':'cq','qualityValue':30}}


class HardwareQueueTests(unittest.TestCase):
    def controller(self,**overrides):
        self.now=0
        data={'cpu':20,'sessionLimit':8,'sessions':1,'encoder':35,'decoder':20,'gpu':10,'freeMiB':8000,**overrides}
        return Admission(Mock(sample=lambda:data),clock=lambda:self.now)

    def feed(self,c,active,candidate,rate,start=0):
        for second in range(start,start+12):
            self.now=second
            for j in active:j['encodedSeconds']+=rate
            value=c.desired(active,candidate)
        return value

    def test_ramps_only_after_baseline_and_keeps_only_throughput_gain(self):
        c=self.controller();a,b=job(),job()
        self.assertEqual(c.desired([a],b),1)
        self.assertEqual(self.feed(c,[a],b,2),2)
        # Two encodes, each 2x: aggregate progress doubles.
        self.assertGreaterEqual(self.feed(c,[a,b],job(),2,12),2)

    def test_no_gain_downshifts_without_cancelling_active_work(self):
        c=self.controller();a,b=job(),job();self.feed(c,[a],b,2)
        self.assertEqual(self.feed(c,[a,b],job(),.9,12),1)
        self.assertIn(hardware_key(a),c.blocked)

    def test_busy_gpu_or_external_sessions_do_not_admit_more(self):
        for data in ({'encoder':95},{'cpu':95},{'freeMiB':200},{'sessions':8}):
            c=self.controller(**data);a=job()
            self.assertEqual(self.feed(c,[a],job(),2),1,data)
        c=self.controller(sessions=8)
        self.assertEqual(c.desired([],job()),0)
        c.busy(hardware_key(job()))
        self.assertEqual(c.desired([],job()),0)
        self.assertEqual(c.desired([],job(),False),0)

    def test_software_analysis_and_mixed_workloads_stay_serial(self):
        c=self.controller();a=job('libsvtav1')
        self.assertIsNone(hardware_key(a));self.assertEqual(self.feed(c,[a],job(),2),1)
        a=job();a['settings']['qualityMode']='perceptual'
        self.assertIsNone(hardware_key(a))
        a['testedAnalysis']={'winner':{'encoder':'av1_nvenc','bitrate':'cqp','qualityValue':30}}
        self.assertIsNotNone(hardware_key(a))
        a=job();b=job('h264_nvenc');self.assertEqual(self.feed(c,[a],b,2),1)

    def test_driver_backoff_and_user_disable(self):
        c=self.controller();a=job();c.busy(hardware_key(a))
        self.assertEqual(self.feed(c,[a],job(),2),1)
        self.assertEqual(c.desired([a],job(),False),1)
        self.assertTrue(session_exhausted(['OpenEncodeSessionEx failed: out of memory']))
        self.assertFalse(session_exhausted(['Invalid encoder argument']))
