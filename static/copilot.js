(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  })[char]);
  const state = { csrf: "", profile: null, staged: null, result: null, project: null };
  const base = "/tools/copilot/api";

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  async function mutate(path, body, contentType = true) {
    if (!state.csrf) state.csrf = (await request(`${base}/csrf`)).csrf_token;
    const headers = { "X-CSRF-Token": state.csrf };
    if (contentType) headers["Content-Type"] = "application/json";
    return request(`${base}/${path}`, {
      method: "POST", headers,
      body: contentType ? JSON.stringify(body) : body
    });
  }

  function notice(message, kind = "info") {
    const target = $("#copilotNotice");
    if (!target) return;
    target.textContent = message;
    target.className = `copilot-notice ${kind}`;
  }

  function open(project) {
    if (!project) return;
    state.project = project;
    $("#agentHubView")?.classList.add("hidden");
    $("#homeView").classList.add("hidden");
    $("#toolView").classList.remove("hidden");
    document.querySelectorAll("[data-view=agent-hub],[data-view=home]").forEach(item => item.classList.remove("active"));
    $("#crumbTitle").textContent = project.title;
    $("#activeTitle").textContent = project.title;
    $("#activeDescription").textContent = project.description;
    $("#activeIcon").textContent = project.icon;
    $("#openDocs").href = `/tools/${project.id}/docs`;
    document.querySelectorAll(".nav-tool").forEach(item => item.classList.toggle("active", item.dataset.id === project.id));
    $("#toolStudio").innerHTML = `
      <div class="studio-intro"><div><div class="eyebrow muted">INSIGHTS WORKFLOW</div><h2>Business Data Copilot</h2>
      <p>Upload a small CSV or Excel workbook, confirm how each column should be used, then ask for a checked result.</p></div>
      <span class="source-badge">READ ONLY · SYNTHETIC DEMO</span></div>
      <div class="copilot-page">
        <div id="copilotNotice" class="copilot-notice" role="status" aria-live="polite">Check your sign-in, or try the synthetic demo.</div>
        <div class="copilot-grid">
          <section class="studio-card copilot-setup">
            <div class="copilot-section-head"><div><h3>Workspace session</h3><p>Identity and workspace come from your signed-in Alpha session.</p></div><span id="copilotUser" class="status-chip">SIGNED OUT</span></div>
            <form id="copilotLogin" class="copilot-login">
              <label class="field"><span>Username</span><input name="username" autocomplete="username" required maxlength="80"></label>
              <label class="field"><span>Password</span><input name="password" type="password" autocomplete="current-password" required maxlength="128"></label>
              <button class="secondary-button">Sign in</button>
            </form>
            <div class="copilot-session-actions"><button id="copilotLogout" type="button" class="quiet-button hidden">Sign out</button></div>
            <div class="copilot-divider"></div>
            <div class="copilot-section-head"><div><h3>Choose data</h3><p>CSV or XLSX · up to 10 MB · preview stays temporary until you confirm the schema.</p></div></div>
            <form id="copilotUpload" class="copilot-upload">
              <label class="field wide"><span>Upload a data file</span><input name="file" type="file" accept=".csv,.xlsx" required></label>
              <button id="copilotUploadButton" class="action-button" type="submit" disabled>Profile file</button>
              <button id="copilotDemoButton" class="secondary-button" type="button" disabled>Use synthetic demo</button>
            </form>
            <div id="copilotSchema" class="copilot-schema hidden"></div>
            <div id="copilotProfile" class="copilot-profile result-empty">Sign in to view your dataset, or load the SYNTHETIC demo.</div>
          </section>
          <section class="studio-card copilot-analysis">
            <div class="copilot-section-head"><div><h3>Ask a question</h3><p>Plans use confirmed columns and bounded, read-only aggregation.</p></div><span id="copilotDataBadge" class="status-chip">NO DATASET</span></div>
            <form id="copilotQuery" class="copilot-query">
              <label class="field"><span>Your question</span><textarea name="question" rows="3" maxlength="1000" placeholder="For example: Show monthly revenue by region" required minlength="4"></textarea></label>
              <div class="copilot-query-actions"><button id="copilotRun" class="action-button" type="submit" disabled>Run verified query</button><span class="copilot-planner-label">Deterministic planner · local LLM optional</span></div>
            </form>
            <div id="copilotResult" class="copilot-result result-empty">Verified results, provenance, and a safe CSV export appear here.</div>
          </section>
        </div>
      </div>`;
    $("#copilotLogin").addEventListener("submit", login);
    $("#copilotLogout").addEventListener("click", logout);
    $("#copilotUpload").addEventListener("submit", upload);
    $("#copilotDemoButton").addEventListener("click", useDemo);
    $("#copilotQuery").addEventListener("submit", query);
    refresh();
  }

  async function refresh() {
    state.profile = null;
    state.staged = null;
    state.result = null;
    const schema = $("#copilotSchema");
    if (schema) { schema.classList.add("hidden"); schema.replaceChildren(); }
    const profilePanel = $("#copilotProfile");
    if (profilePanel) { profilePanel.className = "copilot-profile result-empty"; profilePanel.textContent = "Sign in to view your dataset, or load the SYNTHETIC demo."; }
    const output = $("#copilotResult");
    if (output) { output.className = "copilot-result result-empty"; output.textContent = "Verified results, provenance, and a safe CSV export appear here."; }
    try {
      const [csrf, session] = await Promise.all([
        request(`${base}/csrf`), request("/tools/knowledge/api/me")
      ]);
      state.csrf = csrf.csrf_token;
      $("#copilotUser").textContent = `SIGNED IN · ${session.user.username}`;
      $("#copilotUser").className = "status-chip";
      $("#copilotLogin").classList.add("hidden");
      $("#copilotLogout").classList.remove("hidden");
      $("#copilotUploadButton").disabled = false;
      $("#copilotDemoButton").disabled = false;
      try {
        state.profile = await request(`${base}/profile`);
        renderProfile(state.profile);
        $("#copilotRun").disabled = false;
        $("#copilotDataBadge").textContent = state.profile.data_label;
        $("#copilotDataBadge").className = "status-chip";
        notice("Dataset ready. Ask a question or replace the current dataset.", "success");
      } catch (error) {
        if (!String(error.message).includes("Upload or select")) throw error;
        $("#copilotProfile").className = "copilot-profile result-empty";
        $("#copilotProfile").textContent = "No confirmed dataset yet. Upload a file or use the synthetic demo.";
        $("#copilotRun").disabled = true;
        $("#copilotDataBadge").textContent = "NO DATASET";
        notice("Signed in. Choose a file or load the clearly labelled synthetic demo.", "success");
      }
    } catch (error) {
      state.csrf = "";
      $("#copilotUser").textContent = "SIGNED OUT";
      $("#copilotUser").className = "status-chip warn";
      $("#copilotLogin").classList.remove("hidden");
      $("#copilotLogout").classList.add("hidden");
      $("#copilotUploadButton").disabled = true;
      $("#copilotDemoButton").disabled = true;
      $("#copilotRun").disabled = true;
      notice("Sign in with your existing Knowledge Assistant account to use a private workspace.", "info");
    }
  }

  async function login(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    try {
      await request("/tools/knowledge/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values)
      });
      form.reset();
      await refresh();
    } catch (error) { notice(error.message, "error"); }
  }

  async function logout() {
    try { await request("/tools/knowledge/api/logout", { method: "POST" }); }
    catch (_) { /* The session may already have expired. */ }
    await refresh();
  }

  async function upload(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("#copilotUploadButton");
    button.disabled = true;
    try {
      const profile = await mutate("upload", new FormData(form), false);
      form.reset();
      stage(profile);
    } catch (error) { notice(error.message, "error"); }
    finally { button.disabled = false; }
  }

  async function useDemo() {
    const button = $("#copilotDemoButton");
    button.disabled = true;
    try { stage(await mutate("demo", {})); }
    catch (error) { notice(error.message, "error"); }
    finally { button.disabled = false; }
  }

  function stage(profile) {
    state.staged = profile;
    $("#copilotDataBadge").textContent = profile.data_label;
    $("#copilotDataBadge").className = "status-chip";
    renderSchema(profile);
    notice(`${profile.filename_label}: ${profile.row_count.toLocaleString()} rows and ${profile.column_count} columns. Review the inferred schema before saving.`, "success");
  }

  function renderSchema(profile) {
    const panel = $("#copilotSchema");
    const rows = profile.columns.map((column, index) => {
      const role = column.suggested_role || "dimension";
      return `<tr><th scope="row">${esc(column.name)}</th><td>${esc(column.inferred_type)}</td><td>${column.null_count}</td>
        <td><label class="copilot-select-label"><span class="sr-only">Type for ${esc(column.name)}</span><select name="type_${index}">${["text", "integer", "number", "date", "boolean"].map(type => `<option value="${type}" ${type === column.inferred_type ? "selected" : ""}>${type}</option>`).join("")}</select></label></td>
        <td><label class="copilot-select-label"><span class="sr-only">Role for ${esc(column.name)}</span><select name="role_${index}">${["dimension", "measure", "date", "exclude"].map(item => `<option value="${item}" ${item === role ? "selected" : ""}>${item}</option>`).join("")}</select></label></td>
        <td><label class="copilot-sensitive"><input type="checkbox" name="sensitive_${index}"><span>Sensitive</span></label></td></tr>`;
    }).join("");
    panel.innerHTML = `<form id="copilotConfirm"><div class="copilot-section-head"><div><h3>Confirm the schema</h3><p>Mark private columns sensitive. They are hidden from previews and planning; only aggregates are allowed. Copilot does not encrypt stored files, so use demo or nonconfidential data.</p></div></div>
      <div class="copilot-table-wrap"><table class="copilot-table"><thead><tr><th>Column</th><th>Detected</th><th>Nulls</th><th>Use type</th><th>Use as</th><th>Privacy</th></tr></thead><tbody>${rows}</tbody></table></div>
      <details class="copilot-preview"><summary>Review the first 20 rows</summary>${tableHtml(profile.preview || [])}</details>
      <button class="action-button" type="submit">Confirm and save this dataset</button></form>`;
    panel.classList.remove("hidden");
    $("#copilotConfirm").addEventListener("submit", confirmSchema);
  }

  async function confirmSchema(event) {
    event.preventDefault();
    if (!state.staged) return;
    const form = event.currentTarget;
    const columns = state.staged.columns.map((column, index) => ({
      name: column.name,
      data_type: form.elements[`type_${index}`].value,
      role: form.elements[`role_${index}`].value,
      sensitive: form.elements[`sensitive_${index}`].checked
    }));
    try {
      await mutate("confirm", { upload_id: state.staged.upload_id, columns });
      state.staged = null;
      $("#copilotSchema").classList.add("hidden");
      await refresh();
      notice("Schema confirmed. The dataset is saved in your workspace until its retention date.", "success");
    } catch (error) { notice(error.message, "error"); }
  }

  function renderProfile(profile) {
    const columns = profile.columns || [];
    const preview = profile.preview || [];
    $("#copilotProfile").className = "copilot-profile";
    $("#copilotProfile").innerHTML = `<div class="copilot-profile-cards">
      <div><small>ROWS</small><strong>${Number(profile.row_count).toLocaleString()}</strong></div>
      <div><small>COLUMNS</small><strong>${columns.length}</strong></div>
      <div><small>DATA LABEL</small><strong>${esc(profile.data_label)}</strong></div>
      <div><small>EXPIRES</small><strong>${esc(String(profile.expires_at || "").slice(0, 10))}</strong></div></div>
      <p class="copilot-hash">Dataset fingerprint · ${esc(String(profile.source_sha256 || "").slice(0, 20))}…</p>
      <details class="copilot-preview"><summary>Confirmed columns and first 20 rows</summary>
        <div class="copilot-table-wrap"><table class="copilot-table"><thead><tr><th>Column</th><th>Type</th><th>Role</th><th>Sensitive</th></tr></thead><tbody>${columns.map(column => "<tr><th scope=\"row\">" + esc(column.name) + "</th><td>" + esc(column.data_type || column.inferred_type) + "</td><td>" + esc(column.role || column.suggested_role) + "</td><td>" + (column.sensitive ? "Yes" : "No") + "</td></tr>").join("")}</tbody></table></div>
        ${tableHtml(preview)}</details>`;
  }

  async function query(event) {
    event.preventDefault();
    const button = $("#copilotRun");
    const question = new FormData(event.currentTarget).get("question");
    button.disabled = true;
    notice("Running the bounded query and checking its result independently…", "info");
    try {
      state.result = await mutate("query", { question });
      renderResult(state.result);
      notice("Independent check passed. This result is ready to review or export.", "success");
    } catch (error) { notice(error.message, "error"); }
    finally { button.disabled = false; }
  }

  function renderResult(result) {
    const target = $("#copilotResult");
    target.className = "copilot-result";
    const rows = result.rows || [];
    const keys = rows.length ? Object.keys(rows[0]) : [];
    target.innerHTML = `<div class="copilot-result-head"><div><span class="status-chip">VERIFIED · ${esc(result.data_label)}</span><h3>Result</h3></div>
      <a class="secondary-button copilot-download" href="${base}/export/${encodeURIComponent(result.query_id)}.csv">Download CSV</a></div>
      <p class="copilot-result-note">${rows.length.toLocaleString()} result rows · ${esc(result.planner_mode)} planner · independent pandas check passed</p>
      ${chartHtml(result.chart, rows)}${tableHtml(rows, keys)}
      <details class="copilot-plan"><summary>Query plan and assumptions</summary><pre></pre></details>
      <details class="copilot-plan"><summary>Provenance</summary><pre class="copilot-provenance"></pre></details>`;
    $(".copilot-plan pre", target).textContent = JSON.stringify({ plan: result.plan, assumptions: result.assumptions }, null, 2);
    $(".copilot-provenance", target).textContent = JSON.stringify(result.provenance, null, 2);
  }

  function tableHtml(rows, specifiedKeys) {
    if (!rows.length) return `<p class="copilot-empty-table">No rows to preview.</p>`;
    const keys = specifiedKeys || Object.keys(rows[0]);
    return `<div class="copilot-table-wrap"><table class="copilot-table"><thead><tr>${keys.map(key => `<th scope="col">${esc(key)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${keys.map(key => `<td>${esc(row[key] == null ? "—" : row[key])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }

  function chartHtml(spec, rows) {
    if (!spec || !spec.x || !spec.y || !rows.length || spec.type === "table") return "";
    const values = rows.map(row => Number(row[spec.y]) || 0);
    const maximum = Math.max(1, ...values.map(value => Math.abs(value)));
    return `<div class="copilot-chart" role="img" aria-label="${esc(spec.type)} chart of ${esc(spec.y)} by ${esc(spec.x)}">${rows.slice(0, 30).map(row => {
      const value = Number(row[spec.y]) || 0;
      const height = Math.max(2, Math.abs(value) / maximum * 100);
      return `<div class="copilot-bar-col"><span class="copilot-bar-value">${esc(value.toLocaleString(undefined, { maximumFractionDigits: 2 }))}</span><div class="copilot-bar" style="height:${height}%"></div><span class="copilot-bar-label">${esc(row[spec.x])}</span></div>`;
    }).join("")}</div>`;
  }

  document.addEventListener("click", event => {
    const button = event.target.closest("[data-id='copilot']");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const projects = window.alphaProjects || [];
    const project = projects.find(item => item.id === "copilot") || {
      id: "copilot", title: "Business Data Copilot", icon: "▤",
      description: "Upload and analyze a dataset with verified, read-only queries."
    };
    open(project);
  }, true);

  window.openCopilot = open;
  request("/api/projects").then(projects => {
    const count = String(projects.length);
    window.alphaProjects = projects;
    ["#navProjectCount", "#projectCountText", "#filterCount"].forEach(selector => {
      const node = $(selector);
      if (node) node.textContent = count;
    });
    const hero = $("#projectCount");
    if (hero) hero.textContent = `/ ${count}`;
  }).catch(() => {});
})();
