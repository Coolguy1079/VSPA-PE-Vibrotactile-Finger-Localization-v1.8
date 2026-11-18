"""Balanced VSPA:PE acquisition core, version 1.6.

This module is independent of Tk and usable in offline tests. The existing v1.5
Arduino firmware is retained unchanged. Command acceptance and firmware timers
are software observations; neither establishes physical actuator motion.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import random
import re
import statistics
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

SOFTWARE_VERSION = "VSPA_PE_SELF_TEST_v1.6"
SCHEMA_VERSION = "1.6.0"
SCHEDULE_ALGORITHM = "python-random-shuffle-without-replacement-v1"
FIRMWARE_SIGNATURE = "READY,VSPA_PE_RTP_1.5,mask=11111"
FINGERS = ("pinky", "ring", "middle", "index", "thumb")
CHANNEL_MAP = dict(zip(FINGERS, range(5)))
KEY_MAP = dict(zip(FINGERS, ("a", "s", "d", "f", "space")))
KEY_TO_FINGER = {value: key for key, value in KEY_MAP.items()}
ORDERED_ADJACENT_PAIRS = tuple(
    pair for i in range(4)
    for pair in ((FINGERS[i], FINGERS[i + 1]), (FINGERS[i + 1], FINGERS[i]))
)
PHASES = ("single_finger_fixed", "single_finger_random", "adjacent_pair_random")
PHASE_LABELS = {
    PHASES[0]: "Fixed orientation",
    PHASES[1]: "Random single-finger round",
    PHASES[2]: "Random adjacent-pair round",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class ProtocolConfig:
    """Round counts are independent; one full cycle has 5 + 5 + 8 trials."""
    single_rounds: int = 1
    pair_rounds: int = 1
    run_single: bool = True
    run_pair: bool = True
    stimulus_duration_ms: int = 1000
    rtp_drive_value: int = 48
    adjacent_pair_gap_sec: float = 2.0
    pre_trial_sec: float = 1.0
    response_delay_after_done_sec: float = 0.35
    response_timeout_sec: float = 8.0
    rest_between_trials_sec: float = 2.0
    ask_confounding: bool = True
    nominal_frequency_hz: float = 235.0

    def validate(self) -> None:
        if not self.run_single and not self.run_pair:
            raise ValueError("Enable at least one task.")
        for name in ("single_rounds", "pair_rounds"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 100:
                raise ValueError(f"{name} must be an integer from 1 to 100.")
        # These are the baseline firmware's command constraints, not physical
        # calibration. The GUI retains 1000 ms, 48 and 2.0 s unchanged.
        if type(self.stimulus_duration_ms) is not int or not 100 <= self.stimulus_duration_ms <= 3000:
            raise ValueError("Pulse request must be an integer from 100 to 3000 ms.")
        if type(self.rtp_drive_value) is not int or not 1 <= self.rtp_drive_value <= 80:
            raise ValueError("RTP command must be an integer from 1 to 80.")
        for name in ("adjacent_pair_gap_sec", "pre_trial_sec",
                     "response_delay_after_done_sec", "response_timeout_sec",
                     "rest_between_trials_sec", "nominal_frequency_hz"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")
        if self.response_timeout_sec <= 0:
            raise ValueError("Response timeout must be positive.")
        if self.adjacent_pair_gap_sec < self.stimulus_duration_ms / 1000.0 + 0.5:
            raise ValueError("Keep the requested command gap at least pulse duration + 0.5 s.")


@dataclass(frozen=True)
class TrialSpec:
    trial_number: int
    test_type: str
    block_number: int
    round_number: int
    trial_in_round: int
    fingers: tuple[str, ...]
    orientation: bool = False

    @property
    def pattern_name(self) -> str:
        return f"{self.test_type}_r{self.round_number:03d}_t{self.trial_in_round:02d}"


def build_schedule(seed: int, config: ProtocolConfig) -> list[TrialSpec]:
    """Shuffle a new complete list in each round; never sample with replacement.

    The persisted schedule is the authoritative reconstruction record. Seed,
    Python version, algorithm tag, and schedule hash are also retained.
    """
    config.validate()
    if type(seed) is not int:
        raise ValueError("The randomization seed must be an integer.")
    rng = random.Random(seed)
    schedule: list[TrialSpec] = []
    block = 0

    def add_round(phase: str, number: int, patterns: list[tuple[str, ...]], orientation: bool = False) -> None:
        nonlocal block
        block += 1
        for within, fingers in enumerate(patterns, 1):
            schedule.append(TrialSpec(len(schedule) + 1, phase, block,
                                      number, within, fingers, orientation))

    if config.run_single:
        add_round(PHASES[0], 0, [(finger,) for finger in FINGERS], True)
        for number in range(1, config.single_rounds + 1):
            patterns = [(finger,) for finger in FINGERS]
            rng.shuffle(patterns)
            add_round(PHASES[1], number, patterns)
    if config.run_pair:
        for number in range(1, config.pair_rounds + 1):
            patterns = list(ORDERED_ADJACENT_PAIRS)
            rng.shuffle(patterns)
            add_round(PHASES[2], number, patterns)
    return schedule


def schedule_hash(schedule: list[TrialSpec]) -> str:
    canonical = json.dumps([asdict(trial) for trial in schedule], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def score_response(expected: tuple[str, ...], response: list[str]) -> dict[str, Any]:
    """Score finger identities in temporal order; timeout is handled separately."""
    pair = len(expected) == 2
    return {
        "was_correct": list(expected) == response,
        "first_position_correct": bool(response) and response[0] == expected[0],
        "second_position_correct": (len(response) >= 2 and response[1] == expected[1]) if pair else "",
        "order_reversal": (len(response) == 2 and response == list(reversed(expected))) if pair else "",
        "duplicate_response": (len(response) == 2 and response[0] == response[1]) if pair else "",
        "both_fingers_identified_ignoring_order": (len(response) == 2 and set(response) == set(expected)) if pair else "",
    }


class ProtocolError(RuntimeError):
    pass


class StopRequested(RuntimeError):
    pass


@dataclass
class PulseRecord:
    finger: str
    channel: int
    command: str
    host_command_time: Optional[float] = None
    host_write_complete_time: Optional[float] = None
    start_reply: str = ""
    host_start_reply_time: Optional[float] = None
    done_reply: str = ""
    host_done_reply_time: Optional[float] = None
    firmware_elapsed_ms: Optional[int] = None
    simulated: bool = False


class HapticDevice:
    """Single-worker serial transport with exact replies and a cancellable wait.

    All raw received lines and attempted writes are sent to event_sink. START
    confirms register readback in the existing firmware. DONE is its elapsed
    software timer. No sensor, force, skin amplitude, or physical onset is read.
    """
    BAUD = 9600
    RESET_WAIT_SEC = 2.0
    START_TIMEOUT_SEC = 0.9
    DONE_GRACE_SEC = 1.0

    def __init__(self, port: Optional[str], simulation: bool,
                 event_sink: Optional[Callable[..., None]] = None,
                 serial_factory: Optional[Callable[..., Any]] = None):
        self.port = port
        self.simulation = simulation
        self.event_sink = event_sink or (lambda *args, **kwargs: None)
        self.serial_factory = serial_factory
        self.ser = None
        self.cancel = threading.Event()
        self._buffer = bytearray()
        self.firmware_response = "SIMULATION" if simulation else ""

    def event(self, name: str, **values: Any) -> None:
        self.event_sink(name, **values)

    def _wait_until(self, deadline: float) -> None:
        remaining = deadline - time.perf_counter()
        if self.cancel.wait(max(0.0, remaining)):
            raise StopRequested("Session stopped by operator.")

    def _write(self, command: str, pulse: Optional[PulseRecord] = None) -> float:
        if self.cancel.is_set():
            raise StopRequested("Session stopped before serial write.")
        self.event("serial_write_attempt", command=command)
        payload = (command + "\n").encode("ascii")
        # Timestamp the serial call after journaling, so filesystem logging
        # latency is not part of the defined command timestamp.
        issued = time.perf_counter()
        if pulse is not None:
            pulse.host_command_time = issued
        count = self.ser.write(payload)
        self.ser.flush()
        finished = time.perf_counter()
        if pulse is not None:
            pulse.host_write_complete_time = finished
        if count != len(payload):
            raise ProtocolError(f"Incomplete serial write: {count} of {len(payload)} bytes.")
        self.event("serial_write_complete", command=command, host_command_time=issued,
                   host_write_complete_time=finished)
        return issued

    def _expect(self, kind: str, exact: str, timeout_sec: float) -> tuple[str, float]:
        deadline = time.perf_counter() + timeout_sec
        while time.perf_counter() < deadline:
            if self.cancel.is_set():
                raise StopRequested("Session stopped while waiting for the controller.")
            if b"\n" not in self._buffer:
                raw = self.ser.readline()
                if raw:
                    self._buffer.extend(raw)
                    if len(self._buffer) > 4096:
                        raise ProtocolError("Controller returned an overlong serial response.")
                else:
                    self.cancel.wait(0.002)
                    continue
            if b"\n" not in self._buffer:
                continue
            raw, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            line = raw.decode("ascii", errors="replace").strip()
            received = time.perf_counter()
            if not line:
                continue
            self.event("serial_reply", reply=line, host_reply_time=received)
            if line.startswith("ERR,"):
                raise ProtocolError("Arduino refused command: " + line)
            if kind == "DONE" and line.startswith(exact):
                parts = line.split(",")
                if len(parts) != 3 or not parts[2].isdigit():
                    raise ProtocolError("Malformed DONE reply: " + line)
                return line, received
            if kind != "DONE" and line == exact:
                return line, received
            if line.startswith(("START,", "STARTFX,", "READY,", "DONE,")):
                raise ProtocolError(f"Unexpected {kind} response: {line}; expected {exact}")
            # Initialization/status lines can precede PING and are retained.
        raise ProtocolError(f"No {kind} acknowledgement before its timeout; expected {exact}")

    def connect(self) -> None:
        if self.simulation:
            self.event("simulation_connected", physical_actuation=False)
            return
        if not self.port:
            raise ProtocolError("Select the Arduino serial port.")
        factory = self.serial_factory
        if factory is None:
            try:
                import serial
            except ImportError as exc:
                raise ProtocolError("Install pyserial: python3 -m pip install pyserial") from exc
            factory = serial.Serial
        self.ser = factory(port=self.port, baudrate=self.BAUD, timeout=0.05,
                           write_timeout=0.5, xonxoff=False, rtscts=False, dsrdtr=False)
        self._wait_until(time.perf_counter() + self.RESET_WAIT_SEC)
        self.ser.reset_input_buffer()
        self._buffer.clear()
        self.event("startup_input_cleared")
        self._write("PING")
        reply, _ = self._expect("READY", FIRMWARE_SIGNATURE, 1.5)
        self.firmware_response = reply
        self.event("controller_connected", firmware_response=reply)

    def _pulse(self, finger: str, config: ProtocolConfig, records: list[PulseRecord]) -> None:
        channel = CHANNEL_MAP[finger]
        command = f"PLAY,{channel},{config.stimulus_duration_ms},{config.rtp_drive_value}"
        record = PulseRecord(finger, channel, command, simulated=self.simulation)
        records.append(record)  # Preserve attempted commands even when rejected.
        if self.simulation:
            record.host_command_time = time.perf_counter()
            record.host_write_complete_time = record.host_command_time
            record.host_start_reply_time = record.host_command_time
            record.start_reply = "SIMULATED_START"
            self.event("simulated_command", command=command, physical_actuation=False,
                       host_command_time=record.host_command_time)
            self._wait_until(record.host_command_time + config.stimulus_duration_ms / 1000.0)
            record.host_done_reply_time = time.perf_counter()
            record.done_reply = "SIMULATED_DONE"
            # A simulated wait is not an Arduino timer observation.
            return
        if self.ser is None:
            raise ProtocolError("The Arduino is not connected.")
        self._write(command, record)
        expected = f"START,{channel},{config.stimulus_duration_ms},{config.rtp_drive_value}"
        record.start_reply, record.host_start_reply_time = self._expect("START", expected, self.START_TIMEOUT_SEC)
        record.done_reply, record.host_done_reply_time = self._expect(
            "DONE", f"DONE,{channel},", config.stimulus_duration_ms / 1000.0 + self.DONE_GRACE_SEC)
        record.firmware_elapsed_ms = int(record.done_reply.rsplit(",", 1)[1])
        if record.firmware_elapsed_ms < config.stimulus_duration_ms:
            raise ProtocolError("Controller reported an early DONE; pulse request was interrupted.")

    def stimulate(self, fingers: tuple[str, ...], config: ProtocolConfig,
                  records: list[PulseRecord]) -> None:
        config.validate()
        if not (len(fingers) == 1 and fingers[0] in FINGERS) and fingers not in ORDERED_ADJACENT_PAIRS:
            raise ValueError("The protocol permits one finger or one ordered neighboring pair.")
        self._pulse(fingers[0], config, records)
        if len(fingers) == 2:
            deadline = records[0].host_command_time + config.adjacent_pair_gap_sec
            self._wait_until(deadline)
            self._pulse(fingers[1], config, records)

    def close(self) -> None:
        """Called by the serial worker after cancellation; never claims motion stopped."""
        def best_effort_event(name: str, **values: Any) -> None:
            # An output-disk failure must never prevent an attempted motor stop.
            try:
                self.event(name, **values)
            except Exception:
                pass
        if self.ser is not None:
            try:
                best_effort_event("serial_stop_attempt", command="STOP")
                self.ser.write(b"STOP\n")
                self.ser.flush()
                # The stop write is logged without asserting unobserved ACK.
                best_effort_event("serial_stop_write_complete")
            except Exception as exc:
                best_effort_event("serial_stop_error", error=str(exc))
            finally:
                try:
                    self.ser.close()
                finally:
                    self.ser = None
        best_effort_event("device_closed", simulation_mode=self.simulation)


TRIAL_FIELDS = [
    "timestamp_utc", "participant_id", "session_id", "software_version", "schema_version",
    "simulation_mode", "randomization_seed", "trial_number", "test_type", "block_number",
    "round_number", "trial_in_round", "orientation", "pattern_name", "trial_status",
    "response_status", "descriptive_eligible", "randomized_score_eligible",
    "expected_finger_sequence", "expected_key_sequence", "expected_channel_sequence",
    "requested_stimulus_count", "accepted_stimulus_count", "completed_stimulus_count",
    "requested_stimulus_duration_ms", "requested_rtp_drive_value", "requested_pair_gap_sec",
    "actual_pair_gap_sec", "pair_gap_error_sec", "first_host_command_time", "second_host_command_time",
    "response_window_open_time", "response_key_sequence", "response_finger_sequence",
    "response_length", "response_timeout", "was_correct", "first_position_correct",
    "second_position_correct", "order_reversal", "duplicate_response", "both_fingers_identified_ignoring_order",
    "first_key_from_first_command_sec", "last_key_from_first_command_sec",
    "first_key_from_response_open_sec", "completion_from_response_open_sec",
    "confounding_or_spread_report", "technical_anomaly_flag", "researcher_note",
    "nominal_frequency_hz", "firmware_protocol", "pulses_json", "response_key_times_json",
]


def make_trial_row(trial: TrialSpec, config: ProtocolConfig, records: list[PulseRecord],
                   response_keys: list[str], response_times: list[float], response_open: Optional[float],
                   response_status: str, trial_status: str, report: Optional[bool],
                   simulation: bool, error: str = "") -> dict[str, Any]:
    """Build one row, including interrupted or rejected trials without fake scores."""
    response = [KEY_TO_FINGER[key] for key in response_keys]
    completed = sum(bool(p.done_reply) for p in records)
    valid = trial_status == "completed" and response_status in {"complete", "timeout"} and completed == len(trial.fingers) and not error
    row = asdict(trial)
    row.pop("fingers")
    row.update({
        "timestamp_utc": utc_now(), "software_version": SOFTWARE_VERSION, "schema_version": SCHEMA_VERSION,
        "simulation_mode": simulation, "pattern_name": trial.pattern_name,
        "trial_status": trial_status, "response_status": response_status,
        "descriptive_eligible": valid and not simulation,
        "randomized_score_eligible": valid and not simulation and not trial.orientation,
        "expected_finger_sequence": "-".join(trial.fingers),
        "expected_key_sequence": "-".join(KEY_MAP[f] for f in trial.fingers),
        "expected_channel_sequence": "-".join(str(CHANNEL_MAP[f]) for f in trial.fingers),
        "requested_stimulus_count": len(trial.fingers),
        "accepted_stimulus_count": sum(bool(p.start_reply) for p in records),
        "completed_stimulus_count": completed,
        "requested_stimulus_duration_ms": config.stimulus_duration_ms,
        "requested_rtp_drive_value": config.rtp_drive_value,
        "requested_pair_gap_sec": config.adjacent_pair_gap_sec if len(trial.fingers) == 2 else "",
        "response_window_open_time": response_open if response_open is not None else "",
        "response_key_sequence": "-".join(response_keys),
        "response_finger_sequence": "-".join(response), "response_length": len(response),
        "response_timeout": response_status == "timeout",
        "confounding_or_spread_report": report if report is not None else "",
        "technical_anomaly_flag": bool(error), "researcher_note": error,
        "nominal_frequency_hz": config.nominal_frequency_hz,
        "firmware_protocol": "v1.5:PLAY,channel,duration_ms,rtp_level",
        "pulses_json": json.dumps([asdict(record) for record in records], separators=(",", ":")),
        "response_key_times_json": json.dumps(response_times),
    })
    scores = score_response(trial.fingers, response)
    row.update(scores if valid else {key: "" for key in scores})
    first = records[0].host_command_time if records else None
    second = records[1].host_command_time if len(records) > 1 else None
    row["first_host_command_time"] = first if first is not None else ""
    row["second_host_command_time"] = second if second is not None else ""
    if first is not None and second is not None:
        row["actual_pair_gap_sec"] = second - first
        row["pair_gap_error_sec"] = second - first - config.adjacent_pair_gap_sec
    if response_times and first is not None:
        row["first_key_from_first_command_sec"] = response_times[0] - first
        row["last_key_from_first_command_sec"] = response_times[-1] - first
    if response_times and response_open is not None:
        row["first_key_from_response_open_sec"] = response_times[0] - response_open
        # A partial pair has a first-key latency, but no completion latency.
        if len(response_times) == len(trial.fingers):
            row["completion_from_response_open_sec"] = response_times[-1] - response_open
    return row


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def describe(values: list[Any]) -> dict[str, Any]:
    usable = [float(value) for value in values if value not in (None, "")]
    usable = [value for value in usable if math.isfinite(value)]
    return {"n": len(usable), "mean": statistics.mean(usable) if usable else "",
            "sd": statistics.stdev(usable) if len(usable) >= 2 else ""}


def summarize_group(group: list[dict[str, Any]], planned: int) -> dict[str, Any]:
    valid = [row for row in group if bool_value(row.get("descriptive_eligible", False))]
    n = len(valid)
    correct = sum(bool_value(row["was_correct"]) for row in valid)
    reports = [bool_value(row["confounding_or_spread_report"]) for row in valid
               if row.get("confounding_or_spread_report", "") != ""]
    latency = describe([row.get("first_key_from_response_open_sec", "") for row in valid])
    gaps = describe([row.get("actual_pair_gap_sec", "") for row in valid])
    return {
        "planned_trials": planned, "attempted_trials": len(group), "valid_trials": n,
        "excluded_simulation_rows": sum(bool_value(row.get("simulation_mode", False)) for row in group),
        "technical_error_rows": sum(bool_value(row.get("technical_anomaly_flag", False)) for row in group),
        "interrupted_rows": sum(row.get("trial_status") == "interrupted" for row in group),
        "correct_trials": correct, "accuracy": correct / n if n else "",
        "binary_accuracy_sample_sd": statistics.stdev([int(bool_value(row["was_correct"])) for row in valid]) if n >= 2 else "",
        "response_timeouts": sum(bool_value(row["response_timeout"]) for row in valid),
        "order_reversals": sum(bool_value(row.get("order_reversal", False)) for row in valid),
        "duplicate_responses": sum(bool_value(row.get("duplicate_response", False)) for row in valid),
        "reports_answered": len(reports), "reports_yes": sum(reports),
        "spread_or_blending_rate": sum(reports) / len(reports) if reports else "",
        "first_key_latency_n": latency["n"], "mean_first_key_from_response_open_sec": latency["mean"],
        "sd_first_key_from_response_open_sec": latency["sd"],
        "pair_gap_n": gaps["n"], "mean_actual_pair_gap_sec": gaps["mean"], "sd_actual_pair_gap_sec": gaps["sd"],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Optional[list[str]] = None) -> None:
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


class DataStore:
    """Append/flush data at each transition and maintain an explicit lifecycle."""
    def __init__(self, output_root: Path, participant_id: str, seed: int,
                 config: ProtocolConfig, schedule: list[TrialSpec], simulation: bool):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", participant_id):
            raise ValueError("Use 1–48 letters, numbers, underscores, or hyphens for the study ID.")
        self.session_id = str(uuid.uuid4())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        mode = "SIMULATION" if simulation else "HARDWARE"
        self.output_dir = output_root / f"{mode}_{participant_id}_{stamp}_{self.session_id[:8]}"
        self.output_dir.mkdir(parents=True, exist_ok=False)
        self.participant_id, self.seed = participant_id, seed
        self.config, self.schedule, self.simulation = config, schedule, simulation
        self.rows: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._closed = False
        self._trial_stream = (self.output_dir / "trial_log.csv").open("w", newline="", encoding="utf-8")
        self._trial_writer = csv.DictWriter(self._trial_stream, fieldnames=TRIAL_FIELDS, extrasaction="ignore")
        self._trial_writer.writeheader()
        self._trial_stream.flush()
        self._events = (self.output_dir / "events.jsonl").open("w", encoding="utf-8")
        self.metadata = {
            "participant_id": participant_id, "session_id": self.session_id,
            "software_version": SOFTWARE_VERSION, "schema_version": SCHEMA_VERSION,
            "created_at_utc": utc_now(), "session_status": "created",
            "simulation_mode": simulation, "config": asdict(config),
            "randomization_seed": seed, "randomization_algorithm": SCHEDULE_ALGORITHM,
            "schedule_sha256": schedule_hash(schedule), "python_version": platform.python_version(),
            "platform": platform.platform(), "planned_trial_count": len(schedule),
            "saved_trial_rows": 0, "finger_channel_map": CHANNEL_MAP, "finger_key_map": KEY_MAP,
            "ordered_adjacent_pairs": ORDERED_ADJACENT_PAIRS,
            "firmware_protocol": "VSPA_PE_RTP_1.5",
            "physical_motion_measured": False, "physical_frequency_measured": False,
            "physical_velocity_measured": False, "physical_voltage_measured": False,
            "timing_definition": "Host perf_counter at attempted PLAY write, START/DONE receipt, and GUI response opening; DONE includes the firmware millisecond timer.",
            "fixed_orientation_in_randomized_scores": False,
            "complete_multifinger_sequence_included": False,
            "files_sha256": self._source_hashes(),
        }
        planned = []
        for trial in schedule:
            item = asdict(trial)
            item["fingers"] = "-".join(trial.fingers)
            planned.append(item)
        write_csv(self.output_dir / "schedule.csv", planned)
        self.save_metadata()
        self.event("session_created", planned_trials=len(schedule), simulation_mode=simulation)

    @staticmethod
    def _source_hashes() -> dict[str, str]:
        here = Path(__file__).resolve().parent
        hashes = {}
        for relative in ("vspa_protocol.py", "self_test_gui_v1_6.py",
                         "firmware/firmware_vspa_rtp_v1_5/firmware_vspa_rtp_v1_5.ino"):
            path = here / relative
            if path.is_file():
                hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    def save_metadata(self, **updates: Any) -> None:
        with self._lock:
            self.metadata.update(updates)
            path = self.output_dir / "metadata.json"
            temp = self.output_dir / "metadata.json.tmp"
            temp.write_text(json.dumps(self.metadata, indent=2), encoding="utf-8")
            temp.replace(path)

    def event(self, name: str, **values: Any) -> None:
        with self._lock:
            if self._closed:
                return
            row = {"timestamp_utc": utc_now(), "host_perf_counter": time.perf_counter(),
                   "session_id": self.session_id, "event": name, **values}
            self._events.write(json.dumps(row, separators=(",", ":")) + "\n")
            self._events.flush()

    def append_trial(self, row: dict[str, Any]) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("Session output is closed.")
            if any(saved["trial_number"] == row["trial_number"] for saved in self.rows):
                raise ValueError("A trial row must be saved only once.")
            row = {**row, "participant_id": self.participant_id,
                   "session_id": self.session_id, "randomization_seed": self.seed}
            self._trial_writer.writerow(row)
            self._trial_stream.flush()
            self.rows.append(row)
            self.event("trial_saved", trial_number=row["trial_number"], trial_status=row["trial_status"])
            self.save_metadata(saved_trial_rows=len(self.rows))

    def write_summaries(self) -> None:
        """Retain every planned condition, including zero coverage, and phase."""
        phases, conditions, rounds = [], [], []
        for phase in PHASES:
            planned = [trial for trial in self.schedule if trial.test_type == phase]
            if not planned:
                continue
            group = [row for row in self.rows if row["test_type"] == phase]
            common = {"participant_id": self.participant_id, "session_id": self.session_id,
                      "test_type": phase, "simulation_mode": self.simulation}
            phases.append({**common, **summarize_group(group, len(planned))})
            patterns = [(finger,) for finger in FINGERS] if phase != PHASES[2] else list(ORDERED_ADJACENT_PAIRS)
            for pattern in patterns:
                name = "-".join(pattern)
                target = [row for row in group if row["expected_finger_sequence"] == name]
                conditions.append({**common, "condition": name,
                                   **summarize_group(target, sum(trial.fingers == pattern for trial in planned))})
            for block in sorted({trial.block_number for trial in planned}):
                target = [row for row in group if row["block_number"] == block]
                planned_round = [trial for trial in planned if trial.block_number == block]
                summary = summarize_group(target, len(planned_round))
                rounds.append({**common, "block_number": block, "round_number": planned_round[0].round_number,
                               "round_complete": summary["valid_trials"] == len(planned_round), **summary})
        write_csv(self.output_dir / "phase_summary.csv", phases)
        write_csv(self.output_dir / "condition_summary.csv", conditions)
        write_csv(self.output_dir / "round_summary.csv", rounds)

    def finish(self, status: str, reason: str = "") -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self.write_summaries()
                self.save_metadata(session_status=status, ended_at_utc=utc_now(),
                                   end_reason=reason, saved_trial_rows=len(self.rows))
                self.event("session_finalized", session_status=status, reason=reason)
            finally:
                close_error = None
                for stream in (self._trial_stream, self._events):
                    try:
                        stream.close()
                    except Exception as exc:
                        close_error = close_error or exc
                self._closed = True
                if close_error is not None:
                    raise close_error
