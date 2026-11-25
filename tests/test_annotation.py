import pytest
from playerlens.annotation import configuration_id, read_json, reserve_groups, restore_backup, save_annotation, validate_annotation
from playerlens.text_preparation import digest, extract_passages


def example():
    review=dict(review_id='001',original='Combat is fun but repetitive.')
    passages=extract_passages('001',review['original'])
    evidence=dict(passage_id=passages[0]['passage_id'],start=0,end=len(review['original']),quote=review['original'],opinion='mixed')
    record=dict(review_id='001',text_sha256=digest(review['original']),configuration_id=configuration_id(),status='reviewed',
                flags=[],notes='',needs_review=False,labels=[dict(topic='Combat/difficulty',opinion='mixed',evidence=[evidence])])
    return review,passages,record


def test_save_edit_backup_resume_stale_and_recovery(tmp_path):
    review,passages,record=example()
    path=tmp_path/'001.json'
    one=save_annotation(path,record,review,passages)
    assert read_json(path)==one
    record['status']='draft'
    two=save_annotation(path,record,review,passages,1)
    assert two['revision']==2 and read_json(path.with_suffix('.json.bak'))==one
    with pytest.raises(ValueError,match='Stale'): save_annotation(path,record,review,passages,1)
    path.write_text('corrupt')
    with pytest.raises(ValueError): read_json(path)
    restore_backup(path)
    assert read_json(path)==one and path.with_suffix('.json.damaged').read_text()=='corrupt'


@pytest.mark.parametrize('change',['identity','configuration','no_evidence','quote','mixed','pending','missing','other','duplicate'])
def test_reject_invalid_labels(change):
    r,p,a=example()
    if change=='identity': a['text_sha256']='wrong'
    if change=='configuration': a['configuration_id']='wrong'
    if change=='no_evidence': a['labels'][0]['evidence']=[]
    if change=='quote': a['labels'][0]['evidence'][0]['quote']='wrong'
    if change=='mixed': a['labels'][0]['evidence'][0]['opinion']='praise'
    if change=='pending': a['needs_review']=True
    if change=='missing': a['labels']=[]
    if change=='other': a['labels'][0]['topic']='Other specific feature'
    if change=='duplicate': a['labels']*=2
    with pytest.raises(ValueError): validate_annotation(a,r,p)


def test_draft_and_uncertain_distinct():
    r,p,a=example()
    a.update(status='draft',labels=[],needs_review=True)
    validate_annotation(a,r,p)
    a.update(status='reviewed',needs_review=False,flags=['insufficient_detail'])
    validate_annotation(a,r,p)


def test_failed_replace_preserves_previous(tmp_path,monkeypatch):
    import playerlens.annotation as module
    r,p,a=example()
    path=tmp_path/'label.json'
    save_annotation(path,a,r,p)
    before=path.read_bytes()
    monkeypatch.setattr(module.os,'replace',lambda *_: (_ for _ in ()).throw(PermissionError('synthetic')))
    with pytest.raises(PermissionError): save_annotation(path,a,r,p,1)
    assert path.read_bytes()==before


def test_exclusions_union(tmp_path):
    path=tmp_path/'ledger.json'
    reserve_groups(path,['001','002'])
    reserve_groups(path,['003'])
    assert read_json(path)['review_ids']==['001','002','003']


def test_incomplete_draft_is_not_ground_truth():
    r,p,a=example()
    a.update(status='draft',labels=[dict(topic='Other specific feature',feature='',opinion='',evidence=[])])
    validate_annotation(a,r,p)
    a['status']='reviewed'
    with pytest.raises(ValueError): validate_annotation(a,r,p)
