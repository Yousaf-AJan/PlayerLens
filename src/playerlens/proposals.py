"""Transparent development-only label suggestions, never human reference labels."""

import re

from playerlens.annotation import TOPICS
from playerlens.text_preparation import digest

VERSION = 'rules-v1'
ASPECTS = {
    TOPICS[0]: r'\b(?:performance|fps|frame\s*rate|stutter\w*|crash\w*|bugs?|stability)\b',
    TOPICS[1]: r'\b(?:combat|boss(?:es)?|difficult(?:y)?|dodg\w*|enemy|enemies|fight\w*)\b',
    TOPICS[2]: r'\b(?:explor\w*|world|discovery|traversal|environments?)\b',
    TOPICS[3]: r'\b(?:story|lore|narrative|characters?|storytelling)\b',
    TOPICS[4]: r'\b(?:controls?|camera|inputs?|targeting|lock.on)\b',
    TOPICS[5]: r'\b(?:multiplayer|co.op|pvp|invasions?|online play|matchmaking)\b',
    TOPICS[6]: r'\b(?:progression|leveling|levelling|level.up|upgrades?|builds?|rune costs?)\b',
}
OTHER = {'audio': r'\b(?:audio|music|soundtrack)\b', 'price': r'\b(?:price|value for money)\b'}
PRAISE = r'\b(?:good|great|excellent|amazing|responsive|beautiful|fun|enjoyable|rewarding|smooth|stable)\b'
CRITICISM = r'\b(?:bad|terrible|awful|boring|repetitive|unresponsive|tedious|broken|stutter\w*|crash\w*)\b'
UNCERTAIN = r'\b(?:maybe|perhaps|uncertain|unsure)\b|\b(?:cannot|can.t) tell\b'
NEUTRAL = r'\b(?:has|includes|supports)\b'


def engine_id():
    # Include vocabulary and implementation: changes invalidate proposals without changing source preparation.
    from pathlib import Path
    return digest(Path(__file__).read_text(encoding='utf-8'))


def clauses(text):
    """Return source offsets without replacing or re-normalizing original characters."""
    start = 0
    for match in re.finditer(r'(?<=[.!?;])\s+|\n+|\b(?:but|however|yet)\b', text, re.I):
        if text[start:match.start()].strip():
            yield start, match.start()
        start = match.end()
    if text[start:].strip():
        yield start, len(text)


def opinion_for(clause, aspect_match, ambiguous=False):
    """Bounded scope; abstention is separate from reviewer-expressed uncertainty."""
    if ambiguous or re.search(r'\bnot only\b', clause, re.I):
        return None, 'ambiguous_scope'
    if re.search(UNCERTAIN, clause, re.I):
        return 'uncertain', 'explicit_reviewer_uncertainty'
    cues = []
    for pattern, stance in ((PRAISE,'praise'), (CRITICISM,'criticism')):
        for match in re.finditer(pattern, clause, re.I):
            local_stance = stance
            between = clause[min(match.end(),aspect_match.end()):max(match.start(),aspect_match.start())]
            if len(re.findall(r"\b\w+\b",between)) > 6:
                continue
            before = re.findall(r"[\w]+(?:['’][\w]+)?",clause[:match.start()].casefold())[-3:]
            negations = sum(t in {'not','no','never',"doesn't","don't","isn't","wasn't",'without',"can't",'cannot'} for t in before)
            if negations > 1:
                return None, 'complex_negation'
            if negations:
                local_stance = 'criticism' if local_stance=='praise' else 'praise'
            cues.append(local_stance)
    if set(cues)=={'praise','criticism'}:
        return 'mixed', 'conflicting_supported_cues'
    if cues:
        return cues[0], 'local_polarity_with_bounded_negation'
    if re.search(NEUTRAL,clause,re.I):
        return 'neutral', 'explicit_descriptive_construction'
    return None, 'no_supported_opinion'


def propose_review(review, passages):
    """Inputs deliberately exclude recommendation metadata from all inference decisions."""
    text, review_id = review['original'], review['review_id']
    labels = {}
    unsafe_format = bool(re.search(r'/s\b|yeah right|\[/?(?:quote|s|strike)\]|[☑☐✓✗]|\[[ xX]\]',text,re.I))
    other_game = bool(re.search(r'\b(?:another game|other games?|compared to|unlike|Monster Hunter|Splatoon|Phantasy Star|Valheim|Deep Rock Galactic|Risk of Rain)\b',text,re.I))
    for passage in passages:
        for a,b in clauses(passage['original']):
            clause = passage['original'][a:b]
            matches = [(topic,'',re.search(pattern,clause,re.I)) for topic,pattern in ASPECTS.items()]
            matches += [('Other specific feature',feature,re.search(pattern,clause,re.I)) for feature,pattern in OTHER.items()]
            matches = [(t,f,m) for t,f,m in matches if m]
            if not matches and not labels and re.fullmatch(r'\s*(?:this |the )?(?:game is |great game|good game|bad game|terrible game)[\w\s.!]*',clause,re.I):
                matches = [('General feedback','',re.search(r'\bgame\b',clause,re.I))]
            for topic,feature,match in matches:
                stance, reason = opinion_for(clause, match, len(matches)>1)
                if unsafe_format or other_game:
                    stance, reason = None, 'format_sarcasm_or_attribution_requires_review'
                start, end = passage['start']+a, passage['start']+b
                while start < end and text[start].isspace(): start += 1
                while end > start and text[end-1].isspace(): end -= 1
                evidence = dict(passage_id=passage['passage_id'],start=start,end=end,quote=text[start:end],
                                opinion=stance, rule_id=reason)
                entry = labels.setdefault((topic,feature),dict(topic=topic,feature=feature,evidence=[]))
                entry['evidence'].append(evidence)
    cards = []
    for (topic,feature), label in labels.items():
        stances = {e['opinion'] for e in label['evidence']}
        if None in stances:
            stance = None
        elif 'mixed' in stances or {'praise','criticism'} <= stances:
            stance = 'mixed'
        elif len(stances)==1:
            stance = next(iter(stances))
        else:
            stance = None
        cards.append(label | dict(card_id=digest(f'{review_id}:{topic}:{feature}'),opinion=stance,
                                 prediction_state='proposed' if stance else 'abstained',
                                 abstention_reason=None if stance else 'unresolved_or_unsupported_opinion'))
    return dict(schema_version=1,record_kind='machine_proposal',review_id=review_id,text_sha256=digest(text),
                engine_version=VERSION,engine_id=engine_id(),cards=cards,
                outcome='candidates_found' if cards else 'no_supported_proposal',
                eligible_as_reference=False)
