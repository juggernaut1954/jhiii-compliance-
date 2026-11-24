
import json
import os
import secrets

import requests
import streamlit as st


st.set_page_config(
    page_title="JH III COMPLIANCE",
    page_icon="🛡️",
    layout="wide"
)

API_URL = os.getenv(
    "ARA_API_URL",
    "https://jhiii-compliance.onrender.com"
).rstrip("/")

API_KEY = os.getenv("ARA_API_KEY", "")
DASHBOARD_PASSWORD = os.getenv("ARA_DASHBOARD_PASSWORD", "")


# Dashboard authentication

if not DASHBOARD_PASSWORD:
    st.error("Dashboard authentication is not configured.")
    st.stop()

if not st.session_state.get("authenticated", False):
    st.title("JH III COMPLIANCE")
    st.caption("ARA | Assurance · Risk · Automation")
    st.subheader("Secure Dashboard Access")

    with st.form("login_form"):
        entered_password = st.text_input(
            "Dashboard password",
            type="password"
        )
        submitted = st.form_submit_button("Sign In")

    if submitted:
        if secrets.compare_digest(
            entered_password,
            DASHBOARD_PASSWORD
        ):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid password")

    st.stop()


# Sign out

if st.sidebar.button("Sign Out"):
    st.session_state.authenticated = False
    st.rerun()


# Dashboard

st.title("JH III COMPLIANCE")
st.caption("ARA | Assurance · Risk · Automation")

st.warning(
    "DEMONSTRATION — Not a regulatory compliance certification"
)

if not API_KEY:
    st.error("ARA_API_KEY is not configured.")
    st.stop()


# Backend connection

def api_request(method, endpoint, **kwargs):
    try:
        response = requests.request(
            method,
            f"{API_URL}{endpoint}",
            headers={"X-API-Key": API_KEY},
            timeout=30,
            **kwargs
        )
        response.raise_for_status()
        return response.json()

    except (requests.RequestException, ValueError) as exc:
        st.error(f"API request failed: {exc}")
        return None


# Load organizations

entities = api_request("GET", "/entities")

if entities is None:
    st.stop()

if not entities:
    st.info("No entities registered.")
    st.stop()

entity_options = {
    f"{e['name']} (ID {e['id']})": e["id"]
    for e in entities
}

selected = st.selectbox(
    "Select organization",
    list(entity_options)
)

entity_id = entity_options[selected]


# Load obligations

obligations = api_request(
    "GET",
    "/obligations",
    params={"entity_id": entity_id}
)

if obligations is None:
    st.stop()

pending = sum(
    o["status"] == "pending"
    for o in obligations
)

overdue = sum(
    o["status"] == "overdue"
    for o in obligations
)


# Executive metrics

col1, col2, col3 = st.columns(3)

col1.metric("Total obligations", len(obligations))
col2.metric("Pending", pending)
col3.metric("Overdue", overdue)

st.divider()


# Assessment

if st.button(
    "Run Compliance Assessment",
    type="primary",
    use_container_width=True
):
    result = api_request("POST", "/refresh")

    if result is not None:
        st.success(
            f"Refresh completed. "
            f"{result['evaluated']} evaluated; "
            f"{result['changed']} changed."
        )
        st.rerun()


# Obligation table

st.subheader("Compliance obligations")

if obligations:
    st.dataframe(
        obligations,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No obligations for this organization.")

st.divider()


# Demonstration report

if st.button("Generate demonstration report"):
    report = api_request("GET", "/audit_export")

    if report is not None:
        st.session_state["demo_report"] = report

if "demo_report" in st.session_state:
    st.download_button(
        "Download JSON report",
        data=json.dumps(
            st.session_state["demo_report"],
            indent=2
        ),
        file_name="ara_demo_report.json",
        mime="application/json"
    )
    
