#!/usr/bin/env python3
"""Summarize actual v1.6 sessions without treating repeated trials as people.

Usage: python3 analyze_sessions.py --input experiment_output --output analysis_output
Simulation folders are excluded. Duplicate session IDs are rejected. Configuration
groups and orientation/randomized phases remain separate. No hypothesis tests or
clinical classifications are generated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from vspa_protocol import bool_value, describe, summarize_group, write_csv


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def analyze(input_dir: Path, output_dir: Path) -> dict:
    sessions = []
    excluded_simulation = []
    seen = set()
    for metadata_path in sorted(input_dir.rglob("metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("schema_version") != "1.6.0":
            raise ValueError(f"Unsupported schema in {metadata_path}; keep historical v1.5 data separate.")
        session_id = metadata["session_id"]
        if session_id in seen:
            raise ValueError(f"Duplicate session ID {session_id}; remove duplicate copies from the analysis input.")
        seen.add(session_id)
        if bool_value(metadata.get("simulation_mode", False)):
            excluded_simulation.append(session_id)
            continue
        path = metadata_path.parent
        rows = load_csv(path / "trial_log.csv")
        schedule = load_csv(path / "schedule.csv")
        config_json = json.dumps(metadata["config"], sort_keys=True, separators=(",", ":"))
        config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
        identifiers = [row["trial_number"] for row in rows]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"Duplicate trial numbers in {path}")
        if any(row["session_id"] != session_id for row in rows):
            raise ValueError(f"A trial row has a different session ID in {path}")
        sessions.append((metadata, config_hash, rows, schedule))
    if not sessions:
        raise ValueError("No hardware-mode v1.6 sessions were found. Simulation is not experimental data.")

    session_conditions = []
    for metadata, config_hash, rows, schedule in sessions:
        planned = Counter((trial["test_type"], trial["fingers"]) for trial in schedule)
        for (phase, condition), count in planned.items():
            group = [row for row in rows if row["test_type"] == phase and row["expected_finger_sequence"] == condition]
            stats = summarize_group(group, count)
            session_conditions.append({
                "participant_id": metadata["participant_id"], "session_id": metadata["session_id"],
                "configuration_sha256": config_hash, "session_status": metadata["session_status"],
                "test_type": phase, "condition": condition,
                "condition_complete": stats["valid_trials"] == count,
                **stats,
            })

    # Session-level variability includes complete conditions from completed
    # sessions only. Partial conditions remain fully visible in the first table.
    groups = defaultdict(list)
    for row in session_conditions:
        key = (row["participant_id"], row["configuration_sha256"], row["test_type"], row["condition"])
        groups[key].append(row)
    repeated = []
    for (participant, configuration, phase, condition), group in groups.items():
        complete = [row for row in group if row["condition_complete"] and row["session_status"] == "completed"]
        accuracy = describe([row["accuracy"] for row in complete])
        repeated.append({
            "participant_id": participant, "configuration_sha256": configuration,
            "test_type": phase, "condition": condition,
            "recorded_sessions": len(group), "complete_sessions_used": len(complete),
            "mean_session_accuracy": accuracy["mean"], "sample_sd_session_accuracy": accuracy["sd"],
            "unique_individuals_in_this_row": 1,
        })
    report = {
        "hardware_session_count": len(sessions),
        "completed_hardware_session_count": sum(metadata["session_status"] == "completed" for metadata, *_ in sessions),
        "unique_study_ids": sorted({metadata["participant_id"] for metadata, *_ in sessions}),
        "excluded_simulation_sessions": excluded_simulation,
        "configuration_groups": len({configuration for _, configuration, *_ in sessions}),
        "interpretation": "Descriptive summaries only. Study IDs require researcher verification as unique people. Repeated sessions from one person measure within-person repeatability and do not increase the number of participants. Binary outcome SD and across-session SD are different quantities. Missing SD means fewer than two usable observations.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "per_session_condition.csv", session_conditions)
    write_csv(output_dir / "within_person_session_variability.csv", repeated)
    (output_dir / "analysis_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.input, args.output)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
