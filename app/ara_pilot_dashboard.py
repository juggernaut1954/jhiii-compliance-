"""ARA pilot: per-user Supabase authentication and institution-scoped RPCs.

Deploy separately from the legacy demonstration dashboard.
Required Render environment: SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY.
Never configure a service_role/secret key here.
"""
import os
from html import escape
import requests
import streamlit as st

st.set_page_config(page_title="ARA Institutional Pilot", page_icon="🛡️", layout="wide")
BASE = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
if not BASE.startswith("https://") or not KEY or not KEY.startswith("sb_publishable_"):
    st.error("Configure SUPABASE_URL and a Supabase publishable key in Render.")
    st.stop()

def call(method, path, token=None, payload=None, quiet=False):
    headers = {"apikey": KEY, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = requests.request(method, BASE + path, headers=headers,
                                    json=payload, timeout=20)
        if response.status_code in (400, 401, 403) and path.startswith("/auth/v1/token"):
            if not quiet:
                st.error("Supabase rejected the sign-in. Check your credentials or use account recovery.")
            return None
        if response.status_code in (401, 403):
            raise PermissionError("Authentication or permission denied")
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError, PermissionError) as exc:
        if not quiet:
            st.error("Request failed: " + type(exc).__name__)
        return None

st.markdown("""<style>
.stApp {background:#f5f7fb;color:#172b4d}
[data-testid="stHeader"] {background:#f5f7fb}
.block-container {max-width:1080px;padding-top:2rem}
h1,h2,h3 {color:#142b4e!important;letter-spacing:-.02em}
div[data-testid="stVerticalBlockBorderWrapper"] {background:#fff;border-radius:14px}
.stButton button[kind="primary"] {background:#164b85;color:#fff}
</style>""", unsafe_allow_html=True)
st.title("JH III | ARA Compliance")
st.caption("Institutional test environment · Human decisions required · Not a compliance certification")

if st.sidebar.button("Sign out"):
    st.session_state.pop("ara_token", None)
    st.session_state.pop("ara_access", None)
    st.session_state.pop("ara_refresh", None)
    st.rerun()

if not st.session_state.get("ara_token"):
    with st.form("login"):
        email = st.text_input("Account email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        result = call("POST", "/auth/v1/token?grant_type=password",
                      payload={"email": email.strip().lower(), "password": password}, quiet=True)
        if isinstance(result, dict) and result.get("access_token"):
            st.session_state.ara_token = result["access_token"]
            st.session_state.ara_refresh = result.get("refresh_token")
            st.rerun()
        else:
            st.error("Supabase rejected this sign-in. Check the exact account email and password. If needed, use password recovery. Do not share passwords here.")
    st.stop()

token = st.session_state.ara_token
access = call("POST", "/rest/v1/rpc/ara_my_access", token, {})
if access is None and st.session_state.get("ara_refresh"):
    refreshed = call("POST", "/auth/v1/token?grant_type=refresh_token",
                     payload={"refresh_token": st.session_state.ara_refresh})
    if isinstance(refreshed, dict) and refreshed.get("access_token"):
        st.session_state.ara_token = refreshed["access_token"]
        st.session_state.ara_refresh = refreshed.get("refresh_token")
        token = st.session_state.ara_token
        access = call("POST", "/rest/v1/rpc/ara_my_access", token, {})
if access is None:
    st.warning("Your session is unavailable. Sign out and sign in again.")
    st.stop()
st.caption("Secure institutional workspace")
st.subheader("Workspace overview")
memberships = access.get("memberships", []) if isinstance(access, dict) else []
entities = [int(m["entity_id"]) for m in memberships if isinstance(m, dict) and m.get("entity_id")]
col_a, col_b, col_c = st.columns(3)
col_a.metric("Authorized institutions", len(entities))
col_b.metric("Account type", "Platform admin" if access.get("platform_admin") else "Institutional")
col_c.metric("Review decisions", "Locked")
with st.expander("View my assigned roles"):
    for membership in memberships:
        st.write("Institution", membership.get("entity_id"), "—", ", ".join(membership.get("roles", [])) or "Member")

st.divider()
st.subheader("Institution records")
if not entities:
    st.info("No active institution membership is assigned to this account.")
    st.stop()
entity = st.selectbox("Authorized institution", entities)
kind = st.selectbox("Record type", ["assessments", "obligations", "evidence", "evidence_reviews", "decisions"])
if st.button("Load authorized records", type="primary"):
    rows = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                {"p_entity": int(entity), "p_kind": kind, "p_after": 0, "p_limit": 25})
    if rows is not None:
        st.session_state["ara_records"] = rows
        st.session_state["ara_record_scope"] = (entity, kind)
if st.session_state.get("ara_record_scope") == (entity, kind):
    records = st.session_state.get("ara_records", [])
    st.caption(f"{len(records)} {kind.replace('_',' ')} record(s)")
    if not records:
        st.info("No records found for this institution and category.")
    for record in records:
        with st.container(border=True):
            st.markdown(f"**{kind.replace('_',' ').title()} #{record.get('id', '—')}**")
            fields = [(k.replace("_", " ").title(), v) for k, v in record.items()
                      if k not in ("id", "reviewer_user_id", "user_id") and v is not None]
            for label, value in fields:
                if isinstance(value, (dict, list)):
                    with st.expander(label):
                        st.json(value)
                else:
                    st.write(f"**{label}:** {str(value)[:1000]}")

st.divider()
st.subheader("Submit obligation evidence")
st.caption("Evidence references and descriptions only. File upload and document custody are not yet enabled.")
selected_membership = next((m for m in memberships if m.get("entity_id") == entity), {})
roles = selected_membership.get("roles", [])
if "evidence_contributor" in roles:
    if st.button("Load my institution's obligations"):
        obligations = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                           {"p_entity": int(entity), "p_kind": "obligations", "p_after": 0, "p_limit": 100})
        if obligations is not None:
            st.session_state["ara_obligations"] = obligations
            st.session_state["ara_obligation_entity"] = entity
    if st.session_state.get("ara_obligation_entity") == entity:
        obligations = st.session_state.get("ara_obligations", [])
        if not obligations:
            st.info("No assigned obligations available.")
        else:
            choices = {str(o["id"]): o for o in obligations if o.get("id") is not None}
            with st.form("submit_evidence", clear_on_submit=True):
                assignment = st.selectbox("Obligation assignment ID", list(choices.keys()))
                st.caption("Owner: " + str(choices[assignment].get("responsible_owner") or "Not assigned"))
                reference = st.text_input("Evidence reference", max_chars=250,
                                          placeholder="Internal document or case reference")
                description = st.text_area("Evidence description", max_chars=2000)
                submit = st.form_submit_button("Submit evidence", type="primary")
            if submit:
                if not reference.strip() or not description.strip():
                    st.error("Both evidence fields are required.")
                else:
                    result = call("POST", "/rest/v1/rpc/ara_submit_assignment_evidence", token,
                                  {"p_assignment": int(assignment), "p_reference": reference.strip(),
                                   "p_description": description.strip()})
                    if result is not None:
                        st.success("Evidence submitted. Record ID: " + str(result))
else:
    st.info("Only an authorized evidence contributor can submit evidence for this institution.")

st.divider()
st.subheader("Independent evidence review")
if "independent_reviewer" in roles:
    if st.button("Load evidence awaiting review"):
        evidence = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                        {"p_entity": int(entity), "p_kind": "evidence", "p_after": 0, "p_limit": 100})
        reviews = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                       {"p_entity": int(entity), "p_kind": "evidence_reviews", "p_after": 0, "p_limit": 100})
        if evidence is not None and reviews is not None:
            st.session_state["ara_review_evidence"] = evidence
            st.session_state["ara_review_history"] = reviews
            st.session_state["ara_review_entity"] = entity
    if st.session_state.get("ara_review_entity") == entity:
        evidence = st.session_state.get("ara_review_evidence", [])
        reviews = st.session_state.get("ara_review_history", [])
        reviewed_ids = {int(r["evidence_id"]) for r in reviews if r.get("evidence_id") is not None}
        awaiting = [item for item in evidence if int(item["id"]) not in reviewed_ids]
        st.caption(str(len(awaiting)) + " evidence submissions awaiting first review (first 100 records).")
        if not awaiting:
            st.info("No unreviewed evidence in the loaded records.")
        for item in awaiting:
            with st.container(border=True):
                st.write("**Evidence #" + str(item.get("id")) + "**")
                st.write("Assignment: " + str(item.get("assignment_id")))
                st.write("Reference: " + str(item.get("evidence_reference")))
                st.write("Description: " + str(item.get("description")))
                with st.form("review_evidence_" + str(item.get("id"))):
                    decision = st.selectbox("Decision", ["rejected", "accepted"], key="decision_" + str(item.get("id")))
                    reason = st.text_area("Review reason", max_chars=2000)
                    if decision == "accepted":
                        confirmed = st.checkbox("I have independently verified supporting evidence.")
                    else:
                        confirmed = True
                        st.caption("Rejection does not require verification. Explain why it cannot be accepted.")
                    submitted = st.form_submit_button("Record review decision")
                if submitted:
                    if not reason.strip():
                        st.error("A review reason is required.")
                    elif not confirmed:
                        st.error("Acceptance requires independent verification of supporting evidence.")
                    else:
                        result = call("POST", "/rest/v1/rpc/ara_review_assignment_evidence", token,
                                      {"p_evidence": int(item["id"]), "p_decision": decision,
                                       "p_reason": reason.strip()})
                        if result is not None:
                            st.success("Review recorded. Review ID: " + str(result))
                            st.session_state.pop("ara_review_evidence", None)
                            st.session_state.pop("ara_review_history", None)
                            st.session_state.pop("ara_review_entity", None)
                            st.info("Reload the queue to see updated review status.")
        with st.expander("Previous review decisions (read-only)"):
            if not reviews:
                st.write("No review history in the loaded records.")
            for r in reviews:
                st.write("Evidence #" + str(r.get("evidence_id")) + " — " + str(r.get("decision")) + " — Review #" + str(r.get("id")))
                st.caption(str(r.get("reason") or "No reason recorded"))
else:
    st.info("Evidence decisions require a separately authorized independent reviewer.")


st.divider()
st.subheader("Obligation completion decisions")
st.caption("Pilot workflow. Completion is permitted only when the backend validates independently accepted evidence.")
if "independent_reviewer" in roles:
    if st.button("Load obligation decision workspace"):
        assignments = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                           {"p_entity": int(entity), "p_kind": "obligations", "p_after": 0, "p_limit": 100})
        reviews = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                       {"p_entity": int(entity), "p_kind": "evidence_reviews", "p_after": 0, "p_limit": 100})
        evidence = call("POST", "/rest/v1/rpc/ara_institution_records", token,
                        {"p_entity": int(entity), "p_kind": "evidence", "p_after": 0, "p_limit": 100})
        if assignments is not None and reviews is not None and evidence is not None:
            st.session_state["ara_decision_workspace"] = (assignments, reviews, evidence)
            st.session_state["ara_decision_entity"] = entity
    if st.session_state.get("ara_decision_entity") == entity:
        assignments, reviews, evidence = st.session_state["ara_decision_workspace"]
        if not assignments:
            st.info("No assignments available for this institution.")
        else:
            assignment_map = {int(a["id"]): a for a in assignments}
            assignment_id = st.selectbox("Assignment to assess", list(assignment_map),
                                         format_func=lambda aid: "Assignment #" + str(aid))
            assignment_record = assignment_map[assignment_id]
            current_status = str(assignment_record.get("completion_status") or "unknown")
            st.write("**Calculated current status:** " + current_status)
            if current_status == "evidence_recheck_required":
                st.warning("Evidence recheck required: this obligation must not be treated as currently completed.")
            elif current_status == "completed":
                st.success("Completion recorded and current evidence checks satisfied. This is not regulatory certification.")
            st.write("**Processing eligibility:** " + str(assignment_record.get("eligibility_status") or "unknown"))
            st.caption("Eligibility means the obligation can be processed; it does not establish compliance.")
            evidence_by_id = {int(e["id"]): e for e in evidence}
            accepted = [
                r for r in reviews
                if r.get("decision") == "accepted"
                and int(r.get("evidence_id", -1)) in evidence_by_id
                and int(evidence_by_id[int(r["evidence_id"])].get("assignment_id", -1)) == assignment_id
                and int(r["id"]) == max(
                    int(x["id"]) for x in reviews
                    if x.get("evidence_id") == r.get("evidence_id")
                )
            ]
            st.caption("Accepted evidence reviews shown from the first 100 records; the backend rechecks all conditions.")
            with st.form("obligation_decision_form"):
                decision = st.selectbox("Decision", ["Select a decision", "reopened", "completed"])
                if decision == "completed":
                    options = [int(r["id"]) for r in accepted]
                    review_id = st.selectbox("Accepted evidence review ID", options) if options else None
                    if not options:
                        st.warning("No accepted evidence review available in the loaded records.")
                else:
                    review_id = None
                reason = st.text_area("Decision reason", max_chars=2000)
                confirmed = st.checkbox("I understand this decision will be recorded in the permanent audit history.")
                submit_decision = st.form_submit_button("Record obligation decision")
            if submit_decision:
                if decision == "Select a decision":
                    st.error("Select a decision before submitting.")
                elif not confirmed or not reason.strip():
                    st.error("Confirmation and a written reason are required.")
                elif decision == "completed" and review_id is None:
                    st.error("Completion requires an independently accepted evidence review.")
                elif decision == "reopened" and current_status not in ("completed", "evidence_recheck_required"):
                    st.error("Reopening is available only for assignments with an earlier completion.")
                else:
                    payload = {"p_assignment": int(assignment_id), "p_decision": decision,
                               "p_reason": reason.strip(), "p_review": review_id}
                    result = call("POST", "/rest/v1/rpc/ara_decide_assignment", token, payload)
                    if result is not None:
                        st.success("Obligation decision recorded. Decision ID: " + str(result))
                        st.session_state.pop("ara_decision_workspace", None)
                        st.session_state.pop("ara_decision_entity", None)
                        st.info("Reload the workspace to see the recalculated status.")
else:
    st.info("Obligation completion decisions require an authorized independent reviewer.")

st.divider()
st.subheader("Pending regulatory candidate reviews")
if st.button("Load pending queue", type="primary"):
    queue = call("POST", "/rest/v1/rpc/ara_pending_review_queue", token, {"p_limit": 25})
    if queue is not None:
        st.session_state["ara_queue"] = queue
if "ara_queue" in st.session_state:
    queue = st.session_state["ara_queue"]
    st.caption(f"{len(queue)} pending regulatory candidate(s) returned")
    if not queue:
        st.info("No pending regulatory candidates.")
    for candidate in queue:
        title = str(candidate.get("title") or "Regulatory candidate")
        with st.container(border=True):
            st.markdown(f"### {escape(title)}")
            a, b, d = st.columns(3)
            a.caption("Citation")
            a.write(str(candidate.get("citation") or "Not supplied"))
            b.caption("Review status")
            b.write(str(candidate.get("review_status") or "Unknown").title())
            d.caption("Effective date")
            d.write(str(candidate.get("effective_date") or "Not supplied"))
            source = str(candidate.get("official_url") or "")
            if source.startswith("https://"):
                st.link_button("View official source", source)
            with st.expander("Extracted source evidence"):
                st.write(str(candidate.get("evidence_quote") or "No evidence excerpt")[:12000])
            st.caption(f"Candidate ID: {candidate.get('id', '—')} · Human verification required")
st.info("Review decisions are intentionally disabled in this first integration build until live-user authorization and audit tests pass.")
