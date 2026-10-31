(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = { csrf: null, preview: null, runId: null, polling: null };

  async function request(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`;
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function button(label, className, handler) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = className;
    element.textContent = label;
    element.addEventListener("click", handler);
    return element;
  }

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  }

  function notice(message, kind = "info") {
    const target = $("#hubNotice");
    target.className = `hub-notice ${kind}`;
    target.textContent = message;
    if (kind === "denied") {
      const link = node("a", "hub-signin", "Open Knowledge Assistant sign-in");
      link.href = "/tools/knowledge";
      target.append(" ", link);
    }
  }

  function setBusy(busy, label = "RUNNING") {
    $("#hubPreviewButton").disabled = busy;
    $("#hubRunButton").disabled = busy || !state.preview || state.preview.status !== "ready";
    $("#hubRunState").textContent = label;
    $("#hubCancelButton").classList.toggle("hidden", !busy || !state.runId);
  }

  async function csrf() {
    if (!state.csrf) state.csrf = (await request("/api/agent/csrf")).csrf_token;
    return state.csrf;
  }

  async function post(path, body, extraHeaders = {}) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await csrf(), ...extraHeaders },
      body: JSON.stringify(body),
    });
  }

  function renderPlan(preview) {
    const target = $("#hubPlan");
    target.replaceChildren();
    if (preview.status === "needs_clarification") {
      target.append(node("div", "hub-clarify", preview.question));
      return;
    }
    const list = node("ol", "hub-plan-list");
    for (const step of preview.steps || []) {
      const item = node("li", "hub-plan-step");
      const title = node("strong", "", step.tool);
      const args = node("pre", "result-json", JSON.stringify(step.arguments, null, 2));
      item.append(title, args);
      list.append(item);
    }
    target.append(list);
    $("#hubModeBadge").textContent = preview.mode === "llm_planned" ? "LOCAL LLM PLANNED" : "LLM OFF · DETERMINISTIC";
  }

  async function preview() {
    const question = $("#hubQuestion").value.trim();
    state.preview = null;
    state.runId = null;
    $("#hubRunButton").disabled = true;
    $("#hubRunState").textContent = "PLANNING";
    $("#hubPreviewButton").disabled = true;
    $("#hubPlan").replaceChildren(node("div", "result-empty", "Checking the available tools and arguments…"));
    try {
      const result = await post("/api/agent/preview", { question });
      state.preview = result;
      renderPlan(result);
      $("#hubRunButton").disabled = result.status !== "ready";
      $("#hubRunState").textContent = result.status === "ready" ? "PLAN READY" : "NEEDS CLARIFICATION";
      notice("Plan preview ready. Review each tool and argument before running.", "success");
    } catch (error) {
      $("#hubPlan").replaceChildren(node("div", error.status === 422 ? "form-error" : "result-empty", error.message));
      $("#hubRunState").textContent = error.status === 422 ? "REFUSED" : "ERROR";
      if (error.status === 401) notice("Sign in to the Knowledge Assistant before using the Agent Hub.", "denied");
      else notice(error.message, error.status === 403 ? "denied" : "error");
    } finally {
      $("#hubPreviewButton").disabled = false;
    }
  }

  function makeEvidenceTable(rows) {
    const wrapper = node("div", "hub-table-wrap");
    const table = node("table", "hub-table");
    const head = node("thead");
    const body = node("tbody");
    const keys = [...new Set(rows.flatMap((row) => Object.keys(row || {}).filter((key) => key !== "tool_result_id")))];
    const headerRow = node("tr");
    for (const key of keys) headerRow.append(node("th", "", key.replaceAll("_", " ")));
    head.append(headerRow);
    for (const row of rows) {
      const tr = node("tr");
      for (const key of keys) {
        const value = row?.[key];
        tr.append(node("td", "", typeof value === "object" && value !== null ? JSON.stringify(value) : value));
      }
      body.append(tr);
    }
    table.append(head, body);
    wrapper.append(table);
    return wrapper;
  }

  function makeChart(rows) {
    if (!rows.length || !rows.every((row) => row && typeof row === "object")) return null;
    const labelKey = Object.keys(rows[0]).find((key) => key !== "tool_result_id" && typeof rows[0][key] === "string");
    const valueKey = Object.keys(rows[0]).find((key) => key !== "tool_result_id" && typeof rows[0][key] === "number");
    if (!labelKey || !valueKey) return null;
    const max = Math.max(...rows.map((row) => Math.max(0, Number(row[valueKey]) || 0)));
    if (!max) return null;
    const chart = node("div", "hub-chart");
    chart.setAttribute("role", "img");
    chart.setAttribute("aria-label", `${valueKey.replaceAll("_", " ")} by ${labelKey.replaceAll("_", " ")}`);
    for (const row of rows.slice(0, 12)) {
      const column = node("div", "hub-chart-col");
      const value = Math.max(0, Number(row[valueKey]) || 0);
      const bar = node("div", "hub-chart-bar");
      bar.style.height = `${Math.max(4, (value / max) * 100)}%`;
      bar.title = `${row[labelKey]}: ${value}`;
      column.append(bar, node("span", "hub-chart-label", row[labelKey]));
      chart.append(column);
    }
    return chart;
  }

  function renderTimeline(trace) {
    const timeline = node("ol", "hub-timeline");
    for (const step of trace?.steps || []) {
      const item = node("li", `hub-timeline-item state-${step.state || "unknown"}`);
      item.append(node("strong", "", step.tool), node("span", "status-chip", step.state || "unknown"));
      const meta = [step.elapsed_ms == null ? null : `${step.elapsed_ms} ms`, step.error_code || null,
        step.evidence_id ? `Evidence ${step.evidence_id}` : null].filter(Boolean).join(" · ");
      if (meta) item.append(node("small", "", meta));
      timeline.append(item);
    }
    return timeline;
  }

  function renderRun(result) {
    const target = $("#hubResult");
    target.replaceChildren();
    $("#hubResultState").textContent = String(result.status || "complete").toUpperCase();
    const answer = node("p", "hub-answer", result.answer || "Run details loaded.");
    target.append(answer);
    const sourceResults = Array.isArray(result.data) ? result.data : [];
    if (!sourceResults.length) {
      const message = result.status === "waiting_approval"
        ? "This run is paused until an authorized reviewer approves or rejects the pending proposal."
        : "No verified numeric results are available for this run.";
      target.append(node("div", result.status === "waiting_approval" ? "hub-clarify" : "form-error", message));
    }
    for (const resultItem of sourceResults) {
      const section = node("section", "hub-evidence");
      const heading = node("div", "hub-evidence-head");
      heading.append(node("strong", "", resultItem.tool || "Tool result"), node("span", "status-chip", resultItem.data_label || "DATA"));
      heading.append(node("small", "", `Evidence ID: ${resultItem.tool_result_id || "unavailable"} · ${resultItem.elapsed_ms ?? "?"} ms`));
      section.append(heading);
      const rows = Array.isArray(resultItem.data) ? resultItem.data : [];
      if (rows.length && rows.every((row) => row && typeof row === "object")) {
        const chart = makeChart(rows);
        if (chart) section.append(chart);
        section.append(makeEvidenceTable(rows));
      } else {
        section.append(node("pre", "result-json", JSON.stringify(resultItem.data, null, 2)));
      }
      target.append(section);
    }
    if (result.trace) {
      const traceSection = node("details", "hub-trace");
      traceSection.append(node("summary", "", `Run trace · ${result.trace.run_id || "run"}`), renderTimeline(result.trace));
      target.append(traceSection);
      state.runId = result.trace.run_id || state.runId;
    }
    if (Array.isArray(result.limitations) && result.limitations.length) {
      const list = node("ul", "hub-limitations");
      result.limitations.forEach((item) => list.append(node("li", "", item)));
      target.append(list);
    }
  }

  async function run() {
    if (!state.preview || state.preview.status !== "ready") return;
    setBusy(true, "RUNNING");
    state.runId = null;
    state.polling = window.setInterval(refreshHistory, 1200);
    notice("The Hub is running the reviewed plan and checking each result.", "info");
    try {
      const result = await post("/api/agent/ask", { question: $("#hubQuestion").value.trim() }, {
        "Idempotency-Key": crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      });
      renderRun(result);
      $("#hubRunState").textContent = String(result.status || "complete").toUpperCase();
      if (result.status === "waiting_approval") {
        notice("Run paused for approval. An authorized reviewer can respond in the approval inbox.", "info");
      } else {
        notice(result.status === "complete" ? "Run finished. Review the evidence IDs and limitations." : "Run finished with a clarification or policy result.", result.status === "complete" ? "success" : "error");
      }
      state.preview = null;
      $("#hubRunButton").disabled = true;
      await Promise.all([refreshHistory(), refreshApprovals()]);
    } catch (error) {
      $("#hubResult").replaceChildren(node("div", "form-error", error.message));
      $("#hubResultState").textContent = "ERROR";
      $("#hubRunState").textContent = "ERROR";
      notice(error.message, error.status === 401 || error.status === 403 ? "denied" : "error");
    } finally {
      if (state.polling) window.clearInterval(state.polling);
      state.polling = null;
      setBusy(false, $("#hubRunState").textContent);
    }
  }

  async function cancel() {
    if (!state.runId) return;
    try {
      await post(`/api/agent/runs/${encodeURIComponent(state.runId)}/cancel`, {});
      notice("Cancellation requested. The active tool will stop at its next cancellation check.", "info");
      await refreshHistory();
    } catch (error) {
      notice(error.message, "error");
    }
  }

  async function refreshHistory() {
    try {
      const data = await request("/api/agent/runs?limit=30");
      const target = $("#hubHistory");
      target.replaceChildren();
      if (!data.runs?.length) target.append(node("div", "result-empty", "No runs yet."));
      for (const runInfo of data.runs || []) {
        if (state.polling && !state.runId && runInfo.state === "running") state.runId = runInfo.run_id;
        const row = node("div", "hub-history-row");
        row.append(node("div", "hub-history-copy", runInfo.goal || "Agent Hub run"), node("span", `status-chip ${runInfo.state === "failed" ? "warn" : ""}`, runInfo.state));
        const meta = node("small", "", `${runInfo.created_at || ""} · ${String(runInfo.run_id || "").slice(0, 8)}`);
        row.append(meta);
        row.append(button("Open", "quiet-button", () => openRun(runInfo.run_id)));
        if (["running", "validated", "waiting_approval"].includes(runInfo.state)) {
          row.append(button("Cancel", "quiet-button", async () => {
            state.runId = runInfo.run_id;
            await cancel();
          }));
          if (state.runId === runInfo.run_id) $("#hubCancelButton").classList.remove("hidden");
        }
        target.append(row);
      }
    } catch (error) {
      if (error.status === 401) notice("Sign in to load your run history.", "denied");
    }
  }

  async function openRun(runId) {
    try {
      const data = await request(`/api/agent/runs/${encodeURIComponent(runId)}`);
      const steps = data.steps || [];
      const resultRows = steps.filter((step) => step.tool_name !== "hub.verify_results" && step.result && !step.result.withheld);
      const verificationStep = steps.find((step) => step.tool_name === "hub.verify_results");
      const verified = verificationStep?.result?.data?.verified === true;
      renderRun({
        answer: verified ? "This saved run passed evidence verification." : "Saved run results were withheld because verification did not pass.",
        data: verified ? resultRows.map((step) => step.result) : [],
        trace: { run_id: data.run.run_id, steps: steps.map((step) => ({
          step_index: step.step_index, tool: step.tool_name, state: step.state,
          error_code: step.error_code, evidence_id: step.call_id,
        })) },
        status: data.run.state,
        limitations: ["Saved traces follow the retention policy and the signed-in user's workspace access."],
      });
      $("#hubResult").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      notice(error.message, error.status === 404 ? "denied" : "error");
    }
  }

  async function refreshApprovals() {
    try {
      const [data, approved, rejected] = await Promise.all([
        request("/api/agent/approvals?status=pending"),
        request("/api/agent/approvals?status=approved"),
        request("/api/agent/approvals?status=rejected"),
      ]);
      const target = $("#hubApprovals");
      const approvals = data.approvals || [];
      $("#hubApprovalCount").textContent = `${approvals.length} PENDING`;
      target.replaceChildren();
      if (!approvals.length) target.append(node("div", "result-empty", "No pending approvals."));
      for (const approval of approvals) {
        const card = node("article", "hub-approval");
        card.append(node("strong", "", approval.reason || `Review ${approval.call_id}`));
        card.append(node("small", "", `Requested by ${approval.requested_by} · ${approval.created_at} · expires ${approval.expires_at}`));
        card.append(node("small", "", `Tool call ${approval.call_id} · run ${String(approval.run_id).slice(0, 8)}`));
        const reason = node("input", "hub-reason");
        reason.type = "text";
        reason.maxLength = 500;
        reason.setAttribute("aria-label", "Optional approval decision reason");
        reason.placeholder = "Decision reason (optional)";
        const actions = node("div", "hub-approval-actions");
        actions.append(button("Approve", "secondary-button", () => decide(approval.approval_id, "approve", reason.value)));
        actions.append(button("Reject", "quiet-button", () => decide(approval.approval_id, "reject", reason.value)));
        card.append(reason, actions);
        target.append(card);
      }
      const decisions = [...(approved.approvals || []), ...(rejected.approvals || [])]
        .sort((left, right) => String(right.decided_at || "").localeCompare(String(left.decided_at || "")))
        .slice(0, 5);
      if (decisions.length) {
        target.append(node("h3", "hub-decision-heading", "Recent decisions"));
        for (const decision of decisions) {
          const item = node("div", "hub-decision");
          item.append(node("strong", "", `${decision.status} · ${decision.approver_id || "unknown reviewer"}`));
          item.append(node("small", "", `${decision.decided_at || "time unavailable"}${decision.reason ? ` · ${decision.reason}` : ""}`));
          target.append(item);
        }
      }
    } catch (error) {
      if (error.status === 401) notice("Sign in to view workspace approvals.", "denied");
    }
  }

  async function decide(id, decision, reason) {
    try {
      await post(`/api/agent/approvals/${encodeURIComponent(id)}/${decision}`, { reason: reason || null });
      notice(decision === "approve" ? "Approval recorded." : "Rejection recorded.", "success");
      await Promise.all([refreshApprovals(), refreshHistory()]);
    } catch (error) {
      notice(error.message, error.status === 403 ? "denied" : "error");
    }
  }

  async function refreshCatalogue() {
    const target = $("#hubCatalogue");
    try {
      const data = await request("/api/agent/tools");
      $("#hubModeBadge").textContent = data.mode_default === "local_llm_available"
        ? "LOCAL LLM AVAILABLE · PREVIEW TO PLAN" : "LLM OFF · DETERMINISTIC";
      target.replaceChildren();
      for (const tool of data.tools || []) {
        const row = node("details", "hub-tool");
        const summary = node("summary", "", `${tool.name} · ${tool.side_effect} · ${tool.data_label}`);
        row.append(summary, node("p", "", tool.description));
        row.append(node("pre", "result-json", JSON.stringify(tool.input_schema, null, 2)));
        target.append(row);
      }
      if (!data.tools?.length) target.append(node("div", "result-empty", "No tools are available for this account."));
    } catch (error) {
      target.replaceChildren(node("div", "result-empty", error.message));
      if (error.status === 401) notice("Sign in to the Knowledge Assistant to use the Agent Hub.", "denied");
    }
  }

  async function loadHub() {
    state.csrf = null;
    try {
      await csrf();
      notice("Signed session active. Tool access and results are scoped to this account.", "success");
      await Promise.all([refreshCatalogue(), refreshApprovals(), refreshHistory()]);
    } catch (error) {
      notice("Sign in through the Knowledge Assistant to use the Hub.", "denied");
    }
  }

  function openHub() {
    $("#homeView").classList.add("hidden");
    $("#toolView").classList.add("hidden");
    $("#agentHubView").classList.remove("hidden");
    $("#crumbTitle").textContent = "Agent Hub";
    document.querySelectorAll(".nav-tool,[data-view=home],[data-view=agent-hub]").forEach((item) => item.classList.remove("active"));
    $("[data-view=agent-hub]").classList.add("active");
    loadHub();
  }

  $("[data-view=agent-hub]").addEventListener("click", openHub);
  $("#hubPreviewButton").addEventListener("click", preview);
  $("#hubRunButton").addEventListener("click", run);
  $("#hubCancelButton").addEventListener("click", cancel);
  $("#hubRefreshButton").addEventListener("click", refreshCatalogue);
  $("#hubHistoryButton").addEventListener("click", refreshHistory);
  $("#hubQuestion").addEventListener("input", () => {
    state.preview = null;
    $("#hubRunButton").disabled = true;
    $("#hubRunState").textContent = "PREVIEW REQUIRED";
  });
})();
