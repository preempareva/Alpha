(() => {
  "use strict";

  const app = document.querySelector("#inventory-app");
  if (!app) return;
  const base = app.dataset.apiBase || "/tools/replenishment";
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const number = (value, digits = 1) => Number.isFinite(Number(value))
    ? Number(value).toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
  const currency = (value) => Number.isFinite(Number(value))
    ? new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value)
    : "—";

  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/inventory.css";
  document.head.append(style);

  async function request(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof data.detail === "string" ? data.detail : "The request could not be completed.";
      throw new Error(message);
    }
    return data;
  }

  function notify(message, error = false) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.toggle("error", error);
    toast.classList.add("visible");
    window.clearTimeout(notify.timer);
    notify.timer = window.setTimeout(() => toast.classList.remove("visible"), 4600);
  }

  function loading(button, text) {
    if (!button) return () => {};
    const previous = button.textContent;
    button.disabled = true;
    button.dataset.previous = previous;
    button.textContent = text;
    return () => {
      button.disabled = false;
      button.textContent = button.dataset.previous || previous;
    };
  }

  function setTabs() {
    document.querySelectorAll(".tower-tabs [data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".tower-tabs [data-tab]").forEach((item) => item.classList.remove("active"));
        document.querySelectorAll(".tower-panel").forEach((panel) => panel.classList.remove("active"));
        button.classList.add("active");
        $(`#panel-${button.dataset.tab}`).classList.add("active");
        if (button.dataset.tab === "approvals") refreshApprovals();
      });
    });
  }

  function fillSelectors() {
    const sku = $("#sku");
    const location = $("#location");
    sku.replaceChildren(...Array.from({ length: 24 }, (_, index) => {
      const option = document.createElement("option");
      option.value = `SKU-${String(index + 1).padStart(3, "0")}`;
      option.textContent = option.value;
      return option;
    }));
    location.replaceChildren(...["LOC-001", "LOC-002", "LOC-003"].map((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      return option;
    }));
  }

  function setMetricCards(data) {
    const cover = data.days_of_cover == null ? "No positive demand" : `${number(data.days_of_cover, 1)} days`;
    const values = [
      [number(data.available_to_promise, 0), `${number(data.on_hand, 0)} on hand − ${number(data.reserved, 0)} reserved − ${number(data.blocked, 0)} blocked`],
      [number(data.inventory_position, 0), `${number(data.confirmed_incoming, 0)} confirmed inbound − ${number(data.backorders, 0)} backorders`],
      [cover, data.cover_status.replaceAll("_", " ")],
      [`${number(data.lead_time_days, 0)} days`, `${esc(data.supplier_id)} · reliability ${number(data.supplier_reliability * 100, 0)}%`],
    ];
    $("#inventory-metrics").innerHTML = values.map(([value, sub], index) => `
      <article class="metric-card metric-${index + 1}"><small>${["Available to promise", "Inventory position", "Days of cover", "Supplier lead time"][index]}</small>
      <strong>${esc(value)}</strong><span>${sub}</span></article>`).join("");
    renderStockBreakdown(data);
    renderPurchaseOrders(data);
  }

  function renderStockBreakdown(data) {
    const values = [
      ["On hand", Number(data.on_hand), "on-hand"],
      ["Reserved", Number(data.reserved), "reserved"],
      ["Blocked", Number(data.blocked), "blocked"],
      ["Available to promise", Number(data.available_to_promise), "available"],
      ["Confirmed inbound", Number(data.confirmed_incoming), "inbound"],
      ["Backorders", Number(data.backorders), "backorders"],
      ["Inventory position", Number(data.inventory_position), "position"],
    ];
    const scale = Math.max(1, ...values.map(([, value]) => Math.abs(value)));
    $("#stock-breakdown").innerHTML = values.map(([label, value, cls]) => `<div class="stock-line">
      <span>${esc(label)}</span><div class="stock-track"><i class="stock-fill ${cls}" style="width:${Math.min(100, Math.abs(value) / scale * 100)}%"></i></div>
      <strong>${number(value, 0)}</strong></div>`).join("");
  }

  function renderPurchaseOrders(data) {
    $("#supplier-caption").textContent = `${data.supplier_id} · ${number(data.supplier_reliability * 100, 0)}% reliable · ${currency(data.unit_cost)} / unit`;
    const rows = data.purchase_orders || [];
    if (!rows.length) {
      $("#purchase-orders").innerHTML = '<p class="empty-state">No synthetic supplier delivery records for this SKU and location.</p>';
      return;
    }
    $("#purchase-orders").innerHTML = `<table><thead><tr><th>Reference</th><th>Expected</th><th>Open units</th><th>Supplier</th><th>Status</th></tr></thead><tbody>
      ${rows.map((row) => `<tr><td>${esc(row.po_id)}</td><td>${esc(row.expected_date)}</td><td>${number(row.open_qty, 0)}</td><td>${esc(row.supplier_id)}</td><td><span class="risk-tag ${row.status === "delayed" ? "medium" : "low"}">${esc(row.status)}</span></td></tr>`).join("")}
      </tbody></table>`;
  }

  function renderForecast(data) {
    const rows = data.forecast || [];
    $("#forecast-model").textContent = data.model.replaceAll("_", " ");
    if (!rows.length) {
      $("#forecast-chart").innerHTML = '<p class="empty-state">No forecast is available for this series.</p>';
      return;
    }
    const width = 720;
    const height = 230;
    const left = 42;
    const right = 18;
    const top = 18;
    const bottom = 34;
    const max = Math.max(1, ...rows.map((row) => Number(row.p90) || 0));
    const x = (index) => left + index * ((width - left - right) / Math.max(1, rows.length - 1));
    const y = (value) => height - bottom - (Number(value) / max) * (height - top - bottom);
    const upper = rows.map((row, index) => `${x(index)},${y(row.p90)}`).join(" ");
    const lower = [...rows].reverse().map((row, reverseIndex) => {
      const index = rows.length - reverseIndex - 1;
      return `${x(index)},${y(row.p10)}`;
    }).join(" ");
    const line = rows.map((row, index) => `${index ? "L" : "M"}${x(index)},${y(row.p50)}`).join(" ");
    const grid = [0, 0.5, 1].map((ratio) => {
      const gy = top + ratio * (height - top - bottom);
      const label = Math.round(max * (1 - ratio));
      return `<g><line x1="${left}" y1="${gy}" x2="${width - right}" y2="${gy}" class="chart-grid"/><text x="${left - 9}" y="${gy + 4}" text-anchor="end" class="chart-axis">${label}</text></g>`;
    }).join("");
    const labels = rows.map((row, index) => `<text x="${x(index)}" y="${height - 9}" text-anchor="middle" class="chart-axis">${esc(row.week.slice(5))}</text>`).join("");
    const circles = rows.map((row, index) => `<circle cx="${x(index)}" cy="${y(row.p50)}" r="4.5" class="chart-point"><title>${esc(row.week)} median ${esc(row.p50)} units</title></circle>`).join("");
    $("#forecast-chart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Six week demand forecast with empirical 10th to 90th percentile range">
      ${grid}<polygon points="${upper} ${lower}" class="forecast-band"/><path d="${line}" class="forecast-median"/>${circles}${labels}</svg>
      <div class="forecast-values">${rows.map((row) => `<div><small>${esc(row.week.slice(5))}</small><strong>${number(row.p50, 1)}</strong><span>${number(row.p10, 1)}–${number(row.p90, 1)} units</span></div>`).join("")}</div>`;
  }

  function renderRisk(data) {
    const rows = data.rows || [];
    const excess = data.excess_rows || [];
    $("#excess-count").textContent = `${number(data.excess_count, 0)} positions`;
    if (!excess.length) {
      $("#excess-table").innerHTML = '<p class="empty-state">No positions exceed the current maximum-stock policy.</p>';
    } else {
      $("#excess-table").innerHTML = `<table><thead><tr><th>SKU</th><th>Location</th><th>Excess units</th><th>Inventory position</th><th>Cover</th></tr></thead><tbody>
        ${excess.slice(0, 12).map((row) => `<tr><td>${esc(row.sku)}</td><td>${esc(row.location)}</td><td>${number(row.excess_units, 0)}</td>
        <td>${number(row.inventory_position, 0)}</td><td>${row.days_of_cover == null ? "n/a" : `${number(row.days_of_cover, 1)} d`}</td></tr>`).join("")}
        </tbody></table><p class="table-note">Showing ${Math.min(excess.length, 12)} of ${number(data.excess_count, 0)} synthetic excess positions.</p>`;
    }
    if (!rows.length) {
      $("#risk-table").innerHTML = '<p class="empty-state">No risk rows were returned.</p>';
      return;
    }
    $("#risk-table").innerHTML = `<table><thead><tr><th>Risk / excess</th><th>SKU · location</th><th>Cover</th><th>Position</th></tr></thead><tbody>
      ${rows.slice(0, 12).map((row) => `<tr><td title="${esc(row.reason)}"><span class="risk-tag ${row.risk_level.toLowerCase()}">${esc(row.risk_level)}</span></td>
      <td><button class="row-select" data-sku="${esc(row.sku)}" data-location="${esc(row.location)}">${esc(row.sku)}<small>${esc(row.location)}</small></button></td>
      <td>${row.days_of_cover == null ? "n/a" : `${number(row.days_of_cover, 1)} d`}</td><td>${number(row.inventory_position, 0)}</td></tr>`).join("")}
      </tbody></table><p class="table-note">Showing ${Math.min(rows.length, 12)} of ${number(data.count, 0)} synthetic positions · risk reasons use a six week baseline.</p>`;
    $("#risk-table").querySelectorAll("[data-sku]").forEach((button) => button.addEventListener("click", () => {
      $("#sku").value = button.dataset.sku;
      $("#location").value = button.dataset.location;
      refreshAnalysis();
    }));
  }

  async function refreshAnalysis() {
    const button = $("#refresh-risk");
    const restore = loading(button, "Refreshing…");
    try {
      const sku = encodeURIComponent($("#sku").value);
      const location = encodeURIComponent($("#location").value);
      const [position, forecast, risks] = await Promise.all([
        request(`${base}/api/tower/position/${sku}/${location}`),
        request(`${base}/api/tower/forecast/${sku}/${location}?horizon=6`),
        request(`${base}/api/tower/risk?weeks=6&limit=20`),
      ]);
      setMetricCards(position);
      renderForecast(forecast);
      renderRisk(risks);
    } catch (error) {
      notify(error.message, true);
    } finally {
      restore();
    }
  }

  function renderTable(target, headings, rows, renderers) {
    if (!rows.length) {
      target.innerHTML = '<p class="empty-state">No feasible options were found for the current constraints.</p>';
      return;
    }
    target.innerHTML = `<table><thead><tr>${headings.map((heading) => `<th>${esc(heading)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map((row) => `<tr>${renderers.map((render) => `<td>${render(row)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }

  function renderScenarioChart(rows) {
    if (!rows.length) return "";
    const width = 740;
    const height = 255;
    const left = 70;
    const right = 150;
    const top = 24;
    const bottom = 43;
    const inventory = rows.map((row) => Number(row.average_inventory_units) || 0);
    const fill = rows.map((row) => Number(row.fill_rate) || 0);
    const minX = Math.min(...inventory);
    const maxX = Math.max(...inventory);
    const minY = Math.max(0, Math.min(...fill) - 0.01);
    const maxY = Math.min(1, Math.max(...fill) + 0.002);
    const x = (value) => left + ((value - minX) / Math.max(maxX - minX, 1)) * (width - left - right);
    const y = (value) => height - bottom - ((value - minY) / Math.max(maxY - minY, 0.001)) * (height - top - bottom);
    const colors = { lean: "#c77a42", balanced: "#3d805e", resilient: "#6676a7" };
    const dots = rows.map((row) => `<g><circle cx="${x(Number(row.average_inventory_units))}" cy="${y(Number(row.fill_rate))}" r="6" fill="${colors[row.policy] || "#597264"}" stroke="#fff" stroke-width="2"><title>${esc(row.condition)} · ${esc(row.policy)} · fill ${number(row.fill_rate * 100, 2)}% · average stock ${number(row.average_inventory_units, 1)}</title></circle>
      <text x="${x(Number(row.average_inventory_units)) + 9}" y="${y(Number(row.fill_rate)) - 7}" class="scenario-point-label">${esc(row.policy)}</text></g>`).join("");
    const axes = `<line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" class="chart-grid"/>
      <line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" class="chart-grid"/>
      <text x="${(left + width - right) / 2}" y="${height - 10}" text-anchor="middle" class="chart-axis">Average inventory units →</text>
      <text x="18" y="${height / 2}" text-anchor="middle" class="chart-axis" transform="rotate(-90 18 ${height / 2})">Fill rate</text>
      <text x="${left - 7}" y="${y(maxY) + 4}" text-anchor="end" class="chart-axis">${number(maxY * 100, 1)}%</text>
      <text x="${left - 7}" y="${y(minY) + 4}" text-anchor="end" class="chart-axis">${number(minY * 100, 1)}%</text>`;
    const legend = ["supplier_delay", "demand_spike"].map((condition, index) => `<span><i class="condition-dot condition-${index}"></i>${esc(condition.replaceAll("_", " "))}</span>`).join("");
    return `<div class="scenario-visual"><div class="scenario-chart-legend">${legend}</div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Scenario tradeoff scatter plot of average inventory and fill rate">${axes}${dots}</svg><p class="table-note">Each point is one fixed-seed policy/condition average. Read the table for stockouts, holding cost, excess, expedite cost and order frequency.</p></div>`;
  }

  async function runScenarios() {
    const button = $("#run-scenarios");
    const restore = loading(button, "Simulating…");
    $("#scenario-table").innerHTML = '<p class="loading-state">Running fixed-seed replications for six policy and disruption combinations…</p>';
    try {
      const result = await request(`${base}/api/tower/scenarios?sku=${encodeURIComponent($("#sku").value)}&location=${encodeURIComponent($("#location").value)}&replications=200`);
      const rows = result.tradeoffs || [];
      $("#scenario-table").classList.remove("table-wrap");
      $("#scenario-table").innerHTML = renderScenarioChart(rows);
      const table = document.createElement("div");
      table.className = "table-wrap scenario-table-wrap";
      renderTable(table, ["Condition", "Policy", "Fill rate", "Stockout days", "Avg stock", "Holding cost", "Excess", "Expedite", "Orders"], rows, [
        (row) => esc(row.condition.replaceAll("_", " ")), (row) => `<span class="policy-name ${esc(row.policy)}">${esc(row.policy)}</span>`,
        (row) => `${number(row.fill_rate * 100, 1)}%`, (row) => number(row.stockout_days),
        (row) => number(row.average_inventory_units), (row) => currency(row.holding_cost_estimate),
        (row) => number(row.excess_units), (row) => currency(row.expedite_cost_estimate), (row) => number(row.order_frequency, 1),
      ]);
      $("#scenario-table").append(table);
    } catch (error) {
      $("#scenario-table").innerHTML = `<p class="error-state">${esc(error.message)}</p>`;
    } finally {
      restore();
    }
  }

  async function loadTransfers() {
    const button = $("#load-transfers");
    const restore = loading(button, "Checking routes…");
    $("#transfer-table").innerHTML = '<p class="loading-state">Comparing source surplus, shortage, route time and transfer cost…</p>';
    try {
      const result = await request(`${base}/api/tower/transfers?limit=40`);
      const rows = result.rows || [];
      renderTable($("#transfer-table"), ["SKU", "Source → destination", "Units", "Route", "Est. transfer cost", "Feasibility"], rows, [
        (row) => esc(row.sku), (row) => `${esc(row.source_location)} → ${esc(row.destination_location)}`,
        (row) => number(row.quantity, 0), (row) => `${number(row.route_days, 0)} days`,
        (row) => currency(row.estimated_transfer_cost), (row) => `<span class="risk-tag ${row.eligible ? "low" : "high"}">${row.eligible ? "feasible" : "blocked"}</span>`,
      ]);
    } catch (error) {
      $("#transfer-table").innerHTML = `<p class="error-state">${esc(error.message)}</p>`;
    } finally {
      restore();
    }
  }

  async function csrf() {
    const result = await request("/api/agent/csrf");
    return result.csrf_token;
  }

  async function askHub(question) {
    const token = await csrf();
    const preview = await request("/api/agent/preview", {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ question }),
    });
    if (preview.status !== "ready") throw new Error(preview.question || "The Hub could not prepare this action.");
    const names = preview.steps.map((step) => step.tool).join(" → ");
    const result = await request("/api/agent/ask", {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token,
        "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ question }),
    });
    return { ...result, plannedTools: names };
  }

  async function requestDraft() {
    const button = $("#request-draft");
    const restore = loading(button, "Requesting approval…");
    try {
      const budget = $("#budget").value.trim();
      const budgetClause = budget ? ` with budget ${Number(budget).toFixed(2)}` : "";
      const result = await askHub(`Draft a replenishment proposal for ${$("#sku").value} at ${$("#location").value}${budgetClause}`);
      notify(`Approval recorded in the Hub queue · ${result.plannedTools}`);
      document.querySelector('[data-tab="approvals"]').click();
      await refreshApprovals();
    } catch (error) {
      notify(error.message, true);
    } finally {
      restore();
    }
  }

  async function decideApproval(approvalId, decision) {
    const token = await csrf();
    const result = await request(`/api/agent/approvals/${encodeURIComponent(approvalId)}/${decision}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ reason: `Inventory Control Tower ${decision}` }),
    });
    notify(`Approval ${decision} · run ${result.run?.status || result.approval?.status || "updated"}`);
    await refreshApprovals();
  }

  async function simulateProposal(proposalId, button) {
    const restore = loading(button, "Requesting approval…");
    try {
      const result = await askHub(`Simulate execution of replenishment proposal ${proposalId}`);
      notify(`Simulation approval recorded · ${result.plannedTools}`);
      await refreshApprovals();
    } catch (error) {
      notify(error.message, true);
    } finally {
      restore();
    }
  }

  async function refreshApprovals() {
    const approvalsNode = $("#approval-list");
    const proposalsNode = $("#proposal-list");
    try {
      const [pending, proposals] = await Promise.all([
        request("/api/agent/approvals?status=pending"),
        request(`${base}/api/tower/proposals`),
      ]);
      const items = pending.approvals || [];
      approvalsNode.innerHTML = items.length ? items.map((approval) => `<article class="tower-card approval-card">
        <small>NEEDS APPROVAL · ${esc(approval.status)}</small><h3>${esc(approval.reason || "Inventory draft action")}</h3>
        <p>Requested by ${esc(approval.requested_by || approval.user_id)} · run <code>${esc(approval.run_id)}</code></p>
        <div class="approval-actions"><button class="button-primary" data-approve="${esc(approval.approval_id)}">Approve & resume</button>
        <button class="button-quiet" data-reject="${esc(approval.approval_id)}">Reject</button></div></article>`).join("")
        : '<article class="tower-card"><p class="empty-state">No pending approval requests are visible in this account scope.</p></article>';
      approvalsNode.querySelectorAll("[data-approve]").forEach((button) => button.addEventListener("click", () => {
        decideApproval(button.dataset.approve, "approve").catch((error) => notify(error.message, true));
      }));
      approvalsNode.querySelectorAll("[data-reject]").forEach((button) => button.addEventListener("click", () => {
        decideApproval(button.dataset.reject, "reject").catch((error) => notify(error.message, true));
      }));
      const saved = proposals.proposals || [];
      proposalsNode.innerHTML = saved.length ? saved.map((proposal) => `<article class="tower-card proposal-card">
        <div class="card-title"><div><small>${esc(proposal.status)} · ${esc(proposal.approval_status)}</small><h3>${esc(proposal.sku)} <span>at ${esc(proposal.location)}</span></h3></div><span class="status-pill">${number(proposal.suggested_units, 0)} units</span></div>
        <p>${esc(proposal.reason.replaceAll("_", " "))} · ${currency(proposal.estimated_cost)} at ${currency(proposal.unit_cost)} / unit</p>
        <p class="fine-print">${esc(proposal.notice)}</p>
        ${proposal.simulation ? `<div class="simulation-result"><strong>SIMULATED ONLY</strong><span>${number(proposal.simulation.simulated_units, 0)} units · no real purchase order created</span></div>`
          : `<button class="button-secondary" data-simulate="${esc(proposal.proposal_id)}">Request simulation approval</button>`}</article>`).join("")
        : '<article class="tower-card"><p class="empty-state">No approved replenishment drafts are saved in this account yet.</p></article>';
      proposalsNode.querySelectorAll("[data-simulate]").forEach((button) => button.addEventListener("click", () => {
        simulateProposal(button.dataset.simulate, button).catch((error) => notify(error.message, true));
      }));
    } catch (error) {
      approvalsNode.innerHTML = `<article class="tower-card"><p class="error-state">${esc(error.message)}. Sign in through Knowledge Assistant, then reload this queue.</p></article>`;
      proposalsNode.replaceChildren();
    }
  }

  async function checkQuality() {
    try {
      const report = await request(`${base}/api/tower/quality`);
      $("#quality-status").textContent = report.valid ? "VALIDATED" : "CHECK FAILED";
      $("#quality-status").classList.toggle("quality-error", !report.valid);
      const count = Object.values(report.rows_by_table || {}).reduce((sum, value) => sum + Number(value), 0);
      $("#quality-detail").textContent = report.valid
        ? `${number(count, 0)} synthetic records · ${report.tables_checked} fixed tables`
        : (report.issue_codes || []).join(", ");
    } catch (error) {
      $("#quality-status").textContent = "UNAVAILABLE";
      $("#quality-status").classList.add("quality-error");
      $("#quality-detail").textContent = error.message;
    }
  }

  setTabs();
  fillSelectors();
  $("#refresh-risk").addEventListener("click", refreshAnalysis);
  $("#sku").addEventListener("change", refreshAnalysis);
  $("#location").addEventListener("change", refreshAnalysis);
  $("#run-scenarios").addEventListener("click", runScenarios);
  $("#load-transfers").addEventListener("click", loadTransfers);
  $("#request-draft").addEventListener("click", requestDraft);
  $("#refresh-approvals").addEventListener("click", refreshApprovals);
  checkQuality();
  refreshAnalysis();
})();
