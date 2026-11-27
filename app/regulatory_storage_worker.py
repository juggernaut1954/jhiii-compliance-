"""ARA: store retrieved Federal Register documents with traceable text normalization."""

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

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            'sslmode': 'require',
            'connect_timeout': 10,
        },
    )

    try:
        with engine.connect() as conn:
            event_id = conn.execute(text('''
                SELECT id
                FROM public.regulatory_events
                WHERE source = :source
                  AND source_id = :number
            '''), {
                'source': SOURCE,
                'number': document_number,
            }).scalar_one()

        doc = retrieve(document_number)

        original_body = doc['full_text']

        original_digest = hashlib.sha256(
            original_body.encode('utf-8')
        ).hexdigest()

        null_count = original_body.count('\x00')

        body = original_body.replace('\x00', '')

        if not body.strip():
            raise ValueError(
                'Document text is empty after normalization'
            )

        digest = hashlib.sha256(
            body.encode('utf-8')
        ).hexdigest()

        metadata = {
            k: v for k, v in doc.items()
            if k != 'full_text'
        }

        metadata['text_normalization'] = {
            'method': 'remove_null_characters_only',
            'original_text_sha256': original_digest,
            'stored_text_sha256': digest,
            'original_character_count': len(original_body),
            'stored_character_count': len(body),
            'null_characters_removed': null_count,
        }

        if null_count:
            print(
                f'Document {document_number}: '
                f'removed {null_count} embedded null characters',
                flush=True,
            )

        with engine.begin() as conn:
            stored_id = conn.execute(text('''
                INSERT INTO public.regulatory_documents (
                    regulatory_event_id,
                    document_number,
                    title,
                    document_type,
                    citation,
                    agencies,
                    publication_date,
                    effective_date,
                    official_url,
                    full_text_url,
                    document_text,
                    raw_metadata,
                    content_sha256,
                    retrieved_at
                ) VALUES (
                    :event_id,
                    :number,
                    :title,
                    :kind,
                    :citation,
                    CAST(:agencies AS jsonb),
                    CAST(:published AS date),
                    CAST(:effective AS date),
                    :official,
                    :full_url,
                    :body,
                    CAST(:metadata AS jsonb),
                    :digest,
                    CAST(:retrieved AS timestamptz)
                )
                ON CONFLICT (
                    regulatory_event_id,
                    content_sha256
                )
                DO NOTHING
                RETURNING id
            '''), {
                'event_id': event_id,
                'number': document_number,
                'title': doc['title'],
                'kind': doc['document_type'],
                'citation': doc['citation'],
                'agencies': json.dumps(doc['agencies']),
                'published': doc['publication_date'],
                'effective': doc['effective_on'],
                'official': doc['official_url'],
                'full_url': doc['raw_text_url'],
                'body': body,
                'metadata': json.dumps(metadata),
                'digest': digest,
                'retrieved': doc['retrieved_at'],
            }).scalar_one_or_none()

        if stored_id is not None:
            print(
                f'Document {document_number}: '
                f'stored as ID {stored_id}',
                flush=True,
            )
        else:
            print(
                f'Document {document_number}: '
                'identical text already stored',
                flush=True,
            )

        print(
            f'Original text SHA-256: {original_digest}',
            flush=True,
        )

        print(
            f'Content SHA-256: {digest}; '
            f'characters: {len(body)}',
            flush=True,
        )

    finally:
        engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('document_number')
    args = parser.parse_args()
    store(args.document_number)
