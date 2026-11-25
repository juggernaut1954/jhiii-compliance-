
import json
import os
import secrets

import requests
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="JH III COMPLIANCE",
    page_icon="🛡️",
    layout="wide",
)

API_URL = os.getenv(
    "ARA_API_URL",
    "https://jhiii-compliance.onrender.com",
).rstrip("/")
API_KEY = os.getenv("ARA_API_KEY", "")
DASHBOARD_PASSWORD = os.getenv("ARA_DASHBOARD_PASSWORD", "")

if not DASHBOARD_PASSWORD:
    st.error("Dashboard authentication is not configured.")
    st.stop()

if not st.session_state.get("authenticated", False):
    st.title("JH III COMPLIANCE")
    st.caption("ARA | Assurance · Risk · Automation")
    st.subheader("Dashboard Access — Demonstration")

    with st.form("login_form"):
        entered_password = st.text_input(
            "Dashboard password",
            type="password",
        )
        submitted = st.form_submit_button("Sign In")

    if submitted:
        if secrets.compare_digest(
            entered_password,
            DASHBOARD_PASSWORD,
        ):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid password")
    st.stop()

if st.sidebar.button("Sign Out"):
    st.session_state.authenticated = False
    st.rerun()

st.title("JH III COMPLIANCE")
st.caption("ARA | Assurance · Risk · Automation")
st.warning(
    "DEMONSTRATION — Not a regulatory compliance certification"
)

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
    except (requests.RequestException, ValueError) as exc:
        st.error(f"API request failed: {exc}")
        return None


def render_regulatory_intelligence():
    st.subheader("Regulatory Intelligence")
    st.caption(
        "FinCEN publications discovered in the Federal Register. "
        "Discovery does not establish applicability."
    )

    db_url = os.getenv("DATABASE_URL", "").strip()

    if not db_url:
        st.error(
            "DATABASE_URL is missing from the dashboard "
            "service environment."
        )
        return

    engine = None

    try:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )

        with engine.connect() as conn:
            records = [
                dict(row)
                for row in conn.execute(
                    text("""
                        SELECT
                            source_id,
                            title,
                            url,
                            publication_date,
                            document_type,
                            review_status,
                            discovered_at
                        FROM public.regulatory_events
                        WHERE source = 'federal_register_fincen'
                        ORDER BY
                            publication_date DESC NULLS LAST,
                            discovered_at DESC
                        LIMIT 1000
                    """)
                ).mappings().all()
            ]

    except Exception as exc:
        st.error("Regulatory Intelligence database query failed.")
        st.code(type(exc).__name__)
        st.caption(
            "Inspect dashboard service logs for the underlying "
            "error. Do not share credentials."
        )
        return

    finally:
        if engine is not None:
            engine.dispose()

    if not records:
        st.info("No regulatory publications have been stored yet.")
        return

    types = sorted({
        str(r.get("document_type") or "Unknown")
        for r in records
    })

    statuses = sorted({
        str(r.get("review_status") or "unreviewed")
        for r in records
    })

    c1, c2 = st.columns(2)

    c1.metric("Publications loaded", len(records))
    c2.metric(
        "Awaiting review",
        sum(
            (r.get("review_status") or "unreviewed") == "unreviewed"
            for r in records
        ),
    )

    search = st.text_input(
        "Search publication titles or document numbers"
    )
    type_filter = st.selectbox(
        "Publication type",
        ["All"] + types,
    )
    status_filter = st.selectbox(
        "Review status",
        ["All"] + statuses,
    )

    filtered = [
        r for r in records
        if (
            not search
            or search.casefold() in (
                str(r.get("title") or "")
                + " "
                + str(r.get("source_id") or "")
            ).casefold()
        )
        and (
            type_filter == "All"
            or str(r.get("document_type") or "Unknown")
            == type_filter
        )
        and (
            status_filter == "All"
            or str(r.get("review_status") or "unreviewed")
            == status_filter
        )
    ]

    st.caption(
        f"Showing {len(filtered)} of {len(records)} "
        "loaded publications (maximum 1,000)."
    )

    table = [
        {
            "Published": str(r.get("publication_date") or ""),
            "Title": r.get("title") or "",
            "Type": r.get("document_type") or "Unknown",
            "Review": r.get("review_status") or "unreviewed",
            "Document": r.get("source_id") or "",
            "Official link": r.get("url") or "",
        }
        for r in filtered
    ]

    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "Official link": st.column_config.LinkColumn(
                "Official link"
            )
        },
    )

    if filtered:
        choice = st.selectbox(
            "Inspect publication",
            range(len(filtered)),
            format_func=lambda i: (
                f"{filtered[i]['source_id']} — "
                f"{filtered[i]['title']}"
            ),
        )

        item = filtered[choice]

        st.markdown(
            f"**Document number:** {item['source_id']}"
        )
        st.markdown(
            f"**Published:** {item['publication_date']}"
        )
        st.markdown(
            f"**Type:** {item.get('document_type') or 'Unknown'}"
        )
        st.markdown(
            "**Review status:** "
            f"{item.get('review_status') or 'unreviewed'}"
        )

        if item.get("url"):
            st.link_button(
                "Open official Federal Register publication",
                item["url"],
            )

        st.info(
            "Not yet assessed: legal effect, applicability, "
            "effective date, and required actions."
        )


tab1, tab2 = st.tabs([
    "Compliance Overview",
    "Regulatory Intelligence",
])

with tab1:
    entities = api_request("GET", "/entities")

    if entities is None:
        st.error("Could not load organizations.")

    elif not entities:
        st.info("No entities registered.")

    else:
        entity_options = {
            f"{e['name']} (ID {e['id']})": e["id"]
            for e in entities
        }

        selected = st.selectbox(
            "Select organization",
            list(entity_options),
        )
        entity_id = entity_options[selected]

        obligations = api_request(
            "GET",
            "/obligations",
            params={"entity_id": entity_id},
        )

        if obligations is not None:
            pending = sum(
                o["status"] == "pending"
                for o in obligations
            )
            overdue = sum(
                o["status"] == "overdue"
                for o in obligations
            )

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Total obligations",
                len(obligations),
            )
            col2.metric("Pending", pending)
            col3.metric("Overdue", overdue)

            st.divider()

            if st.button(
                "Refresh obligation deadlines",
                type="primary",
                width="stretch",
            ):
                result = api_request("POST", "/refresh")

                if result is not None:
                    st.success(
                        f"Refresh completed. "
                        f"{result['evaluated']} evaluated; "
                        f"{result['changed']} changed."
                    )
                    st.rerun()

            st.subheader("Compliance obligations")

            if obligations:
                st.dataframe(
                    obligations,
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info(
                    "No obligations for this organization."
                )

            st.divider()

            if st.button("Generate demonstration report"):
                report = api_request(
                    "GET",
                    "/audit_export",
                )

                if report is not None:
                    st.session_state["demo_report"] = report

            if "demo_report" in st.session_state:
                st.download_button(
                    "Download JSON report",
                    data=json.dumps(
                        st.session_state["demo_report"],
                        indent=2,
                    ),
                    file_name="ara_demo_report.json",
                    mime="application/json",
                )

with tab2:
    render_regulatory_intelligence()
