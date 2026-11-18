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


## Documentation update: November 17, 2026

- Added file headers, function and method explanations, and inline comments to the active Python modules, test helpers, and Arduino firmware.
- Corrected outdated descriptions of the default trial count, schedule persistence, and treatment of incomplete hardware sessions.
- Preserved the exact pre-documentation source in `archive/acquisition_v1_8/` and recorded its hashes in `archive/source_manifest.json`.
- Added a reproducible source-equivalence check and maintained the firmware/transport regression so explanatory comments do not cause false failures.
- Updated operating documentation to distinguish the 80-trial default from the recorded 135-trial SELF02 configuration.

The acquisition logic, randomization algorithm, serial commands, response scoring, and firmware executable tokens are unchanged. The four corrected docstrings, comments, source line numbers, and resulting file hashes differ. Original session records and the earlier v1.6 source remain unchanged.
