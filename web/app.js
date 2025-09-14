const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function setLoading(loading) {
  const btn = $("#submit-btn");
  btn.disabled = loading;
  btn.textContent = i18next.t(loading ? "analyzing" : "analyze");
}

async function handleSubmit(e) {
  e.preventDefault();
  const file = $("#file").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  form.append("mode", document.querySelector('input[name="mode"]:checked').value);
  form.append("output", document.querySelector('input[name="output"]:checked').value);
  form.append("reset_state", $("#reset-state").checked ? "true" : "false");

  setLoading(true);
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderResult(data);
  } catch (err) {
    alert(i18next.t("error") + ": " + err);
  } finally {
    setLoading(false);
  }
}

function renderResult(data) {
  $("#result").classList.remove("hidden");
  const meta = $("#meta");
  const totals = data.totals || {};
  const metaParts = [
    `${i18next.t("source_file")}: ${data.source_filename}`,
    `${i18next.t("user")}: ${data.user ? data.user : i18next.t("unrecognized")}`,
    `${i18next.t("mode")}: ${i18next.t(data.mode === "incremental" ? "mode_incremental" : "mode_full")}`,
    `${i18next.t("requested_format")}: ${data.requested_format.toUpperCase()}`,
    `${i18next.t("total_issues")}: ${totals.TOTAL ?? 0}`,
  ];
  if (data.first_time_user) {
    metaParts.splice(2, 0, i18next.t("first_time_auto_full"));
  }
  // 僅在實際有重置時顯示（避免 "否" 的噪音）
  if (data.reset_applied) {
    metaParts.splice(4, 0, `${i18next.t("reset_applied")}: ${i18next.t("yes")}`);
  }
  const metaText = metaParts.join(" · ");
  meta.textContent = metaText;

  const link = $("#download-link");
  link.href = data.download_url;
  // Extract timestamp from filename suffix `_analysis_YYYYMMDD_HHMMSS.*`
  let ts = "";
  if (data.output_filename) {
    const m = data.output_filename.match(/_analysis_(\d{8}_\d{6})\./);
    if (m) ts = m[1];
  }
  const fmtLabel = data.requested_format === 'excel' ? 'Excel' : data.requested_format.toUpperCase();
  const isZh = (i18next.language || '').startsWith('zh');
  const l = isZh ? '（' : ' (';
  const r = isZh ? '）' : ')';
  link.textContent = `${i18next.t("download")} ${fmtLabel}${ts ? `${l}${ts}${r}` : ''}`;

  const status = $("#status");
  status.innerHTML = "";
  if (data.status) {
    const s = data.status;
    const p = document.createElement("div");
    p.className = "muted";
    p.textContent = `${i18next.t("status_info")}: ${s.last_date}, ${i18next.t("complete_days")}: ${s.complete_days}, ${i18next.t("last_time")}: ${s.last_analysis_time || "-"}`;
    status.appendChild(p);
  }

  const tbody = $("#issues-table tbody");
  tbody.innerHTML = "";
  (data.issues_preview || []).forEach((it) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.date}</td>
      <td>${it.type}</td>
      <td class="num">${it.duration_minutes}</td>
      <td>${it.description}</td>
      <td>${it.time_range || ""}</td>
      <td>${it.calculation || ""}</td>
      <td>${it.status || ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById("analyze-form").addEventListener("submit", handleSubmit);

// i18n setup
async function initI18n() {
  const resources = await fetch("/locales/i18n.json").then((r) => r.json());
  i18next.init({
    lng: navigator.language.startsWith("zh") ? "zh" : "en",
    debug: false,
    resources,
  }, () => {
    applyI18n();
  });

  $("#lang-select").value = i18next.language;
  $("#lang-select").addEventListener("change", (e) => {
    i18next.changeLanguage(e.target.value, applyI18n);
  });
}

function applyI18n() {
  $$('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    el.textContent = i18next.t(key);
  });
  // Update button text if needed
  setLoading($("#submit-btn").disabled);
}

initI18n();
