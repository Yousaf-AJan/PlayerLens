"""Pilot-only local human annotation. No predictions, models, or external requests."""

import argparse
from pathlib import Path

import pandas as pd
import streamlit as st

from playerlens.annotation import (TOPICS, OPINIONS, FLAGS, configuration_id, read_json,
                                   reserve_groups, restore_backup, save_annotation)
from playerlens.preparation_report import load_prepared
from playerlens.text_preparation import digest


def app(prepared, annotations):
    st.title('PlayerLens — pilot annotation')
    st.caption('Provisional taxonomy • human labels • no model predictions')
    try:
        run, tables = load_prepared(prepared)
        pilot = [r for r in tables['sampling_manifest'] if r['cohort']=='pilot' and r['split']=='development']
        if not pilot:
            raise ValueError('No pilot reviews available')
        folder = Path(annotations)/'development'
        reviewed = sum(read_json(folder/(r['review_id']+'.json')).get('status')=='reviewed'
                       for r in pilot if (folder/(r['review_id']+'.json')).exists())
        st.write(f'Pilot progress: {reviewed}/{len(pilot)} reviewed')
        ids = [r['review_id'] for r in pilot]
        selected = st.selectbox('Review to open', ids)
        confirmed = st.checkbox('I saved my work or accept discarding unsaved edits')
        if 'active_review' not in st.session_state:
            st.session_state.active_review = ids[0]
        if st.button('Open selected review'):
            if confirmed:
                st.session_state.active_review = selected
            else:
                st.warning('Save your work and confirm before changing reviews.')
        review_id = st.session_state.active_review
        if review_id not in ids:
            raise ValueError('Review is outside this pilot')
        meta = next(r for r in pilot if r['review_id']==review_id)
        reserve_groups(run['exclusions_path'], [r['review_id'] for r in tables['groups'] if r['group_id']==meta['group_id']])
        review = next(r for r in tables['reviews'] if r['review_id']==review_id)
        passages = [p for p in tables['passages'] if p['review_id']==review_id]
        path = folder/(review_id+'.json')
        saved = read_json(path) if path.exists() else {}
        revision_key = 'revision-'+review_id
        if revision_key not in st.session_state:
            st.session_state[revision_key] = saved.get('revision',0)
        if saved and (saved.get('run_id') != digest(str(run['outputs'])) or saved.get('configuration_id') != configuration_id()):
            raise ValueError('Saved annotation belongs to changed preparation/guidelines; explicit re-review is needed')
        st.subheader('Original review '+review_id)
        st.text(review['original'])
        for i,p in enumerate(passages,1):
            with st.expander(f'Passage {i} · characters {p["start"]}:{p["end"]}'):
                st.text(p['original'])
                if p.get('list_heading'):
                    st.caption('List heading: '+p['list_heading'])
                st.caption('Context (neighboring passages included)')
                st.text(review['original'][p['context_start']:p['context_end']])
        rows = []
        p_numbers = {p['passage_id']:i for i,p in enumerate(passages,1)}
        for label in saved.get('labels',[]):
            for evidence in label.get('evidence',[]) or [{}]:
                rows.append(dict(topic=label['topic'],feature=label.get('feature',''),opinion=label['opinion'],
                                 passage=p_numbers.get(evidence.get('passage_id'),1),quote=evidence.get('quote',''),
                                 occurrence=1,evidence_opinion=evidence.get('opinion',label['opinion'])))
        columns = ['topic','feature','opinion','passage','quote','occurrence','evidence_opinion']
        st.info('One row per evidence span. Repeat a topic with the same overall opinion for additional evidence. '
                'Use mixed overall opinion when evidence includes praise and criticism. Blank quote selects the whole passage.')
        with st.form('annotation-'+review_id):
            edited = st.data_editor(pd.DataFrame(rows,columns=columns), num_rows='dynamic', key='rows-'+review_id,
                column_config={
                    'topic':st.column_config.SelectboxColumn(options=TOPICS+['General feedback','Other specific feature']),
                    'opinion':st.column_config.SelectboxColumn(options=OPINIONS),
                    'evidence_opinion':st.column_config.SelectboxColumn(options=OPINIONS),
                    'passage':st.column_config.NumberColumn(min_value=1,max_value=max(1,len(passages)),step=1),
                    'occurrence':st.column_config.NumberColumn(min_value=1,step=1)})
            flags = st.multiselect('Content flags / no usable label reason', FLAGS, default=saved.get('flags',[]))
            notes = st.text_area('Notes (required for ambiguous/off-topic decisions)',value=saved.get('notes',''))
            pending = st.checkbox('I still have unresolved annotation questions',value=saved.get('needs_review',False))
            draft = st.form_submit_button('Save draft')
            complete = st.form_submit_button('Mark reviewed')
        if draft or complete:
            try:
                labels = {}
                for row in edited.fillna('').to_dict('records'):
                    if not any(str(v).strip() for v in row.values()):
                        continue
                    topic, feature = row['topic'], str(row['feature']).strip()
                    key = (topic,feature if topic=='Other specific feature' else '')
                    label = labels.setdefault(key,dict(topic=topic,feature=feature,opinion=row['opinion'],evidence=[]))
                    if label['opinion'] != row['opinion']:
                        raise ValueError('Repeated topic rows need the same overall opinion')
                    if row['passage'] != '':
                        p = passages[int(row['passage'])-1]
                        quote = row['quote'] or p['original']
                        occurrence = int(row['occurrence'] or 1)
                        offsets, start = [], 0
                        while quote and (at := p['original'].find(quote,start)) >= 0:
                            offsets.append(at)
                            start = at+1
                        if not 1 <= occurrence <= len(offsets):
                            raise ValueError('Quotation/occurrence does not match the passage')
                        start = p['start']+offsets[occurrence-1]
                        label['evidence'].append(dict(passage_id=p['passage_id'], start=start,end=start+len(quote),quote=quote,
                                                      opinion=row['evidence_opinion'] or row['opinion']))
                record = dict(review_id=review_id,text_sha256=digest(review['original']),configuration_id=configuration_id(),
                              run_id=digest(str(run['outputs'])), status='reviewed' if complete else 'draft',labels=list(labels.values()),
                              flags=flags,notes=notes,needs_review=pending)
                saved_record = save_annotation(path,record,review,passages,st.session_state[revision_key])
                st.session_state[revision_key] = saved_record['revision']
                st.success('Saved '+record['status']+'. Reopen or rerun to refresh progress.')
            except (ValueError,IndexError,OSError) as exc:
                st.error(str(exc))
        with st.expander('Comparison metadata — not aspect ground truth'):
            st.write('Steam recommended:',review['recommended'])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        st.error(f'Cannot open annotation workspace: {exc}. No data was replaced.')
        st.caption('For corrupt JSON, inspect the .json.bak copy. Explicit restore_backup(path) preserves the damaged file.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared',default='data/processed/m3-ready')
    parser.add_argument('--annotations',default='data/annotations/m3')
    args = parser.parse_args()
    app(args.prepared,args.annotations)
