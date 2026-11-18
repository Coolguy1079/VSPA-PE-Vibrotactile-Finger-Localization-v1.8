"""Offline acknowledged serial trials. Fake replies are NOT physical motor data."""
# Mock serial regression for command content and host command-gap scheduling.
# Shortened test-only pulse/gap values keep this check quick; production defaults
# remain 1000 ms, RTP 48 and 2.0/4.0 s. No physical Arduino or actuator is exercised.
import sys
import unittest
from collections import deque
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vspa_protocol as p

# Provide immediate software acknowledgements and a command ledger without opening a physical port.
class FakeSerial:
    # Initialize an empty outgoing-command list and incoming-reply queue for the fake transport.
    def __init__(self,port=None,**kwargs):
        self.commands=[]
        self.rx=deque()
    # Discard queued fake replies to model the host's startup input-buffer reset.
    def reset_input_buffer(self): self.rx.clear()
    # Record bytes and enqueue exact PING/PLAY replies; no actuator or physical delay is simulated.
    def write(self,data):
        command=data.decode('ascii').strip();self.commands.append(command)
        if command=='PING':self.rx.append(b'READY,VSPA_PE_RTP_1.5,mask=11111\n')
        if command.startswith('PLAY,'):
            _,channel,duration,level=command.split(',')
            self.rx.append(f'START,{channel},{duration},{level}\n'.encode('ascii'))
            self.rx.append(f'DONE,{channel},{duration}\n'.encode('ascii'))
        return len(data)
    # Implement the serial interface's flush hook; in-memory writes are already immediately available.
    def flush(self):pass
    # Return the next complete fake line or an empty read when the queue has no reply.
    def readline(self):return self.rx.popleft() if self.rx else b''
    # Implement the close interface without hardware resources to release.
    def close(self):pass

# Exercise acknowledged serial scheduling separately from physical timing or tactile performance.
class SerialTimingTests(unittest.TestCase):
    # Verify each test interval changes command spacing while preserving channel, pulse and RTP fields.
    def test_both_gap_conditions_drive_unchanged_command(self):
        config=p.ProtocolConfig(stimulus_duration_ms=100,baseline_pair_gap_sec=0.6,long_pair_gap_sec=0.9)
        # For the mocked 100-ms pulse, the safety minimum is 0.6 sec.
        config.validate()
        device=p.HapticDevice('ok',False,serial_factory=FakeSerial)
        device.RESET_WAIT_SEC=0
        device.connect()
        # Fake DONE is immediate; this tests host deadline spacing, not firmware or motor duration.
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
