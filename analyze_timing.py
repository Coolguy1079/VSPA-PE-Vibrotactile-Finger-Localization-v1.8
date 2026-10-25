#!/usr/bin/env python3
"""Analyze actual hardware-mode VSPA:PE v1.8 comparison trial logs.

Run after the experiment, not before. Never generates or imputes trial outcomes.
Shows valid/attempted sample sizes and separate rates for correct ordered response
and self-reported blending. Excludes simulated and incomplete sessions by default.

python3 analyze_timing.py --input experiment_output --output analysis_output
"""
from __future__ import annotations
import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from vspa_protocol import ORDERED_ADJACENT_PAIRS, bool_value, describe, write_csv

CONDITIONS=('baseline_2p0s','long_4p0s')

def analyze(input_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True,exist_ok=True)
    session_reports=[]
    overall=[]
    detailed=[]
    for metadata_path in sorted(input_dir.rglob('metadata.json')):
        metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
        if metadata.get('schema_version')!='1.8.0':
            continue
        if bool_value(metadata.get('simulation_mode',False)):
            continue
        folder=metadata_path.parent
        with (folder/'trial_log.csv').open(newline='',encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        with (folder/'schedule.csv').open(newline='',encoding='utf-8') as f:
            schedule=list(csv.DictReader(f))
        keyset=[r['trial_number'] for r in rows]
        if len(set(keyset))!=len(keyset):raise ValueError(f'Duplicate trial identifiers in {folder}')
        if any(r['session_id']!=metadata['session_id'] for r in rows):
            raise ValueError(f'Session ID mismatch in {folder}')
        if not metadata['config']['timing_comparison_enabled']:
            raise ValueError('Dataset was not collected with timing comparison enabled')
        if not metadata['config']['run_pair']:
            raise ValueError('No adjacent-pair trials configured')
        def expected_map(row):
            return (row['test_type'],row['expected_finger_sequence'],row['timing_condition'],row['requested_pair_gap_sec'])
        plan={r['trial_number']:r for r in schedule}
        for r in rows:
            if r['trial_number'] not in plan:raise ValueError('Trial not in schedule')
            sched=plan[r['trial_number']]
            if (r['expected_finger_sequence']!=sched['fingers'] or r['timing_condition']!=sched['timing_condition']):
                raise ValueError('Logged condition differs from original schedule')
            if r['test_type']=='adjacent_pair_random':
                if abs(float(r['requested_pair_gap_sec'])-float(sched['pair_gap_sec']))>1e-9:
                    raise ValueError('Requested interval differs from original schedule')
            if bool_value(r.get('simulation_mode',False)):raise ValueError('Simulated trial mixed into hardware session')
        pairs=[r for r in rows if r['test_type']=='adjacent_pair_random']
        planned_pairs=[r for r in schedule if r['test_type']=='adjacent_pair_random']
        required=len(ORDERED_ADJACENT_PAIRS)*metadata['config']['pair_rounds']
        if len(planned_pairs)!=required:raise ValueError('Planned pair schedule incomplete')
        for round_id in range(1,metadata['config']['pair_rounds']+1):
            rround=[p for p in planned_pairs if int(p['round_number'])==round_id]
            counts=Counter(p['timing_condition'] for p in rround)
            if len(rround)!=8 or counts!=Counter({'baseline_2p0s':4,'long_4p0s':4}):
                raise ValueError('A planned round is not balanced 4 baseline / 4 long')
        for pair in ORDERED_ADJACENT_PAIRS:
            for cond in CONDITIONS:
                n=sum(p['fingers']=='-'.join(pair) and p['timing_condition']==cond for p in planned_pairs)
                if n!=metadata['config']['pair_rounds']//2:
                    raise ValueError('A planned ordered pair is not equally allocated across intervals')
        complete=(metadata['session_status']=='completed' and len(pairs)==required and
                  len(rows)==len(schedule) and all(r['trial_status']=='completed' for r in pairs))
        session_reports.append({'session_id':metadata['session_id'],
                                'status':metadata['session_status'],'planned_trials':len(schedule),
                                'saved_trials':len(rows),'planned_pairs':required,
                                'saved_pairs':len(pairs),'complete_pair_protocol':complete})
        # Deliberately report incomplete sessions, but do not silently claim all planned trials occurred.
        for condition in CONDITIONS:
            expected=4*metadata['config']['pair_rounds']
            subset=[r for r in pairs if r['timing_condition']==condition]
            if len([p for p in planned_pairs if p['timing_condition']==condition])!=expected:
                raise ValueError('Planned condition balance was not 4 per round')
            def summary(seq, planned, label):
                valid=[r for r in seq if bool_value(r.get('descriptive_eligible',False))]
                scored=[bool_value(r['was_correct']) for r in valid]
                reports=[bool_value(r['confounding_or_spread_report']) for r in valid
                         if r['confounding_or_spread_report'] not in ('',None)]
                intervals=describe([r.get('actual_pair_gap_sec') for r in valid])
                return {'session_id':metadata['session_id'],'condition':condition, 'ordered_pair':label,
                        'planned_n':planned,'recorded_n':len(seq),'valid_n':len(valid),
                        'exact_correct_n':sum(scored),'accuracy':sum(scored)/len(scored) if scored else '',
                        'blending_answers_n':len(reports),'blended_n':sum(reports),
                        'blending_rate':sum(reports)/len(reports) if reports else '',
                        'order_reversal_n':sum(bool_value(r.get('order_reversal',False)) for r in valid),
                        'timeout_n':sum(bool_value(r.get('response_timeout',False)) for r in valid),
                        'observed_host_gap_n':intervals['n'],'observed_host_gap_mean_sec':intervals['mean'],
                        'observed_host_gap_sd_sec':intervals['sd']}
            overall.append(summary(subset,expected,'ALL'))
            for pair in ORDERED_ADJACENT_PAIRS:
                name='-'.join(pair)
                sel=[r for r in subset if r['expected_finger_sequence']==name]
                planned_n=metadata['config']['pair_rounds']//2
                detailed.append(summary(sel,planned_n,name))
    if not session_reports:raise ValueError('No hardware-mode v1.8 metadata found; verify input directory')
    if len({r['session_id'] for r in session_reports})!=len(session_reports):raise ValueError('Duplicate session ID')
    write_csv(output_dir/'session_integrity.csv',session_reports)
    write_csv(output_dir/'timing_summary.csv',overall)
    write_csv(output_dir/'timing_by_pair.csv',detailed)
    report={'sessions':session_reports,'complete_session_count':sum(r['complete_pair_protocol'] for r in session_reports),
      'interpretation':'One person with repeated trials, not independent people. Difference is descriptive only. START/DONE do not measure physical skin onset.',
      'primary_outcome':'Self-reported blending yes / blending answers, by condition.',
      'secondary_outcomes':['exact ordered-pair accuracy','order reversals','response timeouts','host command interval']}
    if len(session_reports)==1:
        b,longer=[next(r for r in overall if r['condition']==x) for x in CONDITIONS]
        if b['blending_rate']!='' and longer['blending_rate']!='':
            report['within_session_blending_long_minus_baseline']=longer['blending_rate']-b['blending_rate']
        if b['accuracy']!='' and longer['accuracy']!='':
            report['within_session_accuracy_long_minus_baseline']=longer['accuracy']-b['accuracy']
    (output_dir/'analysis_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('analysis_output'))
    args=parser.parse_args()
    print(json.dumps(analyze(args.input,args.output),indent=2))
