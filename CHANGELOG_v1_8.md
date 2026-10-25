# v1.8: increased separation between two finger vibrations

## Changes from v1.7

- Changed the two randomized pair-onset command separations from **1.5 s and 2.0 s** to **2.0 s and 4.0 s**.
- Preserved the previous **2.0-second baseline** and added a **4.0-second longer comparison**.
- Renamed condition identifiers to `baseline_2p0s` and `long_4p0s`; output CSVs, plan, metadata, and analysis all use them consistently.
- Kept 10 rounds, all 8 ordered neighboring pairs, 5 presentations per pair at each condition, and 40 presentations per condition.
- Firmware sketch (v1.5), digital motor drive `48`, 1000-ms requested pulse, USB serial transport and all motor wiring assignments are unchanged.
- Separated output directory: `experiment_output_v1_8/` to avoid accidental pooling with earlier records.
- Updated offline schedule, serial, storage and analysis tests. No physical vibration measurements were performed as part of software modification.

**Interpretation:** This is a change of experimental conditions; do not describe it as increasing the pause between completed trials. The latter remains configured at 2.0 seconds, aside from operator-paced breaks after rounds. Software timestamps measure command issuance, not motion at the finger.
