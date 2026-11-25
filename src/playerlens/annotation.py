"""Local human annotation validation and crash-resistant single-session storage."""

import json
import os
from pathlib import Path
import tempfile

from playerlens.text_preparation import digest

TOPICS = ['Performance/stability', 'Combat/difficulty', 'Exploration/world design',
          'Story/lore', 'Controls/camera', 'Online play / Multiplayer', 'Progression/build variety']
OPINIONS = ['praise', 'criticism', 'mixed', 'neutral', 'uncertain']
FLAGS = ['insufficient_detail', 'off_topic', 'ambiguous', 'blank']


def configuration_id():
    guidelines = Path(__file__).resolve().parents[2] / 'docs/ANNOTATION.md'
    return digest(json.dumps(TOPICS+OPINIONS) + guidelines.read_text(encoding='utf-8'))


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            name = handle.name
            json.dump(value, handle, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def reserve_groups(path, ids):
    existing = read_json(path) if Path(path).exists() else {'review_ids': []}
    atomic_json(path, {'review_ids': sorted(set(existing['review_ids']) | set(ids))})


def validate_annotation(record, review, passages):
    if record.get('review_id') != review['review_id'] or record.get('text_sha256') != digest(review['original']):
        raise ValueError('Annotation/source identity mismatch')
    if record.get('configuration_id') != configuration_id():
        raise ValueError('Guidelines/taxonomy changed; explicit re-review is required')
    if record.get('status') not in ('draft', 'reviewed'):
        raise ValueError('Invalid review status')
    flags = record.get('flags', [])
    if not isinstance(flags, list) or set(flags)-set(FLAGS):
        raise ValueError('Invalid content flags')
    labels = record.get('labels', [])
    keys = set()
    by_passage = {p['passage_id']:p for p in passages}
    for label in labels:
        topic, opinion = label.get('topic'), label.get('opinion')
        allowed_topics = TOPICS+['General feedback','Other specific feature']
        if record['status']=='draft':
            allowed_topics = allowed_topics+['',None]
        if topic not in allowed_topics or opinion not in OPINIONS+(['',None] if record['status']=='draft' else []):
            raise ValueError('Choose a valid topic and opinion')
        feature = label.get('feature', '').strip()
        if topic == 'Other specific feature' and not feature and record['status']=='reviewed':
            raise ValueError('Name the other specific feature')
        key = (topic, feature if topic == 'Other specific feature' else '')
        if key in keys:
            raise ValueError('Use one overall opinion per topic/feature; retain multiple evidence entries')
        keys.add(key)
        evidence = label.get('evidence', [])
        if record['status'] == 'reviewed' and not evidence:
            raise ValueError('Every reviewed label needs source evidence')
        for span in evidence:
            start, end = span.get('start'), span.get('end')
            passage = by_passage.get(span.get('passage_id'))
            if not (isinstance(start,int) and isinstance(end,int) and passage and
                    passage['start'] <= start < end <= passage['end'] and
                    review['original'][start:end] == span.get('quote') and span['quote'].strip()):
                raise ValueError('Evidence must match a nonblank original passage span')
            if span.get('opinion') not in OPINIONS+(['',None] if record['status']=='draft' else []):
                raise ValueError('Invalid evidence opinion')
        if record['status']=='reviewed' and opinion=='mixed':
            stances = {s['opinion'] for s in evidence}
            if not ('mixed' in stances or {'praise','criticism'} <= stances):
                raise ValueError('Mixed needs both sides or explicitly mixed evidence')
    if record['status']=='reviewed':
        if record.get('needs_review'):
            raise ValueError('Resolve annotator questions before marking reviewed')
        if not labels and not flags:
            raise ValueError('Label the review or give a no-usable-label reason')
        if ('ambiguous' in flags or 'off_topic' in flags) and not record.get('notes','').strip():
            raise ValueError('Explain ambiguous/off-topic decisions')


def save_annotation(path, record, review, passages, expected_revision=0):
    path = Path(path)
    validate_annotation(record, review, passages)
    previous = read_json(path) if path.exists() else None
    if (previous or {}).get('revision',0) != expected_revision:
        raise ValueError('Stale revision: reload before saving')
    if previous:
        if previous.get('review_id') != record['review_id']:
            raise ValueError('Existing annotation identity mismatch')
        atomic_json(path.with_suffix('.json.bak'), previous)
    saved = record | {'revision': expected_revision+1, 'schema_version':1}
    atomic_json(path, saved)
    return saved


def restore_backup(path):
    """Explicit recovery preserves the damaged file; never runs automatically."""
    path = Path(path)
    backup = read_json(path.with_suffix('.json.bak'))
    damaged = path.with_suffix('.json.damaged')
    if damaged.exists():
        raise ValueError('Preserve/rename the previous damaged copy before recovery')
    if path.exists():
        path.replace(damaged)
    atomic_json(path, backup)
