"""
app.py -- Streamlit UI for Supply Chain Twin MVP (Packages 3A–3F, Week 3).

Wraps the existing backend LangGraph pipeline with a thin read-only display.
No backend contracts are modified.

Sections:
  - Scenario Context          (3A)
  - Twin State Summary        (3A)
  - Governance Recommendation (3B) — all 8 frozen GovernanceOutput fields
  - Supervisor Action         (3C) — Approve / Verify / Override
  - Supervisor Decision Result(3C)
  - Cost & Candidate Details  (3D) — cost estimates, ops ranking, evidence detail
  - Trace & Audit             (3E) — pipeline trace + audit summary
  - Evaluation Results        (Phase 1) — regret and override metrics from case JSON truth
"""

import glob
import os
import sys

import streamlit as st

# ---------------------------------------------------------------------------
# Path setup -- make src/ importable
# ---------------------------------------------------------------------------
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_PROJECT_DIR, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ---------------------------------------------------------------------------
# One-time backend initialization (cached across Streamlit reruns)
# ---------------------------------------------------------------------------

@st.cache_resource
def _init_backend():
    """Build RAG vector store and compile the LangGraph graph exactly once."""
    from rag_setup import build_vector_store
    from graph import compile_graph

    build_vector_store()
    graph = compile_graph()
    return graph


# ---------------------------------------------------------------------------
# Case ID discovery (cached; reads filesystem once)
# ---------------------------------------------------------------------------

@st.cache_data
def _discover_case_ids():
    """Return sorted list of case IDs from data/cases/*.json."""
    cases_dir = os.path.join(_PROJECT_DIR, "data", "cases")
    paths = sorted(glob.glob(os.path.join(cases_dir, "*.json")))
    return [os.path.splitext(os.path.basename(p))[0] for p in paths]


# ---------------------------------------------------------------------------
# Display helpers (defined once, used throughout the page)
# ---------------------------------------------------------------------------

def _fmt_cost(val) -> str:
    """Format a cost float as '$X.XX', or '—' if None / unparseable."""
    if val is None:
        return "—"
    try:
        return f"${float(val):.2f}"
    except (TypeError, ValueError):
        return str(val)


def _trunc(text, max_len: int = 90) -> str:
    """Truncate text to max_len characters, appending '…' if shortened."""
    s = str(text) if text is not None else "—"
    return s[:max_len] + "…" if len(s) > max_len else s


def _fmt_score(val) -> str:
    """Format a feasibility score float to 2 dp, or '—' if None."""
    try:
        return f"{float(val or 0):.2f}"
    except (TypeError, ValueError):
        return "—"


def _render_trace(trace_log: list) -> None:
    """Render a trace_log list as a compact structured table.

    Each entry has: node (str), status (str), and optionally decision_type (str).
    Normalises into Step / Node / Status / Note columns.
    """
    if not trace_log:
        st.markdown("_No trace entries available._")
        return

    _status_labels = {
        "done": "✓ done",
        "stub": "○ stub",
        "skipped": "– skipped",
        "placeholder": "~ placeholder",
    }
    _note_for_status = {
        "stub": "(not yet implemented)",
        "skipped": "(upstream had no output)",
        "placeholder": "(fallback used)",
    }

    rows = []
    for step, entry in enumerate(trace_log, start=1):
        node = entry.get("node", "—")
        status = entry.get("status", "—")
        decision_type = entry.get("decision_type")  # only present on supervisor entry

        if decision_type:
            note = f"decision → {decision_type}"
        else:
            note = _note_for_status.get(status, "")

        rows.append({
            "Step": step,
            "Node": node,
            "Status": _status_labels.get(status, status),
            "Note": note,
        })

    st.table(rows)


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Supply Chain Twin",
    page_icon="🔗",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar -- case selector + Run case button
# Fail-fast: check case list before initialising the backend.
# ---------------------------------------------------------------------------
case_ids = _discover_case_ids()

st.sidebar.title("Supply Chain Twin")

if not case_ids:
    st.error("No case files found in data/cases/. Cannot continue.")
    st.stop()

# Backend init is deferred until after the empty-case guard so the
# expensive first-run build_vector_store() is skipped if data is missing.
graph = _init_backend()

selected_case = st.sidebar.selectbox("Select a case", case_ids)
run_clicked = st.sidebar.button("Run case", type="primary")

# ---------------------------------------------------------------------------
# Session-state container for the latest graph result
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
    st.session_state.result_case_id = None
    st.session_state.supervisor_result = None
    st.session_state.supervisor_case_id = None

# ---------------------------------------------------------------------------
# Graph invocation -- only on explicit button click
# ---------------------------------------------------------------------------
if run_clicked:
    with st.spinner("Running pipeline..."):
        result = graph.invoke({
            "case_id": selected_case,
            "supervisor_instruction": {"mode": "approve"},
            "policy_gate_enabled": True,
        })
        st.session_state.result = result
        st.session_state.result_case_id = selected_case
        # Clear any prior supervisor action result for this new case load
        st.session_state.supervisor_result = None
        st.session_state.supervisor_case_id = None

# ---------------------------------------------------------------------------
# Main area -- page title + selected case
# ---------------------------------------------------------------------------
st.title("Supply Chain Twin — Case Viewer")

if st.session_state.result is None:
    st.info("Select a case in the sidebar and click **Run case** to begin.")
    st.stop()

result = st.session_state.result
loaded_case = st.session_state.result_case_id
st.subheader(f"Loaded case: {loaded_case}")

if selected_case != loaded_case:
    st.warning(f"Selection changed to **{selected_case}**. Click **Run case** to load the new case.")

# ---------------------------------------------------------------------------
# Scenario context card
# ---------------------------------------------------------------------------
scenario = result.get("scenario_context", {})

st.markdown("### Scenario Context")
col1, col2 = st.columns(2)
with col1:
    st.metric("Scenario Type", scenario.get("scenario_type", "—"))
with col2:
    st.metric("Risk Level", scenario.get("risk_level", "—"))
st.markdown(scenario.get("exception_description", "—"))

# ---------------------------------------------------------------------------
# Twin state summary (carriers / warehouses / customer zones)
# ---------------------------------------------------------------------------
twin = result.get("twin_state", {})

st.markdown("### Twin State Summary")

# -- Carriers
carriers = twin.get("carriers", [])
if carriers:
    st.markdown("**Carriers**")
    carrier_rows = []
    for c in carriers:
        carrier_rows.append({
            "ID": c.get("id", ""),
            "Name": c.get("name", ""),
            "Available": "Yes" if c.get("available") else "No",
            "Cost/unit": c.get("cost_per_unit", ""),
            "Transit (hrs)": c.get("transit_time_hours", ""),
            "Capacity": c.get("capacity_limit", ""),
        })
    st.table(carrier_rows)

# -- Warehouses
warehouses = twin.get("warehouses", [])
if warehouses:
    st.markdown("**Warehouses**")
    wh_rows = []
    for w in warehouses:
        wh_rows.append({
            "ID": w.get("id", ""),
            "Name": w.get("name", ""),
            "Location": w.get("location", ""),
            "Inventory": f"{w.get('current_inventory', '?')}/{w.get('max_capacity', '?')}",
            "Op Cost/unit": w.get("operating_cost_per_unit", ""),
        })
    st.table(wh_rows)

# -- Customer zones
zones = twin.get("customer_zones", [])
if zones:
    st.markdown("**Customer Zones**")
    zone_rows = []
    for z in zones:
        zone_rows.append({
            "ID": z.get("id", ""),
            "Name": z.get("name", ""),
            "Demand": z.get("demand_units", ""),
            "SLA Deadline (hrs)": z.get("sla_deadline_hours", ""),
            "Penalty/hr": z.get("sla_penalty_per_hour", ""),
        })
    st.table(zone_rows)

# ---------------------------------------------------------------------------
# Governance recommendation panel (all 8 frozen GovernanceOutput fields)
# ---------------------------------------------------------------------------
gov = result.get("governance_output", {})

st.markdown("---")
st.markdown("### Governance Recommendation")
st.caption(
    "Decision-support output generated by the governance agent. "
    "All fields are read-only. Human review is required before any action is taken."
)

# -- Row 1: risk level + recommended action side by side
risk = gov.get("risk_level", "UNKNOWN")
risk_colors = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}
risk_color = risk_colors.get(risk, "gray")

col_risk, col_action = st.columns([1, 3])
with col_risk:
    st.markdown("**Risk Level**")
    st.markdown(f":{risk_color}[**{risk}**]")
with col_action:
    st.markdown("**Recommended Action**")
    st.markdown(gov.get("recommended_action", "—"))

st.markdown("")

# -- Situational explanation
st.markdown("**Situational Explanation**")
st.markdown(gov.get("situational_explanation", "—"))

# -- Cost summary
st.markdown("**Cost Summary**")
st.markdown(gov.get("cost_summary", "—"))

# -- Confidence note
st.markdown("**Confidence Note**")
st.info(gov.get("confidence_note", "—"), icon="ℹ️")

# -- Rationale trace (expandable)
with st.expander("Rationale Trace", expanded=False):
    rationale = gov.get("rationale_trace", "")
    if rationale:
        st.markdown(rationale)
    else:
        st.markdown("_No rationale trace available._")

# -- Evidence sources (expandable compact table)
with st.expander("Evidence Sources", expanded=False):
    evidence = gov.get("evidence_sources", [])
    if evidence:
        ev_rows = []
        for e in evidence:
            relevance_raw = str(e.get("relevance", ""))
            relevance_short = (
                relevance_raw[:80] + "…" if len(relevance_raw) > 80 else relevance_raw
            )
            ev_rows.append({
                "Source Type": e.get("source_type", ""),
                "Key": e.get("field_or_key", ""),
                "Value": str(e.get("value", "")),
                "Relevance (excerpt)": relevance_short,
            })
        st.table(ev_rows)
    else:
        st.markdown("_No evidence sources recorded._")

# -- Alternative actions (expandable compact table)
with st.expander("Alternative Actions", expanded=False):
    alternatives = gov.get("alternative_actions", [])
    if alternatives:
        alt_rows = []
        for a in alternatives:
            alt_rows.append({
                "Action": a.get("action_label", ""),
                "Cost & Feasibility": a.get("description", ""),
                "Risk Profile": a.get("estimated_risk", ""),
            })
        st.table(alt_rows)
    else:
        st.markdown("_No alternative actions available._")

# ---------------------------------------------------------------------------
# D3 Policy Gate indicator (Phase 1 — additive)
# ---------------------------------------------------------------------------
_policy = result.get("policy_decision", {})
if _policy:
    st.markdown("---")
    st.markdown("### Policy Gate Result")
    _pg_route = _policy.get("route", "UNKNOWN")
    _pg_risk = _policy.get("risk_level", "UNKNOWN")
    _pg_reason = _policy.get("reason", "")

    _route_colors = {"AUTO_EXECUTE": "green", "HUMAN_REQUIRED": "orange"}
    _route_color = _route_colors.get(_pg_route, "gray")
    _route_icon = "⚡" if _pg_route == "AUTO_EXECUTE" else "👤"

    col_pg1, col_pg2, col_pg3 = st.columns([1, 1, 3])
    with col_pg1:
        st.markdown(f"**Route:** {_route_icon} :{_route_color}[**{_pg_route}**]")
    with col_pg2:
        st.markdown(f"**Risk Level:** {_pg_risk}")
    with col_pg3:
        st.markdown(f"**Reason:** {_pg_reason}")

    if _pg_route == "AUTO_EXECUTE":
        st.success("This case was auto-approved by the policy gate. Supervisor was not invoked.")
    else:
        st.info("This case requires human review. Use the Supervisor Action section below.")

# ---------------------------------------------------------------------------
# Supervisor interaction section
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Supervisor Action")
st.caption(
    "Choose a supervision mode and submit. "
    "This re-runs the pipeline for the currently loaded case with your chosen instruction. "
    "The governance panel above remains unchanged."
)

tab_approve, tab_verify, tab_override = st.tabs(["Approve", "Verify", "Override"])

# -- Approve tab
with tab_approve:
    st.markdown("Accept the governance recommendation as-is.")
    if st.button("Approve", key="btn_approve"):
        with st.spinner("Running Approve..."):
            sup_result = graph.invoke({
                "case_id": loaded_case,
                "supervisor_instruction": {"mode": "approve"},
                "policy_gate_enabled": True,
            })
            st.session_state.supervisor_result = sup_result
            st.session_state.supervisor_case_id = loaded_case

# -- Verify tab
with tab_verify:
    st.markdown("Request a focused review before committing to the recommendation.")
    review_focus = st.text_area(
        "Review focus",
        placeholder="Describe what should be checked, e.g. 'Confirm carrier capacity before expediting.'",
        key="verify_focus_input",
    )
    if st.button("Submit Verify", key="btn_verify"):
        if not review_focus.strip():
            st.warning("Please enter a review focus before submitting.")
        else:
            with st.spinner("Running Verify..."):
                sup_result = graph.invoke({
                    "case_id": loaded_case,
                    "supervisor_instruction": {
                        "mode": "verify",
                        "review_focus": review_focus.strip(),
                    },
                    "policy_gate_enabled": True,
                })
                st.session_state.supervisor_result = sup_result
                st.session_state.supervisor_case_id = loaded_case

# -- Override tab
with tab_override:
    st.markdown("Select an alternative action to override the governance recommendation.")
    override_alternatives = gov.get("alternative_actions", [])
    if not override_alternatives:
        st.info("No alternative actions are available for this case.")
    else:
        override_labels = [a.get("action_label", "") for a in override_alternatives]
        chosen_label = st.selectbox(
            "Choose alternative action",
            override_labels,
            key="override_label_select",
        )
        if st.button("Submit Override", key="btn_override"):
            with st.spinner("Running Override..."):
                sup_result = graph.invoke({
                    "case_id": loaded_case,
                    "supervisor_instruction": {
                        "mode": "override",
                        "target_action_label": chosen_label,
                    },
                    "policy_gate_enabled": True,
                })
                st.session_state.supervisor_result = sup_result
                st.session_state.supervisor_case_id = loaded_case

# ---------------------------------------------------------------------------
# Supervisor decision result panel
# ---------------------------------------------------------------------------
if st.session_state.supervisor_result is not None:
    sup = st.session_state.supervisor_result.get("supervisor_output", {})

    st.markdown("---")
    st.markdown("### Supervisor Decision Result")
    st.caption(f"Supervisor action applied to case: **{st.session_state.supervisor_case_id}**")

    # Decision type with color badge
    decision_type = sup.get("supervisor_decision_type", "UNKNOWN")
    dt_colors = {"APPROVE": "green", "VERIFY": "orange", "OVERRIDE": "red"}
    dt_color = dt_colors.get(decision_type, "gray")
    st.markdown(f"**Decision Type:** :{dt_color}[**{decision_type}**]")

    # Two-column row: candidate ID + type
    col_id, col_type = st.columns(2)
    with col_id:
        st.markdown("**Selected Candidate ID**")
        st.markdown(sup.get("selected_candidate_id") or "—")
    with col_type:
        st.markdown("**Selected Candidate Type**")
        st.markdown(sup.get("selected_candidate_type") or "—")

    # Decision rationale
    st.markdown("**Decision Rationale**")
    st.markdown(sup.get("decision_rationale", "—"))

    # Three boolean/focus fields in a compact row
    col_rv, col_rf, col_ov = st.columns(3)
    with col_rv:
        st.markdown("**Review Requested**")
        st.markdown("Yes" if sup.get("review_requested") else "No")
    with col_rf:
        st.markdown("**Review Focus**")
        st.markdown(sup.get("review_focus") or "—")
    with col_ov:
        st.markdown("**Override from Recommendation**")
        st.markdown("Yes" if sup.get("override_from_recommendation") else "No")

# ---------------------------------------------------------------------------
# Cost & Candidate Details (3D)
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Cost & Candidate Details")
st.caption(
    "Read-only detail views from the operations and cost agents. "
    "All cost figures are runtime decision-support estimates — not authoritative evaluation truth."
)

# -- A. Cost Comparison Table
with st.expander("A — Cost Comparison (all candidates)", expanded=False):
    cost_estimates = result.get("cost_output", {}).get("cost_estimates", [])
    if cost_estimates:
        cost_rows = []
        for ce in cost_estimates:
            cost_rows.append({
                "Candidate ID": ce.get("candidate_id", ""),
                "Type": ce.get("candidate_type", ""),
                "Feasible": "Yes" if ce.get("is_feasible") else "No",
                "Direct Est.": _fmt_cost(ce.get("direct_cost_estimate")),
                "Recovery Est.": _fmt_cost(ce.get("recovery_cost_estimate")),
                "Total Est.": _fmt_cost(ce.get("total_cost_estimate")),
                "Breakdown (excerpt)": _trunc(ce.get("cost_breakdown_explanation")),
                "Notes (excerpt)": _trunc(ce.get("estimation_notes")),
            })
        st.table(cost_rows)
    else:
        st.markdown("_No cost estimates available._")


# -- B. Operations Ranking Table
with st.expander("B — Operations Candidate Ranking", expanded=False):
    ranked = result.get("operations_output", {}).get("ranked_candidates", [])
    if ranked:
        ops_rows = []
        for rc in ranked:
            ops_rows.append({
                "Candidate ID": rc.get("candidate_id", ""),
                "Type": rc.get("candidate_type", ""),
                "Score": _fmt_score(rc.get("feasibility_score")),
                "Feasible": "Yes" if rc.get("feasible") else "No",
                "Infeasibility Reason": rc.get("feasibility_reason") or "—",
                "Description (excerpt)": _trunc(rc.get("description")),
                "Rationale (excerpt)": _trunc(rc.get("rationale")),
            })
        st.table(ops_rows)
    else:
        st.markdown("_No ranked candidates available._")


# -- C. Evidence Detail View (full relevance text)
with st.expander("C — Evidence Detail (full text)", expanded=False):
    evidence_detail = result.get("governance_output", {}).get("evidence_sources", [])
    if evidence_detail:
        for i, e in enumerate(evidence_detail, start=1):
            st.markdown(f"**{i}. {e.get('field_or_key', '—')}**")
            col_st, col_val = st.columns([1, 2])
            with col_st:
                st.markdown(f"*Source type:* {e.get('source_type', '—')}")
                st.markdown(f"*Value:* {e.get('value', '—')}")
            with col_val:
                st.markdown("*Relevance:*")
                st.markdown(e.get("relevance", "—"))
            if i < len(evidence_detail):
                st.markdown("---")
    else:
        st.markdown("_No evidence sources recorded._")

# ---------------------------------------------------------------------------
# Trace & Audit (3E)
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Trace & Audit")
st.caption("Read-only pipeline execution trace for the loaded case and any subsequent supervisor action.")

# -- Audit summary panel (always visible)
has_supervisor = st.session_state.supervisor_result is not None
sup_decision_type = "—"
if has_supervisor:
    sup_decision_type = (
        st.session_state.supervisor_result
        .get("supervisor_output", {})
        .get("supervisor_decision_type", "—")
    )

gov_rec = result.get("governance_output", {}).get("recommended_action", "—")
gov_rec_short = gov_rec[:60] + "…" if len(gov_rec) > 60 else gov_rec

col_a1, col_a2, col_a3, col_a4 = st.columns(4)
with col_a1:
    st.metric("Loaded Case", loaded_case)
with col_a2:
    st.metric("Governance Recommendation", gov_rec_short)
with col_a3:
    st.metric("Supervisor Action Run", "Yes" if has_supervisor else "No")
with col_a4:
    st.metric(
        "Supervisor Decision",
        sup_decision_type,
        help="Decision type from the most recent supervisor action, if run.",
    )

st.markdown("")

# -- Trace tabs
tab_base_trace, tab_sup_trace = st.tabs(["Base Run Trace", "Supervisor Run Trace"])

with tab_base_trace:
    st.caption(f"Pipeline execution trace for case **{loaded_case}** (loaded via Run case).")
    _render_trace(result.get("trace_log", []))

with tab_sup_trace:
    if not has_supervisor:
        st.info("No supervisor action has been run yet. Use the Supervisor Action section above to run Approve, Verify, or Override.")
    else:
        sup_case = st.session_state.supervisor_case_id or loaded_case
        sup_mode = sup_decision_type
        st.caption(f"Pipeline execution trace for case **{sup_case}** (supervisor re-run, decision: **{sup_mode}**).")
        _render_trace(st.session_state.supervisor_result.get("trace_log", []))

# ---------------------------------------------------------------------------
# Evaluation Results (Phase 1) — deterministic metrics from case JSON truth
# ---------------------------------------------------------------------------

def _render_evaluation_panel(ev: dict, label: str) -> None:
    """Render a single evaluation_result dict as a compact panel."""
    status = ev.get("status", "unknown")
    if status != "ok":
        reason = ev.get("reason", "")
        st.info(f"{label}: evaluation {status}. {reason}")
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Human action code", ev.get("human_action_code", "—"))
    with col2:
        st.metric("Agent action code", ev.get("agent_action_code", "—"))
    with col3:
        st.metric("Oracle action code", ev.get("oracle_action_code", "—"))
    with col4:
        regret = ev.get("regret")
        st.metric("Regret", f"{regret:.2f}" if isinstance(regret, (int, float)) else "—")

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Chosen cost", _fmt_cost(ev.get("chosen_cost")))
    with col6:
        st.metric("Oracle cost", _fmt_cost(ev.get("oracle_cost")))
    with col7:
        st.metric("Override effectiveness", ev.get("override_effectiveness", "—"))

    col8, col9 = st.columns(2)
    with col8:
        st.markdown(f"**Is override:** {'Yes' if ev.get('is_override') else 'No'}")
    with col9:
        st.markdown(
            f"**Unnecessary override:** "
            f"{'Yes' if ev.get('is_unnecessary_override') else 'No'}"
        )


st.markdown("---")
st.markdown("### Evaluation Results")
st.caption(
    "Deterministic metrics computed from case JSON `cost_ground_truth` and `oracle` "
    "(authoritative evaluation truth). These figures do NOT use runtime cost estimates."
)

tab_base_eval, tab_sup_eval = st.tabs(["Base Run Evaluation", "Supervisor Run Evaluation"])

with tab_base_eval:
    base_ev = result.get("evaluation_result", {}) or {}
    _render_evaluation_panel(base_ev, "Base run")

with tab_sup_eval:
    if not has_supervisor:
        st.info("No supervisor action has been run yet. Use the Supervisor Action section above to run Approve, Verify, or Override.")
    else:
        sup_ev = (
            st.session_state.supervisor_result.get("evaluation_result", {}) or {}
        )
        _render_evaluation_panel(sup_ev, "Supervisor run")
