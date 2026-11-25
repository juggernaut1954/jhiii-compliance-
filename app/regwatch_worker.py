
"""ARA V0.5: Federal Register FinCEN discovery worker.

Scheduled publication discovery only.
Does not determine regulatory applicability or compliance.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import create_engine, text

API = "https://www.federalregister.gov/api/v1/documents.json"
SOURCE = "federal_register_fincen"


def poll():
    engine = create_engine(
        os.environ["DATABASE_URL"],
        pool_pre_ping=True,
    )

    since = (
        datetime.now(timezone.utc) - timedelta(days=365)
    ).date().isoformat()

    params = {
        "conditions[publication_date][gte]": since,
        "conditions[agencies][]":
            "financial-crimes-enforcement-network",
        "per_page": 100,
        "order": "newest",
        "fields[]": [
            "document_number",
            "title",
            "html_url",
            "publication_date",
            "type",
        ],
    }

    run_id = None
    inserted = 0
    status = "error"
    error = None

    try:
        with engine.begin() as conn:
            run_id = conn.execute(
                text("""
                    INSERT INTO public.regulatory_poll_runs
                        (source, status)
                    VALUES (:source, 'running')
                    RETURNING id
                """),
                {"source": SOURCE},
            ).scalar_one()

        for page in range(1, 6):
            response = requests.get(
                API,
                params={**params, "page": page},
                timeout=25,
            )
            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload, dict):
                raise RuntimeError(
                    "Federal Register response is not an object"
                )

            if (
                payload.get("count") == 0
                and "results" not in payload
            ):
                records = []
            else:
                records = payload.get("results")
                if not isinstance(records, list):
                    raise RuntimeError(
                        "Unexpected Federal Register response: "
                        f"{str(payload)[:700]}"
                    )

            with engine.begin() as conn:
                for doc in records:
                    required = (
                        "document_number",
                        "title",
                        "html_url",
                    )
                    if (
                        not isinstance(doc, dict)
                        or not all(
                            doc.get(k) for k in required
                        )
                    ):
                        raise ValueError(
                            "Publication missing required fields: "
                            f"{str(doc)[:300]}"
                        )

                    result = conn.execute(
                        text("""
                            INSERT INTO public.regulatory_events
                                (
                                    source,
                                    source_id,
                                    title,
                                    url,
                                    publication_date,
                                    document_type,
                                    raw_metadata
                                )
                            VALUES
                                (
                                    :source,
                                    :source_id,
                                    :title,
                                    :url,
                                    :publication_date,
                                    :document_type,
                                    CAST(:raw_metadata AS jsonb)
                                )
                            ON CONFLICT (source, source_id)
                            DO NOTHING
                            RETURNING id
                        """),
                        {
                            "source": SOURCE,
                            "source_id":
                                doc["document_number"],
                            "title": doc["title"],
                            "url": doc["html_url"],
                            "publication_date":
                                doc.get("publication_date"),
                            "document_type":
                                doc.get("type"),
                            "raw_metadata":
                                json.dumps(doc),
                        },
                    )

                    if (
                        result.scalar_one_or_none()
                        is not None
                    ):
                        inserted += 1

            if (
                not records
                or page >= int(
                    payload.get("total_pages", 1)
                )
            ):
                break

        status = "ok"

    except Exception as exc:
        error = str(exc)[:1000]
        raise

    finally:
        try:
            if run_id is not None:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE public.regulatory_poll_runs
                            SET finished_at = now(),
                                status = :status,
                                discovered_count = :count,
                                error = :error
                            WHERE id = :id
                        """),
                        {
                            "status": status,
                            "count": inserted,
                            "error": error,
                            "id": run_id,
                        },
                    )
        finally:
            engine.dispose()

    print(
        f"Federal Register FinCEN poll complete: "
        f"{inserted} new records"
    )


if __name__ == "__main__":
    poll()
    
