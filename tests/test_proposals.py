import pytest

from playerlens.annotation import TOPICS
from playerlens.proposals import propose_review
from playerlens.text_preparation import extract_passages


def propose(text, recommended=True):
    review=dict(review_id='001',original=text,recommended=recommended)
    return propose_review(review,extract_passages('001',text))


@pytest.mark.parametrize('text,topic,opinion',[
    ('Combat is fun.',TOPICS[1],'praise'),
    ('Combat is not fun.',TOPICS[1],'criticism'),
    ('Combat is not bad.',TOPICS[1],'praise'),
    ('It never crashes.',TOPICS[0],'praise'),
    ('It crashes constantly.',TOPICS[0],'criticism'),
    ('Maybe combat is good.',TOPICS[1],'uncertain'),
    ('The game supports co-op.',TOPICS[5],'neutral'),
    ('The soundtrack is amazing.','Other specific feature','praise'),
    ('Great game.','General feedback','praise'),
    ('Combat is fun but combat becomes repetitive.',TOPICS[1],'mixed')])
def test_supported_proposals_and_original_evidence(text,topic,opinion):
    result=propose(text)
    card=next(c for c in result['cards'] if c['topic']==topic)
    assert card['opinion']==opinion
    assert result['record_kind']=='machine_proposal' and result['eligible_as_reference'] is False
    for e in card['evidence']:
        assert text[e['start']:e['end']]==e['quote']


@pytest.mark.parametrize('text',[
    'Combat exists.', 'Combat and controls are great.', 'Combat is great /s',
    'Combat\n☑ Good\n☐ Bad', '[quote]Combat is great[/quote]',
    'Unlike another game, combat is great.', 'Combat is not only fun.',
    'Combat is not never good.'])
def test_abstention_is_not_reviewer_uncertainty(text):
    result=propose(text)
    assert result['cards']
    assert all(c['prediction_state']=='abstained' and c['opinion'] is None for c in result['cards'])


def test_repeated_cues_do_not_carry_negation_to_later_matches():
    assert propose("Combat isn't good, although really good.")['cards'][0]['opinion']=='mixed'


def test_known_other_game_attribution_abstains():
    assert propose('Monster Hunter combat is great.')['cards'][0]['opinion'] is None


def test_multiple_aspects_long_tail_and_recommendation_independence():
    text='Combat is fun. Performance is terrible. '+'Unrelated words. '*200+'Camera is good.'
    a,b=propose(text,True),propose(text,False)
    assert a==b
    assert {c['topic'] for c in a['cards']}=={TOPICS[0],TOPICS[1],TOPICS[4]}


@pytest.mark.parametrize('text',['','   ','yes','Something unfamiliar.'])
def test_no_proposal_does_not_claim_no_aspects(text):
    result=propose(text)
    assert result['cards']==[] and result['outcome']=='no_supported_proposal'
