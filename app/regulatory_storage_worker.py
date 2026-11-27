"""ARA: store one retrieved Federal Register document without assessing applicability."""
import argparse
import hashlib
import json
import os

from sqlalchemy import create_engine, text
from app.regulatory_document_worker import retrieve

SOURCE = 'federal_register_fincen'


def store(document_number):
    url = os.environ['DATABASE_URL']
    for prefix in ('postgres://', 'postgresql://'):
        if url.startswith(prefix):
            url = 'postgresql+psycopg://' + url[len(prefix):]
            break
    engine = create_engine(url, pool_pre_ping=True,
                           connect_args={'sslmode': 'require', 'connect_timeout': 10})
    try:
        with engine.connect() as conn:
            event_id = conn.execute(text('''
                SELECT id FROM public.regulatory_events
                WHERE source = :source AND source_id = :number
            '''), {'source': SOURCE, 'number': document_number}).scalar_one()
        doc = retrieve(document_number)
        body = doc['full_text']
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        metadata = {k: v for k, v in doc.items() if k != 'full_text'}
        with engine.begin() as conn:
            stored_id = conn.execute(text('''
                INSERT INTO public.regulatory_documents (
                    regulatory_event_id, document_number, title,
                    document_type, citation, agencies, publication_date,
                    effective_date, official_url, full_text_url,
                    document_text, raw_metadata, content_sha256, retrieved_at
                ) VALUES (
                    :event_id, :number, :title, :kind, :citation,
                    CAST(:agencies AS jsonb), CAST(:published AS date),
                    CAST(:effective AS date), :official, :full_url,
                    :body, CAST(:metadata AS jsonb), :digest,
                    CAST(:retrieved AS timestamptz)
                ) ON CONFLICT (regulatory_event_id, content_sha256)
                DO NOTHING RETURNING id
            '''), dict(event_id=event_id, number=document_number,
                       title=doc['title'], kind=doc['document_type'],
                       citation=doc['citation'], agencies=json.dumps(doc['agencies']),
                       published=doc['publication_date'], effective=doc['effective_on'],
                       official=doc['official_url'], full_url=doc['raw_text_url'],
                       body=body, metadata=json.dumps(metadata), digest=digest,
                       retrieved=doc['retrieved_at'])).scalar_one_or_none()
        print(f'Document {document_number}: ' + (f'stored as ID {stored_id}' if stored_id is not None else 'identical text already stored'))
        print(f'Content SHA-256: {digest}; characters: {len(body)}')
    finally:
        engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('document_number')
    args = parser.parse_args()
    store(args.document_number)
