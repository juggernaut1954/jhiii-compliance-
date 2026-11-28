"""ARA pilot: per-user Supabase authentication and institution-scoped RPCs.

Deploy separately from the legacy demonstration dashboard.
Required Render environment: SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY.
Never configure a service_role/secret key here.
"""
import os
import requests
import streamlit as st

st.set_page_config(page_title="ARA Institutional Pilot", page_icon="🛡️", layout="wide")
BASE = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
if not BASE.startswith("https://") or not KEY or KEY.startswith(("sb_secret_", "eyJ")):
    st.error("Configure SUPABASE_URL and a Supabase publishable key in Render.")
    st.stop()

def call(method, path, token=None, payload=None):
    headers = {"apikey": KEY, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = requests.request(method, BASE + path, headers=headers,
                                    json=payload, timeout=20)
        if response.status_code in (401, 403):
            raise PermissionError("Authentication or permission denied")
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError, PermissionError) as exc:
        st.error("Request failed: " + type(exc).__name__)
        return None

st.title("JH III COMPLIANCE — ARA Pilot")
st.caption("Institutional test environment · Human decisions required · Not a compliance certification")

if st.sidebar.button("Sign out"):
    st.session_state.pop("ara_token", None)
    st.session_state.pop("ara_access", None)
    st.rerun()

if not st.session_state.get("ara_token"):
    with st.form("login"):
        email = st.text_input("Account email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        result = call("POST", "/auth/v1/token?grant_type=password",
                      payload={"email": email, "password": password})
        if isinstance(result, dict) and result.get("access_token"):
            st.session_state.ara_token = result["access_token"]
            st.rerun()
        else:
            st.error("Sign-in failed. Verify account credentials.")
    st.stop()

token = st.session_state.ara_token
access = call("POST", "/rest/v1/rpc/ara_my_access", token, {})
if access is None:
    st.warning("Your session may have expired. Sign out and sign in again.")
    st.stop()
st.subheader("My authorized access")
st.json(access)

st.divider()
st.subheader("Institution records")
entity = st.number_input("Institution ID", min_value=1, step=1)
kind = st.selectbox("Record type", ["assessments", "assignments", "evidence", "decisions"])
if st.button("Load authorized records"):
    rows = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                {"p_entity": int(entity), "p_kind": kind, "p_after": 0, "p_limit": 25})
    if rows is not None:
        st.json(rows)

st.divider()
st.subheader("Pending regulatory candidate reviews")
if st.button("Load pending queue"):
    queue = call("POST", "/rest/v1/rpc/ara_pending_review_queue", token, {"p_limit": 25})
    if queue is not None:
        st.json(queue)
st.info("Review decisions are intentionally disabled in this first integration build until live-user authorization and audit tests pass.")
