from difflib import SequenceMatcher
import pytest
from playerlens.sampling import build_groups, related_edges, sample_reviews
from playerlens.validation import normalise_for_duplicates


@pytest.mark.parametrize('a,b',[
    ('The combat is good, the controls are responsive, and exploration feels rewarding.', 'The combat is bad, the controls are responsive, and exploration feels rewarding.'),
    ('The combat is good, the controls are responsive, and exploration feels rewarding.', 'The combat is not good, the controls are responsive, and exploration feels rewarding.'),
    ('Combat\n☑ Satisfying\n☐ Frustrating\nControls\n☑ Responsive\n☐ Awkward','Combat\n☐ Satisfying\n☑ Frustrating\nControls\n☐ Responsive\n☑ Awkward')])
def test_opinion_reversal_grouped_without_text_replacement(a,b):
    rows = [dict(review_id='1',original=a),dict(review_id='2',original=b)]
    groups=build_groups(rows)
    assert groups[0]['group_id']==groups[1]['group_id']
    assert normalise_for_duplicates(a)!=normalise_for_duplicates(b)
    assert rows[0]['original']==a and rows[1]['original']==b


def test_candidate_filter_matches_brute_force():
    keys=sorted(['good combat','not good combat','good combat!', 'bad combat','gg','gg!','never crashes','never crash','plain different sentence'])
    expected=set()
    for i,a in enumerate(keys):
        for j,b in enumerate(keys[:i]):
            for w in (2,3):
                if w==2 and max(len(a),len(b))>24: continue
                gram=lambda t:{t[k:k+w] for k in range(max(1,len(t)-w+1))}
                x,y=gram(a),gram(b)
                if len(x&y)/len(x|y)>=.5 and SequenceMatcher(None,b,a,autojunk=False).ratio()>=.8:
                    expected.add(tuple(sorted((i,j))))
    assert {tuple(sorted((i,j))) for i,j,_ in related_edges(keys)}==expected


def test_sampling_is_grouped_deterministic_and_excluded():
    rows=[dict(review_id=str(i),original=f'unique {i}',recommended=i%3==0) for i in range(250)]
    groups=[dict(review_id=str(i),group_id=str(i//2)) for i in range(250)]
    first=sample_reviews(rows,groups,['0'])
    assert first==sample_reviews(rows[::-1],groups[::-1],['0'])
    splits={}
    for r in first:
        assert splits.setdefault(r['group_id'],r['split'])==r['split']
    assert all(r['split']=='development' for r in first if r['review_id'] in ['0','1'] or r['cohort']=='pilot')
    assert sum(r['cohort']=='representative' for r in first)==120
    assert len({r['review_id'] for r in first})==250


def test_normalized_and_blank_groups():
    rows=[dict(review_id=str(i),original=t) for i,t in enumerate(['Good GAME','good game','',' '])]
    g=build_groups(rows)
    assert g[0]['group_id']==g[1]['group_id']
    assert g[2]['group_id']!=g[3]['group_id']


def test_extended_ledger_does_not_change_pilot():
    rows=[dict(review_id=str(i),original=f'unique {i}',recommended=False) for i in range(230)]
    groups=[dict(review_id=str(i),group_id=str(i//2)) for i in range(230)]
    first=sample_reviews(rows,groups,['1'],pilot_ids=['1'])
    expanded=[r['review_id'] for r in first if r['development_only']]
    assert first==sample_reviews(rows,groups,expanded,pilot_ids=['1'])
