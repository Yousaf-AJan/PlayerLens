"""Textual relatedness is a leakage safeguard, never an opinion label."""

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from math import ceil
import re

from playerlens.text_preparation import digest
from playerlens.validation import normalise_for_duplicates

SETTINGS = dict(seed=42, candidate_jaccard=0.5, related_similarity=0.8,
                near_similarity=0.9, short_bigram_max_characters=24)


def related_edges(keys: list[str]):
    """Rare-first prefix filtering retains all pairs meeting the shingle threshold."""
    for width, indices in ((3, range(len(keys))), (2, [i for i,k in enumerate(keys) if len(k) <= 24])):
        sets = {i: {keys[i][j:j+width] for j in range(max(1, len(keys[i])-width+1))} for i in indices}
        frequency = Counter(g for grams in sets.values() for g in grams)
        postings = defaultdict(list)
        for i in sorted(sets, key=lambda i: (len(sets[i]), keys[i])):
            grams = sets[i]
            prefix = sorted(grams, key=lambda g: (frequency[g], g))[:len(grams)-ceil(.5*len(grams))+1]
            candidates = {j for g in prefix for j in postings[g] if len(sets[j]) >= .5*len(grams)}
            for j in sorted(candidates):
                if len(grams & sets[j]) / len(grams | sets[j]) >= .5:
                    a, b = sorted((keys[i], keys[j]))
                    score = SequenceMatcher(None, a, b, autojunk=False).ratio()
                    if score >= .8:
                        yield i, j, score
            for g in prefix:
                postings[g].append(i)


def build_groups(reviews: list[dict]) -> list[dict]:
    members = defaultdict(list)
    for row in reviews:
        key = normalise_for_duplicates(row['original'])
        members[key if key else '\x00'+row['review_id']].append(row['review_id'])
    keys = sorted(k for k in members if not k.startswith('\x00'))
    graph = {k: set() for k in members}
    for i, j, _ in related_edges(keys):
        graph[keys[i]].add(keys[j])
        graph[keys[j]].add(keys[i])
    output, seen = [], set()
    for key in sorted(graph):
        if key in seen:
            continue
        stack, ids = [key], []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            ids.extend(members[current])
            stack.extend(sorted(graph[current]-seen))
        group_id = digest('\n'.join(sorted(ids)))
        output.extend(dict(review_id=i, group_id=group_id) for i in sorted(ids))
    return sorted(output, key=lambda r: r['review_id'])


def sample_reviews(reviews, groups, exclusions, seed=42, pilot_ids=None):
    by_id = {r['review_id']: r for r in reviews}
    group = {r['review_id']: r['group_id'] for r in groups}
    selected = {}
    rank = lambda stage, i: digest(f'{seed}:{stage}:{i}')
    def take(stage, candidates, target):
        for i in sorted(set(candidates)-selected.keys(), key=lambda i: rank(stage, i))[:target]:
            selected[i] = stage
    known = sorted(set(exclusions) & by_id.keys())
    pilot_known = known if pilot_ids is None else sorted(set(pilot_ids) & by_id.keys())
    for i in pilot_known[:20]:
        selected[i] = 'pilot'
    pilot_groups = {group[i] for i in selected}
    for i in sorted(by_id, key=lambda i: rank('pilot', i)):
        if sum(v == 'pilot' for v in selected.values()) >= 20:
            break
        if group[i] not in pilot_groups:
            selected[i] = 'pilot'
            pilot_groups.add(group[i])
    take('representative', by_id, 120)
    take('not_recommended_enrichment', [i for i,r in by_id.items() if r['recommended'] is False], 40)
    patterns = [r'/s\b|yeah right', r'\b(?:not|never|no|don.t)\b', r'\b(?:but|however|yet)\b', None]
    reasons = {}
    for number, pattern in enumerate(patterns):
        candidates = [i for i,r in by_id.items() if (re.search(pattern, r['original'], re.I) if pattern else 0 < len(r['original'].split()) <= 5)]
        for i in candidates:
            reasons.setdefault(i, []).append(number)
        take('challenge', candidates, 5)
    take('challenge', reasons, 20-sum(v == 'challenge' for v in selected.values()))
    forced = {group[i] for i in known} | pilot_groups
    counts = Counter()
    split = {g:'development' for g in forced}
    for i,c in selected.items():
        if group[i] in forced and c != 'pilot':
            counts[c, 'development'] += 1
    pending = set(group[i] for i in selected)-forced
    for g in sorted(pending, key=lambda g: (-sum(group[i] == g for i in selected), rank('split', g))):
        contributions = Counter(c for i,c in selected.items() if group[i] == g)
        costs = {s: sum((counts[c,s]+n)**2-counts[c,s]**2 for c,n in contributions.items()) for s in ('development','test')}
        side = min(costs, key=lambda s: (costs[s], rank(g, s)))
        split[g] = side
        for c,n in contributions.items():
            counts[c,side] += n
    for g in set(group.values())-split.keys():
        split[g] = 'development' if int(rank('unsampled',g),16)%2 else 'test'
    return [dict(review_id=i, group_id=group[i], split=split[group[i]], cohort=selected.get(i),
                 development_only=group[i] in forced, challenge_indicators=reasons.get(i, []) if selected.get(i)=='challenge' else [])
            for i in sorted(by_id)]
