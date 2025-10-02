const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let cleanupContext = null;
let pendingFile = null;

function getSelectedValue(name) {
  const node = document.querySelector(`input[name="${name}"]:checked`);
  return node ? node.value : null;
}

function getCleanupState() {
  return {
    enabled: $("#cleanup-exports").checked,
    debug: $("#debug-mode").checked,
    output: getSelectedValue("output") || "excel",
    exportPolicy: getSelectedValue("export_policy") || "merge",
  };
}

function resetCleanupContext() {
  cleanupContext = null;
}

function toggleCleanupButton() {
  const btn = $("#cleanup-preview-btn");
  if (!btn) return;
  const enabled = $("#cleanup-exports").checked;
  btn.classList.toggle("hidden", !enabled);
  btn.disabled = !enabled;
}

function setLoading(loading) {
  const btn = $("#submit-btn");
  btn.disabled = loading;
  btn.textContent = i18next.t(loading ? "analyzing" : "analyze");
  const previewBtn = $("#cleanup-preview-btn");
  if (previewBtn) previewBtn.disabled = loading || previewBtn.classList.contains("hidden");
}

async function handleSubmit(event) {
  event.preventDefault();
  const fileInput = $("#file");
  const file = fileInput.files[0];
  if (!file) return;
  pendingFile = file;

  const cleanupState = getCleanupState();
  if (cleanupState.enabled) {
    const contextValid =
      cleanupContext &&
      cleanupContext.confirmed &&
      cleanupContext.filename === file.name &&
      cleanupContext.output === cleanupState.output &&
      cleanupContext.debug === cleanupState.debug &&
      cleanupContext.exportPolicy === cleanupState.exportPolicy;

    if (!contextValid) {
      await requestCleanupPreview(file, cleanupState);
      return;
    }
  }

  await submitAnalyze(file, cleanupState);
}

async function submitAnalyze(file, cleanupState) {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", getSelectedValue("mode"));
  form.append("output", cleanupState.output);
  form.append("reset_state", $("#reset-state").checked ? "true" : "false");
  form.append("debug", cleanupState.debug ? "true" : "false");
  form.append("export_policy", cleanupState.exportPolicy);
  form.append("cleanup_exports", cleanupState.enabled ? "true" : "false");

  if (cleanupState.enabled && cleanupContext && cleanupContext.confirmed) {
    form.append("cleanup_token", cleanupContext.token);
    form.append("cleanup_snapshot", JSON.stringify(cleanupContext.snapshot));
  }

  setLoading(true);
  try {
    const res = await fetch("/api/analyze", { method: "POST", body: form });
    if (res.status === 409) {
      const detail = await res.json();
      if (detail.preview) {
        resetCleanupContext();
        await showCleanupModal(detail.preview, file, cleanupState);
        return;
      }
      throw new Error(detail.reason || res.statusText);
    }
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderResult(data);
  } catch (err) {
    alert(i18next.t("error") + ": " + err);
  } finally {
    setLoading(false);
  }
}

async function requestCleanupPreview(file, cleanupState) {
  try {
    const payload = {
      filename: file.name,
      output: cleanupState.output,
      debug: cleanupState.debug,
      export_policy: cleanupState.exportPolicy,
    };
    const res = await fetch("/api/exports/cleanup-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const preview = await res.json();
    await showCleanupModal(preview, file, cleanupState);
  } catch (err) {
    alert(i18next.t("error") + ": " + err);
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
  if (data.first_time_user) metaParts.splice(2, 0, i18next.t("first_time_auto_full"));
  if (data.debug_mode) metaParts.splice(3, 0, `${i18next.t("debug_mode")}: ${i18next.t("yes")}`);
  if (data.reset_applied) metaParts.splice(4, 0, `${i18next.t("reset_applied")}: ${i18next.t("yes")}`);
  meta.textContent = metaParts.join(" · ");

  const link = $("#download-link");
  link.href = data.download_url;
  let ts = "";
  if (data.output_filename) {
    const match = data.output_filename.match(/_analysis_(\d{8}_\d{6})\./);
    if (match) ts = match[1];
  }
  const fmtLabel = data.requested_format === "excel" ? "Excel" : data.requested_format.toUpperCase();
  const isZh = (i18next.language || "").startsWith("zh");
  const l = isZh ? "（" : " (";
  const r = isZh ? "）" : ")";
  link.textContent = `${i18next.t("download")} ${fmtLabel}${ts ? `${l}${ts}${r}` : ""}`;

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

  const cleanupStatus = $("#cleanup-status");
  cleanupStatus.innerHTML = "";
  if (data.cleanup) {
    const line = document.createElement("div");
    line.className = "muted";
    if (data.cleanup.status === "performed") {
      const deleted = (data.cleanup.deleted || []).join(", ");
      line.textContent = deleted
        ? i18next.t("cleanup_performed_with", { files: deleted })
        : i18next.t("cleanup_performed");
    } else if (data.cleanup.status === "stale") {
      line.textContent = i18next.t("cleanup_stale");
    } else if (data.cleanup.status === "skipped") {
      line.textContent = i18next.t("cleanup_skipped");
    }
    cleanupStatus.appendChild(line);
  }

  resetCleanupContext();
}

function populateList(listNode, items) {
  listNode.innerHTML = "";
  items.forEach((item) => {
    const li = document.createElement("li");
    const size = item.size != null ? `${(item.size / 1024).toFixed(1)} KB` : "";
    li.textContent = size ? `${item.name} · ${size}` : item.name;
    listNode.appendChild(li);
  });
}

async function showCleanupModal(preview, file, cleanupState) {
  const modal = $("#cleanup-modal");
  const backdrop = $("#modal-backdrop");
  const backupList = $("#cleanup-backup-list");
  const canonicalList = $("#cleanup-canonical-list");
  const canonicalContainer = $("#cleanup-canonical-container");
  const emptyState = $("#cleanup-modal-empty");

  const backups = (preview.items || []).filter((item) => item.kind === "backup");
  const canonicals = (preview.items || []).filter((item) => item.kind === "canonical" && item.delete);

  populateList(backupList, backups);
  populateList(canonicalList, canonicals);

  canonicalContainer.classList.toggle("hidden", canonicals.length === 0);
  emptyState.classList.toggle("hidden", backups.length + canonicals.length !== 0);

  modal.classList.remove("hidden");
  backdrop.classList.remove("hidden");

  return new Promise((resolve) => {
    const cancelBtn = $("#cleanup-cancel");
    const confirmBtn = $("#cleanup-confirm");

    const cleanupHandlers = () => {
      cancelBtn.onclick = null;
      confirmBtn.onclick = null;
      modal.classList.add("hidden");
      backdrop.classList.add("hidden");
    };

    cancelBtn.onclick = () => {
      cleanupHandlers();
      resetCleanupContext();
      resolve(false);
    };

    confirmBtn.onclick = async () => {
      cleanupContext = {
        confirmed: true,
        token: preview.token,
        snapshot: preview.snapshot,
        filename: file.name,
        output: cleanupState.output,
        debug: cleanupState.debug,
        exportPolicy: cleanupState.exportPolicy,
      };
      cleanupHandlers();
      await submitAnalyze(file, cleanupState);
      resolve(true);
    };
  });
}

document.getElementById("analyze-form").addEventListener("submit", handleSubmit);

async function initI18n() {
  const resources = await fetch("/locales/i18n.json").then((r) => r.json());
  i18next.init(
    {
      lng: navigator.language.startsWith("zh") ? "zh" : "en",
      debug: false,
      resources,
    },
    () => {
      applyI18n();
    }
  );

  $("#lang-select").value = i18next.language;
  $("#lang-select").addEventListener("change", (event) => {
    i18next.changeLanguage(event.target.value, applyI18n);
  });
}

function applyI18n() {
  $$('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    el.textContent = i18next.t(key);
  });
  setLoading($("#submit-btn").disabled);
}

initI18n();

toggleCleanupButton();
["#cleanup-exports", "#debug-mode", "#file"].forEach((selector) => {
  const node = $(selector);
  if (!node) return;
  node.addEventListener("change", () => {
    resetCleanupContext();
    toggleCleanupButton();
  });
});

$$('input[name="output"]').forEach((node) =>
  node.addEventListener("change", () => {
    resetCleanupContext();
  })
);

$$('input[name="mode"]').forEach((node) =>
  node.addEventListener("change", () => {
    // nothing extra, but keep parity for completeness
  })
);

$$('input[name="export_policy"]').forEach((node) =>
  node.addEventListener("change", () => {
    resetCleanupContext();
  })
);

const previewBtn = $("#cleanup-preview-btn");
if (previewBtn) {
  previewBtn.addEventListener("click", async () => {
    const file = $("#file").files[0];
    if (!file) {
      alert(i18next.t("cleanup_need_file"));
      return;
    }
    const cleanupState = getCleanupState();
    await requestCleanupPreview(file, cleanupState);
  });
}
