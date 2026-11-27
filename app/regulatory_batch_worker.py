
"""ARA: retrieve outstanding FinCEN publications in bounded batches."""
import argparse
import os
import time

from sqlalchemy import create_engine, text
from app.regulatory_storage_worker import SOURCE, store


def pending_documents(limit):
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
            return conn.execute(text('''
                SELECT e.source_id
                FROM public.regulatory_events e
                WHERE e.source = :source
                  AND NOT EXISTS (
                    SELECT 1
                    FROM public.regulatory_documents d
                    WHERE d.regulatory_event_id = e.id
                  )
                ORDER BY e.publication_date DESC NULLS LAST, e.id
                LIMIT :limit
            '''), {
                'source': SOURCE,
                'limit': limit,
            }).scalars().all()
    finally:
        engine.dispose()


def report_failure(number, exc):
    original = getattr(exc, 'orig', exc)
    sqlstate = getattr(original, 'sqlstate', None)
    diag = getattr(original, 'diag', None)

    print(
        f'Document {number}: FAILED ({type(exc).__name__})',
        flush=True,
    )

    print(
        f'Database error type: {type(original).__name__}',
        flush=True,
    )

    print(
        f'SQLSTATE: {sqlstate or "unavailable"}',
        flush=True,
    )

    if diag is not None:
        for field in (
            'schema_name',
            'table_name',
            'column_name',
            'datatype_name',
            'constraint_name',
        ):
            value = getattr(diag, field, None)
            if value:
                print(f'{field}: {value}', flush=True)

    # Never print raw exceptions, SQL parameters,
    # credentials, or regulatory document contents.


def run(limit):
    documents = pending_documents(limit)
    succeeded = 0
    failed = 0

    print(
        f'ARA batch: {len(documents)} pending publications',
        flush=True,
    )

    for index, number in enumerate(documents):
        if index:
            time.sleep(1)

        try:
            store(number)
            succeeded += 1

        except Exception as exc:
            failed += 1
            report_failure(number, exc)

    print(
        f'ARA batch complete: attempted={len(documents)}, '
        f'succeeded={succeeded}, failed={failed}',
        flush=True,
    )

    return 1 if failed else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()

    if not 1 <= args.limit <= 100:
        parser.error('--limit must be between 1 and 100')

    raise SystemExit(run(args.limit))
