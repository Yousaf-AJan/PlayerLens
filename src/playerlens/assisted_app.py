"""Development-only approve/correct cards with prominent missing-aspect and feedback controls."""

import argparse
from pathlib import Path

import streamlit as st

from playerlens.annotation import TOPICS, OPINIONS, FLAGS, configuration_id, read_json, reserve_groups
from playerlens.preparation_report import file_hash, load_prepared
from playerlens.proposal_store import load_proposals, preparation_id, save_assisted, save_feedback
from playerlens.text_preparation import digest


def correction_controls(key, default, review, passages):
    """All corrections use original passage offsets; no generated quotations."""
    choices = ['Choose an aspect']+TOPICS+['General feedback','Other specific feature']
    chosen = default.get('topic') or 'Choose an aspect'
    topic = st.selectbox('Aspect',choices,index=choices.index(chosen),key=key+'topic')
    feature = st.text_input('Other feature name',value=default.get('feature',''),key=key+'feature') if topic=='Other specific feature' else ''
    opinions = ['Choose an opinion']+OPINIONS
    opinion = st.selectbox('Overall opinion',opinions,index=opinions.index(default.get('opinion')) if default.get('opinion') in OPINIONS else 0,key=key+'opinion')
    ids = [p['passage_id'] for p in passages]
    suggested = list(dict.fromkeys(e['passage_id'] for e in default.get('evidence',[]) if e['passage_id'] in ids))
    selected = st.multiselect('Supporting passages',ids,default=suggested,
                             format_func=lambda i:f"Passage {ids.index(i)+1}: "+next(p['original'] for p in passages if p['passage_id']==i)[:100],key=key+'passages')
    evidence = []
    for passage_id in selected:
        p = next(p for p in passages if p['passage_id']==passage_id)
        st.text(p['original'])
        quote = st.text_input('Exact quote (blank uses this whole passage)',key=key+passage_id+'quote')
        selected_text = quote or p['original']
        positions = [i for i in range(len(p['original'])) if selected_text and p['original'].startswith(selected_text,i)]
        occurrence = st.selectbox('Quote occurrence',list(range(1,len(positions)+1)) or [0],key=key+passage_id+'occurrence')
        stance = st.selectbox('Evidence opinion',opinions,index=opinions.index(opinion),key=key+passage_id+'stance')
        if not positions:
            raise ValueError('Quotation must occur in the original passage')
        start = p['start']+positions[occurrence-1]
        evidence.append(dict(passage_id=passage_id,start=start,end=start+len(selected_text),quote=selected_text,
                             opinion=stance if stance in OPINIONS else ''))
    return dict(topic=topic if topic!='Choose an aspect' else '',feature=feature,opinion=opinion if opinion in OPINIONS else '',evidence=evidence)


def app(prepared, proposals, decisions):
    st.title('PlayerLens — assisted pilot')
    st.caption('Provisional categories · rule suggestions, not ground truth · development only')
    st.info('Try 3–5 reviews, then pause and share feedback below. There is no requirement to finish all 20 before improving usability.')
    try:
        run,tables = load_prepared(prepared)
        proposal_run, candidates = load_proposals(proposals,run,tables['sampling_manifest'])
        pilot = [r for r in tables['sampling_manifest'] if r['cohort']=='pilot' and r['split']=='development']
        if not pilot or any(r['review_id'] not in candidates for r in pilot):
            raise ValueError('Pilot proposals missing; run the propose command first')
        root = Path(decisions)
        source_parent = Path(run['source']).resolve().parent
        if root.resolve()==source_parent or source_parent in root.resolve().parents:
            raise ValueError('Decision files must be outside the raw source directory')
        for immutable in (Path(prepared).resolve(),Path(proposals).resolve()):
            if root.resolve()==immutable or immutable in root.resolve().parents:
                raise ValueError('Decisions must be outside immutable preparation/proposal directories')
        folder = root/'assisted'/'development'
        ids = [r['review_id'] for r in pilot]
        checked = sum(read_json(folder/(i+'.json')).get('status')=='reviewed' for i in ids if (folder/(i+'.json')).exists())
        st.write(f'{checked}/{len(ids)} assisted reviews checked — independent reference labels: none generated here')
        selected = st.selectbox('Pilot review',ids)
        discard = st.checkbox('My work is saved, or I accept discarding unsaved changes')
        if 'assisted_active' not in st.session_state:
            st.session_state.assisted_active = ids[0]
        if st.button('Open selected review'):
            if discard: st.session_state.assisted_active = selected
            else: st.warning('Save a draft and confirm before navigating.')
        review_id = st.session_state.assisted_active
        if review_id not in ids: raise ValueError('Review is outside the development pilot')
        membership = next(r for r in pilot if r['review_id']==review_id)
        reserve_groups(run['exclusions_path'],[r['review_id'] for r in tables['groups'] if r['group_id']==membership['group_id']])
        review = next(r for r in tables['reviews'] if r['review_id']==review_id)
        passages = [p for p in tables['passages'] if p['review_id']==review_id]
        proposal = candidates[review_id]
        if proposal['text_sha256']!=digest(review['original']): raise ValueError('Proposal/source mismatch')
        path = folder/(review_id+'.json')
        saved = read_json(path) if path.exists() else {}
        proposal_id = file_hash(Path(proposals)/'run.json')
        if saved and (saved.get('proposal_run_id')!=proposal_id or saved.get('preparation_id')!=preparation_id(run)
                      or saved.get('configuration_id')!=configuration_id()):
            raise ValueError('Saved decisions belong to another configuration; preserve them and choose a new decision workspace')
        key = review_id+'-'+proposal_id[:12]+'-'
        revision_key = key+'revision'
        st.session_state.setdefault(revision_key,saved.get('revision',0))
        st.subheader('1. Read the complete original and look for missed aspects')
        left,right = st.columns([3,1])
        with left: st.text(review['original'])
        additions_key = key+'additions'
        st.session_state.setdefault(additions_key,[d for d in saved.get('decisions',[]) if d.get('added_by_human')])
        with right:
            st.write('Notice a missing aspect?')
            if st.button('Add missing aspect',type='primary'):
                st.session_state[additions_key].append(dict(card_id='human-'+str(len(st.session_state[additions_key])),added_by_human=True,
                                                           action='correct',label={}))
            st.caption('This is part of normal review, including when the rules found nothing.')
        for i,p in enumerate(passages,1):
            with st.expander(f'Original passage {i} (with context)'):
                st.text(p['original'])
                if p.get('list_heading'): st.caption('List heading: '+p['list_heading'])
                st.text(review['original'][p['context_start']:p['context_end']])
        st.subheader('2. Approve, correct, reject, or defer suggestions')
        if not proposal['cards']: st.warning('No supported proposal. This does not mean the review contains no aspects. Use Add missing aspect above.')
        saved_decisions = {d['card_id']:d for d in saved.get('decisions',[])}
        human_decisions,labels,problems = [],[],[]
        cards = proposal['cards']+[dict(card_id=d['card_id'],added_by_human=True,**(d.get('label') or {})) for d in st.session_state[additions_key]]
        for card in cards:
            cid = card['card_id']
            prior = saved_decisions.get(cid,{})
            added = card.get('added_by_human',False)
            st.markdown('**'+('Missing aspect added by you' if added else card['topic'])+'**')
            if not added:
                st.write('Suggested opinion:',card.get('opinion') or 'ABSTAIN — needs your judgment')
                for e in card['evidence']:
                    st.text(e['quote'])
                    st.caption('Rule: '+e['rule_id'])
            actions = ['defer','approve','correct','reject'] if not added else ['correct','defer','reject']
            default_action = prior.get('action','correct' if added else 'defer')
            action = st.radio('Decision',actions,index=actions.index(default_action),horizontal=True,key=key+cid+'action')
            label = None
            if action=='approve':
                if card.get('opinion') is None:
                    problems.append('Abstained opinions cannot be approved; choose Correct or Defer.')
                    st.warning(problems[-1])
                else:
                    label = {k:card[k] for k in ('topic','feature','opinion','evidence')}
            elif action=='correct':
                try:
                    label = correction_controls(key+cid,prior.get('label') or card,review,passages)
                except ValueError as exc:
                    problems.append(str(exc)); st.warning(str(exc))
            if label: labels.append(label)
            human_decisions.append(dict(card_id=cid,action=action,label=label,added_by_human=added))
        flags = st.multiselect('Content flags / reason for no usable label',FLAGS,default=saved.get('flags',[]),key=key+'flags')
        notes = st.text_area('Annotation notes',value=saved.get('notes',''),key=key+'notes')
        full_check = st.checkbox('I read the complete original and checked for missing aspects',value=saved.get('full_review_checked',False),key=key+'full')
        pending = st.checkbox('I still have unresolved annotation questions',value=saved.get('needs_review',False),key=key+'pending')
        draft = st.button('Save draft')
        complete = st.button('Save checked assisted review')
        if draft or complete:
            try:
                if problems: raise ValueError('Resolve invalid corrections before saving: '+'; '.join(problems))
                record = dict(record_kind='assisted_review',proposal_visible=True,eligible_as_reference=False,
                              review_id=review_id,text_sha256=digest(review['original']),configuration_id=configuration_id(),
                              preparation_id=preparation_id(run),proposal_run_id=proposal_id,
                              status='reviewed' if complete else 'draft',full_review_checked=full_check,
                              labels=labels,flags=flags,notes=notes,needs_review=pending,decisions=human_decisions)
                result = save_assisted(path,record,review,passages,run,membership,st.session_state[revision_key])
                st.session_state[revision_key] = result['revision']
                st.success('Assisted decision saved. It remains ineligible as an independent reference.')
            except (ValueError,OSError) as exc: st.error(str(exc))
        st.subheader('3. Pause and give feedback whenever you want')
        st.caption('Save your annotation first. Feedback and refinements stay development-only; no need to complete the pilot.')
        feedback = st.text_area('What should we improve?',key=key+'feedback')
        if st.button('Save pilot feedback'):
            try:
                save_feedback(root/'pilot_feedback.json',feedback,membership)
                st.success('Feedback saved locally. You can stop now and share your concerns in chat.')
            except (ValueError,OSError) as exc: st.error(str(exc))
    except (ValueError,OSError,KeyError,TypeError) as exc:
        st.error(f'Cannot open assisted workspace: {exc}. Existing files were not replaced.')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared',default='data/processed/m3-ready')
    parser.add_argument('--proposals',default='data/proposals/m3-assisted-v1')
    parser.add_argument('--decisions',default='data/annotations/m3-assisted-v1')
    args = parser.parse_args()
    app(args.prepared,args.proposals,args.decisions)
