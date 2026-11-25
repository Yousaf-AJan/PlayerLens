from copy import deepcopy
from pathlib import Path

import pytest

from playerlens.annotation import configuration_id, read_json
from playerlens.preparation_report import load_prepared
from playerlens.proposal_store import (eligible_reference, generate_proposals, load_proposals,
                                      preparation_id, save_assisted, save_feedback)
from playerlens.text_preparation import digest


def setup(csv_factory,tmp_path):
    from playerlens.preparation_report import prepare_run
    source=csv_factory([{'review':'Combat is good.'},{'review':'Unfamiliar specific feedback.'}])
    prepared=tmp_path/'prepared'
    prepare_run(source,prepared,tmp_path/'ledger.json')
    output=tmp_path/'proposals'
    generate_proposals(prepared,output)
    run,tables=load_prepared(prepared)
    return prepared,output,run,tables


def test_immutable_deterministic_proposals_and_staleness(csv_factory,tmp_path):
    prepared,output,run,tables=setup(csv_factory,tmp_path)
    second=tmp_path/'second'
    generate_proposals(prepared,second)
    assert (output/'proposals.jsonl').read_bytes()==(second/'proposals.jsonl').read_bytes()
    with pytest.raises(ValueError,match='fresh'): generate_proposals(prepared,output)
    _,rows=load_proposals(output,run,tables['sampling_manifest'])
    assert len(rows)==2
    (output/'proposals.jsonl').write_text('changed')
    with pytest.raises(ValueError): load_proposals(output,run,tables['sampling_manifest'])


def test_decisions_do_not_modify_proposals_or_become_references(csv_factory,tmp_path):
    prepared,output,run,t=setup(csv_factory,tmp_path)
    before=(output/'proposals.jsonl').read_bytes()
    review=t['reviews'][0]
    passages=[p for p in t['passages'] if p['review_id']==review['review_id']]
    membership=next(r for r in t['sampling_manifest'] if r['review_id']==review['review_id'])
    a=dict(review_id=review['review_id'],text_sha256=digest(review['original']),configuration_id=configuration_id(),
           record_kind='assisted_review',proposal_visible=True,eligible_as_reference=False,preparation_id=preparation_id(run),
           proposal_run_id='synthetic-run',status='draft',full_review_checked=False,labels=[],flags=[],needs_review=False,
           decisions=[dict(card_id='test',action='defer')])
    path=tmp_path/'decisions'/'001.json'
    saved=save_assisted(path,a,review,passages,run,membership)
    assert not eligible_reference(saved)
    a.update(status='reviewed',flags=['insufficient_detail'])
    with pytest.raises(ValueError,match='full original'): save_assisted(path,a,review,passages,run,membership,1)
    a['full_review_checked']=True
    with pytest.raises(ValueError,match='Deferred'): save_assisted(path,a,review,passages,run,membership,1)
    a['decisions'][0]['action']='reject'
    save_assisted(path,a,review,passages,run,membership,1)
    assert (output/'proposals.jsonl').read_bytes()==before
    assert not eligible_reference(read_json(path))
    bad=deepcopy(a); bad['record_kind']='independent_reference'
    with pytest.raises(ValueError,match='provenance'): save_assisted(path,bad,review,passages,run,membership,2)
    with pytest.raises(ValueError,match='development-only'): save_assisted(path,a,review,passages,run,membership|{'split':'test'},2)


def test_proposal_and_feedback_test_gates(csv_factory,tmp_path):
    prepared,output,run,t=setup(csv_factory,tmp_path)
    with pytest.raises(ValueError): generate_proposals(prepared,tmp_path/'bad','test')
    with pytest.raises(ValueError): save_feedback(tmp_path/'feedback.json','issue',dict(review_id='x',split='test'))
    save_feedback(tmp_path/'feedback.json','Issue after first review',dict(review_id='001',split='development'))
    assert len(read_json(tmp_path/'feedback.json'))==1
    assert not eligible_reference(dict(status='reviewed'))


def test_cli_assisted_launch_and_reference_lock(csv_factory,tmp_path,monkeypatch):
    import subprocess
    from playerlens.cli import main
    prepared,output,run,t=setup(csv_factory,tmp_path)
    calls=[]
    monkeypatch.setattr(subprocess,'call',lambda a:calls.append(a) or 0)
    assert main(['annotate','--prepared',str(prepared),'--proposals',str(output),'--decisions',str(tmp_path/'decisions')])==0
    assert 'assisted_app.py' in calls[0][5]
    assert '--server.address=127.0.0.1' in calls[0]
    assert main(['annotate','--mode','reference'])==2
    assert main(['annotate','--split','test'])==2
