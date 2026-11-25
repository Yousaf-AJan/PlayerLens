import json
import pytest
from playerlens.cli import main
from playerlens.preparation_report import load_prepared, prepare_run


def test_prepare_deterministic_integrity_and_source(csv_factory,tmp_path):
    source=csv_factory([{'review':'Synthetic combat is fun.'},{'review':'  '}])
    before=source.read_bytes()
    a,b=tmp_path/'a',tmp_path/'b'
    ledger=tmp_path/'exclusions.json'
    prepare_run(source,tmp_path/'prime',ledger)
    prepare_run(source,a,ledger)
    prepare_run(source,b,ledger)
    for p in a.iterdir():
        if p.name != 'run.json':
            assert p.read_bytes()==(b/p.name).read_bytes()
    run,tables=load_prepared(a)
    assert run['complete'] and len(tables['reviews'])==2
    assert source.read_bytes()==before
    with pytest.raises(ValueError): prepare_run(source,a,ledger)
    (a/'passages.jsonl').write_text('changed')
    with pytest.raises(ValueError,match='checksum'): load_prepared(a)


def test_cli_gates_errors_and_source_protection(csv_factory,tmp_path):
    source=csv_factory()
    assert main(['prepare','--input',str(source),'--output',str(source.parent/'bad')])==2
    assert main(['annotate','--split','test'])==2
    assert main(['freeze-annotations'])==2
    invalid=csv_factory([{'votes_up':'invalid'}])
    assert main(['prepare','--input',str(invalid),'--output',str(tmp_path/'bad')])==2
    assert not (tmp_path/'bad').exists()


def test_launch_enforces_localhost_and_telemetry(csv_factory,tmp_path,monkeypatch):
    import subprocess
    source=csv_factory()
    output=tmp_path/'prepared'
    prepare_run(source,output,tmp_path/'ledger.json')
    calls=[]
    monkeypatch.setattr(subprocess,'call',lambda args: calls.append(args) or 0)
    assert main(['annotate','--mode','manual','--prepared',str(output)])==0
    assert '--server.address=127.0.0.1' in calls[0]
    assert '--browser.gatherUsageStats=false' in calls[0]
