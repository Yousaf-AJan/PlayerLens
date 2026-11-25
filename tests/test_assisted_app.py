from pathlib import Path

from streamlit.testing.v1 import AppTest

from playerlens.annotation import read_json
from playerlens.preparation_report import prepare_run
from playerlens.proposal_store import generate_proposals, eligible_reference


def workspace(csv_factory,tmp_path,text='Combat is fun.'):
    source=csv_factory([{'review':text}])
    prepared=tmp_path/'prepared'
    proposals=tmp_path/'proposals'
    decisions=tmp_path/'decisions'
    prepare_run(source,prepared,tmp_path/'ledger.json')
    generate_proposals(prepared,proposals)
    script=f'from playerlens.assisted_app import app\napp({str(prepared)!r},{str(proposals)!r},{str(decisions)!r})'
    return AppTest.from_string(script).run(timeout=30),decisions,script,proposals


def button(app,label):
    return next(b for b in app.button if b.label==label)


def test_approve_resume_feedback_and_full_review_gate(csv_factory,tmp_path):
    app,decisions,script,proposals=workspace(csv_factory,tmp_path)
    before=(proposals/'proposals.jsonl').read_bytes()
    assert not app.exception
    assert button(app,'Add missing aspect')
    app.radio[0].set_value('approve').run()
    button(app,'Save checked assisted review').click().run()
    assert any('full original' in e.value for e in app.error)
    next(c for c in app.checkbox if 'complete original' in c.label).check()
    button(app,'Save checked assisted review').click().run()
    path=decisions/'assisted/development/001.json'
    saved=read_json(path)
    assert saved['status']=='reviewed' and saved['labels'][0]['opinion']=='praise'
    assert not eligible_reference(saved)
    resumed=AppTest.from_string(script).run(timeout=30)
    assert resumed.radio[0].value=='approve'
    next(t for t in resumed.text_area if t.label=='What should we improve?').set_value('Feedback after one review')
    button(resumed,'Save pilot feedback').click().run()
    assert len(read_json(decisions/'pilot_feedback.json'))==1
    assert (proposals/'proposals.jsonl').read_bytes()==before


def test_add_missing_aspect_from_no_proposals(csv_factory,tmp_path):
    app,decisions,script,_=workspace(csv_factory,tmp_path,'Synthetic bright melodies delight me.')
    assert not app.exception and app.warning
    button(app,'Add missing aspect').click().run()
    assert not app.exception
    next(s for s in app.selectbox if s.label=='Aspect').select('Other specific feature').run()
    next(t for t in app.text_input if t.label=='Other feature name').set_value('audio')
    next(s for s in app.selectbox if s.label=='Overall opinion').select('praise')
    passage=app.multiselect[0].options[0]
    # Select by underlying ID (the multiselect displays a formatted source snippet).
    from playerlens.preparation_report import load_prepared
    run,t=load_prepared(tmp_path/'prepared')
    app.multiselect[0].select(t['passages'][0]['passage_id']).run()
    assert not app.exception
    next(s for s in app.selectbox if s.label=='Evidence opinion').select('praise')
    next(c for c in app.checkbox if 'complete original' in c.label).check()
    button(app,'Save checked assisted review').click().run()
    assert not app.exception
    record=read_json(decisions/'assisted/development/001.json')
    assert record['labels'][0]['feature']=='audio' and record['decisions'][0]['added_by_human']


def test_abstain_cannot_approve_and_defer_can_resume(csv_factory,tmp_path):
    app,decisions,script,_=workspace(csv_factory,tmp_path,'Combat exists.')
    app.radio[0].set_value('approve').run()
    button(app,'Save draft').click().run()
    assert app.error
    app.radio[0].set_value('defer').run()
    button(app,'Save draft').click().run()
    assert read_json(decisions/'assisted/development/001.json')['status']=='draft'
