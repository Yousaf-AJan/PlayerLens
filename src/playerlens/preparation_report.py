"""Local artifacts and integrity checks for a completed preparation run."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
from time import perf_counter

from playerlens.annotation import atomic_json, read_json, reserve_groups
from playerlens.eda import DEVELOPMENT_IDS
from playerlens.sampling import SETTINGS, build_groups, sample_reviews
from playerlens.text_preparation import VERSION, extract_passages
from playerlens.validation import validate_csv


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_run(source, output, exclusions):
    source, output, exclusions = map(lambda p: Path(p).resolve(), (source,output,exclusions))
    if output == source.parent or source.parent in output.parents or exclusions == source or source.parent in exclusions.parents:
        raise ValueError('Outputs must be outside the source directory')
    if output == exclusions or output in exclusions.parents:
        raise ValueError('Exclusion ledger must be outside immutable preparation output')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Choose a new or empty preparation output directory')
    tick = perf_counter()
    result = validate_csv(source)
    if result.summary['validation']['error_count']:
        raise ValueError('Resolve source validation errors before annotation preparation')
    reviews = [dict(review_id=row['id'], original=row['review'], recommended=bool(result.validated.at[i,'voted_up']))
               for i,row in result.raw.iterrows()]
    reviews.sort(key=lambda r:r['review_id'])
    passages = [p for r in reviews for p in extract_passages(r['review_id'],r['original'])]
    excluded = set(DEVELOPMENT_IDS)
    if exclusions.exists():
        excluded.update(read_json(exclusions)['review_ids'])
    groups = build_groups(reviews)
    manifest = sample_reviews(reviews, groups, excluded, pilot_ids=DEVELOPMENT_IDS)
    summary = dict(rows=len(reviews), passages=len(passages), groups=len({g['group_id'] for g in groups}),
                   cohorts=dict(Counter(r['cohort'] for r in manifest if r['cohort'])),
                   cohort_splits=dict(Counter(r['cohort']+':'+r['split'] for r in manifest if r['cohort'])),
                   taxonomy_status='provisional', preparation_version=VERSION, settings=SETTINGS,
                   exclusions=sorted(excluded), source_sha256=result.summary['input']['sha256'])
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in [('reviews',reviews),('passages',passages),('groups',groups),('sampling_manifest',manifest)]:
        with (output/(name+'.jsonl')).open('w',encoding='utf-8',newline='\n') as handle:
            for row in rows:
                handle.write(json.dumps(row,sort_keys=True,ensure_ascii=True)+'\n')
    atomic_json(output/'summary.json',summary)
    reserve_groups(exclusions,[r['review_id'] for r in manifest if r['development_only']])
    if file_hash(source) != summary['source_sha256']:
        raise ValueError('Source changed during preparation; incomplete output has no run marker')
    run = dict(complete=True, source_sha256=summary['source_sha256'], source=str(source), exclusions_path=str(exclusions),
               outputs={p.name:file_hash(p) for p in sorted(output.iterdir())},
               finished_at_utc=datetime.now(timezone.utc).isoformat(), seconds=perf_counter()-tick,
               code_sha256={n:file_hash(Path(__file__).with_name(n+'.py')) for n in ('text_preparation','sampling','preparation_report','validation')},
               python=platform.python_version(), dependencies={n:version(n) for n in ('pandas','streamlit')})
    atomic_json(output/'run.json',run)
    return summary


def load_prepared(path):
    path = Path(path)
    run = read_json(path/'run.json')
    if run.get('complete') is not True or set(run['outputs']) != {'reviews.jsonl','passages.jsonl','groups.jsonl','sampling_manifest.jsonl','summary.json'}:
        raise ValueError('Incomplete preparation run')
    for name, checksum in run['outputs'].items():
        if file_hash(path/name) != checksum:
            raise ValueError('Prepared artifact checksum mismatch')
    if file_hash(run['source']) != run['source_sha256']:
        raise ValueError('Source checksum mismatch')
    tables = {name:[json.loads(line) for line in (path/(name+'.jsonl')).read_text(encoding='utf-8').splitlines()]
              for name in ('reviews','passages','sampling_manifest','groups')}
    return run, tables
