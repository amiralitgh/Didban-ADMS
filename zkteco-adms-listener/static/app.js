const state = {
  view: "overview",
  devices: [],
  knownCommands: [],
  backupFile: null,
  backupInspection: null,
  backupTargets: [],
  context: {
    users: "",
    biometrics: "",
    commands: "",
    traffic: ""
  },
  filters: {
    users: [],
    biometrics: [],
    attendance: []
  },
  editingPin: null,
  userTargetSn: null,
  copyUser: null,
  renameSn: null,
  confirmAction: null,
  lastCommandId: null,
  lastCommandIds: [],
  commandPollingTimer: null,
  backupPollTimer: null,
  deviceStatusTimer: null
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const viewTitles = {
  overview: "دستگاه‌ها",
  users: "مدیریت کارکنان",
  biometrics: "اثر انگشت و چهره",
  attendance: "ترددها",
  commands: "عملیات",
  backups: "پشتیبان‌گیری",
  settings: "تنظیمات",
  traffic: "عیب‌یابی"
};

const contextLabels = {
  users: "دستگاه‌های اطلاعات کارکنان",
  biometrics: "دستگاه‌های داده‌های هویتی",
  traffic: "دستگاه ارتباطی"
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[character]));
}

const svgIconPaths = {
  refresh: '<path d="M20 11a8 8 0 0 0-14.9-3.9L4 9"/><path d="M4 4v5h5"/><path d="M4 13a8 8 0 0 0 14.9 3.9L20 15"/><path d="M20 20v-5h-5"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
  upload: '<path d="M12 15V3"/><path d="m7 8 5-5 5 5"/><path d="M5 20h14"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  users: '<path d="M16 21v-1.8a3.8 3.8 0 0 0-3.8-3.8H6.8A3.8 3.8 0 0 0 3 19.2V21"/><circle cx="9.5" cy="7.5" r="3.5"/><path d="M17 11a3.5 3.5 0 0 0 0-7"/><path d="M21 21v-1.7a3.8 3.8 0 0 0-2.8-3.7"/>',
  fingerprint: '<use href="/assets/fingerprint.svg#fingerprint"></use>',
  face: '<circle cx="12" cy="12" r="8.5"/><path d="M9 10h.01M15 10h.01"/><path d="M8.8 14a4.2 4.2 0 0 0 6.4 0"/>',
  command: '<path d="m7 8 4 4-4 4"/><path d="M13 16h4"/><path d="M4 4h16v16H4z"/>',
  attendance: '<path d="M5 5h14v14H5z"/><path d="M8 3v4M16 3v4M5 10h14"/><path d="M9 14h2M13 14h2M9 17h2"/>',
  device: '<rect x="6" y="3.5" width="12" height="17" rx="2.5"/><path d="M9 7.5h6M9 11h6"/><circle cx="12" cy="16.2" r="1.1" fill="currentColor" stroke="none"/>',
  sync: '<path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.2 9A7 7 0 0 1 18.5 7"/><path d="M17.8 15A7 7 0 0 1 5.5 17"/>',
  rename: '<path d="m14 6 4 4"/><path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16v4z"/>',
  edit: '<path d="m14 6 4 4"/><path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16v4z"/>',
  copy: '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="m9 7 .7-2h4.6l.7 2"/><path d="M6 7l1 13h10l1-13"/>',
  play: '<path d="m9 6 9 6-9 6z"/>',
  archive: '<path d="M4 7h16v13H4z"/><path d="M3 4h18v3H3z"/><path d="M9 12h6"/>',
  settings: '<path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/><path d="m19.4 15 .1.1a2 2 0 0 1-2.8 2.8l-.1-.1a7.6 7.6 0 0 1-1.7 1l-.1.2a2 2 0 0 1-4 0l-.1-.2a7.6 7.6 0 0 1-1.7-1l-.1.1A2 2 0 0 1 6.1 15l.1-.1a7.6 7.6 0 0 1-1-1.7H5a2 2 0 0 1 0-4h.2a7.6 7.6 0 0 1 1-1.7L6.1 7A2 2 0 0 1 9 4.2l.1.1a7.6 7.6 0 0 1 1.7-1V3a2 2 0 0 1 4 0v.3a7.6 7.6 0 0 1 1.7 1l.1-.1A2 2 0 0 1 19.5 7l-.1.1a7.6 7.6 0 0 1 1 1.7h.2a2 2 0 0 1 0 4h-.2a7.6 7.6 0 0 1-1 1.7Z"/>',
  inspect: '<circle cx="10.8" cy="10.8" r="6.3"/><path d="m16 16 4.5 4.5"/><path d="M8.5 10.8h4.6"/>',
  restore: '<path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 5v6h6"/>',
  save: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4"/><path d="M8 20v-6h8v6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  lock: '<rect x="5" y="10" width="14" height="10" rx="2.4"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><circle cx="12" cy="15" r="1"/>',
  arrow: '<path d="M19 12H5"/><path d="m11 6-6 6 6 6"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>'
};

function svgIcon(name, className = "button-icon") {
  const paths = svgIconPaths[name] || svgIconPaths.command;
  const viewBox = name === "fingerprint" ? "0 0 48 48" : "0 0 24 24";
  return `<svg class="${className}" aria-hidden="true" focusable="false" viewBox="${viewBox}" fill="none">${paths}</svg>`;
}

function enhanceButtonIcons(root = document) {
  root.querySelectorAll("button[data-icon]").forEach((button) => {
    if (button.querySelector(".button-icon")) return;
    const label = button.dataset.iconOnly === "true" ? "" : button.textContent.trim();
    const icon = svgIcon(button.dataset.icon);
    const text = label ? `<span class="button-label">${escapeHtml(label)}</span>` : "";
    button.innerHTML = button.dataset.icon === "arrow" ? `${text}${icon}` : `${icon}${text}`;
  });
}

function enhanceNavIcons(root = document) {
  root.querySelectorAll("[data-nav-icon]").forEach((container) => {
    if (container.querySelector(".nav-icon-svg")) return;
    container.innerHTML = svgIcon(container.dataset.navIcon, "nav-icon-svg");
  });
}

function initializeLoginScreen(authenticated = false) {
  const screen = $("#login-screen");
  const form = $("#login-form");
  const errorBox = $("#login-error");
  if (!screen || !form) return;
  if (form.dataset.authBound !== "true") {
    form.addEventListener("input", () => {
      if (!errorBox) return;
      errorBox.hidden = true;
      errorBox.textContent = "";
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const submitButton = form.querySelector("button[type=submit]");
      submitButton.disabled = true;
      try {
        await api("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ password: form.password.value })
        });
        form.reset();
        document.body.classList.remove("login-visible");
        screen.classList.add("is-closing");
        window.setTimeout(() => {
          screen.hidden = true;
          screen.classList.remove("is-closing");
        }, 260);
        await refreshAll();
      } catch (error) {
        if (errorBox) {
          errorBox.textContent = error.message;
          errorBox.hidden = false;
        }
      } finally {
        submitButton.disabled = false;
      }
    });
    form.dataset.authBound = "true";
  }
  if (authenticated) {
    screen.hidden = true;
    document.body.classList.remove("login-visible");
    return;
  }
  showLoginScreen();
}

function showLoginScreen() {
  const screen = $("#login-screen");
  const form = $("#login-form");
  const errorBox = $("#login-error");
  if (!screen || !form) return;
  form.reset();
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  screen.classList.remove("is-closing");
  screen.hidden = false;
  document.body.classList.add("login-visible");
  window.requestAnimationFrame(() => form.password?.focus());
}

async function lockApp() {
  const button = $("#lock-app-button");
  if (button) button.disabled = true;
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
    closeMobileMenu({ restoreFocus: false });
    showLoginScreen();
  } catch (error) {
    notify(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function faNumber(value) {
  return String(value ?? 0).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    throw new Error(data?.error || data?.message || data || `خطای ${response.status}`);
  }
  return data;
}

function notify(message, error = false) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.style.borderColor = error ? "#e64a4a" : "#cbd5e1";
  toast.classList.add("show");
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(() => toast.classList.remove("show"), 3600);
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("fa-IR");
}

function statusLabel(status) {
  return ({
    online: "متصل",
    offline: "قطع ارتباط",
    queued: "در صف",
    sent: "ارسال شد",
    acked: "تأیید شد",
    error: "خطا",
    unknown: "نامشخص",
    manual: "ثبت دستی"
  }[String(status || "unknown").toLowerCase()] || status || "نامشخص");
}

function statusBadge(status) {
  const cleanStatus = String(status || "unknown").toLowerCase();
  return `<span class="status ${escapeHtml(cleanStatus)}"><span class="status-dot" aria-hidden="true"></span><span>${escapeHtml(statusLabel(cleanStatus))}</span></span>`;
}

function deviceBySn(sn) {
  return state.devices.find((device) => device.sn === sn);
}

function deviceLabel(sn) {
  const device = deviceBySn(sn);
  return device?.display_name || device?.sn || sn || "بدون دستگاه";
}

function trackQueuedCommands(queued = []) {
  state.lastCommandIds = queued
    .map((item) => Number(item?.id))
    .filter((id) => Number.isFinite(id));
  state.lastCommandId = state.lastCommandIds.at(-1) || null;
}

let appleSelectDocumentEventsBound = false;

function closeAppleSelects(except = null) {
  $$(".apple-select.open").forEach((shell) => {
    if (shell !== except) {
      shell.classList.remove("open");
      shell.querySelector(".apple-select-trigger")?.setAttribute("aria-expanded", "false");
    }
  });
}

function syncAppleSelect(select) {
  const shell = select.closest(".apple-select");
  if (!shell) return;
  const trigger = shell.querySelector(".apple-select-trigger");
  const menu = shell.querySelector(".apple-select-menu");
  const options = [...select.options];
  const multiple = select.multiple;
  const selectedValues = new Set(
    options.filter((option) => option.selected && option.value).map((option) => option.value)
  );
  const selected = options.find((option) => option.value === select.value)
    || options[0];
  if (!trigger || !menu || !selected) return;
  const selectedLabels = options
    .filter((option) => selectedValues.has(option.value))
    .map((option) => option.textContent.trim());
  const triggerLabel = multiple
    ? (selectedLabels.length === 0
      ? (options.find((option) => !option.value)?.textContent.trim() || "همه دستگاه‌ها")
      : selectedLabels.length === 1
        ? selectedLabels[0]
        : `${faNumber(selectedLabels.length)} دستگاه انتخاب شده`)
    : selected.textContent.trim();
  shell.classList.toggle("multi", multiple);
  trigger.innerHTML = `
    <span class="apple-select-value" title="${escapeHtml(triggerLabel)}">${escapeHtml(triggerLabel)}</span>
    ${svgIcon("chevron", "button-icon select-chevron")}
  `;
  menu.innerHTML = options.map((option) => {
    const isSelected = multiple
      ? (option.value ? selectedValues.has(option.value) : selectedValues.size === 0)
      : option.value === selected.value;
    return `
    <button type="button" class="apple-select-option" role="option"
      aria-selected="${isSelected ? "true" : "false"}"
      data-value="${escapeHtml(option.value)}">
      ${isSelected ? svgIcon("check", "button-icon apple-select-check") : ""}
      <span class="apple-select-option-label">${escapeHtml(option.textContent.trim())}</span>
    </button>
  `;
  }).join("");
  menu.querySelectorAll(".apple-select-option").forEach((optionButton) => {
    optionButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const value = optionButton.dataset.value;
      if (multiple) {
        if (value) {
          const option = options.find((item) => item.value === value);
          if (option) option.selected = !option.selected;
          const allOption = options.find((item) => !item.value);
          if (allOption) allOption.selected = false;
        } else {
          options.forEach((item) => { item.selected = !item.value; });
        }
      } else {
        select.value = value;
      }
      select.dispatchEvent(new Event("change", { bubbles: true }));
      syncAppleSelect(select);
      if (!multiple) closeAppleSelects();
    });
  });
}

function enhanceSelect(select) {
  if (select.dataset.appleEnhanced === "true") {
    syncAppleSelect(select);
    return;
  }
  select.dataset.appleEnhanced = "true";
  const shell = document.createElement("div");
  shell.className = "apple-select";
  select.parentNode.insertBefore(shell, select);
  shell.appendChild(select);
  select.classList.add("apple-select-source");
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "apple-select-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "apple-select-menu";
  menu.setAttribute("role", "listbox");
  shell.append(trigger, menu);
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const isOpen = shell.classList.contains("open");
    closeAppleSelects(shell);
    shell.classList.toggle("open", !isOpen);
    trigger.setAttribute("aria-expanded", String(!isOpen));
  });
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeAppleSelects();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      trigger.click();
    }
  });
  syncAppleSelect(select);
}

function enhanceSelects() {
  if (!appleSelectDocumentEventsBound) {
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".apple-select")) closeAppleSelects();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeAppleSelects();
    });
    appleSelectDocumentEventsBound = true;
  }
  $$("select:not([data-apple-enhanced])").forEach(enhanceSelect);
  $$("select[data-apple-enhanced]").forEach(syncAppleSelect);
}

function contextFor(view) {
  return state.context[view] || "";
}

function filterSns(view) {
  const selected = state.filters[view] || [];
  return selected.length ? selected : state.devices.map((device) => device.sn);
}

function singleContext(view) {
  const selected = state.filters[view] || [];
  return state.context[view] || (selected.length === 1 ? selected[0] : "");
}

function setDeviceFilter(view, sns) {
  if (!(view in state.filters)) return;
  state.filters[view] = [...new Set((sns || []).filter(Boolean))];
  state.context[view] = state.filters[view].length === 1 ? state.filters[view][0] : "";
  renderScopedContext(view);
}

function setContext(view, sn) {
  if (!(view in state.context)) return;
  state.context[view] = sn || "";
  if (view in state.filters) {
    state.filters[view] = sn ? [sn] : [];
    renderScopedContext(view);
  }
  if (view === "commands") {
    renderCommandTarget();
    renderTerminalHeader();
  }
}

function renderSummary(summary) {
  $("#metric-devices").textContent = faNumber(summary.devices);
  $("#metric-users").textContent = faNumber(summary.users);
  $("#metric-fingerprints").textContent = faNumber(summary.fingerprints ?? summary.biometrics);
  $("#metric-faces").textContent = faNumber(summary.faces ?? 0);
}

function renderReceiverStatus(message, error = false) {
  $$("[id^='receiver-status-']").forEach((element) => {
    element.textContent = message;
    element.classList.toggle("error", error);
  });
}

function renderDeviceCards() {
  const container = $("#device-cards");
  if (!state.devices.length) {
    container.innerHTML = `
      <div class="empty-state">
        <strong>هنوز دستگاهی با ADMS ثبت نشده است.</strong>
        <span>آدرس سرور را روی دستگاه وارد کنید؛ بعد از اولین ارتباط، دستگاه اینجا ظاهر می‌شود.</span>
      </div>`;
    return;
  }

  container.innerHTML = state.devices.map((device) => {
    const status = String(device.status || "unknown").toLowerCase();
    const displayName = device.display_name || "دستگاه بدون نام";
    const model = device.model || "گزارش نشده";
    return `
      <article class="device-card ${escapeHtml(status)}" data-device-card="${escapeHtml(device.sn)}">
        <header class="device-card-header">
          <div class="device-card-header-main">
            <div class="device-meta">
              <div class="device-title-row">
                <strong class="device-name">${escapeHtml(displayName)}</strong>
                ${statusBadge(status)}
              </div>
              <small class="device-serial"><span>شناسه:</span><b dir="ltr">${escapeHtml(device.sn)}</b></small>
              <span class="device-model ${device.model ? "" : "fallback"}">مدل: ${escapeHtml(model)}</span>
            </div>
          </div>
        </header>
        <section class="device-card-stats" aria-label="آمار دستگاه">
          <div class="device-stat"><strong>${faNumber(device.user_count)}</strong><span>کارمند</span></div>
          <div class="device-stat"><strong>${faNumber(device.fingerprint_count ?? 0)}</strong><span>اثر انگشت</span></div>
          <div class="device-stat"><strong>${faNumber(device.face_count ?? 0)}</strong><span>چهره</span></div>
        </section>
        <section class="device-card-actions" aria-label="عملیات دستگاه">
          <div class="device-card-action-grid">
            <button class="mini-button" data-icon="users" data-card-action="users" data-sn="${escapeHtml(device.sn)}">کارکنان</button>
            <button class="mini-button" data-icon="fingerprint" data-card-action="biometrics" data-sn="${escapeHtml(device.sn)}">اثر انگشت و چهره</button>
            <button class="mini-button primary" data-icon="sync" data-card-action="sync" data-sn="${escapeHtml(device.sn)}">دریافت اطلاعات</button>
            <button class="mini-button" data-icon="command" data-card-action="commands" data-sn="${escapeHtml(device.sn)}">فرمان‌ها</button>
          </div>
          <button class="mini-button rename-button" data-icon="rename" data-card-action="rename" data-sn="${escapeHtml(device.sn)}">تغییر نام دستگاه</button>
        </section>
        <footer class="device-card-footer">
          <div class="device-card-meta-block">
            <span class="meta-label">آخرین ارتباط</span>
            <strong class="meta-value">${escapeHtml(formatTime(device.last_seen))}</strong>
          </div>
          <div class="device-card-meta-block device-card-meta-end">
            <span class="meta-label">نشانی شبکه</span>
            <strong class="meta-value" dir="ltr">${escapeHtml(device.last_ip || "ناموجود")}</strong>
          </div>
        </footer>
      </article>`;
  }).join("");

  $$("[data-card-action]").forEach((button) => {
    button.addEventListener("click", () => handleDeviceAction(button.dataset.cardAction, button.dataset.sn));
  });
  enhanceButtonIcons(container);
}

async function handleDeviceAction(action, sn) {
  if (!sn) return;
  if (action === "rename") return openRenameDialog(sn);
  if (action === "sync") return syncDevice(sn);
  if (action === "users" || action === "biometrics" || action === "traffic") {
    setContext(action, sn);
    return setView(action);
  }
  if (action === "commands") {
    setContext("commands", sn);
    return setView("commands");
  }
}

function openRenameDialog(sn) {
  const device = deviceBySn(sn);
  state.renameSn = sn;
  const form = $("#rename-form");
  form.reset();
  form.display_name.value = device?.display_name || "";
  $("#rename-dialog-title").textContent = `تغییر نام ${device?.sn || sn}`;
  $("#rename-dialog").showModal();
  window.setTimeout(() => form.display_name.focus(), 0);
}

async function saveDeviceRename(event) {
  event.preventDefault();
  const form = event.target;
  const sn = state.renameSn;
  const name = form.display_name.value.trim();
  if (!sn) return notify("دستگاه مقصد مشخص نیست.", true);
  if (!name) {
    form.display_name.setCustomValidity("نام دستگاه را وارد کنید.");
    form.reportValidity();
    form.display_name.setCustomValidity("");
    return;
  }
  try {
    await api(`/api/devices/${encodeURIComponent(sn)}`, {
      method: "PUT",
      body: JSON.stringify({ display_name: name })
    });
    $("#rename-dialog").close();
    state.renameSn = null;
    notify("نام دستگاه ذخیره شد.");
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  }
}

function openConfirmDialog({ title, message, confirmLabel, icon = "trash", action }) {
  state.confirmAction = action;
  $("#confirm-dialog-title").textContent = title;
  $("#confirm-dialog-message").textContent = message;
  const confirmButton = $("#confirm-dialog-confirm");
  confirmButton.dataset.icon = icon;
  confirmButton.innerHTML = escapeHtml(confirmLabel);
  confirmButton.classList.toggle("button-danger", icon === "trash");
  enhanceButtonIcons($("#confirm-dialog"));
  $("#confirm-dialog").showModal();
}

async function submitConfirmDialog(event) {
  event.preventDefault();
  const action = state.confirmAction;
  state.confirmAction = null;
  $("#confirm-dialog").close();
  if (action) await action();
}

async function syncDevice(sn, navigate = true) {
  if (!sn) return notify("دستگاه مقصد مشخص نیست.", true);
  try {
    const result = await api(`/api/devices/${encodeURIComponent(sn)}/sync`, {
      method: "POST",
      body: "{}"
    });
    trackQueuedCommands(result.queued);
    setContext("commands", sn);
    notify(`درخواست دریافت اطلاعات برای «${deviceLabel(sn)}» در صف قرار گرفت.`);
    if (navigate) setView("commands");
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  }
}

async function syncAllDevices() {
  if (!state.devices.length) return notify("هنوز دستگاهی برای دریافت اطلاعات ثبت نشده است.", true);
  const results = await Promise.allSettled(
    state.devices.map((device) => api(`/api/devices/${encodeURIComponent(device.sn)}/sync`, {
      method: "POST",
      body: "{}"
    }))
  );
  trackQueuedCommands(results.flatMap((result) => (
    result.status === "fulfilled" ? (result.value.queued || []) : []
  )));
  const succeeded = results.filter((result) => result.status === "fulfilled").length;
  const failed = results.length - succeeded;
  notify(
    `درخواست دریافت برای ${faNumber(succeeded)} دستگاه ثبت شد${failed ? `؛ ${faNumber(failed)} دستگاه خطا داشت` : ""}.`,
    Boolean(failed)
  );
  await refreshAll();
}

function ensureScopedSelectors() {
  ["users", "biometrics", "traffic"].forEach((view) => {
    const toolbar = $(`#view-${view} .section-heading .toolbar`);
    if (!toolbar || toolbar.querySelector(`[data-context-view="${view}"]`)) return;
    const wrapper = document.createElement("label");
    wrapper.className = "context-picker";
    wrapper.innerHTML = `
      <span>${contextLabels[view]}</span>
      <select class="input" data-context-view="${view}" ${view === "traffic" ? "" : "multiple"}>
        <option value="">انتخاب دستگاه</option>
      </select>`;
    toolbar.prepend(wrapper);
    wrapper.querySelector("select").addEventListener("change", (event) => {
      if (event.target.multiple) {
        setDeviceFilter(view, [...event.target.selectedOptions].map((option) => option.value));
      } else {
        setContext(view, event.target.value);
      }
      loadViewData().catch((error) => notify(error.message, true));
    });
  });
}

function renderScopedContext(view) {
  const select = $(`[data-context-view="${view}"]`);
  if (!select) return;
  const multiple = select.multiple;
  const selectedSns = state.filters[view] || [];
  select.innerHTML = `
    <option value="">${multiple ? "همه دستگاه‌ها" : "انتخاب دستگاه"}</option>
  ${state.devices.map((device) => `
      <option value="${escapeHtml(device.sn)}">
        ${escapeHtml(device.display_name || "دستگاه بدون نام")} · ${escapeHtml(device.sn)}
      </option>`).join("")}`;
  if (multiple) {
    [...select.options].forEach((option) => {
      option.selected = option.value
        ? selectedSns.includes(option.value)
        : selectedSns.length === 0;
    });
  } else {
    select.value = contextFor(view);
  }
  syncAppleSelect(select);
}

function renderAttendanceDevices() {
  const select = $("#attendance-devices");
  if (!select) return;
  const selectedSns = state.filters.attendance || [];
  select.innerHTML = `
    <option value="">همه دستگاه‌ها</option>
    ${state.devices.map((device) => `
      <option value="${escapeHtml(device.sn)}">
        ${escapeHtml(device.display_name || "دستگاه بدون نام")} · ${escapeHtml(device.sn)}
      </option>`).join("")}`;
  [...select.options].forEach((option) => {
    option.selected = option.value
      ? selectedSns.includes(option.value)
      : selectedSns.length === 0;
  });
  syncAppleSelect(select);
}

function renderCommandTarget() {
  const select = $("#command-target");
  if (!select) return;
  const current = contextFor("commands");
  select.innerHTML = `
    <option value="">یک دستگاه را انتخاب کنید</option>
  ${state.devices.map((device) => `
      <option value="${escapeHtml(device.sn)}">
        ${escapeHtml(device.display_name || "دستگاه بدون نام")} · ${escapeHtml(device.sn)}
      </option>`).join("")}`;
  select.value = current;
  syncAppleSelect(select);
}

function renderKnownCommands() {
  const select = $("#known-command-select");
  if (!select) return;
  select.innerHTML = `
    <option value="">انتخاب دستور آماده</option>
    ${state.knownCommands.map((item) => `
      <option value="${escapeHtml(item.command)}">${escapeHtml(item.label)}</option>
    `).join("")}`;
  syncAppleSelect(select);
}

function renderTerminalHeader() {
  const target = contextFor("commands");
  const label = $("#operation-target-label");
  if (label) {
    label.textContent = target
      ? `${deviceLabel(target)} · ${target}`
      : "بدون مقصد";
  }
}

function renderCommandOutput(commands, results) {
  const output = $("#operation-log");
  if (!output) return;
  const events = [];
  commands.forEach((item) => {
    events.push({
      timestamp: item.ts_created,
      html: `<div class="log-line command">#${escapeHtml(item.id)} · ${escapeHtml(statusLabel(item.status))} · ${escapeHtml(item.command_text)}</div>`
    });
  });
  results.forEach((item) => {
    const returnCode = item.return_code === null || item.return_code === undefined
      ? "بدون کد"
      : item.return_code;
    const isError = Number(item.return_code) !== 0 && item.return_code !== null;
    const lineClass = isError ? "error" : "response";
    const body = String(item.raw_body || item.cmd || "").slice(0, 4000);
    events.push({
      timestamp: item.ts,
      html: `<div class="log-line ${lineClass}">#${escapeHtml(item.cmd_id ?? "؟")} · return=${escapeHtml(returnCode)} · ${escapeHtml(body || "پاسخ خالی")}</div>`
    });
  });
  events.sort((left, right) => String(left.timestamp || "").localeCompare(String(right.timestamp || "")));
  if (!events.length) {
    output.innerHTML = `<div class="log-line muted">برای شروع، دستگاه مقصد و عملیات را انتخاب کنید.</div>`;
    return;
  }
  output.innerHTML = events.slice(-60).map((event) => event.html).join("");
  output.scrollTop = output.scrollHeight;
}

function processStep(label, stateName, detail) {
  return `
    <div class="process-step ${escapeHtml(stateName)}">
      <span class="step-dot"></span>
      <div><strong>${escapeHtml(label)}</strong><div>${escapeHtml(detail)}</div></div>
    </div>`;
}

function renderCommandProcess(commands, results) {
  const panel = $("#command-process");
  if (!panel) return;
  const trackedIds = new Set(state.lastCommandIds || []);
  const trackedCommands = trackedIds.size
    ? commands.filter((item) => trackedIds.has(Number(item.id)))
    : [];
  const current = state.lastCommandId
    ? trackedCommands.find((item) => Number(item.id) === Number(state.lastCommandId))
      || commands.find((item) => Number(item.id) === Number(state.lastCommandId))
    : commands[0];
  if (!current) {
    panel.className = "process-empty";
    panel.textContent = "هنوز دستوری برای این دستگاه ارسال نشده است.";
    return;
  }
  const result = results.find((item) => (
    Number(item.cmd_id) === Number(current.wire_id || current.id)
  ));
  const trackedResults = trackedIds.size
    ? results.filter((item) => trackedIds.has(Number(item.cmd_id)))
    : [];
  const status = String(current.status || "queued").toLowerCase();
  const finished = status === "acked" || status === "error";
  const groupHasError = trackedCommands.some((item) => String(item.status || "").toLowerCase() === "error")
    || trackedResults.some((item) => Number(item.return_code) !== 0);
  const groupFinished = trackedCommands.length > 0
    && trackedCommands.every((item) => ["acked", "error"].includes(String(item.status || "").toLowerCase()));
  const commandLabel = trackedCommands.length > 1
    ? `${faNumber(trackedCommands.length)} عملیات در این درخواست · آخرین: ${current.command_text}`
    : current.command_text;
  panel.className = "process-steps";
  panel.innerHTML = `
    <div class="process-command" dir="ltr">#${escapeHtml(current.id)} · ${escapeHtml(commandLabel)}</div>
    ${processStep("ثبت در صف", "done", formatTime(current.ts_created))}
    ${processStep("دریافت توسط دستگاه", current.ts_sent ? "done" : "active", current.ts_sent ? formatTime(current.ts_sent) : "منتظر درخواست دستگاه")}
    ${processStep("پاسخ دستگاه", result ? (groupHasError ? "active error" : "done") : (finished ? "active" : "active"), result ? `${faNumber(trackedResults.length || 1)} پاسخ · آخرین return=${result.return_code ?? "—"}` : "منتظر /iclock/devicecmd")}
    ${processStep("نتیجه نهایی", groupFinished ? (groupHasError ? "active error" : "done") : "active", groupFinished ? (groupHasError ? "یکی از عملیات خطا داشت" : "همه عملیات تأیید شد") : statusLabel(status))}
  `;
}

function renderCommandTable(commands) {
  const body = $("#commands-table");
  if (!body) return;
  if (!commands.length) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty muted">برای این دستگاه عملیاتی ثبت نشده است.</td></tr>`;
    return;
  }
  body.innerHTML = commands.map((item) => `
    <tr>
      <td data-label="شماره" dir="ltr">#${escapeHtml(item.id)}</td>
      <td data-label="دستگاه" dir="ltr">${escapeHtml(item.sn)}</td>
      <td data-label="وضعیت">${statusBadge(item.status)}</td>
      <td data-label="ایجاد">${escapeHtml(formatTime(item.ts_created))}</td>
      <td data-label="ارسال">${escapeHtml(formatTime(item.ts_sent))}</td>
      <td data-label="شرح عملیات" class="raw-cell" title="${escapeHtml(item.command_text)}">${escapeHtml(item.command_text)}</td>
    </tr>
  `).join("");
}

async function loadCommandConsole(silent = false) {
  const sn = contextFor("commands");
  if (!sn) {
    renderCommandTable([]);
    renderCommandOutput([], []);
    renderCommandProcess([], []);
    renderTerminalHeader();
    return;
  }
  const query = new URLSearchParams({ limit: "300" });
  query.set("sn", sn);
  try {
    const [commandsResult, resultsResult] = await Promise.all([
      api(`/api/commands?${query}`),
      api(`/api/command-results?sn=${encodeURIComponent(sn)}&limit=100`)
    ]);
    const commands = commandsResult.data || [];
    const results = resultsResult.data || [];
    renderCommandTable(commands);
    renderCommandOutput(commands, results);
    renderCommandProcess(commands, results);
    if (!silent && sn) renderTerminalHeader();
  } catch (error) {
    if (!silent) notify(error.message, true);
  }
}

function startCommandPolling() {
  window.clearInterval(state.commandPollingTimer);
  if (state.view !== "commands") return;
  state.commandPollingTimer = window.setInterval(() => {
    loadCommandConsole(true);
  }, 2500);
}

async function loadUsers() {
  const body = $("#users-table");
  const sns = filterSns("users");
  if (!sns.length) {
    body.innerHTML = `<tr><td colspan="8" class="muted">هنوز دستگاهی برای نمایش ثبت نشده است.</td></tr>`;
    return;
  }
  const query = new URLSearchParams({ limit: "500" });
  sns.forEach((sn) => query.append("sns", sn));
  const search = $("#user-search").value.trim();
  if (search) query.set("search", search);
  const bioQuery = new URLSearchParams();
  sns.forEach((sn) => bioQuery.append("sns", sn));
  const [result, biometrics] = await Promise.all([
    api(`/api/users?${query}`),
    api(`/api/biometrics?${bioQuery}`)
  ]);
  const bioPins = new Set(
    (biometrics.data || [])
      .filter((item) => item.pin)
      .map((item) => `${item.sn}:${item.pin}`)
  );
  if (!result.data.length) {
    body.innerHTML = `<tr><td colspan="8" class="table-empty muted">برای دستگاه‌های انتخاب‌شده کارمندی دریافت نشده است. از «دریافت اطلاعات» استفاده کنید.</td></tr>`;
    return;
  }
  body.innerHTML = result.data.map((user) => `
    <tr>
      <td data-label="شماره پرسنلی"><strong dir="ltr">${escapeHtml(user.pin)}</strong></td>
      <td data-label="نام">${escapeHtml(user.name || "بدون نام")}</td>
      <td data-label="کارت">${escapeHtml(user.card || "ندارد")}</td>
      <td data-label="سطح دسترسی">${user.privilege === "14" ? "مدیر دستگاه" : "کارمند عادی"}</td>
      <td data-label="داده هویتی">${bioPins.has(`${user.sn}:${user.pin}`) ? "دریافت شده" : "ثبت نشده"}</td>
      <td data-label="دستگاه" dir="ltr">${escapeHtml(user.sn)}</td>
      <td data-label="آخرین دریافت">${escapeHtml(formatTime(user.updated_at))}</td>
      <td class="table-actions" data-label="عملیات">
        <div class="mini-actions">
          <button class="mini-button" data-icon="edit" data-edit-pin="${escapeHtml(user.pin)}" data-edit-sn="${escapeHtml(user.sn)}">ویرایش</button>
          <button class="mini-button" data-icon="copy" data-copy-pin="${escapeHtml(user.pin)}" data-copy-sn="${escapeHtml(user.sn)}">کپی به دستگاه‌ها</button>
          <button class="mini-button danger-button" data-icon="trash" data-delete-pin="${escapeHtml(user.pin)}" data-delete-sn="${escapeHtml(user.sn)}">حذف</button>
        </div>
      </td>
    </tr>
  `).join("");
  $$("[data-edit-pin]").forEach((button) => {
    button.addEventListener("click", () => openUserDialog(
      result.data.find((user) => user.pin === button.dataset.editPin && user.sn === button.dataset.editSn),
      button.dataset.editSn
    ));
  });
  $$("[data-copy-pin]").forEach((button) => {
    button.addEventListener("click", () => openCopyDialog(
      result.data.find((user) => user.pin === button.dataset.copyPin && user.sn === button.dataset.copySn),
      button.dataset.copySn
    ));
  });
  $$("[data-delete-pin]").forEach((button) => {
    button.addEventListener("click", () => deleteUser(button.dataset.deletePin, button.dataset.deleteSn));
  });
  enhanceButtonIcons(body);
}

async function loadBiometrics() {
  const body = $("#biometrics-table");
  const sns = filterSns("biometrics");
  if (!sns.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted">هنوز دستگاهی برای نمایش ثبت نشده است.</td></tr>`;
    return;
  }
  const query = new URLSearchParams();
  sns.forEach((sn) => query.append("sns", sn));
  const pin = $("#bio-pin").value.trim();
  if (pin) query.set("pin", pin);
  const result = await api(`/api/biometrics?${query}`);
  const labels = {
    fingerprint: "اثر انگشت",
    face: "چهره",
    finger_vein: "رگ انگشت",
    palm: "کف دست",
    file: "فایل زیستی"
  };
  if (!result.data.length) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty muted">اثر انگشت یا چهره‌ای از این دستگاه دریافت نشده است.</td></tr>`;
    return;
  }
  body.innerHTML = result.data.map((item) => `
    <tr>
      <td data-label="نوع داده">${escapeHtml(labels[item.kind] || item.kind)}</td>
      <td data-label="شماره پرسنلی" dir="ltr">${escapeHtml(item.pin || "—")}</td>
      <td data-label="شماره ثبت" dir="ltr">${escapeHtml(item.template_no || "—")}</td>
      <td data-label="دستگاه" dir="ltr">${escapeHtml(item.sn)}</td>
      <td data-label="زمان دریافت">${escapeHtml(formatTime(item.ts))}</td>
      <td data-label="جزئیات فنی" class="raw-cell" title="${escapeHtml(item.raw_line)}">${escapeHtml(item.raw_line)}</td>
    </tr>
  `).join("");
}

async function loadAttendance() {
  const body = $("#attendance-table");
  if (!body) return;
  const query = new URLSearchParams({ limit: "1000" });
  (state.filters.attendance || []).forEach((sn) => query.append("sns", sn));
  const start = $("#attendance-start").value;
  const end = $("#attendance-end").value;
  if (start) query.set("start", start);
  if (end) query.set("end", end);
  const result = await api(`/api/attendance?${query}`);
  if (!result.data.length) {
    body.innerHTML = `<tr><td colspan="7" class="table-empty muted">در بازه و دستگاه‌های انتخاب‌شده، رکورد ترددی پیدا نشد.</td></tr>`;
    return;
  }
  body.innerHTML = result.data.map((item) => `
    <tr>
      <td data-label="شماره پرسنلی" dir="ltr">${escapeHtml(item.pin || "—")}</td>
      <td data-label="زمان تردد" dir="ltr">${escapeHtml(item.event_time || "ثبت نشده")}</td>
      <td data-label="دستگاه" dir="ltr">${escapeHtml(item.sn || "—")}</td>
      <td data-label="وضعیت" dir="ltr">${escapeHtml(item.status || "—")}</td>
      <td data-label="روش تأیید" dir="ltr">${escapeHtml(item.verify || "—")}</td>
      <td data-label="ثبت دریافت">${escapeHtml(formatTime(item.ts))}</td>
      <td data-label="متن خام دستگاه" class="raw-cell" title="${escapeHtml(item.raw_line)}">${escapeHtml(item.raw_line)}</td>
    </tr>
  `).join("");
}

async function loadTraffic() {
  const body = $("#traffic-table");
  const query = new URLSearchParams({ limit: "200" });
  const sn = contextFor("traffic");
  if (sn) query.set("sn", sn);
  const result = await api(`/api/requests?${query}`);
  if (!result.data.length) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty muted">هنوز ارتباطی ثبت نشده است.</td></tr>`;
    return;
  }
  body.innerHTML = result.data.map((item) => `
    <tr>
      <td data-label="زمان">${escapeHtml(formatTime(item.ts))}</td>
      <td data-label="روش" dir="ltr">${escapeHtml(item.method)}</td>
      <td data-label="مسیر" dir="ltr">${escapeHtml(item.path)}</td>
      <td data-label="دستگاه" dir="ltr">${escapeHtml(item.sn || "—")}</td>
      <td data-label="پارامترها" class="raw-cell">${escapeHtml(item.query_json)}</td>
      <td data-label="نمونه متن" class="raw-cell">${escapeHtml((item.body || "").split("\n")[0])}</td>
    </tr>
  `).join("");
}

async function loadViewData() {
  if (state.view === "users") await loadUsers();
  if (state.view === "biometrics") await loadBiometrics();
  if (state.view === "attendance") await loadAttendance();
  if (state.view === "commands") await loadCommandConsole();
  if (state.view === "traffic") await loadTraffic();
}

async function saveSettingsPassword(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const password = form.password.value;
  if (password.length < 8) {
    notify("رمز عبور باید حداقل ۸ نویسه باشد.", true);
    return;
  }
  button.disabled = true;
  try {
    await api("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ password })
    });
    form.reset();
    notify("رمز عبور با موفقیت تغییر کرد.");
  } catch (error) {
    notify(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function renderMobileMenuButton(isOpen) {
  const button = $("#mobile-menu-button");
  if (!button) return;
  button.innerHTML = svgIcon(isOpen ? "close" : "menu");
  button.setAttribute("aria-label", isOpen ? "بستن منو" : "باز کردن منو");
  button.setAttribute("aria-expanded", String(isOpen));
}

function openMobileMenu() {
  const button = $("#mobile-menu-button");
  const backdrop = $("#mobile-menu-backdrop");
  if (!button || !backdrop) return;
  backdrop.hidden = false;
  document.body.classList.add("mobile-menu-open");
  renderMobileMenuButton(true);
  window.setTimeout(() => {
    const firstItem = $("#mobile-navigation .nav-item");
    if (document.body.classList.contains("mobile-menu-open")) firstItem?.focus();
  }, 120);
}

function closeMobileMenu({ restoreFocus = true } = {}) {
  const button = $("#mobile-menu-button");
  const backdrop = $("#mobile-menu-backdrop");
  if (!button || !backdrop) return;
  document.body.classList.remove("mobile-menu-open");
  backdrop.hidden = true;
  renderMobileMenuButton(false);
  if (restoreFocus) button.focus({ preventScroll: true });
}

function toggleMobileMenu() {
  if (document.body.classList.contains("mobile-menu-open")) {
    closeMobileMenu();
  } else {
    openMobileMenu();
  }
}

function setView(view) {
  state.view = view;
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  $$(".view").forEach((item) => item.classList.toggle("active", item.id === `view-${view}`));
  $("#page-title").textContent = viewTitles[view] || view;
  closeMobileMenu({ restoreFocus: false });
  startCommandPolling();
  loadViewData().catch((error) => notify(error.message, true));
}

function openUserDialog(user = null, sn = contextFor("users")) {
  if (!sn) return notify("ابتدا دستگاه مقصد را از فهرست همین صفحه انتخاب کنید.", true);
  state.editingPin = user?.pin || null;
  state.userTargetSn = sn;
  $("#user-dialog-title").textContent = user ? `ویرایش ${user.pin}` : "کارمند جدید";
  const form = $("#user-form");
  form.reset();
  form.pin.value = user?.pin || "";
  form.name.value = user?.name || "";
  form.privilege.value = user?.privilege || "0";
  form.password.value = user?.password || "";
  form.card.value = user?.card || "";
  form.group_id.value = user?.group_id || "1";
  form.pin.readOnly = Boolean(user);
  syncAppleSelect(form.privilege);
  $("#user-dialog").showModal();
}

function openCopyDialog(user, sourceSn = contextFor("users")) {
  if (!user || !sourceSn) return notify("دستگاه مبدأ مشخص نیست.", true);
  state.copyUser = { ...user, sourceSn };
  $("#copy-biometrics").checked = false;
  const targets = state.devices.filter((device) => device.sn !== sourceSn);
  $("#copy-dialog-title").textContent = `کپی ${user.name || user.pin} به دستگاه‌ها`;
  $("#copy-devices").innerHTML = targets.length
    ? targets.map((device) => `
      <label class="device-check">
        <input type="checkbox" value="${escapeHtml(device.sn)}">
        <span><strong>${escapeHtml(device.display_name || "دستگاه بدون نام")}</strong><small dir="ltr">${escapeHtml(device.sn)}</small></span>
      </label>`).join("")
    : `<div class="muted">دستگاه دیگری برای انتخاب وجود ندارد.</div>`;
  $("#copy-dialog").showModal();
}

async function saveUser(event) {
  event.preventDefault();
  const form = event.target;
  const payload = Object.fromEntries(new FormData(form).entries());
  const sn = state.userTargetSn || contextFor("users");
  if (!sn) return notify("دستگاه مقصد مشخص نیست.", true);
  payload.sn = sn;
  const editing = Boolean(state.editingPin);
  try {
    const result = await api(
      editing ? `/api/users/${encodeURIComponent(state.editingPin)}` : "/api/users",
      {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify(payload)
      }
    );
    $("#user-dialog").close();
    trackQueuedCommands(result.queued);
    setContext("commands", sn);
    notify(`${editing ? "ویرایش" : "ساخت کارمند"} برای دستگاه در صف قرار گرفت.`);
    setView("commands");
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  }
}

async function copyUser(event) {
  event.preventDefault();
  if (!state.copyUser) return;
  const targets = $$("#copy-devices input:checked").map((input) => input.value);
  if (!targets.length) return notify("حداقل یک دستگاه مقصد را انتخاب کنید.", true);
  try {
    const result = await api("/api/users/copy", {
      method: "POST",
      body: JSON.stringify({
        source_sn: state.copyUser.sourceSn,
        pin: state.copyUser.pin,
        target_sns: targets,
        include_biometrics: $("#copy-biometrics").checked
      })
    });
    $("#copy-dialog").close();
    trackQueuedCommands(result.targets?.flatMap((target) => target.queued || []) || []);
    const accepted = result.targets?.length || 0;
    const rejected = result.rejected_targets?.length || 0;
    notify(`کارمند برای ${faNumber(accepted)} دستگاه در صف قرار گرفت${rejected ? `؛ ${faNumber(rejected)} دستگاه رد شد` : ""}.`);
    setContext("commands", targets[0]);
    setView("commands");
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  }
}

async function deleteUser(pin, sn = contextFor("users")) {
  if (!sn) return;
  openConfirmDialog({
    title: "حذف کارمند",
    message: `حذف شماره پرسنلی ${pin} از «${deviceLabel(sn)}» در صف دستگاه قرار می‌گیرد.`,
    confirmLabel: "حذف و ارسال",
    action: async () => {
      try {
        const result = await api(
          `/api/users/${encodeURIComponent(pin)}?sn=${encodeURIComponent(sn)}`,
          { method: "DELETE" }
        );
        trackQueuedCommands(result.queued);
        setContext("commands", sn);
        notify("درخواست حذف در صف قرار گرفت.");
        setView("commands");
        await refreshAll();
      } catch (error) {
        notify(error.message, true);
      }
    }
  });
}

async function importUsers(file) {
  const sn = contextFor("users");
  if (!sn) return notify("دستگاه مقصد مشخص نیست.", true);
  try {
    const result = await api(`/api/users/import?sn=${encodeURIComponent(sn)}`, {
      method: "POST",
      headers: { "Content-Type": file.type || "text/csv" },
      body: await file.text()
    });
    trackQueuedCommands(result.queued);
    setContext("commands", sn);
    notify(`${faNumber(result.queued?.length || 0)} عملیات برای ورود کارکنان در صف قرار گرفت.`);
    setView("commands");
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  }
}

async function sendCommand(command) {
  const sn = contextFor("commands");
  const cleanCommand = String(command || "").trim();
  if (!sn) return notify("دستگاه مقصد را انتخاب کنید.", true);
  if (!cleanCommand) return notify("دستور خالی است.", true);
  try {
    const result = await api("/api/commands", {
      method: "POST",
      body: JSON.stringify({ sn, command: cleanCommand })
    });
    trackQueuedCommands(result.queued);
    renderTerminalHeader();
    notify("دستور در صف دستگاه قرار گرفت.");
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  }
}

async function queryBiometrics() {
  const sns = filterSns("biometrics");
  if (!sns.length) return notify("دستگاه مقصد را انتخاب کنید.", true);
  try {
    const results = await Promise.all(
      sns.map((sn) => api("/api/biometrics/query", {
        method: "POST",
        body: JSON.stringify({ sn, mode: "both" })
      }))
    );
    trackQueuedCommands(results.flatMap((result) => result.queued || []));
    setContext("commands", sns[0]);
    notify(`درخواست دریافت اثر انگشت و چهره برای ${faNumber(sns.length)} دستگاه در صف قرار گرفت.`);
    setView("commands");
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  }
}

function renderBackupInspection(inspection) {
  const panel = $("#backup-inspection");
  if (!panel) return;
  const counts = inspection.counts || {};
  const issues = inspection.issues || [];
  const warnings = inspection.warnings || [];
  const countText = [
    `دستگاه: ${faNumber((inspection.source_devices || []).length)}`,
    `کارمند: ${faNumber(counts.users || 0)}`,
    `اثر انگشت/چهره: ${faNumber(counts.biometrics || 0)}`,
    `تردد: ${faNumber(counts.attendance_raw || 0)}`
  ].join(" · ");
  const issueItems = issues.map((item) => (
    `<li class="issue">${escapeHtml(item.message || item.code || "خطای سازگاری")}</li>`
  )).join("");
  const warningItems = warnings.map((item) => (
    `<li class="warning">${escapeHtml(item.message || item.code || "هشدار")}</li>`
  )).join("");
  panel.innerHTML = `
    <strong>${inspection.compatible ? "فایل قابل بازگردانی است" : "فایل نیاز به بررسی دارد"}</strong>
    <div>${escapeHtml(countText)}</div>
    ${(issueItems || warningItems) ? `<ul>${issueItems}${warningItems}</ul>` : "<div class=\"muted\">ناسازگاری مهمی پیدا نشد.</div>"}
  `;
}

function renderBackupProgress(steps, targets = []) {
  const panel = $("#backup-progress");
  if (!panel) return;
  panel.innerHTML = `
    <div class="backup-progress-heading">
      <strong>روند بازگردانی</strong>
      <span>${escapeHtml(targets.length ? `${faNumber(targets.length)} مقصد` : "در حال بررسی")}</span>
    </div>
    <div class="backup-progress-steps">
      ${steps.map((step) => processStep(step.label, step.state, step.detail)).join("")}
    </div>
    ${targets.length ? `
      <div class="backup-targets">
        ${targets.map((target) => `
          <div class="backup-target-row ${escapeHtml(target.progress?.state || "")}">
            <span>${escapeHtml(deviceLabel(target.target_sn))}</span>
            <small>${escapeHtml(target.progress?.label || `${faNumber(target.command_ids?.length || (target.users_queued || 0) + (target.biometrics_queued || 0))} عملیات در صف`)}</small>
          </div>`).join("")}
      </div>` : ""}
  `;
}

function stopBackupPolling() {
  window.clearInterval(state.backupPollTimer);
  state.backupPollTimer = null;
}

async function fetchCommandsByIds(sn, ids) {
  const chunks = [];
  for (let index = 0; index < ids.length; index += 200) {
    chunks.push(ids.slice(index, index + 200));
  }
  const responses = await Promise.all(chunks.map((chunk) => (
    api(`/api/commands?sn=${encodeURIComponent(sn)}&ids=${chunk.join(",")}`)
  )));
  return responses.flatMap((response) => response.data || []);
}

async function pollBackupProgress() {
  const targets = state.backupTargets || [];
  if (!targets.length) {
    stopBackupPolling();
    return;
  }
  const results = await Promise.allSettled(targets.map((target) => (
    fetchCommandsByIds(target.target_sn, target.command_ids || [])
  )));
  let allFinished = true;
  let hasError = false;
  targets.forEach((target, index) => {
    const commandIds = new Set((target.command_ids || []).map((id) => Number(id)));
    const rows = results[index].status === "fulfilled"
      ? results[index].value.filter((row) => commandIds.has(Number(row.id)))
      : [];
    const queued = rows.filter((row) => ["queued", "sent"].includes(String(row.status || "").toLowerCase())).length;
    const failed = rows.filter((row) => String(row.status || "").toLowerCase() === "error").length;
    const completed = rows.filter((row) => String(row.status || "").toLowerCase() === "acked").length;
    const total = target.command_ids?.length || 0;
    const targetFinished = total === 0 || (!queued && rows.length >= total);
    if (!targetFinished) allFinished = false;
    if (failed) hasError = true;
    target.progress = failed
      ? { state: "error", label: `${faNumber(failed)} خطا · ${faNumber(completed)} تأیید شد` }
      : targetFinished
        ? { state: "done", label: `${faNumber(completed)} عملیات تأیید شد` }
        : { state: "active", label: `${faNumber(completed)} از ${faNumber(total)} تأیید شد` };
  });
  renderBackupProgress([
    { label: "فایل تأیید شد", state: "done", detail: "بررسی سازگاری با موفقیت انجام شد." },
    { label: "عملیات ارسال ساخته شد", state: "done", detail: `${faNumber(targets.length)} مقصد در صف قرار گرفت.` },
    {
      label: "دریافت توسط دستگاه‌ها",
      state: allFinished ? (hasError ? "error" : "done") : "active",
      detail: allFinished ? (hasError ? "برخی عملیات با خطا پاسخ داده‌اند." : "همه عملیات توسط دستگاه‌ها دریافت شد.") : "منتظر ارتباط ADMS دستگاه‌ها."
    },
    {
      label: "تأیید نهایی",
      state: allFinished ? (hasError ? "error" : "done") : "active",
      detail: allFinished ? (hasError ? "بازبینی پاسخ‌های خطادار لازم است." : "پاسخ همه عملیات ثبت شد.") : "پس از پاسخ دستگاه‌ها تکمیل می‌شود."
    }
  ], targets);
  if (allFinished) stopBackupPolling();
}

function startBackupPolling() {
  stopBackupPolling();
  if (!state.backupTargets.length) return;
  pollBackupProgress().catch((error) => notify(error.message, true));
  state.backupPollTimer = window.setInterval(() => {
    pollBackupProgress().catch((error) => notify(error.message, true));
  }, 2500);
}

async function inspectBackup() {
  if (!state.backupFile) return notify("ابتدا فایل ZIP را انتخاب کنید.", true);
  stopBackupPolling();
  state.backupTargets = [];
  renderBackupProgress([
    { label: "خواندن فایل ZIP", state: "active", detail: "در حال باز کردن فایل پشتیبان…" },
    { label: "بررسی سازگاری", state: "active", detail: "در حال مقایسه دستگاه‌ها و رکوردها…" },
    { label: "آماده‌سازی ارسال", state: "active", detail: "بعد از تأیید فایل فعال می‌شود." }
  ]);
  try {
    const inspection = await api("/api/backups/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: state.backupFile
    });
    state.backupInspection = inspection;
    renderBackupInspection(inspection);
    $("#backup-restore-button").disabled = !inspection.compatible;
    renderBackupProgress([
      { label: "خواندن فایل ZIP", state: "done", detail: "فایل با موفقیت خوانده شد." },
      {
        label: "بررسی سازگاری",
        state: inspection.compatible ? "done" : "error",
        detail: inspection.compatible ? "ناسازگاری مسدودکننده‌ای پیدا نشد." : "فایل برای ارسال ایمن نیست."
      },
      {
        label: "آماده‌سازی ارسال",
        state: inspection.compatible ? "active" : "error",
        detail: inspection.compatible ? "برای بازگردانی آماده است." : "ابتدا خطاهای فایل را برطرف کنید."
      }
    ]);
    notify(inspection.compatible ? "بررسی پشتیبان کامل شد." : "فایل ناسازگار است و ارسال نشد.", !inspection.compatible);
  } catch (error) {
    state.backupInspection = null;
    $("#backup-restore-button").disabled = true;
    renderBackupProgress([
      { label: "خواندن فایل ZIP", state: "error", detail: error.message }
    ]);
    notify(error.message, true);
  }
}

async function restoreBackup() {
  if (!state.backupFile || !state.backupInspection?.compatible) {
    return notify("ابتدا یک فایل سالم را بررسی کنید.", true);
  }
  const progress = $("#backup-progress");
  stopBackupPolling();
  state.backupTargets = [];
  $("#backup-restore-button").disabled = true;
  renderBackupProgress([
    { label: "فایل تأیید شد", state: "done", detail: "بررسی سازگاری با موفقیت انجام شد." },
    { label: "ساخت عملیات ارسال", state: "active", detail: "در حال آماده‌سازی رکوردهای کارکنان و داده‌های هویتی…" },
    { label: "دریافت توسط دستگاه‌ها", state: "active", detail: "بعد از ارتباط ADMS، صف دستگاه‌ها تخلیه می‌شود." },
    { label: "تأیید نهایی", state: "active", detail: "منتظر پاسخ دستگاه‌ها." }
  ]);
  try {
    const result = await api("/api/backups/restore", {
      method: "POST",
      headers: {
        "Content-Type": "application/zip",
        "X-Backup-Options": JSON.stringify({
          mode: $("#backup-restore-mode").value
        })
      },
      body: state.backupFile
    });
    const targets = result.targets || [];
    state.backupTargets = targets;
    renderBackupProgress([
      { label: "فایل تأیید شد", state: "done", detail: "بررسی سازگاری با موفقیت انجام شد." },
      { label: "عملیات ارسال ساخته شد", state: "done", detail: `${faNumber(targets.length)} مقصد در صف قرار گرفت.` },
      { label: "دریافت توسط دستگاه‌ها", state: targets.length ? "active" : "error", detail: targets.length ? "منتظر ارتباط ADMS دستگاه‌ها." : "مقصدی برای ارسال وجود ندارد." },
      { label: "تأیید نهایی", state: "active", detail: "پس از ACK دستگاه‌ها قابل تأیید است." }
    ], targets);
    notify("اطلاعات قابل ارسال در صف دستگاه‌ها قرار گرفت.");
    startBackupPolling();
    await refreshAll();
  } catch (error) {
    $("#backup-restore-button").disabled = false;
    progress.innerHTML = `<div class="process-step error"><span class="step-dot"></span><div><strong>بازگردانی متوقف شد</strong><div>${escapeHtml(error.message)}</div></div></div>`;
    notify(error.message, true);
  }
}

function bindEvents() {
  ensureScopedSelectors();
  enhanceSelects();
  enhanceNavIcons();
  enhanceButtonIcons();
  $$("dialog").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close("cancel");
    });
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", () => dialog.close("cancel"));
    });
    dialog.addEventListener("close", () => {
      if (dialog.id === "rename-dialog") state.renameSn = null;
      if (dialog.id === "confirm-dialog") state.confirmAction = null;
      if (dialog.id === "user-dialog") {
        state.editingPin = null;
        state.userTargetSn = null;
      }
      if (dialog.id === "copy-dialog") state.copyUser = null;
    });
  });
  $$(".nav-item").forEach((item) => {
    item.addEventListener("click", () => setView(item.dataset.view));
  });
  $("#mobile-menu-button")?.addEventListener("click", toggleMobileMenu);
  $("#mobile-menu-backdrop")?.addEventListener("click", () => closeMobileMenu());
  $("#lock-app-button")?.addEventListener("click", lockApp);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("mobile-menu-open")) {
      closeMobileMenu();
    }
  });
  window.addEventListener("resize", () => {
    if (window.matchMedia("(min-width: 761px)").matches) {
      closeMobileMenu({ restoreFocus: false });
    }
  });
  $("#sync-all-button").addEventListener("click", syncAllDevices);
  $("#refresh-button").addEventListener("click", refreshAll);
  $("#commands-refresh-button").addEventListener("click", () => loadCommandConsole());
  $("#traffic-refresh-button").addEventListener("click", () => loadTraffic());
  $("#attendance-load-button").addEventListener("click", () => loadAttendance().catch((error) => notify(error.message, true)));
  $("#attendance-export-button").addEventListener("click", () => {
    const query = new URLSearchParams({ format: "csv" });
    (state.filters.attendance || []).forEach((sn) => query.append("sns", sn));
    const start = $("#attendance-start").value;
    const end = $("#attendance-end").value;
    if (start) query.set("start", start);
    if (end) query.set("end", end);
    window.open(`/api/attendance/export?${query}`, "_blank");
  });
  $("#attendance-devices").addEventListener("change", (event) => {
    setDeviceFilter("attendance", [...event.target.selectedOptions].map((option) => option.value));
    loadAttendance().catch((error) => notify(error.message, true));
  });
  $("#new-user-button").addEventListener("click", () => openUserDialog());
  $("#user-form").addEventListener("submit", saveUser);
  $("#copy-form").addEventListener("submit", copyUser);
  $("#rename-form").addEventListener("submit", saveDeviceRename);
  $("#confirm-form").addEventListener("submit", submitConfirmDialog);
  $("#settings-password-form").addEventListener("submit", saveSettingsPassword);
  $("#user-search").addEventListener("input", () => loadUsers().catch((error) => notify(error.message, true)));
  $("#import-button").addEventListener("click", () => {
    if (!singleContext("users")) return notify("برای ورود فایل، فقط یک دستگاه مقصد انتخاب کنید.", true);
    $("#import-input").click();
  });
  $("#import-input").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) importUsers(file);
    event.target.value = "";
  });
  $("#export-button").addEventListener("click", () => {
    const sns = filterSns("users");
    if (!sns.length) return notify("دستگاهی برای خروجی گرفتن وجود ندارد.", true);
    const query = new URLSearchParams({ format: "csv" });
    sns.forEach((sn) => query.append("sns", sn));
    window.open(`/api/users/export?${query}`, "_blank");
  });
  $("#bio-query-button").addEventListener("click", queryBiometrics);
  $("#bio-export-button").addEventListener("click", () => {
    const sns = filterSns("biometrics");
    if (!sns.length) return notify("دستگاهی برای خروجی گرفتن وجود ندارد.", true);
    const query = new URLSearchParams({ format: "csv" });
    sns.forEach((sn) => query.append("sns", sn));
    window.open(`/api/biometrics/export?${query}`, "_blank");
  });
  $("#bio-pin").addEventListener("input", () => {
    loadBiometrics().catch((error) => notify(error.message, true));
  });
  $("#command-target").addEventListener("change", (event) => {
    setContext("commands", event.target.value);
    state.lastCommandId = null;
    state.lastCommandIds = [];
    loadCommandConsole().catch((error) => notify(error.message, true));
  });
  $("#send-known-command").addEventListener("click", () => {
    sendCommand($("#known-command-select").value);
  });
  $("#backup-export-button").addEventListener("click", () => window.open("/api/backups/export", "_blank"));
  $("#backup-export-page-button").addEventListener("click", () => window.open("/api/backups/export", "_blank"));
  $("#backup-input").addEventListener("change", (event) => {
    stopBackupPolling();
    state.backupTargets = [];
    state.backupFile = event.target.files[0] || null;
    state.backupInspection = null;
    $("#backup-restore-button").disabled = true;
    $("#backup-file-label").textContent = state.backupFile?.name || "فایل پشتیبان را انتخاب کنید";
    $("#backup-inspection").innerHTML = `<span class="muted">برای ادامه، فایل را بررسی کنید.</span>`;
    $("#backup-progress").innerHTML = `<div class="process-empty">بعد از بررسی فایل، روند بازگردانی اینجا نمایش داده می‌شود.</div>`;
  });
  $("#backup-inspect-button").addEventListener("click", inspectBackup);
  $("#backup-restore-button").addEventListener("click", restoreBackup);
}

async function refreshAll() {
  try {
    const [summary, devicesResult, knownCommandsResult] = await Promise.all([
      api("/api/summary"),
      api("/api/devices"),
      api("/api/known-commands")
    ]);
    state.devices = devicesResult.data || [];
    state.knownCommands = knownCommandsResult.data || [];
    ensureScopedSelectors();
    renderSummary(summary);
    renderDeviceCards();
    renderScopedContext("users");
    renderScopedContext("biometrics");
    renderScopedContext("traffic");
    renderAttendanceDevices();
    renderCommandTarget();
    renderKnownCommands();
    renderTerminalHeader();
    await loadViewData();
    renderReceiverStatus("فعال · درگاه ۸۰۹۰");
  } catch (error) {
    renderReceiverStatus("قطع است", true);
    notify(error.message, true);
  }
}

function startDeviceStatusPolling() {
  window.clearInterval(state.deviceStatusTimer);
  state.deviceStatusTimer = window.setInterval(async () => {
    if (document.hidden || document.body.classList.contains("login-visible")) return;
    try {
      const devicesResult = await api("/api/devices");
      const nextDevices = devicesResult.data || [];
      const deviceSetChanged = nextDevices.length !== state.devices.length
        || nextDevices.some((device, index) => device.sn !== state.devices[index]?.sn);
      state.devices = nextDevices;
      renderDeviceCards();
      if (deviceSetChanged) {
        ensureScopedSelectors();
        renderScopedContext("users");
        renderScopedContext("biometrics");
        renderScopedContext("traffic");
        renderAttendanceDevices();
        renderCommandTarget();
      }
    } catch {
      // The main refresh path reports receiver errors; status polling stays quiet.
    }
  }, 30_000);
}

async function boot() {
  bindEvents();
  let authenticated = false;
  try {
    const result = await api("/api/auth/status");
    authenticated = Boolean(result.authenticated);
  } catch {
    authenticated = false;
  }
  initializeLoginScreen(authenticated);
  if (authenticated) {
    await refreshAll();
    startDeviceStatusPolling();
  }
}

boot();
