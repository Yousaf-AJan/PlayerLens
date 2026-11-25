"""Conservative derived text and lossless source-span passages; no model tokenizer."""

import hashlib
import re
import unicodedata

VERSION = 1


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def prepare_text(text: str) -> str:
    text = unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\[/?(?:b|i|u|h[1-6])\]', '', text, flags=re.I)
    return re.sub(r'[^\S\n]+', ' ', text).strip()


def extract_passages(review_id: str, text: str, max_words: int = 120) -> list[dict]:
    """Partition original characters; context is separate, so overlap is not counted twice."""
    if max_words < 1:
        raise ValueError('max_words must be positive')
    if not text:
        return []
    words = list(re.finditer(r'\S+', text))
    cuts = [0]
    while len(words) and sum(w.start() >= cuts[-1] for w in words) > max_words:
        remaining = [w for w in words if w.start() >= cuts[-1]]
        window = remaining[:max_words]
        # Favor paragraph/sentence ends without splitting on conjunctions or list lines.
        candidates = [w.end() for w in window[max_words // 2:]
                      if re.search(r'[!?]$|(?<!\b[A-Z])\.$', w.group())
                      or '\n\n' in text[w.end():remaining[window.index(w)+1].start()]]
        cut = candidates[-1] if candidates else remaining[max_words].start()
        if cut <= cuts[-1]:
            cut = remaining[max_words].start()
        cuts.append(cut)
    cuts.append(len(text))
    passages = []
    for ordinal, (start, end) in enumerate(zip(cuts, cuts[1:])):
        passages.append(dict(review_id=review_id, passage_id=digest(f'{VERSION}:{review_id}:{digest(text)}:{start}:{end}'),
                             ordinal=ordinal, start=start, end=end, original=text[start:end],
                             prepared=prepare_text(text[start:end])))
    for i, passage in enumerate(passages):
        # Adjacent cores keep context available, including list headings and contrasts.
        passage.update(context_start=passages[max(0, i-1)]['start'],
                       context_end=passages[min(len(passages)-1, i+1)]['end'],
                       previous=passages[i-1]['passage_id'] if i else None,
                       next=passages[i+1]['passage_id'] if i+1 < len(passages) else None)
        headings = list(re.finditer(r'(?m)^(?![ \t]*(?:[☑☐✓✗]|\[[ xX]\]))([^\r\n]+)\r?\n(?=[ \t]*[☑☐✓✗]|[ \t]*\[[ xX]\])', text[:passage['end']]))
        passage['list_heading'] = headings[-1].group(1) if headings else None
    return passages
