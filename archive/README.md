# Preserved acquisition source

`acquisition_v1_8/` preserves the exact 15 non-data files from repository commit
`6041d4adc8f4c507671996160b7b0f3a439b69ef`, before the documentation revision.
Every preserved file was checked against that commit's Git blob identifier.
`source_manifest.json` records the original paths, byte counts, SHA-256 hashes
and Git blob identifiers. No generated Python caches are part of this snapshot.

The snapshot includes the original executable modules, original tests, original
firmware, the retained v1.6 baseline, requirements and historical instructions.
The original instructions are preserved as evidence of that source version;
use the repository's current top-level README for operational status and commands.
Research records remain in the repository's existing `experiment_output_v1_6/`
and `experiment_output_v1_8/` directories, outside this non-data source snapshot.

## Connection to the recorded v1.8 session

The metadata for the SELF02 hardware-mode session
`527d2499-7cd9-4eba-925d-f1c1ca1192de` records these exact source hashes:

| Original source path within the snapshot | SHA-256 |
| --- | --- |
| `vspa_protocol.py` | `09dc861fda7142cc9f45ebc398e8c82dd99e48f10b3583c7ed7870ac33e79a8b` |
| `self_test_gui_v1_8.py` | `4cfa2efc6e858f05894f947506d1042ae8bfefb8be74597659955e24e1f53ab5` |
| `firmware/firmware_vspa_rtp_v1_5/firmware_vspa_rtp_v1_5.ino` | `80ed2073bf716c7eb4119e36874482bf187c2f0f37aabadc7f22a3d2b9b1bea0` |

All three match the files preserved here. That session enabled ten randomized
single-finger rounds as well as ten pair rounds: five orientation trials,
50 randomized single-finger trials and 80 randomized ordered-pair trials, for
135 planned and saved trial rows. The executable default remains the pair-only
80-trial configuration. The recorded session configuration, not the default
alone, establishes the acquired schedule.

## Documented source and verification

The active top-level sources add explanatory file, definition and inline
comments. Four inaccurate or ambiguous Python docstrings were corrected:
the protocol module's description of firmware preservation, the configuration's
trial count, the schedule builder's construction/persistence description and
the analyzer's treatment of partial hardware sessions. The analyzer's corrected
module docstring also changes the corresponding command-line help text.

These changes alter source-byte hashes, documentation introspection and line
numbers. They preserve the executable Python structure and tokens after only
syntactic docstrings are excluded. The documented firmware retains the exact
non-comment token stream of the hash-pinned original. Its command protocol,
drive values and timing logic are unchanged.

Run from the current repository root:

```bash
python3 verify_documentation.py --json documentation_equivalence.json
python3 -m unittest discover -s tests -v
```

The verifier checks this archive against independent fixed SHA-256 constants,
checks the active production modules against the frozen source, and compares
the serial transport with the retained v1.6 implementation. The original tests
remain here without modification. Current tests maintain the original firmware
hash requirement against this archive, compare executable firmware/transport
content, and add a complete production-source equivalence check.

Future acquisition metadata records hashes of the documented source files
present on disk. The bundled firmware-source hash does not independently
verify which sketch is flashed on the controller. Those future values should not be substituted into the
historical session metadata. Offline verification does not establish physical
actuator performance or native macOS/Arduino operation.
