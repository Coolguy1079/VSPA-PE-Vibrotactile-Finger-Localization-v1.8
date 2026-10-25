"""Offline v1.8 regressions: synthetic/mock data are NOT physical or participant data."""
import sys
import csv
import tempfile
import hashlib
import random
import unittest
from pathlib import Path
from collections import Counter
from dataclasses import asdict, replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vspa_protocol as p
from analyze_timing import analyze

class TimingProtocolTests(unittest.TestCase):
    def test_1000_random_seeds_have_exact_balance(self):
        for seed in range(1000):
            trials=p.build_schedule(seed,p.ProtocolConfig())
            self.assertEqual(len(trials),80)
            counts=Counter((t.fingers,t.timing_condition) for t in trials)
            self.assertEqual(counts,Counter({(pair,cond):5 for pair in p.ORDERED_ADJACENT_PAIRS
                                              for cond in ('baseline_2p0s','long_4p0s')}))
            for block in range(1,11):
                br=[t for t in trials if t.block_number==block]
                self.assertEqual(len(br),8)
                self.assertEqual(Counter(t.timing_condition for t in br),
                                 Counter({'baseline_2p0s':4,'long_4p0s':4}))
                self.assertEqual({t.fingers for t in br},set(p.ORDERED_ADJACENT_PAIRS))
                for t in br:
                    self.assertEqual(t.pair_gap_sec,2.0 if t.timing_condition=='baseline_2p0s' else 4.0)
    def test_seed_reconstructibility(self):
        c=p.ProtocolConfig()
        self.assertEqual(p.schedule_hash(p.build_schedule(2026,c)),p.schedule_hash(p.build_schedule(2026,c)))
        self.assertNotEqual(p.schedule_hash(p.build_schedule(2026,c)),p.schedule_hash(p.build_schedule(2027,c)))
    def test_invalid_comparisons_and_optional_singles(self):
        for kwargs in [{'pair_rounds':9},{'baseline_pair_gap_sec':1.4},
                       {'baseline_pair_gap_sec':4.0},{'long_pair_gap_sec':1.5},
                       {'baseline_pair_gap_sec':float('nan')}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):p.build_schedule(2026,replace(p.ProtocolConfig(),**kwargs))
        schedule=p.build_schedule(2026,replace(p.ProtocolConfig(),run_single=True,single_rounds=1))
        self.assertEqual(len(schedule),90)
        self.assertEqual(sum(t.orientation for t in schedule),5)
    def test_source_firmware_and_serial_transport_unchanged(self):
        here=Path(__file__).resolve().parents[1]
        self.assertEqual(hashlib.sha256((here/'firmware/firmware_vspa_rtp_v1_5/firmware_vspa_rtp_v1_5.ino').read_bytes()).hexdigest(),
                         '80ed2073bf716c7eb4119e36874482bf187c2f0f37aabadc7f22a3d2b9b1bea0')
        old=(here/'baseline_v1_6/vspa_protocol.py').read_text()
        new=(here/'vspa_protocol.py').read_text()
        def get_class(s): return s[s.index('class HapticDevice:'):s.index('\n\nTRIAL_FIELDS',s.index('class HapticDevice:'))]
        self.assertEqual(get_class(old),get_class(new))
        self.assertEqual(p.ProtocolConfig().rtp_drive_value,48)
        self.assertEqual(p.ProtocolConfig().stimulus_duration_ms,1000)
    def test_row_has_correct_condition_and_gap(self):
        config=p.ProtocolConfig()
        short=next(t for t in p.build_schedule(2026,config) if t.pair_gap_sec==2.0)
        c=replace(config,adjacent_pair_gap_sec=short.pair_gap_sec)
        expected=p.score_response(short.fingers,list(short.fingers))
        chan1=p.CHANNEL_MAP[short.fingers[0]];chan2=p.CHANNEL_MAP[short.fingers[1]]
        a=p.PulseRecord(short.fingers[0],chan1,f'PLAY,{chan1},1000,48',10,10.001,f'START,{chan1},1000,48',10.04,f'DONE,{chan1},1000',11.01,1000)
        b=p.PulseRecord(short.fingers[1],chan2,f'PLAY,{chan2},1000,48',12.0,12.001,f'START,{chan2},1000,48',12.04,f'DONE,{chan2},1000',13.01,1000)
        keys=[p.KEY_MAP[f] for f in short.fingers]
        r=p.make_trial_row(short,c,[a,b],keys,[13.49,13.8],13.4,'complete','completed',True,False)
        self.assertEqual(r['timing_condition'],'baseline_2p0s')
        self.assertEqual(r['requested_pair_gap_sec'],2.0)
        self.assertEqual(r['actual_pair_gap_sec'],2.0)
        self.assertTrue(r['was_correct'])
        self.assertEqual(r['schema_version'],'1.8.0')
        self.assertEqual(r['confounding_or_spread_report'],True)
    def test_datastore_persists_condition_and_empty_summary(self):
        with tempfile.TemporaryDirectory() as d:
            config=p.ProtocolConfig()
            schedule=p.build_schedule(11,config)
            ds=p.DataStore(Path(d),'SELFTEST',11,config,schedule,True)
            with (ds.output_dir/'schedule.csv').open() as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),80)
            ds.finish('stopped')
            with (ds.output_dir/'timing_condition_summary.csv').open() as handle:
                summaries=list(csv.DictReader(handle))
            with (ds.output_dir/'timing_by_ordered_pair.csv').open() as handle:
                pairs=list(csv.DictReader(handle))
            self.assertEqual(len(summaries),2);self.assertEqual(len(pairs),16)
            self.assertTrue(all(int(row['planned_trials'])==40 for row in summaries))
            self.assertTrue(all(int(row['planned_trials'])==5 for row in pairs))
            self.assertTrue(all(row['accuracy']=='' for row in summaries))
            self.assertEqual(ds.metadata['planned_trial_count'],80)
    def test_analysis_rejects_simulation(self):
        with tempfile.TemporaryDirectory() as d:
            conf=p.ProtocolConfig();schedule=p.build_schedule(1,conf)
            ds=p.DataStore(Path(d),'SELFTEST',1,conf,schedule,True);ds.finish('completed')
            with self.assertRaises(ValueError):analyze(Path(d),Path(d)/'analysed')

if __name__=='__main__':unittest.main(verbosity=2)
