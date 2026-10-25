"""Offline acknowledged serial trials. Fake replies are NOT physical motor data."""
import sys
import unittest
from collections import deque
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vspa_protocol as p

class FakeSerial:
    def __init__(self,port=None,**kwargs):
        self.commands=[]
        self.rx=deque()
    def reset_input_buffer(self): self.rx.clear()
    def write(self,data):
        command=data.decode('ascii').strip();self.commands.append(command)
        if command=='PING':self.rx.append(b'READY,VSPA_PE_RTP_1.5,mask=11111\n')
        if command.startswith('PLAY,'):
            _,channel,duration,level=command.split(',')
            self.rx.append(f'START,{channel},{duration},{level}\n'.encode('ascii'))
            self.rx.append(f'DONE,{channel},{duration}\n'.encode('ascii'))
        return len(data)
    def flush(self):pass
    def readline(self):return self.rx.popleft() if self.rx else b''
    def close(self):pass

class SerialTimingTests(unittest.TestCase):
    def test_both_gap_conditions_drive_unchanged_command(self):
        config=p.ProtocolConfig(stimulus_duration_ms=100,baseline_pair_gap_sec=0.6,long_pair_gap_sec=0.9)
        # For the mocked 100-ms pulse, the safety minimum is 0.6 sec.
        config.validate()
        device=p.HapticDevice('ok',False,serial_factory=FakeSerial)
        device.RESET_WAIT_SEC=0
        device.connect()
        for interval in (0.6,0.9):
            actual=replace(config,adjacent_pair_gap_sec=interval)
            records=[]
            device.stimulate(('ring','middle'),actual,records)
            self.assertEqual(len(records),2)
            self.assertEqual([r.command for r in records],['PLAY,1,100,48','PLAY,2,100,48'])
            self.assertAlmostEqual(records[1].host_command_time-records[0].host_command_time,interval,delta=.20)
            self.assertTrue(all(r.start_reply.startswith('START,') and r.done_reply.startswith('DONE,') for r in records))
        device.close()

if __name__=='__main__':unittest.main()
