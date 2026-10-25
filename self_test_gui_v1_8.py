#!/usr/bin/env python3
"""VSPA:PE two-interval self-study GUI v1.8; run with Python 3 and Tkinter.

No hardware commands are sent in Simulation mode. Defaults retain the working
firmware v1.5 command: PLAY,channel,1000,48. In a normal hardware run,
80 randomized ordered-pair trials compare 2.0 s versus 4.0 s. Files are saved
under experiment_output_v1_8. Run `python3 -m unittest discover -s tests -v` to test
software without attaching an Arduino.
"""
from __future__ import annotations

import queue
import random
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Optional

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError as exc:
    raise SystemExit("This program needs a Python installation with Tkinter.") from exc

from vspa_protocol import (
    CHANNEL_MAP, FINGERS, KEY_TO_FINGER, PHASE_LABELS, DataStore,
    HapticDevice, ProtocolConfig, PulseRecord, StopRequested, TrialSpec,
    build_schedule, make_trial_row,
)

MAPPING_TEXT = "Pinky = A     Ring = S     Middle = D     Index = F     Thumb = Space"
OUTPUT_ROOT = Path(__file__).resolve().parent / "experiment_output_v1_8"


def available_ports() -> list[tuple[str, str]]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    records = [(port.device, f"{port.device} | {port.description}") for port in list_ports.comports()]
    return sorted(records, key=lambda item: ("usbmodem" not in item[0].lower(), item[0]))


class SerialWorker:
    """Own the serial stream in one worker so Tk stays responsive to Stop."""
    def __init__(self, device: HapticDevice):
        self.device = device
        self.jobs: queue.Queue = queue.Queue()
        self.results: queue.Queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True, name="vspa-serial")
        self.thread.start()

    def _run(self) -> None:
        while True:
            kind, payload = self.jobs.get()
            records: list[PulseRecord] = []
            error = None
            try:
                if kind == "connect":
                    self.device.connect()
                elif kind == "stimulate":
                    fingers, config = payload
                    self.device.stimulate(fingers, config, records)
                elif kind == "close":
                    self.device.close()
                else:
                    raise ValueError("Unknown worker operation.")
            except Exception as exc:
                error = exc
            self.results.put((kind, records, error))
            if kind == "close":
                return


class SetupWindow:
    def __init__(self, root: tk.Tk, on_start):
        self.root, self.on_start = root, on_start
        root.title("VSPA:PE v1.8 | Two-interval comparison setup")
        root.geometry("820x710")
        root.minsize(760, 630)
        shell = ttk.Frame(root)
        shell.pack(fill="both", expand=True)
        footer = ttk.Frame(shell, padding=(26, 12))
        footer.pack(side="bottom", fill="x")
        body = ttk.Frame(shell)
        body.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(body, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        frame = ttk.Frame(self.canvas, padding=26)
        content_window = self.canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(content_window, width=event.width))
        root.bind("<MouseWheel>", self.scroll)
        root.bind("<Button-4>", self.scroll)
        root.bind("<Button-5>", self.scroll)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="VSPA:PE balanced timing comparison", font=("Arial", 21, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))
        self.pid = tk.StringVar(value="SELF01")
        self.port = tk.StringVar()
        self.simulation = tk.BooleanVar(value=False)
        self.single = tk.BooleanVar(value=False)
        self.pair = tk.BooleanVar(value=True)
        self.single_rounds = tk.StringVar(value="1")
        self.pair_rounds = tk.StringVar(value="10")
        self.seed = tk.StringVar(value="")
        self.total = tk.StringVar()
        ttk.Label(frame, text="Study ID").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(frame, textvariable=self.pid).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(12, 0))
        ttk.Label(frame, text="Arduino port").grid(row=2, column=0, sticky="w", pady=8)
        self.port_combo = ttk.Combobox(frame, textvariable=self.port, state="readonly")
        self.port_combo.grid(row=2, column=1, sticky="ew", padx=(12, 0))
        ttk.Button(frame, text="Refresh", command=self.refresh).grid(row=2, column=2, padx=(8, 0))
        ttk.Checkbutton(frame, text="Simulation: no Arduino connection or physical vibration", variable=self.simulation).grid(row=3, column=0, columnspan=3, sticky="w", pady=12)
        ttk.Separator(frame).grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Checkbutton(frame, text="Single fingers: fixed orientation + balanced random rounds", variable=self.single).grid(row=5, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(frame, text="Random single rounds").grid(row=6, column=0, sticky="w", pady=8)
        ttk.Spinbox(frame, from_=1, to=100, textvariable=self.single_rounds, width=8).grid(row=6, column=1, sticky="w", padx=12)
        ttk.Label(frame, text="Each finger appears once per round.").grid(row=6, column=2, sticky="w")
        ttk.Checkbutton(frame, text="Adjacent pairs: all eight ordered neighboring pairs per round", variable=self.pair).grid(row=7, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(frame, text="Adjacent-pair rounds (even; 10 recommended)").grid(row=8, column=0, sticky="w", pady=8)
        ttk.Spinbox(frame, from_=2, to=100, increment=2, textvariable=self.pair_rounds, width=8).grid(row=8, column=1, sticky="w", padx=12)
        ttk.Label(frame, text="Four 2.0 s and four 4.0 s trials each round.").grid(row=8, column=2, sticky="w")
        ttk.Label(frame, textvariable=self.total, font=("Arial", 12, "bold")).grid(row=9, column=0, columnspan=3, sticky="w", pady=14)
        ttk.Label(frame, text="Pauses follow each complete round. Comparison uses both intervals within every round.\nSingle-finger testing is optional; the prior 50 trials need not be repeated.", justify="left").grid(row=10, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Label(frame, text="Random seed (blank = new)").grid(row=11, column=0, sticky="w", pady=10)
        ttk.Entry(frame, textvariable=self.seed).grid(row=11, column=1, columnspan=2, sticky="ew", padx=(12, 0))
        ttk.Label(frame, text="Pulse request: 1000 ms    Balanced pair gaps: 2.0 s / 4.0 s    RTP: 48\nIntervals are randomized and logged per trial; RTP is not calibrated volts.", justify="left").grid(row=12, column=0, columnspan=3, sticky="w", pady=12)
        ttk.Label(frame, text="Close Arduino Serial Monitor before connecting. Use the retained v1.5 firmware.\nResponses use A/S/D/F/Space; a Y/N spread or blending report follows each trial.", justify="left").grid(row=13, column=0, columnspan=3, sticky="w", pady=8)
        # Keep actions reachable when the settings are taller than the screen.
        buttons = ttk.Frame(footer)
        buttons.pack()
        ttk.Button(buttons, text="Connect and prepare", command=self.start).pack(side="left", padx=8)
        ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="left", padx=8)
        for variable in (self.single, self.pair, self.single_rounds, self.pair_rounds):
            variable.trace_add("write", lambda *_: self.update_total())
        self.update_total()
        self.refresh()

    def scroll(self, event):
        direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(direction, "units")
        return "break"

    def refresh(self) -> None:
        self.ports = {label: port for port, label in available_ports()}
        self.port_combo["values"] = list(self.ports)
        self.port.set(next(iter(self.ports), ""))

    def update_total(self) -> None:
        try:
            s, p = int(self.single_rounds.get()), int(self.pair_rounds.get())
            n = (5 + 5 * s if self.single.get() else 0) + (8 * p if self.pair.get() else 0)
            self.total.set(f"Planned response trials: {n}")
        except ValueError:
            self.total.set("Enter whole numbers for the round counts.")

    def start(self) -> None:
        try:
            config = ProtocolConfig(single_rounds=int(self.single_rounds.get()),
                                    pair_rounds=int(self.pair_rounds.get()),
                                    run_single=self.single.get(), run_pair=self.pair.get())
            config.validate()
            seed = int(self.seed.get()) if self.seed.get().strip() else random.SystemRandom().randrange(1, 2**63)
            port = self.ports.get(self.port.get())
            if not self.simulation.get() and not port:
                raise ValueError("Select an Arduino port, or select Simulation to test the interface.")
            schedule = build_schedule(seed, config)
            store = DataStore(OUTPUT_ROOT, self.pid.get().strip(), seed, config, schedule, self.simulation.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror("Session setup", str(exc), parent=self.root)
            return
        for binding in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.unbind(binding)
        self.on_start(config, schedule, seed, port, self.simulation.get(), store)


class VSPAPEApp:
    def __init__(self, root: tk.Tk, config: ProtocolConfig, schedule: list[TrialSpec],
                 seed: int, port: Optional[str], simulation: bool, store: DataStore):
        self.root, self.config, self.schedule = root, config, schedule
        self.seed, self.simulation, self.store = seed, simulation, store
        self.device = HapticDevice(port, simulation, event_sink=store.event)
        self.worker = SerialWorker(self.device)
        self.state = "connecting"
        self.index = -1
        self.current: Optional[TrialSpec] = None
        self.current_saved = True
        self.records: list[PulseRecord] = []
        self.active_trial_config: ProtocolConfig = config
        self.response_keys: list[str] = []
        self.response_times: list[float] = []
        self.response_open: Optional[float] = None
        self.response_status = "not_started"
        self.report: Optional[bool] = None
        self.held_keys: set[str] = set()
        self.pending_finish_status: Optional[str] = None
        self.finish_reason = ""
        self.after_ids: set[str] = set()
        self.timeout_id = None
        self.root.title("VSPA:PE v1.8 | Two-interval finger localization")
        self.root.geometry("1000x710")
        self.root.minsize(850, 640)
        self._build_ui()
        root.bind("<KeyPress>", self.on_keypress)
        root.bind("<KeyRelease>", self.on_keyrelease)
        root.bind("<FocusOut>", self.on_focus_out)
        root.report_callback_exception = self._callback_error
        root.protocol("WM_DELETE_WINDOW", self.request_stop)
        self.heading.set("Preparing the controller")
        self.prompt.set("Please wait while the connection is checked.")
        self.detail.set("Simulation mode: no motor output." if simulation else "Firmware v1.5 and all five controller channels must respond.")
        self.worker.jobs.put(("connect", None))
        self.root.after(20, self._poll)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=30)
        outer.pack(fill="both", expand=True)
        self.progress, self.heading, self.prompt, self.detail, self.response_text = (tk.StringVar() for _ in range(5))
        ttk.Label(outer, text="SIMULATION | No physical actuation" if self.simulation else "HARDWARE SESSION", font=("Arial", 11, "bold")).pack(anchor="w")
        ttk.Label(outer, textvariable=self.progress, anchor="e").pack(fill="x", pady=8)
        ttk.Label(outer, textvariable=self.heading, font=("Arial", 23, "bold"), wraplength=900, anchor="center", justify="center").pack(fill="x", pady=22)
        ttk.Label(outer, textvariable=self.prompt, font=("Arial", 18), wraplength=890, anchor="center", justify="center").pack(fill="both", expand=True, pady=18)
        ttk.Label(outer, textvariable=self.detail, font=("Arial", 12), wraplength=890, anchor="center", justify="center").pack(fill="x", pady=10)
        ttk.Label(outer, textvariable=self.response_text, font=("Arial", 12, "bold"), anchor="center").pack(fill="x", pady=8)
        self.action = ttk.Button(outer, text="Begin session", command=self.begin, takefocus=False, state="disabled")
        self.action.pack(pady=10)
        self.stop_button = ttk.Button(outer, text="Stop session (Esc)", command=self.request_stop, takefocus=False)
        self.stop_button.pack(pady=5)

    def _later(self, seconds: float, callback) -> str:
        holder = []
        def run():
            self.after_ids.discard(holder[0])
            if self.pending_finish_status is None:
                callback()
        token = self.root.after(max(0, int(round(seconds * 1000))), run)
        holder.append(token)
        self.after_ids.add(token)
        return token

    def _poll(self) -> None:
        if self.state == "finished":
            return
        try:
            while True:
                kind, records, error = self.worker.results.get_nowait()
                if kind == "connect":
                    if self.pending_finish_status is not None:
                        continue
                    if error is not None:
                        self._finish("connection_error", str(error))
                    else:
                        self.store.save_metadata(session_status="ready", serial_port=self.device.port,
                                                 serial_baud=self.device.BAUD, firmware_response=self.device.firmware_response)
                        self.instructions()
                elif kind == "stimulate":
                    self.records = records
                    if self.pending_finish_status is not None:
                        self._save_interrupted()
                    elif error is not None:
                        self.store.event("stimulus_error", trial_number=self.current.trial_number, error=str(error))
                        self._save("stimulus_error", error=str(error))
                        self._finish("hardware_error", str(error))
                    else:
                        self.state = "post_stimulus"
                        self._later(self.config.response_delay_after_done_sec, self.enable_response)
                elif kind == "close":
                    if error is not None:
                        self.finish_reason += " Device close error: " + str(error)
                    self.finalize()
                    return
        except queue.Empty:
            pass
        except Exception as exc:
            self._callback_error(type(exc), exc, None)
        self.root.after(20, self._poll)

    def _callback_error(self, exc_type, exc, traceback) -> None:
        """Terminate explicitly when a Tk callback cannot persist its output."""
        status = "output_error" if isinstance(exc, OSError) else "software_error"
        reason = f"Acquisition callback failed: {exc}"
        if self.pending_finish_status is not None:
            self.pending_finish_status = status
            self.finish_reason += " " + reason
        else:
            self._finish(status, reason)

    def instructions(self) -> None:
        self.state = "instructions"
        self.heading.set("Finger localization")
        self.prompt.set(MAPPING_TEXT)
        self.detail.set("Respond after the response prompt appears. Single trials require one key;\nneighboring-pair trials require two separate key presses in perceived order.\nPress Y or N for the spread or blending question. No correctness feedback is shown.\nA pause follows each complete round.")
        self.action.config(state="normal", text="Begin session", command=self.begin)

    def begin(self) -> None:
        self.store.save_metadata(session_status="running")
        self.store.event("session_started")
        self.next_trial()

    def next_trial(self, pause_checked: bool = False) -> None:
        if self.pending_finish_status is not None:
            return
        next_index = self.index + 1
        if next_index >= len(self.schedule):
            self._finish("completed")
            return
        upcoming = self.schedule[next_index]
        if self.current is not None and upcoming.block_number != self.current.block_number and not pause_checked:
            self.state = "round_pause"
            self.store.write_summaries()
            self.store.event("round_pause_started", completed_block=self.current.block_number, next_block=upcoming.block_number)
            self.heading.set("Round complete")
            self.prompt.set("Rest your hand. Select Continue when you are ready.")
            self.detail.set(f"Next: {PHASE_LABELS[upcoming.test_type]} {upcoming.round_number}")
            self.response_text.set("")
            self.action.config(state="normal", text="Continue", command=self.resume_round)
            return
        self.index = next_index
        self.current = upcoming
        self.current_saved = False
        self.records, self.response_keys, self.response_times = [], [], []
        self.response_open, self.report = None, None
        self.active_trial_config = replace(self.config, adjacent_pair_gap_sec=upcoming.pair_gap_sec) \
            if upcoming.pair_gap_sec is not None else self.config
        self.response_status = "not_started"
        self.state = "pre_trial"
        self.progress.set(f"Trial {upcoming.trial_number} of {len(self.schedule)} | {PHASE_LABELS[upcoming.test_type]} {upcoming.round_number if not upcoming.orientation else ''}")
        self.heading.set("Single-finger test" if len(upcoming.fingers) == 1 else "Adjacent-pair test")
        self.prompt.set("Prepare for the next cue.")
        self.detail.set("One finger will vibrate." if len(upcoming.fingers) == 1 else "Two neighboring fingers will vibrate one after the other.")
        self.response_text.set("")
        self.action.config(state="disabled")
        self.store.event("trial_started", trial_number=upcoming.trial_number,
                         test_type=upcoming.test_type, block_number=upcoming.block_number,
                         timing_condition=upcoming.timing_condition,
                         requested_pair_gap_sec=upcoming.pair_gap_sec)
        self._later(self.config.pre_trial_sec, self.deliver)

    def resume_round(self) -> None:
        self.store.event("round_pause_ended", next_block=self.schedule[self.index + 1].block_number)
        self.next_trial(pause_checked=True)

    def deliver(self) -> None:
        self.state = "stimulating"
        self.heading.set("Attend to the vibration")
        self.prompt.set("Wait for the response prompt.")
        self.detail.set("")
        self.worker.jobs.put(("stimulate", (self.current.fingers, self.active_trial_config)))

    def enable_response(self) -> None:
        self.state = "waiting_response"
        self.response_status = "waiting"
        self.heading.set("Which finger did you feel?" if len(self.current.fingers) == 1 else "Which two fingers did you feel, in order?")
        self.prompt.set(MAPPING_TEXT)
        self.detail.set(f"Enter {len(self.current.fingers)} {'key' if len(self.current.fingers) == 1 else 'keys'} within {self.config.response_timeout_sec:g} seconds.")
        self.response_text.set(f"Responses entered: 0 of {len(self.current.fingers)}")
        # The clock is taken at the GUI state transition, not at motor onset.
        self.root.focus_set()
        self.response_open = time.perf_counter()
        self.store.event("response_window_opened", trial_number=self.current.trial_number,
                         response_window_open_time=self.response_open)
        self.timeout_id = self._later(self.config.response_timeout_sec, self.response_timeout)

    def response_timeout(self) -> None:
        self.timeout_id = None
        if self.state == "waiting_response":
            self.response_status = "timeout"
            self.store.event("response_timeout", trial_number=self.current.trial_number,
                             responses_entered=len(self.response_keys))
            self.after_response()

    def on_keyrelease(self, event) -> None:
        self.held_keys.discard(event.keysym.lower())

    def on_focus_out(self, event) -> None:
        # A key can be released in another window, where Tk will not receive
        # its KeyRelease. Avoid treating its next real press as a held repeat.
        self.held_keys.clear()
        self.store.event("window_focus_lost", gui_state=self.state)

    def on_keypress(self, event):
        key = event.keysym.lower()
        if key == "escape":
            self.request_stop()
            return "break"
        if key in self.held_keys:
            return "break"
        self.held_keys.add(key)
        if self.pending_finish_status is not None:
            return "break"
        if self.state == "waiting_response" and key in KEY_TO_FINGER:
            stamp = time.perf_counter()
            # A busy desktop can deliver the Tk timeout callback late. Enforce
            # the elapsed-time deadline as well as scheduling that callback.
            if stamp > self.response_open + self.config.response_timeout_sec:
                if self.timeout_id is not None:
                    self.root.after_cancel(self.timeout_id)
                    self.after_ids.discard(self.timeout_id)
                    self.timeout_id = None
                self.store.event("ignored_late_response_key", trial_number=self.current.trial_number,
                                 key=key, response_key_time=stamp)
                self.response_timeout()
                return "break"
            self.response_keys.append(key)
            self.response_times.append(stamp)
            self.store.event("response_key", trial_number=self.current.trial_number,
                             key=key, response_key_time=stamp, position=len(self.response_keys))
            self.response_text.set(f"Responses entered: {len(self.response_keys)} of {len(self.current.fingers)}")
            if len(self.response_keys) == len(self.current.fingers):
                if self.timeout_id is not None:
                    self.root.after_cancel(self.timeout_id)
                    self.after_ids.discard(self.timeout_id)
                    self.timeout_id = None
                self.response_status = "complete"
                self.after_response()
        elif self.state == "waiting_report" and key in {"y", "n"}:
            self.report = key == "y"
            self.store.event("subjective_report", trial_number=self.current.trial_number, report=self.report)
            self.complete_trial()
        elif key in KEY_TO_FINGER:
            self.store.event("ignored_response_key", key=key, gui_state=self.state,
                             trial_number=self.current.trial_number if self.current else None)
        return "break"

    def after_response(self) -> None:
        if not self.config.ask_confounding:
            self.complete_trial()
            return
        self.state = "waiting_report"
        self.heading.set("Vibration spread" if len(self.current.fingers) == 1 else "Cue separation")
        self.prompt.set("Did the vibration seem to spread to another finger?" if len(self.current.fingers) == 1 else "Did the two vibrations feel blended, overlapping, or difficult to distinguish?")
        self.detail.set("Press Y for Yes or N for No.")
        self.response_text.set("")

    def _save(self, status: str, error: str = "") -> None:
        if self.current is None or self.current_saved:
            return
        row = make_trial_row(self.current, self.active_trial_config, self.records, self.response_keys,
                             self.response_times, self.response_open, self.response_status,
                             status, self.report, self.simulation, error)
        self.store.append_trial(row)
        self.current_saved = True

    def complete_trial(self) -> None:
        self._save("completed")
        self.state = "rest"
        self.heading.set("Response recorded")
        self.prompt.set("Relax your hand before the next trial.")
        self.detail.set("")
        self.response_text.set("")
        self._later(self.config.rest_between_trials_sec, self.next_trial)

    def _save_interrupted(self) -> None:
        if self.response_status in {"complete", "timeout"}:
            # If Stop occurs during Y/N collection, preserve completed objective
            # responses and leave the report blank instead of discarding them.
            self._save("completed")
        else:
            self.response_status = "aborted" if self.response_open is not None else "not_started"
            self._save("interrupted")

    def request_stop(self) -> None:
        if self.state == "finished":
            self.root.destroy()
            return
        self._finish("stopped", "Operator selected Stop or closed the session window.")

    def _finish(self, status: str, reason: str = "") -> None:
        if self.pending_finish_status is not None:
            return
        self.pending_finish_status, self.finish_reason = status, reason
        # Cancellation and close scheduling are unconditional. Journaling or
        # trial-saving errors must not prevent the STOP attempt.
        self.device.cancel.set()
        self.worker.jobs.put(("close", None))
        for token in list(self.after_ids):
            try:
                self.root.after_cancel(token)
            except Exception:
                pass
        self.after_ids.clear()
        try:
            self.store.event("stop_or_finish_requested", requested_status=status, reason=reason)
            if self.state != "stimulating":
                self._save_interrupted()
        except Exception as exc:
            self.pending_finish_status = "output_error"
            self.finish_reason += f" Output could not be fully saved: {exc}"
        self.heading.set("Saving the session")
        self.prompt.set("Please wait for the output files to close.")
        self.detail.set("")
        self.action.config(state="disabled")
        self.stop_button.config(state="disabled")

    def finalize(self) -> None:
        try:
            self.store.finish(self.pending_finish_status or "stopped", self.finish_reason)
        except Exception as exc:
            self.finish_reason += " Output error: " + str(exc)
        self.state = "finished"
        self.heading.set("Session complete" if self.pending_finish_status == "completed" else "Session ended")
        self.prompt.set(f"Saved trial rows: {len(self.store.rows)}\n\n{self.store.output_dir}")
        self.detail.set(self.finish_reason or "The trial log, event log, schedule, metadata, and summaries are saved.")
        self.response_text.set("")
        self.action.config(state="normal", text="Close", command=self.root.destroy)
        self.stop_button.config(state="disabled")


def main() -> None:
    root = tk.Tk()
    def start(config, schedule, seed, port, simulation, store):
        for widget in root.winfo_children():
            widget.destroy()
        root.vspa_app = VSPAPEApp(root, config, schedule, seed, port, simulation, store)
    SetupWindow(root, start)
    root.mainloop()


if __name__ == "__main__":
    main()
