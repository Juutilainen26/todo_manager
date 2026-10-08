/* 일정 관리 - 모바일 웹 화면 (빌드 없는 순수 JS). 데스크톱 클라이언트와 같은 규칙을 따른다. */
(() => {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const WD = ["월", "화", "수", "목", "금", "토", "일"];
const PAGE = 400;                       // 한 번에 그릴 행 수(대량 목록 대비)
const LS = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };

/* 안드로이드 앱(Capacitor)에서는 화면 파일이 앱 안에 들어 있어서, 데이터는 사용자가 입력한 서버 주소로 받는다.
   브라우저에서 서버 주소로 직접 열 때는 이전처럼 같은 서버(상대 경로)를 쓴다. */
const NATIVE = !!(window.Capacitor && typeof window.Capacitor.isNativePlatform === "function" && window.Capacitor.isNativePlatform());
let BASE = NATIVE ? (LS("server") || "") : "";

let tasks = [], offset = 0, tab = "all", q = "", onlyPending = true;
let online = false, busy = false, again = false, sinceFetch = 0, shown = PAGE, editingId = null, lastFetch = 0;

/* ---------- 시간/문구 (util.py 와 동일 규칙) ---------- */
const now = () => new Date(Date.now() + offset);
const pdt = s => (s ? new Date(s) : null);
const day0 = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const dayDiff = (a, b) => Math.round((day0(a) - day0(b)) / 86400000);
const p2 = n => String(n).padStart(2, "0");
const hm = d => p2(d.getHours()) + ":" + p2(d.getMinutes());

function fmtSpan(sec) {
  sec = Math.max(0, Math.floor(sec));
  const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
  if (d) return h ? `${d}일 ${h}시간` : `${d}일`;
  if (h) return m ? `${h}시간 ${m}분` : `${h}시간`;
  if (m) return `${m}분`;
  return "1분 미만";
}
function fmtDue(dt, n) {
  const k = dayDiff(dt, n);
  if (k === 0) return `오늘 ${hm(dt)}`;
  if (k === 1) return `내일 ${hm(dt)}`;
  return `${dt.getMonth() + 1}/${dt.getDate()}(${WD[(dt.getDay() + 6) % 7]}) ${hm(dt)}`;
}
function ruleText(t, n) {
  if (t.kind === "daily") return `매일 ${t.reset_time} 초기화` + (t.due_time ? ` · 마감 ${t.due_time}` : "");
  if (t.kind === "weekly") return `매주 ${WD[t.reset_weekday]} ${t.reset_time} 초기화` + (t.due_time ? ` · 마감 ${WD[t.due_weekday]} ${t.due_time}` : "");
  return t._due ? `마감 ${fmtDue(t._due, n)}` : "기한 없음";
}
const explicitDue = t => (t.kind === "once" && !!t.due_at) || !!t.due_time;
function rightText(t, n) {
  const reset = t._end ? ` · ${fmtSpan((t._end - n) / 1000)} 후 초기화` : "";
  if (t.status === "done") return ["✔ 완료" + reset, "ok"];
  if (t.status === "missed") return ["마감 초과" + reset, "danger"];
  if (!t._due) return ["기한 없음", "sub"];
  const rem = (t._due - n) / 1000;
  const label = explicitDue(t) ? `${fmtSpan(rem)} 남음` : `초기화까지 ${fmtSpan(rem)}`;
  return [label, rem <= 600 ? "danger" : rem <= 3600 ? "warn" : "text"];
}

/* ---------- 데이터 ---------- */
function prepare(t) {
  t._due = pdt(t.due_at);
  t._end = t.kind !== "once" ? pdt(t.cycle_end) : null;
  t._exp = t.status === "pending" ? t._due : t._end;
  return t;
}
const order = { pending: 0, missed: 1, done: 2 };
function sortKey(t, n) {
  const rem = t.status === "pending" && t._due ? (t._due - n) : Infinity;
  return [order[t.status], rem, t.title];
}
function cmp(a, b) {
  const n = now(), ka = sortKey(a, n), kb = sortKey(b, n);
  for (let i = 0; i < 3; i++) { if (ka[i] < kb[i]) return -1; if (ka[i] > kb[i]) return 1; }
  return 0;
}
function upsert(t) {
  t = prepare({ ...t });
  const i = tasks.findIndex(x => x.id === t.id);
  if (i >= 0) tasks[i] = t; else tasks.push(t);
  tasks.sort(cmp);
}
function visible() {
  const n = now(), today = day0(n);
  const ql = q.trim().toLowerCase();
  return tasks.filter(t => {
    if (onlyPending && t.status !== "pending") return false;
    if (ql && !(t.title + " " + (t.note || "")).toLowerCase().includes(ql)) return false;
    const due = t._due;
    switch (tab) {
      case "daily": return t.kind === "daily";
      case "weekly": return t.kind === "weekly";
      case "today": return t.kind === "daily" || (t.kind === "once" && due && day0(due).getTime() === today.getTime());
      case "upcoming": return t.kind === "once" && (!due || day0(due) > today);
      default: return true;
    }
  });
}

/* ---------- 서버 통신 ---------- */
async function api(method, path, body) {
  if (NATIVE && !BASE) { const err = new Error("offline"); err.offline = true; throw err; }
  const ctl = new AbortController(), to = setTimeout(() => ctl.abort(), 7000);
  let r;
  try {
    r = await fetch(BASE + path, { method, signal: ctl.signal, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  } catch (e) { const err = new Error("offline"); err.offline = true; throw err; }
  finally { clearTimeout(to); }
  if (r.status === 204) return null;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    let d = data.detail || r.statusText;
    if (Array.isArray(d)) d = d.map(x => x.msg || x).join("; ");
    throw new Error(d);
  }
  return data;
}

async function fetchTasks() {
  if (busy) { again = true; return; }
  busy = true; sinceFetch = 0; lastFetch = Date.now();
  try {
    const res = await api("GET", "/api/tasks?keep_closed_days=3");
    offset = new Date(res.server_now) - Date.now();
    tasks = res.tasks.map(prepare);
    LS("cache", JSON.stringify({ tasks: res.tasks, server_now: res.server_now, at: Date.now() }));
    setOnline(true);
  } catch (e) { setOnline(false); }
  busy = false;
  render();
  if (again) { again = false; fetchTasks(); }
}
function setOnline(v) {
  online = v;
  $("#conn").className = "conn " + (v ? "on" : "off");
  $("#banner").hidden = v;
}

/* ---------- 화면 ---------- */
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function render() {
  const n = now(), rows = visible();
  const pend = rows.filter(t => t.status === "pending").length;
  const list = $("#list");
  if (!rows.length) {
    list.innerHTML = `<div class="empty">${tasks.length ? "표시할 일정이 없어요" : "일정이 없어요. 위에서 추가해 보세요"}</div>`;
  } else {
    const part = rows.slice(0, shown);
    list.innerHTML = part.map(t => {
      const sub = (t.kind === "once" && t._due ? `마감 ${fmtDue(t._due, n)}` : ruleText(t, n)) + (t.note ? "  ·  " + t.note.split("\n")[0] : "");
      const mark = t.status === "done" ? "✓" : t.status === "missed" ? "✕" : "";
      const [rt, c] = rightText(t, n);
      return `<div class="row ${t.status}" data-id="${t.id}">
        <button class="chkbtn" data-act="toggle" aria-label="완료 전환">${mark}</button>
        <div class="mid" data-act="edit"><div class="title">${esc(t.title)}</div><div class="sub">${esc(sub)}</div></div>
        <div class="rt c-${c}" data-act="edit" data-rt>${esc(rt)}</div></div>`;
    }).join("") + (rows.length > shown ? `<button class="more" data-act="more">더 보기 (${rows.length - shown}건 남음)</button>` : "");
  }
  $("#status").textContent = `${online ? "● 연결됨" : "○ 오프라인"}  |  진행 중 ${pend} / 표시 ${rows.length}  |  전체 ${tasks.length}건`;
}
function tickTexts() {            // 매초: 남은 시간 글자만 갱신
  const n = now();
  document.querySelectorAll(".row").forEach(el => {
    const t = tasks.find(x => x.id === +el.dataset.id); if (!t) return;
    const [rt, c] = rightText(t, n), r = el.querySelector("[data-rt]");
    if (r && r.textContent !== rt) r.textContent = rt;
    if (r) r.className = "rt c-" + c;
  });
}
let toastT;
function toast(msg, ms = 2600) {
  const el = $("#toast"); el.textContent = msg; el.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => (el.hidden = true), ms);
}

/* ---------- 동작 ---------- */
async function act(fn, okMsg) {
  try { const res = await fn(); if (res && res.id) { upsert(res); render(); } if (okMsg) toast(okMsg, 1600); }
  catch (e) { toast(e.offline ? "서버에 연결할 수 없어요" : e.message); }
  fetchTasks();
}
function toggle(t) {
  if (t.status === "missed") return toast("마감이 지난 일정은 완료 처리할 수 없어요.");
  const going = t.status === "pending";
  const local = { ...t, status: going ? "done" : "pending", last_completed_at: going ? new Date().toISOString() : null };
  upsert(local); render();                      // 낙관적 반영
  act(() => api("POST", `/api/tasks/${t.id}/${going ? "complete" : "uncomplete"}`));
}
function quickAdd(title, kind) {
  const n = now(), data = { title };
  if (kind === "today") Object.assign(data, { kind: "once", due_at: `${n.getFullYear()}-${p2(n.getMonth() + 1)}-${p2(n.getDate())}T23:59:00` });
  else if (kind === "daily") Object.assign(data, { kind: "daily", reset_time: "00:00" });
  else if (kind === "weekly") Object.assign(data, { kind: "weekly", reset_weekday: 0, reset_time: "00:00" });
  else Object.assign(data, { kind: "once" });
  act(() => api("POST", "/api/tasks", data), "추가했어요");
}

/* ---------- 시트(추가/수정) ---------- */
function fillSelects() {
  const opts = WD.map((n, i) => `<option value="${i}">${n}요일</option>`).join("");
  $("#f-rwd").innerHTML = opts; $("#f-dwd").innerHTML = opts;
}
function syncSheet() {
  const k = $("#f-kind").value, rec = k !== "once";
  $("#g-weekly").hidden = k !== "weekly";
  $("#g-rec").hidden = !rec;
  $("#g-once").hidden = rec;
  $("#g-due").hidden = !(rec && $("#f-usedue").checked);
  $("#g-dwd").hidden = k !== "weekly";
  $("#g-onceval").hidden = !$("#f-useonce").checked;
}
function localInput(d) { return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}`; }
function openSheet(t) {
  editingId = t ? t.id : null;
  $("#sheet-title").textContent = t ? "일정 수정" : "일정 추가";
  $("#f-title").value = t ? t.title : ""; $("#f-note").value = t ? (t.note || "") : "";
  $("#f-kind").value = t ? t.kind : "daily";
  $("#f-rwd").value = t && t.reset_weekday != null ? t.reset_weekday : 0;
  $("#f-rt").value = (t && t.reset_time) || "00:00";
  $("#f-usedue").checked = !!(t && t.due_time);
  $("#f-dwd").value = t && t.due_weekday != null ? t.due_weekday : 0;
  $("#f-dt").value = (t && t.due_time) || "22:00";
  $("#f-useonce").checked = t ? !!t.due_at : false;
  const base = t && t._due ? t._due : (() => { const d = now(); d.setHours(23, 59, 0, 0); return d; })();
  $("#f-due").value = localInput(base);
  $("#f-err").textContent = ""; $("#f-del").hidden = !t; $("#f-del").textContent = "삭제"; $("#f-del").dataset.arm = "";
  syncSheet();
  $("#sheet").hidden = false; $("#sheet-bg").hidden = false;
  if (!t) setTimeout(() => $("#f-title").focus(), 50);
}
function closeSheet() { $("#sheet").hidden = true; $("#sheet-bg").hidden = true; editingId = null; }
function payload() {
  const k = $("#f-kind").value;
  const d = { title: $("#f-title").value.trim(), note: $("#f-note").value.trim(), kind: k,
    reset_time: null, reset_weekday: null, due_time: null, due_weekday: null, due_at: null };
  if (k !== "once") {
    d.reset_time = $("#f-rt").value || "00:00";
    if (k === "weekly") d.reset_weekday = +$("#f-rwd").value;
    if ($("#f-usedue").checked) { d.due_time = $("#f-dt").value || "22:00"; if (k === "weekly") d.due_weekday = +$("#f-dwd").value; }
  } else if ($("#f-useonce").checked && $("#f-due").value) d.due_at = $("#f-due").value + ":00";
  return d;
}

/* ---------- 이벤트 ---------- */
function init() {
  fillSelects();
  const k = LS("quick_kind"); if (k) $("#quick-kind").value = k;
  try { const c = JSON.parse(LS("cache") || "null"); if (c && c.tasks) { tasks = c.tasks.map(prepare); } } catch (e) { /* 캐시 없음 */ }
  render();

  $("#quick").addEventListener("submit", e => {
    e.preventDefault();
    const v = $("#quick-title").value.trim(); if (!v) return;
    $("#quick-title").value = ""; quickAdd(v, $("#quick-kind").value);
  });
  $("#quick-kind").addEventListener("change", e => LS("quick_kind", e.target.value));
  $("#tabs").addEventListener("click", e => {
    const b = e.target.closest("button[data-tab]"); if (!b) return;
    tab = b.dataset.tab; shown = PAGE;
    document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("on", x === b));
    const map = { today: "today", daily: "daily", weekly: "weekly", upcoming: "future" };
    if (map[tab]) { $("#quick-kind").value = map[tab]; LS("quick_kind", map[tab]); }
    render();
  });
  $("#search").addEventListener("input", e => { q = e.target.value; shown = PAGE; render(); });
  $("#only-pending").addEventListener("change", e => { onlyPending = e.target.checked; shown = PAGE; render(); });
  $("#refresh").addEventListener("click", () => { fetchTasks(); toast("새로고침", 900); });
  $("#fab").addEventListener("click", () => openSheet(null));
  $("#list").addEventListener("click", e => {
    const el = e.target.closest("[data-act]"); if (!el) return;
    if (el.dataset.act === "more") { shown += PAGE; return render(); }
    const row = e.target.closest(".row"); if (!row) return;
    const t = tasks.find(x => x.id === +row.dataset.id); if (!t) return;
    if (el.dataset.act === "toggle") toggle(t); else openSheet(t);
  });
  $("#f-kind").addEventListener("change", syncSheet);
  $("#f-usedue").addEventListener("change", syncSheet);
  $("#f-useonce").addEventListener("change", syncSheet);
  $("#f-cancel").addEventListener("click", closeSheet);
  $("#sheet-bg").addEventListener("click", closeSheet);
  $("#sheet").addEventListener("submit", e => {
    e.preventDefault();
    const d = payload(); if (!d.title) { $("#f-err").textContent = "제목을 입력해 주세요."; return; }
    const id = editingId; closeSheet();
    act(() => (id ? api("PATCH", `/api/tasks/${id}`, d) : api("POST", "/api/tasks", d)), id ? "수정했어요" : "추가했어요");
  });
  $("#f-del").addEventListener("click", e => {          // 두 번 눌러야 삭제(브라우저 확인창 없이)
    const b = e.currentTarget;
    if (b.dataset.arm !== "1") { b.dataset.arm = "1"; b.textContent = "정말 삭제"; return; }
    const id = editingId; closeSheet();
    tasks = tasks.filter(x => x.id !== id); render();
    act(() => api("DELETE", `/api/tasks/${id}`), "삭제했어요");
  });

  setInterval(() => {
    tickTexts(); sinceFetch++;
    const exp = tasks.reduce((m, t) => (t._exp && (!m || t._exp < m) ? t._exp : m), null);
    const dueNow = exp && now() >= exp && Date.now() - lastFetch > 2500;
    if (sinceFetch >= (online ? 30 : 5) || dueNow) fetchTasks();
  }, 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) fetchTasks(); });
  fetchTasks();
}
/* ---------- 서버 주소 설정(앱 전용) ---------- */
function normalizeServer(raw) {
  let u = (raw || "").trim().replace(/\s+/g, "");
  if (!u) return "";
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(u)) u = "http://" + u;
  const m = u.match(/^(https?:\/\/)([^/?#]+)/i);
  if (!m) return "";
  let host = m[2];
  if (m[1].toLowerCase() === "http://" && !/:\d+$/.test(host)) host += ":8765";
  return m[1].toLowerCase() + host;
}
function showSetup(first) {
  $("#s-url").value = BASE.replace(/^http:\/\//, "");
  $("#s-msg").textContent = ""; $("#s-force").hidden = true;
  $("#s-cancel").hidden = !!first;
  $("#setup").hidden = false;
  setTimeout(() => $("#s-url").focus(), 50);
}
async function trySetup(force) {
  const url = normalizeServer($("#s-url").value);
  if (!url) { $("#s-msg").textContent = "주소를 입력해 주세요."; return; }
  if (!force) {
    $("#s-ok").disabled = true; $("#s-msg").textContent = "연결 확인 중…";
    const ctl = new AbortController(), to = setTimeout(() => ctl.abort(), 6000);
    try {
      const r = await fetch(url + "/api/health", { signal: ctl.signal });
      const j = await r.json();
      if (!r.ok || j.ok !== true) throw new Error("bad");
    } catch (e) {
      $("#s-ok").disabled = false;
      $("#s-msg").textContent = "연결하지 못했어요. 서버 PC에서 서버를 켰는지, 폰의 Tailscale이 켜져 있는지, 주소가 맞는지 확인해 주세요.";
      $("#s-force").hidden = false;
      return;
    } finally { clearTimeout(to); }
  }
  $("#s-ok").disabled = false;
  if (url !== BASE) LS("cache", "");          // 다른 서버로 바꾸면 이전 서버의 저장 목록은 버린다
  BASE = url; LS("server", url);
  $("#setup").hidden = true;
  tasks = []; render(); fetchTasks();
  toast("서버 주소를 저장했어요", 1600);
}
function initNative() {
  if (!NATIVE) return;
  $("#gear").hidden = false;
  $("#gear").addEventListener("click", () => showSetup(false));
  $("#setup").addEventListener("submit", e => { e.preventDefault(); trySetup(false); });
  $("#s-force").addEventListener("click", () => trySetup(true));
  $("#s-cancel").addEventListener("click", () => { $("#setup").hidden = true; });
  if (!BASE) showSetup(true);
}
document.addEventListener("DOMContentLoaded", () => { initNative(); init(); });
})();
