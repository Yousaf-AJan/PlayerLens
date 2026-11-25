from pathlib import Path
from streamlit.testing.v1 import AppTest
from playerlens.annotation import read_json
from playerlens.preparation_report import prepare_run


def test_synthetic_interface_save_resume_and_review(csv_factory,tmp_path):
    source=csv_factory([{'review':'Synthetic combat feels fun.'},{'review':'Synthetic blank of detail.'}])
    prepared=tmp_path/'prepared'
    labels=tmp_path/'labels'
    prepare_run(source,prepared,tmp_path/'ledger.json')
    script=f'from playerlens.annotation_app import app\napp({str(prepared)!r},{str(labels)!r})'
    app=AppTest.from_string(script).run(timeout=30)
    assert not app.exception
    assert any('Synthetic' in e.value for e in app.text)
    app.multiselect[0].select('insufficient_detail')
    next(b for b in app.button if b.label=='Save draft').click().run()
    assert not app.exception and app.success
    saved=list((labels/'development').glob('*.json'))
    assert len(saved)==1 and read_json(saved[0])['status']=='draft'
    resumed=AppTest.from_string(script).run(timeout=30)
    assert 'insufficient_detail' in resumed.multiselect[0].value
    next(b for b in resumed.button if b.label=='Mark reviewed').click().run()
    assert not resumed.exception and read_json(saved[0])['status']=='reviewed'


def test_synthetic_aspect_evidence_editing(csv_factory,tmp_path,monkeypatch):
    import pandas as pd
    import streamlit as st
    source=csv_factory([{'review':'Combat is fun but repetitive.'}])
    prepared=tmp_path/'prepared'
    labels=tmp_path/'labels'
    prepare_run(source,prepared,tmp_path/'ledger.json')
    # Inject synthetic editor input; exercise the form's grouping and span resolution.
    rows=[dict(topic='Combat/difficulty',feature='',opinion='mixed',passage=1,quote=q,occurrence=1,evidence_opinion=o)
          for q,o in [('Combat is fun','praise'),('repetitive','criticism')]]
    monkeypatch.setattr(st,'data_editor',lambda *args,**kwargs:pd.DataFrame(rows))
    script=f'from playerlens.annotation_app import app\napp({str(prepared)!r},{str(labels)!r})'
    app=AppTest.from_string(script).run(timeout=30)
    next(b for b in app.button if b.label=='Mark reviewed').click().run()
    assert not app.exception and app.success
    saved=read_json(labels/'development/001.json')
    assert saved['labels'][0]['opinion']=='mixed'
    assert len(saved['labels'][0]['evidence'])==2
    app.text_area[0].set_value('Editing synthetic saved work')
    next(b for b in app.button if b.label=='Save draft').click().run()
    assert read_json(labels/'development/001.json')['status']=='draft'
    assert read_json(labels/'development/001.json')['revision']==2
