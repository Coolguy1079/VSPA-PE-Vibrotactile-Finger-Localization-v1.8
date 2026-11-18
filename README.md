# VSPA:PE v1.8: Finger Localization and Interval Comparison

This repository contains the Python acquisition interface, serial-control protocol, Arduino firmware, analysis utilities, tests, and recorded data for **Design and Preliminary Evaluation of a Finger-Mounted Vibrotactile Feedback System Using Linear Resonant Actuators**, by Colton Carvalho.

The prototype addresses five finger-mounted Linear Resonant Actuators (LRAs). The interface records finger identification separately from the wearer's report of perceived spreading or blending. The two recorded sessions are repeated self-study observations of one researcher.

## Recorded sessions

| Recording | Acquisition program | Fixed orientation | Randomized single-finger trials | Ordered adjacent-pair trials | Total trials |
| --- | --- | ---: | ---: | ---: | ---: |
| SELF01 | v1.6 | 5 | 50 | 80, all at a 2-second command interval | 135 |
| SELF02 | v1.8 | 5 | 50 | 80, with 40 at each of two intervals | 135 |

The repository's `experiment_output_v1_6/` and `experiment_output_v1_8/` directories preserve the original session exports and ZIP archives. These contain **270 response trials and 430 requested motor pulses** in total. The 10 orientation trials are separate from randomized identification accuracy. `SCHEDULE_PREVIEW_NOT_RESEARCH_DATA.csv` is a software-generated example and is not an observed session.

The v1.8 default remains **80 adjacent-pair trials**. The recorded SELF02 session also enabled orientation and ten single-finger rounds, producing its documented 135-trial total. The default count and the completed session count describe different configurations.

Recorded randomized single-finger identification was 46/50 in SELF01 and 48/50 in SELF02. Within SELF02, exact ordered-pair recognition was 37/40 at the two-second command interval and 39/40 at four seconds. Blending was reported on 18/40 and 13/40 trials, respectively. These are descriptive outcomes for one researcher; they do not establish a population-level effect or learning benefit. The original trial logs are available in the [SELF01 recording](experiment_output_v1_6/HARDWARE_SELF01_20261021T105755Z_0fd5d9f8/) and [SELF02 recording](experiment_output_v1_8/HARDWARE_SELF02_20261025T063026Z_527d2499/).

## Source files and documentation

| File or directory | Responsibility |
| --- | --- |
| `self_test_gui_v1_8.py` | Configuration dialog, serial-worker coordination, trial states, accepted keypresses, perceptual reports, and session finalization. |
| `vspa_protocol.py` | Validated settings, balanced schedule construction, serial command/reply handling, response scoring, and durable output files. |
| `analyze_timing.py` | Descriptive interval and ordered-pair summaries, with completeness and integrity reporting. |
| `diagnose_arduino.py` | Bench inspection of the serial connection and installed driver channels. |
| `firmware/firmware_vspa_rtp_v1_5/` | Arduino v1.5 pulse execution, driver selection, command parsing, and START/DONE replies. |
| `tests/` | Schedule, scoring, transport, and firmware/source-equivalence regression checks. |
| `baseline_v1_6/` | Unmodified earlier Python sources retained for traceability. |
| `archive/acquisition_v1_8/` | Exact pre-documentation v1.8 source snapshot, including the original firmware. |

The active files contain explanatory file headers, function and method comments, and inline descriptions of the main scheduling, input, transport, and persistence paths. Comments distinguish requested settings from measured host timestamps and distinguish electronic replies from physical vibration.

The acquisition behavior is unchanged by this documentation revision. Historical source hashes in session metadata refer to the exact archived acquisition sources. Comments and corrected docstrings change file hashes, so the documented active files are not expected to match those historical byte hashes. Preserve the original recordings and archived sources together. Future runs record hashes of the active source files present on disk. The bundled firmware-source hash does not independently verify which sketch is flashed on the controller.

The archive and the existing `baseline_v1_6/` files deliberately retain their historical text. Their descriptions of study status or software defaults may reflect the earlier release. Use this README and the active source comments for the documented working copy.

## Setup and operation

1. Download or clone the repository. Keep `self_test_gui_v1_8.py` and its matching `vspa_protocol.py` together.
2. Use the established v1.5 Arduino firmware. Updating Python comments does not require reflashing the controller. The documented firmware retains the original executable instructions; the exact original sketch is preserved in the archive.
3. Check wiring and verify the five channel-to-finger assignments on the bench before a new recording. Controller acknowledgements alone do not establish motor motion.
4. Install PySerial into the Python environment used to launch the program:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

5. Close Arduino Serial Monitor, select the device port in the graphical interface, and launch:

   ```bash
   python3 self_test_gui_v1_8.py
   ```

6. For the default timing-only protocol, leave **Single fingers** unchecked, select **Adjacent pairs**, and retain **10 adjacent rounds**. The interface should show **80 trials**. To repeat both tasks, enable single-finger testing and choose the intended number of complete rounds before beginning.
7. Enter a new session identifier. For hardware acquisition, leave simulation unchecked. Respond only after the response window opens; then answer the separate Yes/No perceptual question. Complete rounds are separated by a Continue pause; the final round ends the session. Stop or Escape ends a session through the cancellation path.
8. Preserve the whole new session folder under `experiment_output_v1_8/`. It contains metadata, the schedule, trial rows, the event journal, and derived summary files. Keep new sessions separate from SELF01 and SELF02.

When using Spyder, install dependencies in its selected interpreter and run the GUI file from the extracted project. The output directory is located beside the acquisition script, independent of the terminal's working directory.

## Experimental settings and response mapping

| Item | Definition |
| --- | --- |
| Finger/channel/key mapping | Pinky / 0 / A; ring / 1 / S; middle / 2 / D; index / 3 / F; thumb / 4 / Space |
| Ordered pairs | Both directions of pinky-ring, ring-middle, middle-index, and index-thumb: eight conditions |
| Timing allocation | Four 2-second and four 4-second trials in each eight-trial round |
| Allocation across ten rounds | Five presentations of every ordered pair at each interval |
| Requested pulse | 1000 ms, using `PLAY,channel,1000,48` |
| Drive input | Real-time playback (RTP) register setting 48; this is not a calibrated voltage or force |
| Pair response | Two keys entered in the perceived order after the response window opens |
| Perceptual report | Whether successive vibrations felt blended, overlapping, or difficult to distinguish |

The two- and four-second values are **requested first-command-to-second-command intervals**. They are not motor durations and are not measured silent gaps at the skin. With one-second pulse requests, the nominal schedules leave approximately one or three seconds after the requested first-pulse end. Actual mechanical onset and decay were not measured.

The saved seed reproduces the schedule. Each round covers every ordered neighboring pair once. Balanced interval assignments preserve four trials per interval per round and five presentations per pair per interval over ten rounds. The procedure does not claim uniform sampling of every mathematically possible balanced allocation.

## Tests and analysis

Run the existing regression suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

Analyze recorded v1.8 hardware sessions with:

```bash
python3 analyze_timing.py --input experiment_output_v1_8 --output analysis_output
```

The analysis creates `session_integrity.csv`, `timing_summary.csv`, `timing_by_pair.csv`, and `analysis_manifest.json`. It excludes simulated, interrupted, and technically failed trial rows from outcome summaries. Valid hardware rows from incomplete sessions can still contribute; session-level completeness and integrity flags must therefore be inspected before interpreting results. Missing conditions remain visible.

A complete default timing-only session has 80 pair rows, 40 per interval, and 160 requested pulses. If optional single-finger testing is enabled, its trials and pulses increase the session totals. Software tests verify the implemented logic and simulated transport cases; they are not physical motor tests.

For the manuscript's Overleaf companion, the documented working copy is under `code/documented_v1_8/`, the exact historical sources are under `code/acquisition_v1_6/` and `code/acquisition_v1_8/`, and the original records are under `data/raw/SELF01/` and `data/raw/SELF02/`. The Overleaf root README provides commands using those package paths.
