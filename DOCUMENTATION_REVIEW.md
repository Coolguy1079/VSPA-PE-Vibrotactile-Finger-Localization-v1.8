# v1.8 code documentation revision

## Scope and source baseline

This revision documents the active source from
`Coolguy1079/VSPA-PE-Vibrotactile-Finger-Localization-v1.8`, with source baseline
commit `6041d4adc8f4c507671996160b7b0f3a439b69ef`. The exact pre-documentation
non-data repository files are preserved in `archive/acquisition_v1_8/`.
Their SHA-256 and Git blob identifiers are recorded in
`archive/source_manifest.json` and checked by `verify_documentation.py`.
The v1.6 baseline and existing research records retain their original bytes.

The executable acquisition and analysis logic is unchanged. File headers,
comments above named classes/functions/methods and inline explanations were
added to these active sources:

| File | Main explanation added |
| --- | --- |
| `vspa_protocol.py` | Complete schedules, exact timing-condition margins, serial transaction semantics, scoring eligibility, clocks and persistent records |
| `self_test_gui_v1_8.py` | Tk/worker ownership, trial states, hidden target information, response deadlines, inter-round pauses and shutdown ordering |
| `analyze_timing.py` | Saved-plan validation, partial-session completeness, eligible denominators and descriptive differences |
| `diagnose_arduino.py` | Bench-console purpose, reply collection and separation from acquisition records |
| `firmware/firmware_vspa_rtp_v1_5/firmware_vspa_rtp_v1_5.ino` | Multiplexer selection, cached driver availability, command validation, RTP readback and the firmware timer |
| `tests/test_v1_8.py` | Balance, reconstruction, row/summary checks and maintained executable-equivalence regression |
| `tests/test_serial_timing.py` | Fake acknowledgements, test-only shortened intervals and host scheduling scope |

The new standalone verifier is itself documented and performs no GUI or serial
operations. All 104 named Python definitions in the active sources, tests and
verifier have adjacent explanatory comments or docstrings. All 12 firmware
functions have purpose comments. The archived source is intentionally unchanged.

## Protocol descriptions retained in the code

The current default is **80 ordered-pair trials**: ten rounds containing all
eight directed neighboring-finger pairs once per round. Each round has four
2.0-second and four 4.0-second assignments. Each ordered pair appears five times
at each interval over the ten rounds. The matrix is initialized with exact
margins and randomized using margin-preserving 2-by-2 exchanges plus row/column
permutations. The implementation does not claim uniform sampling of all
possible balanced matrices. Pair order is shuffled within each round.

Single-finger testing is optional. Enabling it adds five fixed pinky-to-thumb
orientation trials and five randomized single-finger trials per requested
single round. The recorded SELF02 session enabled ten single rounds,
producing 5 + 50 + 80 = **135 trials**. Its configuration and the three recorded
source-file hashes match the preserved snapshot. No historical schedule or
metadata was reconstructed or rewritten by this documentation revision.

The GUI retains the 1000-millisecond pulse request and RTP value 48. The second
pair command is scheduled relative to the first pre-write host timestamp.
The worker first receives the first pulse's DONE reply, waits any remaining
time to the selected 2.0/4.0-second deadline, and sends the second command.
Serial overhead or an overdue deadline can increase observed command spacing;
the saved timestamps make this visible. START is register-readback acceptance,
and DONE is a firmware software-timer report. Neither observes physical skin
onset or actuator motion.

Tk polls the worker result and schedules the 0.35-second post-delivery delay.
The response-clock origin is the subsequent GUI response-state transition.
Consequently, response timing is explicitly distinct from the command clock
and physical onset. The response key handler checks elapsed time as well as
the Tk timeout callback, so delayed desktop callbacks do not admit late keys.
Target order and assigned interval remain in the saved schedule; randomized
participant prompts do not disclose them or provide correctness feedback.

Raw attempts and events are preserved with explicit status and eligibility
fields. Interrupted or technical-error rows are retained without invented
scores. Completed timeouts remain objective outcomes. Simulation rows are
excluded from hardware summaries. Missing subjective reports remain missing
and use a separate report denominator. The analyzer includes eligible rows
from partial hardware sessions while reporting session completeness; it does
not silently fill missing trials or treat repeated trials as independent people.

## Intentional documentation-visible differences

Exactly four existing docstrings changed:

1. `vspa_protocol.py` module: clarifies preservation of firmware command behavior
   while exact original source bytes are archived.
2. `ProtocolConfig`: replaces the obsolete 18-trial description with the current
   80-trial default and optional-single calculation, including 135 trials when
   ten single rounds are enabled.
3. `build_schedule`: clarifies that the function constructs the plan in memory;
   `DataStore` persists it, and single-finger blocks add to the pair task.
4. `analyze_timing.py` module: corrects the claim that incomplete sessions are
   excluded; eligible rows from partial hardware sessions are reported with
   completeness flags. Its example input path now matches the v1.8 output folder.

These edits intentionally change `__doc__` values and the analyzer's help
description. Added comments change line numbers and source-file SHA-256 values.
Future sessions record those new source-file hashes from disk; a bundled
firmware-source hash does not independently verify the flashed sketch. The revision does not
claim byte-identical active files; the exact historical bytes remain available
and hash-verified in the archive.

## Regression-test maintenance

The pre-documentation suite contained eight tests. Seven functional tests
remain AST-identical. The original source-identity test required byte-identical
active firmware and a byte-identical `HapticDevice` source slice, so explanatory
comments alone would fail that test. It was maintained as
`test_firmware_and_serial_transport_executable_equivalence`:

- The archived original firmware must retain its fixed SHA-256
  `80ed2073bf716c7eb4119e36874482bf187c2f0f37aabadc7f22a3d2b9b1bea0`.
- The active firmware's non-comment token stream must match that exact original.
- The active `HapticDevice` AST and non-comment Python token stream, including
  its docstrings and executable literals, must match the retained v1.6 class.
- RTP 48 and the 1000-millisecond pulse default remain explicit assertions.

One additional test, `test_documentation_preserves_production_logic`, verifies
all four production Python modules and all 15 frozen-source hashes. Only the
four named docstrings may differ. All other executable literals, statements,
imports and control flow must match in both normalized AST and token comparisons.
The resulting suite contains **nine passing offline tests**, including the
existing **1,000-seed schedule-balance check**.

## Verification and limits

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 verify_documentation.py --json documentation_equivalence.json
```

Both commands completed successfully in the revision workspace. Targeted
negative controls confirmed that the verifier accepts added comments but
rejects changes to a firmware RTP constant, string literal, compound operator,
Python numeric constant and serial-protocol string. The firmware lexer preserves
quoted strings and preprocessing-line boundaries; it checks this existing
sketch and is not a substitute for an Arduino compiler. Python source files and
tests also parsed successfully.

`documentation_equivalence.json` contains the source hashes, normalized-AST
fingerprints, firmware token fingerprint and the exact before/after docstrings.
The original and documented analyzers were also run against the same recorded
v1.8 session into separate output folders. All four generated files were
byte-identical: `analysis_manifest.json`, `session_integrity.csv`,
`timing_by_pair.csv` and `timing_summary.csv`. Their hashes are recorded in
`analysis_equivalence.json`. The source metadata, saved schedule and raw trial
log were read without modification.

This evidence establishes source-level preservation of executable logic within
the stated comparisons. It does not add physical motor trials, certify actuator
output, compile/upload firmware or establish native macOS GUI operation.

The original source had already recorded hardware-mode sessions; the offline
checks for this documentation revision are separate evidence. No new research
observations were created by the tests or by the documentation verifier.
