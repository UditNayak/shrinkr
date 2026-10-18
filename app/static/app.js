// shrinkr web UI: plain JavaScript, no framework, no build step.
// Security rule for this file: user-controlled text is only ever inserted with textContent
// (or as attribute values), never as HTML. The page's Content-Security-Policy blocks inline
// scripts as a second line of defence.

"use strict";

const STORAGE_KEY = "shrinkr.links"; // [{code, short_url, target_url, token, created_at}]
const MAX_LIST_REFRESH = 10; // live status for the newest 10 links (rate limit: 60/min)
const STATS_DAYS = 90; // fetched once; the 7 / 30 / 90-day views are slices of it
const $ = (selector) => document.querySelector(selector);

// --- small helpers ------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

function showMessage(node, text) {
  node.textContent = text || "";
  node.hidden = !text;
}

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" }) : "Never";
}

function formatDateTime(iso) {
  return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "Never";
}

// Stats days are UTC dates ("2026-10-18"), so format them in UTC too.
function formatDay(isoDay, options = { month: "short", day: "numeric" }) {
  return new Date(`${isoDay}T00:00:00Z`).toLocaleDateString(undefined, { ...options, timeZone: "UTC" });
}

function plural(n, word) {
  return `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
}

function sum(days) {
  return days.reduce((total, day) => total + day.clicks, 0);
}

function expiryFromNow(seconds) {
  // toISOString() is UTC with a "Z" suffix, so the server knows the timezone.
  return new Date(Date.now() + Number(seconds) * 1000).toISOString();
}

function withScheme(url) {
  // "example.com/page" → "https://example.com/page"
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(url) ? url : `https://${url}`;
}

function linkPath(code, suffix = "") {
  return `/api/links/${encodeURIComponent(code)}${suffix}`;
}

function linkStatus(details) {
  if (details.is_disabled) return ["Disabled", "off"];
  if (details.expires_at && new Date(details.expires_at) <= new Date()) return ["Expired", "off"];
  if (details.max_clicks !== null && details.clicks >= details.max_clicks) return ["Used up", "off"];
  return ["Active", "on"];
}

async function copyText(text, button) {
  const label = button.dataset.label || button.textContent;
  button.dataset.label = label;
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = "Copied!";
  } catch {
    button.textContent = "Copy failed"; // the clipboard API needs https (or localhost)
  }
  setTimeout(() => { button.textContent = label; }, 1500);
}

// --- storage: the browser remembers the user's links and their tokens -----------------

function loadLinks() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return []; // private mode, blocked storage or corrupted data
  }
}

function saveLinks(links) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(links));
  } catch {
    // Storage unavailable: the page still works, it just won't remember links.
  }
}

function rememberLink(link) {
  saveLinks([link, ...loadLinks().filter((saved) => saved.code !== link.code)]);
}

function forgetLink(code) {
  saveLinks(loadLinks().filter((saved) => saved.code !== code));
}

// --- API ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function api(path, { method = "GET", token, body } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError("Can't reach shrinkr. Check your connection and try again.", 0);
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorMessage(response, data), response.status);
  return data;
}

function errorMessage(response, data) {
  if (response.status === 429) {
    const wait = response.headers.get("Retry-After");
    return `Too many requests. Please try again in ${wait || "a few"} seconds.`;
  }
  const detail = data && data.detail;
  if (typeof detail === "string") return detail; // e.g. 409 "Alias 'x' is already taken"
  if (Array.isArray(detail) && detail.length) return detail[0].msg; // 422 validation errors
  return `Something went wrong (HTTP ${response.status}).`;
}

// --- create ------------------------------------------------------------------------

$("#create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const error = $("#create-error");
  showMessage(error, "");

  const url = $("#url").value.trim();
  if (!url) {
    showMessage(error, "Paste a URL to shorten.");
    return;
  }
  const body = { url: withScheme(url) };
  const alias = $("#alias").value.trim();
  if (alias) body.alias = alias;
  if ($("#expires").value) body.expires_at = expiryFromNow($("#expires").value);
  if ($("#max-clicks").value) body.max_clicks = Number($("#max-clicks").value);

  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const link = await api("/api/links", { method: "POST", body });
    rememberLink({
      code: link.code,
      short_url: link.short_url,
      target_url: link.target_url,
      token: link.manage_token,
      created_at: link.created_at,
    });
    showResult(link);
    form.reset();
    renderLinks();
  } catch (e) {
    showMessage(error, e.message);
  } finally {
    button.disabled = false;
  }
});

function showResult(link) {
  const anchor = $("#result-link");
  anchor.href = link.short_url;
  anchor.textContent = link.short_url;
  $("#result-target").textContent = link.target_url;
  $("#result-token").textContent = link.manage_token;

  const qr = linkPath(link.code, "/qr");
  $("#result-qr").src = qr;
  $("#result-qr").alt = `QR code for ${link.short_url}`;
  $("#qr-svg").href = `${qr}?download=true`;
  $("#qr-png").href = `${qr}?format=png&scale=12&download=true`;

  $("#result-copy").onclick = (e) => copyText(link.short_url, e.currentTarget);
  $("#result-token-copy").onclick = (e) => copyText(link.manage_token, e.currentTarget);
  $("#result-manage").onclick = () => openManage(link.code);

  const section = $("#result");
  section.hidden = false;
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// --- your links --------------------------------------------------------------------

function renderLinks() {
  const links = loadLinks();
  const list = $("#links-list");
  list.replaceChildren();
  $("#links-empty").hidden = links.length > 0;

  links.forEach((link, index) => {
    const meta = el("span", { class: "link-meta", text: index < MAX_LIST_REFRESH ? "…" : "" });
    const item = el(
      "li",
      { "data-code": link.code },
      el(
        "div",
        { class: "link-text" },
        el("a", { href: link.short_url, target: "_blank", rel: "noopener", text: link.short_url }),
        el("div", { class: "muted small truncate", text: link.target_url }),
      ),
      meta,
      el("button", { type: "button", class: "secondary", text: "Copy", onclick: (e) => copyText(link.short_url, e.currentTarget) }),
      el("button", { type: "button", class: "secondary", text: "Manage", onclick: () => openManage(link.code) }),
    );
    list.append(item);
    if (index < MAX_LIST_REFRESH) refreshListItem(link, meta);
  });
}

async function refreshListItem(link, meta) {
  try {
    const details = await api(linkPath(link.code), { token: link.token });
    const [status, kind] = linkStatus(details);
    meta.replaceChildren(
      el("strong", { text: details.clicks.toLocaleString() }),
      details.clicks === 1 ? " click" : " clicks",
      el("span", { class: `badge ${kind}`, text: status }),
    );
  } catch (e) {
    const text = e.status === 404 ? "Deleted" : e.status === 403 ? "Token not valid" : "Unavailable";
    meta.replaceChildren(el("span", { class: "badge off", text }));
  }
}

$("#import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget; // currentTarget is null again after the first await
  const error = $("#import-error");
  showMessage(error, "");
  const code = $("#import-code").value.trim();
  const token = $("#import-token").value.trim();
  if (!code || !token) {
    showMessage(error, "Enter both the code and its management token.");
    return;
  }
  try {
    const details = await api(linkPath(code), { token }); // proves the token is right
    rememberLink({ code: details.code, short_url: details.short_url, target_url: details.target_url, token, created_at: details.created_at });
    form.reset();
    renderLinks();
  } catch (e) {
    showMessage(error, e.status === 403 ? "That token doesn't belong to this link." : e.message);
  }
});

// --- manage dialog -----------------------------------------------------------------

const dialog = $("#manage");
let current = null; // { link: stored entry, details, daily: last STATS_DAYS days }
let chartDays = 30;

async function openManage(code) {
  const link = loadLinks().find((saved) => saved.code === code);
  if (!link) return;
  current = { link, details: null };
  $("#manage-title").textContent = link.short_url;
  $("#manage-target").textContent = `→ ${link.target_url}`;
  showMessage($("#manage-error"), "");
  showMessage($("#manage-ok"), "");
  if (!dialog.open) dialog.showModal();
  await refreshManage();
}

async function refreshManage() {
  const { link } = current;
  try {
    const [details, stats] = await Promise.all([
      api(linkPath(link.code), { token: link.token }),
      api(linkPath(link.code, `/stats?days=${STATS_DAYS}`), { token: link.token }),
    ]);
    current.details = details;
    current.daily = stats.daily;
    $("#manage-target").textContent = `→ ${details.target_url}`;

    const [status, kind] = linkStatus(details);
    const badge = $("#stat-status");
    badge.textContent = status;
    badge.className = `badge ${kind}`;
    $("#stat-expires").textContent = details.expires_at ? `Expires ${formatDate(details.expires_at)}` : "Never expires";
    $("#stat-expires").title = formatDateTime(details.expires_at);
    $("#stat-limit").textContent = details.max_clicks === null ? "No click limit" : `Limit: ${plural(details.max_clicks, "click")}`;
    $("#toggle-link").textContent = details.is_disabled ? "Enable link" : "Disable link";
    $("#edit-url").value = details.target_url;
    $("#edit-max-clicks").value = details.max_clicks ?? "";
    $("#edit-expires").value = "";

    showSummary(stats.total_clicks, stats.daily);
    showChart();
  } catch (e) {
    showMessage($("#manage-error"), e.status === 404 ? "This link no longer exists." : e.message);
  }
}

// --- clicks: summary tiles, chart, table ---------------------------------------------

function showSummary(total, daily) {
  const week = sum(daily.slice(-7));
  const previousWeek = sum(daily.slice(-14, -7));
  $("#stat-total").textContent = total.toLocaleString();
  $("#stat-week").textContent = week.toLocaleString();
  $("#stat-today").textContent = daily[daily.length - 1].clicks.toLocaleString();

  const change = week - previousWeek;
  const delta = $("#stat-week-delta");
  delta.className = `delta small ${change > 0 ? "up" : change < 0 ? "down" : ""}`;
  delta.textContent =
    change === 0 ? "Same as the 7 days before" : `${change > 0 ? "▲" : "▼"} ${Math.abs(change).toLocaleString()} vs the 7 days before`;
}

document.querySelectorAll(".range button").forEach((button) => {
  button.addEventListener("click", () => {
    chartDays = Number(button.dataset.days);
    document.querySelectorAll(".range button").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    showChart();
  });
});

function showChart() {
  const days = current.daily.slice(-chartDays);
  drawChart($("#chart"), days);
  $("#chart-empty").hidden = sum(days) > 0;
  // Table view: the same numbers without hovering, newest first.
  $("#day-rows").replaceChildren(
    ...[...days].reverse().map((day) =>
      el("tr", {}, el("td", { text: formatDay(day.day, { weekday: "short", month: "short", day: "numeric" }) }), el("td", { text: day.clicks.toLocaleString() })),
    ),
  );
}

function niceTicks(max) {
  // 0 plus 2-4 round steps (1, 2, 5 × 10^n) covering max, e.g. 0 / 5 / 10 / 15.
  if (max <= 0) return [0, 1];
  const raw = max / 3;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw);
  const ticks = [];
  for (let t = 0; t < max + step; t += step) ticks.push(Math.round(t));
  return ticks;
}

function drawChart(container, days) {
  const SVG = "http://www.w3.org/2000/svg";
  const W = 640, H = 210, left = 34, right = 4, top = 18, bottom = 24;
  const plotW = W - left - right, plotH = H - top - bottom;
  const ticks = niceTicks(Math.max(...days.map((d) => d.clicks)));
  const yMax = ticks[ticks.length - 1];
  const y = (value) => top + plotH - (plotH * value) / yMax;
  const slot = plotW / days.length;
  const barW = Math.max(2, Math.min(24, slot - 2)); // thin bars, a 2px gap between them

  const node = (tag, attrs, text) => {
    const n = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const svg = node("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Clicks per day over ${days.length} days, ${plural(sum(days), "click")} in total` });

  // Recessive y gridlines with round-number labels.
  for (const t of ticks) {
    svg.append(node("line", { class: t === 0 ? "baseline" : "grid", x1: left, x2: W - right, y1: y(t), y2: y(t) }));
    svg.append(node("text", { x: left - 8, y: y(t) + 4, "text-anchor": "end" }, t.toLocaleString()));
  }

  // X labels: a few dates, not every one (each day for 7, about weekly for 30, ~fortnightly for 90).
  const every = days.length <= 7 ? 1 : days.length <= 30 ? 7 : 15;
  const peak = days.reduce((best, d, i) => (d.clicks > days[best].clicks ? i : best), 0);
  const tip = $("#chart-tip");

  days.forEach((day, i) => {
    const cx = left + slot * i + slot / 2;
    if ((days.length - 1 - i) % every === 0) {
      const label = days.length <= 7 ? formatDay(day.day, { weekday: "short" }) : formatDay(day.day);
      svg.append(node("text", { x: cx, y: H - 6, "text-anchor": "middle" }, label));
    }
    // Hit area: the whole column, much bigger than the bar, and keyboard-focusable.
    const text = `${plural(day.clicks, "click")} · ${formatDay(day.day, { weekday: "short", month: "short", day: "numeric" })}`;
    const hit = node("rect", { class: "hit", x: left + slot * i, y: top, width: slot, height: plotH, tabindex: 0, "aria-label": text });
    svg.append(hit);
    const bar = day.clicks ? node("path", { class: "bar", d: columnPath(cx - barW / 2, y(day.clicks), barW, y(0) - y(day.clicks)) }) : null;
    if (bar) svg.append(bar);

    const show = () => {
      tip.replaceChildren(el("strong", { text: day.clicks.toLocaleString() }), text.split(" · ")[1]);
      tip.style.left = `${(100 * cx) / W}%`;
      // Near an edge, anchor the tooltip on that side so it never runs out of the dialog.
      tip.classList.toggle("edge-right", cx / W > 0.8);
      tip.classList.toggle("edge-left", cx / W < 0.2);
      tip.style.top = `${(100 * y(day.clicks)) / H}%`;
      tip.hidden = false;
      bar?.classList.add("active");
    };
    const hide = () => {
      tip.hidden = true;
      bar?.classList.remove("active");
    };
    hit.addEventListener("pointerenter", show);
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("focus", show);
    hit.addEventListener("blur", hide);
  });

  // One direct label: the busiest day's value.
  if (days[peak].clicks > 0) {
    svg.append(node("text", { class: "peak", x: left + slot * peak + slot / 2, y: y(days[peak].clicks) - 5, "text-anchor": "middle" }, days[peak].clicks.toLocaleString()));
  }
  container.replaceChildren(svg);
}

function columnPath(x, y, width, height) {
  // A column with 4px rounded top corners and a square bottom on the baseline.
  const r = Math.min(4, width / 2, height);
  return `M${x},${y + height} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + height} Z`;
}

$("#edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const { link, details } = current;
  if (!details) return;
  showMessage($("#manage-error"), "");
  showMessage($("#manage-ok"), "");

  // Send only what changed: PATCH leaves the other fields alone.
  const changes = {};
  const url = $("#edit-url").value.trim();
  if (url && url !== details.target_url) changes.url = withScheme(url);
  const maxRaw = $("#edit-max-clicks").value;
  const maxClicks = maxRaw === "" ? null : Number(maxRaw); // empty = unlimited
  if (maxClicks !== details.max_clicks) changes.max_clicks = maxClicks;
  const expiry = $("#edit-expires").value;
  if (expiry === "never") changes.expires_at = null;
  else if (expiry) changes.expires_at = expiryFromNow(expiry);

  if (!Object.keys(changes).length) {
    showMessage($("#manage-ok"), "Nothing to change.");
    return;
  }
  try {
    const updated = await api(linkPath(link.code), { method: "PATCH", token: link.token, body: changes });
    rememberLink({ ...link, target_url: updated.target_url });
    current.link = { ...link, target_url: updated.target_url };
    showMessage($("#manage-ok"), "Saved.");
    await refreshManage();
    renderLinks();
  } catch (e) {
    showMessage($("#manage-error"), e.message);
  }
});

$("#toggle-link").addEventListener("click", async () => {
  const { link, details } = current;
  if (!details) return;
  try {
    await api(linkPath(link.code), { method: "PATCH", token: link.token, body: { is_disabled: !details.is_disabled } });
    showMessage($("#manage-ok"), details.is_disabled ? "Link enabled." : "Link disabled. Visitors now see a 'link disabled' page.");
    await refreshManage();
    renderLinks();
  } catch (e) {
    showMessage($("#manage-error"), e.message);
  }
});

$("#delete-link").addEventListener("click", async () => {
  const { link } = current;
  const sure = confirm(
    `Delete ${link.short_url}?\n\nAnyone using the link or its QR code will get "not found", its ` +
      "stats are deleted, and the code becomes free for someone else. Disabling is reversible.",
  );
  if (!sure) return;
  try {
    await api(linkPath(link.code), { method: "DELETE", token: link.token });
    forgetLink(link.code);
    dialog.close();
    if ($("#result-link").textContent === link.short_url) $("#result").hidden = true;
    renderLinks();
  } catch (e) {
    showMessage($("#manage-error"), e.message);
  }
});

$("#forget-link").addEventListener("click", () => {
  const { link } = current;
  const sure = confirm(
    `Remove ${link.short_url} from this browser?\n\nThe link keeps working. Without its token ` +
      "you won't be able to manage it again, so copy the token first if you need it.",
  );
  if (!sure) return;
  forgetLink(link.code);
  dialog.close();
  renderLinks();
});

renderLinks();
