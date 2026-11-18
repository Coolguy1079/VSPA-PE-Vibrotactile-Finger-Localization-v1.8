# VSPA:PE v1.8 - Two-Interval Adjacent-Finger Comparison

**Researcher-only acquisition program, built from the user's verified v1.6 baseline.**

This folder includes the GUI and its required `vspa_protocol.py` module, an unchanged copy of the working Arduino firmware, descriptive analysis code, tests, and the original v1.6 Python sources for traceability. This package **does not** contain newly collected trials. Its software checks cannot prove physical vibration.

## What is new

- The **default experiment is adjacent-pair only:** 10 complete rounds of eight ordered neighboring pairs = **80 response trials**. The earlier 50 single-finger trials do not need to be repeated.
- Each ordered pair occurs **five times with the baseline 2.0-second onset-command gap** and **five times with the longer 4.0-second gap**.
- Every eight-trial round contains **four trials of each timing condition**; the pair order and timing allocation are randomized reproducibly from the stored seed.
- The interface does **not** identify the upcoming finger pair or timing condition during trials.
- Requested one-second pulses (`PLAY,channel,1000,48`), the five-channel mapping, firmware START and DONE acknowledgement checks, and the pretrial and report questions remain unchanged.
- A separate `timing_condition` value and `requested_pair_gap_sec` are stored in each **schedule.csv** and **trial_log.csv** row. `actual_pair_gap_sec` is recorded from **host command timestamps**, not physical skin onset.
- Additional `timing_condition_summary.csv` and `timing_by_ordered_pair.csv` are generated during the session.
- Missing or interrupted trials remain visible and are not scored as invented misses. Simulation is clearly identified and excluded by the new analysis script.

## Setup on a Mac with Spyder

1. Unzip the package and keep `self_test_gui_v1_8.py` and `vspa_protocol.py` **together in the same extracted directory**.
2. Confirm the known-good **v1.5 Arduino firmware** is still installed. **Do not upload a different sketch for this test.** The matching original is in `firmware/firmware_vspa_rtp_v1_5/` for reference.
3. Inspect the repaired motor connections and run the existing short bench checks, with the motors off your hand, before using the glove. Confirm all five motors are physically discernible at their intended channels. A firmware acknowledgement does **not** prove motor motion.
4. Install PySerial if necessary: `python3 -m pip install -r requirements.txt` (Spyder's Python interpreter must have the same package).
5. Close Arduino Serial Monitor. In Spyder, open and run **`self_test_gui_v1_8.py`**. Alternatively, from a terminal inside the extracted folder: `python3 self_test_gui_v1_8.py`.
6. Select the correct `/dev/cu.usbmodem...` port. **Simulation must be unchecked for the physical study.** Confirm the defaults: **Single fingers unchecked**, **Adjacent pairs checked**, and **10 adjacent rounds**. The GUI should say **80 trials**.
7. Enter a de-identified study ID. Start the session, respond **after** the response screen appears, and answer **Y/N** for whether the two cues felt blended. The program pauses after each complete 8-trial round. Use the Stop button or Escape to end an interrupted session safely.
8. On completion, copy the entire folder in `experiment_output_v1_8/`, including `metadata.json`, `schedule.csv`, `trial_log.csv`, `events.jsonl`, and summary CSVs. **Do not rename trial entries or hand-edit the original CSV.**

## Experiment design

| Factor | Configuration |
| --- | --- |
| Experimental unit | One researcher, repeated within-person observations |
| Pairs | Pinky/Ring, Ring/Middle, Middle/Index, Index/Thumb, **both directions** (8 total) |
| Timing conditions | 2.0 s or 4.0 s, requested first-command to second-command interval |
| Allocation per round | 4 baseline, 4 long, shuffled pair order |
| Allocation per pair across 10 rounds | 5 baseline, 5 long |
| Requested pulse duration | 1000 ms per finger (unchanged) |
| RTP register command | 48 (unchanged, not calibrated as voltage or force) |
| Primary outcome | Subjective report of blending/overlap (yes/no) |
| Secondary outcomes | Exact ordered recognition, order reversal, timeouts, latency from response-window opening, host command gap |

**Reason for separate study:** The earlier ten-round v1.6 session used only a 2.0-second interval, and was conducted at a different time. This randomized, within-session comparison tests both intervals under the same study procedure rather than attributing across-day differences to the interval.

**Terminology:** With 1000-ms pulses, the nominal inter-command start separation is 2000 or 4000 ms, leaving a nominal no-drive gap of about 1000 or 3000 ms. Pulse termination and decay at the skin have not been measured, so these are not directly measured inter-vibration gaps. The 2.0-s baseline is retained from the previous self-study; the 4.0-s condition increases nominal temporal separation.

## Running tests and analysis

From the extracted folder:

```bash
python3 -m unittest discover -s tests -v
python3 analyze_timing.py --input experiment_output_v1_8 --output analysis_output
```

The analysis creates `session_integrity.csv`, `timing_summary.csv`, `timing_by_pair.csv`, and `analysis_manifest.json`. It reports missing conditions rather than fabricating results. Analyze only actual hardware-mode records; the script rejects simulated data as experimental evidence.

A complete, correctly run 10-round session should contain **80 pair rows** (40 at each interval) and **160 acknowledged motor pulses**, with five presentations per pair under each condition. These are **target counts**, not claims that any real session has been completed.

## Limitations and precautions

- The Python GUI and tests are verified offline; **v1.8 has not yet been tested on the user's physical Arduino/glove**.
- The firmware and serial transport are unchanged from the exact baseline that recorded the prior v1.6 session (verified by SHA-256 hashes). No physical amplitude/frequency sweep is introduced.
- The current program records electrical-controller acknowledgements and host-side command timing, not skin acceleration, displacement, force, or nerve status.
- The study is one person, with correlated trials. Do not describe the 80 trials as independent participants or a clinical validation experiment.
- Avoid repeated excessive contact pressure or continuing if you experience discomfort, irritation or pain. Stop and inspect the device if movement is unexpectedly strong, wiring gets warm, or a connection becomes unstable.
- For sharing data on GitHub, exclude personal identifiers, local serial-port paths if sensitive, and any other people's research records without appropriate authorization. Preserve unmodified originals separately.


## v1.8 interval change

The condition comparison now uses **2.0 s baseline** and **4.0 s long** between the FIRST and SECOND motor command. Both are onset-command intervals rather than measured physical vibration gaps. Each 1000-ms pulse is unchanged. The nominal no-drive interval is about **1 s vs 3 s**. The 2.0 s baseline matches the prior v1.6 study. This changes the research protocol: keep v1.7 and v1.8 datasets separately identified.
