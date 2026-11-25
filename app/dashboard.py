import json
import logging
import os
import secrets
from datetime import date, datetime

import requests
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

st.set_page_config(page_title="JH III COMPLIANCE", page_icon="🛡️", layout="wide")
logger = logging.getLogger(__name__)

API_URL = os.getenv("ARA_API_URL", "https://jhiii-compliance.onrender.com").rstrip("/")
API_KEY = os.getenv("ARA_API_KEY", "")
DASHBOARD_PASSWORD = os.getenv("ARA_DASHBOARD_PASSWORD", "")
REVIEWER_PASSWORD = os.getenv("ARA_REVIEWER_PASSWORD", "")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def connection_config():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing from the dashboard Render environment.")
    try:
        url = make_url(DATABASE_URL)
    except Exception as exc:
        raise ValueError("DATABASE_URL is not a valid SQLAlchemy PostgreSQL URL.") from exc
    if url.drivername not in ("postgres", "postgresql", "postgresql+psycopg"):
        raise ValueError("DATABASE_URL must use PostgreSQL and the psycopg driver.")
    if not url.host or not url.database or not url.username:
        raise ValueError("DATABASE_URL is missing a hostname, username, or database name.")
    return url.set(drivername="postgresql+psycopg")


@st.cache_resource(show_spinner=False)
def get_engine():
    return create_engine(
        connection_config(),
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=1,
        pool_timeout=15,
        pool_recycle=1800,
        connect_args={"sslmode": "require", "connect_timeout": 10},
    )


def database_error(exc, operation):
    # Never display or log a connection string, password, or SQL parameters.
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    logger.error("ARA database %s failed: %s; SQLSTATE=%s", operation, type(exc).__name__, sqlstate or "unknown")
    if sqlstate == "3D000":
        st.error(
            "Supabase rejected the requested database (SQLSTATE 3D000). "
            "This cannot be corrected by changing Python driver settings. "
            "Verify that this Render service uses the current Supabase Session Pooler "
            "connection string for the intended project, including the project-specific "
            "username, pooler host, port and database name. Do not create another database."
        )
    elif sqlstate == "28P01":
        st.error("Supabase rejected database authentication (SQLSTATE 28P01). Check the dashboard's database credentials privately.")
    else:
        st.error(f"Database {operation} failed ({type(exc).__name__}). Check Render logs for the SQLSTATE diagnostic.")


def db_read(sql, params=None):
    try:
        with get_engine().connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params or {}).mappings().all()]
    except (SQLAlchemyError, ValueError) as exc:
        if isinstance(exc, ValueError):
            st.error(str(exc))
        else:
            database_error(exc, "read")
        return None


if not DASHBOARD_PASSWORD:
    st.error("Dashboard authentication is not configured.")
    st.stop()

if not st.session_state.get("authenticated", False):
    st.title("JH III COMPLIANCE")
    st.caption("ARA | Assurance · Risk · Automation")
    st.subheader("Demonstration dashboard access")
    with st.form("login_form"):
        entered = st.text_input("Dashboard password", type="password")
        submitted = st.form_submit_button("Sign In")
    if submitted:
        if secrets.compare_digest(entered, DASHBOARD_PASSWORD):
            st.session_state.authenticated = True
            st.rerun()
        st.error("Invalid password")
    st.stop()

if st.sidebar.button("Sign Out"):
    st.session_state.clear()
    st.rerun()

st.title("JH III COMPLIANCE")
st.caption("ARA | Assurance · Risk · Automation")
st.warning("DEMONSTRATION — Not a regulatory compliance certification")

if not API_KEY:
    st.error("ARA_API_KEY is not configured.")
    st.stop()


def api_request(method, endpoint, **kwargs):
    try:
        response = requests.request(
            method,
            f"{API_URL}{endpoint}",
            headers={"X-API-Key": API_KEY},
            timeout=60,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("ARA backend request failed: %s %s (%s)", method, endpoint, type(exc).__name__)
        st.error(f"Backend request failed ({type(exc).__name__}). Check the FastAPI service in Render.")
        return None
    except ValueError:
        logger.warning("ARA backend returned invalid JSON: %s %s", method, endpoint)
        st.error("Backend returned an invalid response.")
        return None


def load_publications():
    return db_read("""
        SELECT id, source_id, title, url, publication_date,
               document_type, review_status, discovered_at
        FROM public.regulatory_events
        WHERE source = 'federal_register_fincen'
        ORDER BY publication_date DESC NULLS LAST, discovered_at DESC
        LIMIT 1000
    """)


def render_regulatory_intelligence():
    st.subheader("Regulatory Intelligence")
    st.caption("FinCEN publications discovered in the Federal Register. Discovery does not establish applicability.")
    records = load_publications()
    if records is None:
        return
    if not records:
        st.info("No regulatory publications have been stored yet.")
        return

    c1, c2 = st.columns(2)
    c1.metric("Publications loaded", len(records))
    c2.metric("Awaiting review", sum((r.get("review_status") or "unreviewed") == "unreviewed" for r in records))
    search = st.text_input("Search publication titles or document numbers")
    types = sorted({str(r.get("document_type") or "Unknown") for r in records})
    statuses = sorted({str(r.get("review_status") or "unreviewed") for r in records})
    type_filter = st.selectbox("Publication type", ["All"] + types)
    status_filter = st.selectbox("Review status", ["All"] + statuses)
    filtered = [
        r for r in records
        if (not search or search.casefold() in (
            str(r.get("title") or "") + " " + str(r.get("source_id") or "")
        ).casefold())
        and (type_filter == "All" or str(r.get("document_type") or "Unknown") == type_filter)
        and (status_filter == "All" or str(r.get("review_status") or "unreviewed") == status_filter)
    ]
    st.caption(f"Showing {len(filtered)} of {len(records)} loaded publications (maximum 1,000).")
    st.dataframe(
        [{
            "Published": str(r.get("publication_date") or ""),
            "Title": r.get("title") or "",
            "Type": r.get("document_type") or "Unknown",
            "Review": r.get("review_status") or "unreviewed",
            "Document": r.get("source_id") or "",
            "Official link": r.get("url") or "",
        } for r in filtered],
        width="stretch", hide_index=True,
        column_config={"Official link": st.column_config.LinkColumn("Official link")},
    )
    if filtered:
        choice = st.selectbox(
            "Inspect publication", range(len(filtered)),
            format_func=lambda i: f"{filtered[i]['source_id']} — {filtered[i]['title']}",
        )
        item = filtered[choice]
        st.markdown(f"**Document number:** {item['source_id']}")
        st.markdown(f"**Published:** {item['publication_date']}")
        st.markdown(f"**Type:** {item.get('document_type') or 'Unknown'}")
        st.markdown(f"**Review status:** {item.get('review_status') or 'unreviewed'}")
        if item.get("url"):
            st.link_button("Open official Federal Register publication", item["url"])
        st.info("Not yet assessed: legal effect, applicability, effective date, and required actions.")


def render_impact_assessment():
    st.subheader("Regulatory Impact Assessment")
    st.caption("Record a human review for one institution and one publication. No automatic applicability decisions.")
    if not REVIEWER_PASSWORD:
        st.error("ARA_REVIEWER_PASSWORD is not configured in this dashboard service.")
        return
    entities = api_request("GET", "/entities")
    if entities is None:
        return
    publications = load_publications()
    if publications is None:
        return
    if not entities or not publications:
        st.info("An organization and a regulatory publication are required.")
        return

    entity_ids = {f"{e['name']} (ID {e['id']})": e["id"] for e in entities}
    selected_entity = st.selectbox("Organization", list(entity_ids), key="impact_entity")
    entity_id = entity_ids[selected_entity]
    publication_ids = {f"{p['source_id']} — {p['title']}": p["id"] for p in publications}
    selected_publication = st.selectbox("Federal Register publication", list(publication_ids), key="impact_publication")
    event_id = publication_ids[selected_publication]
    publication = next(p for p in publications if p["id"] == event_id)
    st.caption(f"Published: {publication.get('publication_date')} | Type: {publication.get('document_type') or 'Unknown'}")
    if publication.get("url"):
        st.link_button("Read official publication before assessing", publication["url"])

    rows = db_read("""
        SELECT id, applicability, impact_level, review_status,
               rationale, proposed_action, action_due_date,
               reviewer_name, reviewed_at, created_at, updated_at
        FROM public.regulatory_impact_assessments
        WHERE entity_id = :entity_id AND regulatory_event_id = :event_id
    """, {"entity_id": entity_id, "event_id": event_id})
    if rows is None:
        return
    existing = rows[0] if rows else None
    if existing:
        st.info(f"Existing assessment #{existing['id']} — last updated {existing['updated_at']}. Saving will update this record.")
    else:
        st.info("No assessment recorded for this organization and publication.")

    if not st.session_state.get("reviewer_authorized", False):
        with st.form("reviewer_login"):
            reviewer_entry = st.text_input("Reviewer password", type="password")
            authorize = st.form_submit_button("Unlock assessment editing")
        if authorize:
            if secrets.compare_digest(reviewer_entry, REVIEWER_PASSWORD):
                st.session_state.reviewer_authorized = True
                st.rerun()
            st.error("Incorrect reviewer password")
        if existing:
            st.markdown("**Recorded assessment (read-only)**")
            st.json({
                k: str(v) if isinstance(v, (date, datetime)) else v
                for k, v in existing.items()
            })
        return

    if st.button("Lock reviewer editing"):
        st.session_state.reviewer_authorized = False
        st.rerun()

    applicability_options = ["not_assessed", "potentially_applicable", "applicable", "not_applicable", "needs_legal_review"]
    impact_options = ["undetermined", "low", "medium", "high", "critical"]
    review_options = ["unreviewed", "in_review", "reviewed"]
    current = existing or {}

    def option_index(options, value, default):
        return options.index(value) if value in options else options.index(default)

    with st.form("impact_assessment_form"):
        applicability = st.selectbox(
            "Applicability", applicability_options,
            index=option_index(applicability_options, current.get("applicability"), "not_assessed"),
        )
        impact = st.selectbox(
            "Impact level", impact_options,
            index=option_index(impact_options, current.get("impact_level"), "undetermined"),
        )
        review = st.selectbox(
            "Review status", review_options,
            index=option_index(review_options, current.get("review_status"), "unreviewed"),
        )
        rationale = st.text_area("Rationale and supporting reasoning", value=current.get("rationale") or "")
        action = st.text_area("Proposed action", value=current.get("proposed_action") or "")
        due = st.date_input("Action due date (optional)", value=current.get("action_due_date") or None)
        reviewer = st.text_input("Reviewer name", value=current.get("reviewer_name") or "")
        save = st.form_submit_button("Save impact assessment", type="primary")

    if save:
        if review == "reviewed" and (not reviewer.strip() or not rationale.strip()):
            st.error("A completed review requires a reviewer name and rationale.")
            return
        if applicability == "applicable" and review != "reviewed":
            st.error("An 'applicable' determination must have a completed human review.")
            return
        try:
            with get_engine().begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO public.regulatory_impact_assessments
                        (entity_id, regulatory_event_id, applicability, impact_level,
                         review_status, rationale, proposed_action, action_due_date,
                         reviewer_name, reviewed_at)
                    VALUES
                        (:entity_id, :event_id, :applicability, :impact,
                         :review, :rationale, :action, :due, :reviewer,
                         CASE WHEN :review = 'reviewed' THEN now() ELSE NULL END)
                    ON CONFLICT (entity_id, regulatory_event_id)
                    DO UPDATE SET
                        applicability = EXCLUDED.applicability,
                        impact_level = EXCLUDED.impact_level,
                        review_status = EXCLUDED.review_status,
                        rationale = EXCLUDED.rationale,
                        proposed_action = EXCLUDED.proposed_action,
                        action_due_date = EXCLUDED.action_due_date,
                        reviewer_name = EXCLUDED.reviewer_name,
                        reviewed_at = CASE WHEN EXCLUDED.review_status = 'reviewed'
                                           THEN now() ELSE NULL END,
                        updated_at = now()
                    RETURNING id
                """), {
                    "entity_id": entity_id,
                    "event_id": event_id,
                    "applicability": applicability,
                    "impact": impact,
                    "review": review,
                    "rationale": rationale.strip() or None,
                    "action": action.strip() or None,
                    "due": due,
                    "reviewer": reviewer.strip() or None,
                })
                assessment_id = result.scalar_one()
            st.success(f"Assessment #{assessment_id} saved to Supabase.")
        except (SQLAlchemyError, ValueError) as exc:
            if isinstance(exc, ValueError):
                st.error(str(exc))
            else:
                database_error(exc, "save")

    st.divider()
    st.subheader("Saved assessments for this organization")
    history = db_read("""
        SELECT a.id, r.source_id AS document_number, r.title,
               a.applicability, a.impact_level, a.review_status,
               a.reviewer_name, a.updated_at
        FROM public.regulatory_impact_assessments AS a
        JOIN public.regulatory_events AS r ON r.id = a.regulatory_event_id
        WHERE a.entity_id = :entity_id
        ORDER BY a.updated_at DESC
        LIMIT 100
    """, {"entity_id": entity_id})
    if history is not None:
        if history:
            st.dataframe(history, width="stretch", hide_index=True)
        else:
            st.info("No saved assessments for this organization yet.")
    st.caption("This list shows current records, not a tamper-proof change history. Reviewer names are self-reported.")


tab1, tab2, tab3 = st.tabs(["Compliance Overview", "Regulatory Intelligence", "Impact Assessment"])
with tab1:
    entities = api_request("GET", "/entities")
    if entities is None:
        st.error("Could not load organizations.")
    elif not entities:
        st.info("No entities registered.")
    else:
        entity_options = {f"{e['name']} (ID {e['id']})": e["id"] for e in entities}
        selected = st.selectbox("Select organization", list(entity_options))
        obligations = api_request("GET", "/obligations", params={"entity_id": entity_options[selected]})
        if obligations is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total obligations", len(obligations))
            c2.metric("Pending", sum(o["status"] == "pending" for o in obligations))
            c3.metric("Overdue", sum(o["status"] == "overdue" for o in obligations))
            st.divider()
            if st.button("Refresh obligation deadlines", type="primary", width="stretch"):
                result = api_request("POST", "/refresh")
                if result is not None:
                    st.success(f"Refresh completed. {result['evaluated']} evaluated; {result['changed']} changed.")
                    st.rerun()
            st.subheader("Compliance obligations")
            if obligations:
                st.dataframe(obligations, width="stretch", hide_index=True)
            else:
                st.info("No obligations for this organization.")
            st.divider()
            if st.button("Generate demonstration report"):
                report = api_request("GET", "/audit_export")
                if report is not None:
                    st.session_state["demo_report"] = report
            if "demo_report" in st.session_state:
                st.download_button(
                    "Download JSON report",
                    data=json.dumps(st.session_state["demo_report"], indent=2),
                    file_name="ara_demo_report.json", mime="application/json",
                )
with tab2:
    render_regulatory_intelligence()
with tab3:
    render_impact_assessment()
    
