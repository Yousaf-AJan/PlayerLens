import pytest
from playerlens.text_preparation import extract_passages, prepare_text


@pytest.mark.parametrize('text',['','  \n','NA','Not bad!','[b]Never[/b] crashes.\r\n☑ good\n☐ bad','e\u0301 😀','word '*1000,'x'*30000,'Great. Another crash.'])
def test_lossless_stable_spans(text):
    passages = extract_passages('001',text)
    assert ''.join(p['original'] for p in passages)==text
    assert passages==extract_passages('001',text)
    for p in passages:
        assert text[p['start']:p['end']]==p['original']
        assert p['context_start'] <= p['start'] < p['end'] <= p['context_end']


def test_preparation_keeps_meaning_markers():
    assert prepare_text('[b]Not[/b] bad\r\n☑ yes\n☐ no [quote]never[/quote]')=='Not bad\n☑ yes\n☐ no [quote]never[/quote]'
    assert extract_passages('001','text')[0]['passage_id']!=extract_passages('002','text')[0]['passage_id']


def test_invalid_word_limit():
    with pytest.raises(ValueError):
        extract_passages('1','x',0)


def test_long_checklist_keeps_heading_and_tail():
    text='Combat\n'+'☑ Synthetic positive entry\n'*200+'☐ Negative option'
    passages=extract_passages('1',text)
    assert len(passages)>2 and all(p['list_heading']=='Combat' for p in passages)
    assert ''.join(p['original'] for p in passages)==text
