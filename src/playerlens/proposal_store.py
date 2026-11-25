"""Immutable proposal runs and separately saved assisted decisions; test access stays locked."""

from datetime import datetime, timezone
import json
from pathlib import Path

from playerlens.annotation import (atomic_json, configuration_id, read_json, reserve_groups,
                                   save_annotation, validate_annotation)
from playerlens.preparation_report import file_hash, load_prepared
from playerlens.proposals import engine_id, propose_review
from playerlens.text_preparation import digest


def preparation_id(run):
    return digest(json.dumps(run['outputs'],sort_keys=True))


def generate_proposals(prepared, output, cohort='pilot'):
    run, tables = load_prepared(prepared)
    output = Path(output).resolve()
    source_parent = Path(run['source']).resolve().parent
    if output==source_parent or source_parent in output.parents or output==Path(prepared).resolve() or Path(prepared).resolve() in output.parents:
        raise ValueError('Proposals must be outside source/preparation directories')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Choose a fresh proposal output directory')
    if cohort not in ('pilot','development'):
        raise ValueError('Only development proposals are authorized')
    selected = [r for r in tables['sampling_manifest'] if r['split']=='development' and
                (r['cohort']=='pilot' if cohort=='pilot' else r['cohort'] is not None)]
    ids = {r['review_id'] for r in selected}
    rows = []
    for review in tables['reviews']:
        if review['review_id'] in ids:
            passages = [p for p in tables['passages'] if p['review_id']==review['review_id']]
            rows.append(propose_review(review,passages))
    output.mkdir(parents=True,exist_ok=True)
    with (output/'proposals.jsonl').open('w',encoding='utf-8',newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row,sort_keys=True,ensure_ascii=True)+'\n')
    manifest = dict(complete=True,record_kind='machine_proposal',preparation_id=preparation_id(run),
                    configuration_id=configuration_id(),engine_id=engine_id(),cohort=cohort,count=len(rows),
                    proposals_sha256=file_hash(output/'proposals.jsonl'),
                    created_at_utc=datetime.now(timezone.utc).isoformat(),eligible_as_reference=False)
    atomic_json(output/'run.json',manifest)
    return {'reviews':len(rows),'cards':sum(len(r['cards']) for r in rows),
            'abstained_cards':sum(c['prediction_state']=='abstained' for r in rows for c in r['cards'])}


def load_proposals(path, prepared_run, sampling_manifest):
    path = Path(path)
    run = read_json(path/'run.json')
    if not (run.get('complete') is True and run.get('record_kind')=='machine_proposal' and
            run.get('preparation_id')==preparation_id(prepared_run) and
            run.get('configuration_id')==configuration_id() and run.get('engine_id')==engine_id() and
            run.get('proposals_sha256')==file_hash(path/'proposals.jsonl')):
        raise ValueError('Missing, stale, or mismatched proposals; create a fresh run')
    rows = [json.loads(line) for line in (path/'proposals.jsonl').read_text(encoding='utf-8').splitlines()]
    allowed = {r['review_id'] for r in sampling_manifest if r['split']=='development' and r['cohort'] is not None}
    if len(rows)!=run['count'] or len({r['review_id'] for r in rows})!=len(rows) or any(r['review_id'] not in allowed for r in rows):
        raise ValueError('Proposal membership violates development isolation')
    return run, {r['review_id']:r for r in rows}


def eligible_reference(record):
    """Neither reviewed status nor a human approval can erase visible-proposal provenance."""
    return bool(record.get('record_kind')=='independent_reference' and record.get('proposal_visible') is False
                and record.get('status')=='reviewed' and record.get('independence_verified') is True
                and not record.get('proposal_run_id') and not record.get('decisions'))


def save_assisted(path, record, review, passages, prepared_run, membership, expected_revision=0):
    if membership['review_id']!=review['review_id'] or membership['split']!='development':
        raise ValueError('Assisted review is development-only')
    if record.get('record_kind')!='assisted_review' or record.get('proposal_visible') is not True or record.get('eligible_as_reference') is not False:
        raise ValueError('Assisted provenance cannot be promoted to reference data')
    if record.get('preparation_id')!=preparation_id(prepared_run) or not record.get('proposal_run_id'):
        raise ValueError('Assisted preparation/proposal identity mismatch')
    if record['status']=='reviewed' and not record.get('full_review_checked'):
        raise ValueError('Read the full original and check for missing aspects first')
    for decision in record.get('decisions',[]):
        if decision.get('action') not in ('approve','correct','reject','defer'):
            raise ValueError('Invalid card decision')
        if record['status']=='reviewed' and decision['action']=='defer':
            raise ValueError('Deferred decisions remain drafts')
    return save_annotation(path,record,review,passages,expected_revision)


def save_feedback(path, notes, membership):
    if membership['split']!='development':
        raise ValueError('Feedback is development-only')
    if not notes.strip():
        raise ValueError('Enter feedback before saving')
    path = Path(path)
    records = read_json(path) if path.exists() else []
    records.append(dict(review_id=membership['review_id'],split='development',notes=notes,
                        at_utc=datetime.now(timezone.utc).isoformat()))
    atomic_json(path,records)
