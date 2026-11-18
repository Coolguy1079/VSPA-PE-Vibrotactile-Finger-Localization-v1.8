#!/usr/bin/env python3
"""Interactive VSPA:PE DRV2605L bench diagnostics (firmware v1.5 only).

No stimulation is performed until the operator types the command. Always
bench-test with all actuators OFF THE BODY first.

python -m pip install pyserial
python diagnose_arduino.py --list
python diagnose_arduino.py --port /dev/cu.usbmodem...   # macOS
python diagnose_arduino.py --port COM3                   # Windows
"""
import argparse
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    raise SystemExit("Install PySerial: python -m pip install pyserial")


def query(device, command, wait_sec=0.4):
    device.write((command + "\n").encode("ascii"))
    device.flush()
    print("> " + command)
    deadline = time.monotonic() + wait_sec
    lines = []
    while time.monotonic() < deadline:
        raw = device.readline()
        if raw:
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                print("< " + line)
                lines.append(line)
                # Extend collection slightly to allow terminal DONE replies.
                deadline = max(deadline, time.monotonic() + 0.15)
    if not lines:
        print("< NO RESPONSE. Check COM port, baud, sketch, USB cable, board reset.")
    return lines


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", help="USB serial port for Arduino Uno")
    p.add_argument("--list", action="store_true", help="List available serial ports")
    args = p.parse_args()
    if args.list:
        for prt in list_ports.comports():
            print(prt.device, "-", prt.description)
        return
    if not args.port:
        p.error("Specify --port, or use --list to find the device")
    print("BENCH TEST ONLY: detach the glove from the body, inspect motor power and wiring.")
    print("STOP stops the active motor, and Ctrl+C exits after STOP.")
    with serial.Serial(args.port, 9600, timeout=0.05, write_timeout=0.5) as dev:
        time.sleep(2.0)
        dev.reset_input_buffer()
        hello = query(dev, "PING", wait_sec=1.0)
        if not any(x.startswith("READY,VSPA_PE_RTP_1.5,") for x in hello):
            print("ERROR: firmware v1.5 did not reply. Do not run the main study GUI.")
            return
        query(dev, "SCAN", wait_sec=0.7)
        print("\nCommands: PING, SCAN, STATUS, REG,0, TESTFX,0, PLAY,0,1000,48, STOP, quit")
        print("TESTFX,0 uses the LRA effect library; PLAY uses RTP mode.")
        print("Do not increase RTP above verified motor-rated electrical conditions.")
        try:
            while True:
                command = input("BENCH> ").strip().upper()
                if command in {"QUIT", "EXIT", "Q"}:
                    break
                if not command:
                    continue
                if not (
                    command in {"PING", "SCAN", "STATUS", "STOP"}
                    or command.startswith(("REG,", "TESTFX,", "PLAY,"))
                ):
                    print("Unrecognized command. Try SCAN, REG,0, TESTFX,0, PLAY,0,1000,48 or STOP")
                    continue
                if command.startswith(("PLAY,", "TESTFX,")):
                    print("Confirm: motors are on the BENCH, NOT on your hand.")
                    if input("Type BENCH to proceed: ").strip() != "BENCH":
                        print("Cancelled")
                        continue
                query(dev, command, wait_sec=(3.8 if command.startswith("PLAY,") else 1.0))
        except (KeyboardInterrupt, EOFError):
            print("\nInterrupted")
        finally:
            query(dev, "STOP", wait_sec=0.3)


if __name__ == "__main__":
    main()
