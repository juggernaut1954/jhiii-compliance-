"""ARA V0.5 pilot worker: Federal Register publication discovery only.
Run from a separate scheduled process, not the Streamlit web request loop.
Does not assert applicability or legal obligations.
"""
import os
from datetime import datetime, timedelta, timezone
import requests
from sqlalchemy import create_engine, text

API = 'https://www.federalregister.gov/api/v1/documents.json'


def poll():
    db_url = os.environ['DATABASE_URL']
    engine = create_engine(db_url, pool_pre_ping=True)
    since = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    params = {
        'conditions[publication_date][gte]': since,
        'conditions[agencies][]': 'financial-crimes-enforcement-network',
        'per_page': 100,
        'order': 'newest',
        'fields[]': ['document_number', 'title', 'html_url', 'publication_date', 'type'],
    }
    inserted = 0
    error = None
    with engine.begin() as conn:
        run_id = conn.execute(text("INSERT INTO public.regulatory_poll_runs(source,status) VALUES ('federal_register_fincen','running') RETURNING id")).scalar_one()
    try:
        for page in range(1, 6):
            response = requests.get(API, params={**params, 'page': page}, timeout=25)
            response.raise_for_status()
            payload = response.json()
            records = payload.get('results', [])
            with engine.begin() as conn:
                for doc in records:
                    result = conn.execute(text('''
                        INSERT INTO public.regulatory_events
                          (source,source_id,title,url,publication_date,document_type)
                        VALUES (:source,:source_id,:title,:url,:publication_date,:document_type)
                        ON CONFLICT (source,source_id) DO NOTHING RETURNING id
                    '''), {
                        'source':'federal_register_fincen',
                        'source_id':doc['document_number'],
                        'title':doc['title'],
                        'url':doc['html_url'],
                        'publication_date':doc.get('publication_date'),
                        'document_type':doc.get('type')
                    })
                    if result.scalar_one_or_none() is not None:
                        inserted += 1
            if not records or page >= int(payload.get('total_pages', 1)):
                break
        status = 'ok'
    except Exception as exc:
        status = 'error'
        error = str(exc)[:1000]
        raise
    finally:
        with engine.begin() as conn:
            conn.execute(text('''UPDATE public.regulatory_poll_runs
              SET finished_at=now(),status=:status,discovered_count=:count,error=:error WHERE id=:id'''),
              {'status':status,'count':inserted,'error':error,'id':run_id})
    print(f'Federal Register FinCEN poll complete: {inserted} new records')


if __name__ == '__main__':
    poll()
