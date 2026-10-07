// 조문.py — 화면 동작 (SPEC 입력 → /api/build → BUILD 로그 → INSPECT)
const $ = (sel) => document.querySelector(sel);

const state = {
  result: null,
  builtSpec: "",
  answers: {},          // 되묻기 답변 {question_id: value}
  selectedKey: null,
  tab: "decompiled",
  examples: [],
  exampleIndex: 0,
  checks: loadChecks(),
};

// ── 상태 배지 아이콘 ─────────────────────────────
const BADGE_ICON = {
  MATCH: '<svg class="ico" viewBox="0 0 24 24"><path d="m4.5 12.5 5 5L20 7" stroke-width="3"/></svg>',
  REQUIRED: '<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="3.2" fill="#fff" stroke="none"/></svg>',
  REVIEW: '<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#f3a83b" stroke="none"/><path d="M12 7v6.5M12 16.8h.01" stroke="#fff" stroke-width="2.6"/></svg>',
  CONDITIONAL: '<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" stroke-width="2.2"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none"/></svg>',
  SHOULD: '<svg class="ico" viewBox="0 0 24 24"><path d="M12 3 22 20.5H2z" fill="currentColor" stroke="currentColor" stroke-width="1.5"/><path d="M12 9.5v5M12 17.6h.01" stroke="#fff" stroke-width="2.4"/></svg>',
  OPPORTUNITY: '<svg class="ico" viewBox="0 0 24 24"><path d="M12 2.5 21.5 12 12 21.5 2.5 12z" fill="currentColor" stroke="none"/></svg>',
  OUT_OF_SCOPE: '<svg class="ico" viewBox="0 0 24 24"><path d="M5 5v6a4 4 0 0 0 4 4h10M15 11l4 4-4 4" stroke-width="2.4"/></svg>',
  INFO: '<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke-width="2.2"/><path d="M12 11v5.5M12 7.8h.01" stroke-width="2.4"/></svg>',
};
const STATUS_TEXT = { OUT_OF_SCOPE: "OUT OF SCOPE" };
const OBLIGATION_KO = { MUST: "MUST · 하여야 한다", SHOULD: "SHOULD · 노력하여야 한다", MAY: "MAY · 할 수 있다", MUST_NOT: "MUST_NOT · 하여서는 아니 된다" };

// ── 공통 유틸 ─────────────────────────────────────
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove("show"), 2200);
}
function loadChecks() {
  try { return new Set(JSON.parse(localStorage.getItem("jomun.checks") || "[]")); } catch { return new Set(); }
}
function saveChecks() {
  try { localStorage.setItem("jomun.checks", JSON.stringify([...state.checks])); } catch { /* 저장 불가 환경 무시 */ }
}

// ── Python 코드 하이라이트 (디컴파일 탭) ────────────
const TOKEN = /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(@\w+)|\b(def|class|if|elif|else|return|not|in|and|or|for|while|raise|import|from|lambda|None|True|False|pass|with|as|is)\b(\s+[A-Za-z_]\w*)?|\b(\d[\d_]*)\b/g;
function highlight(line) {
  let out = "", last = 0;
  line.replace(TOKEN, (m, com, str, dec, kw, name, num, idx) => {
    out += esc(line.slice(last, idx));
    if (com) out += `<span class="tok-com">${esc(com)}</span>`;
    else if (str) out += `<span class="tok-str">${esc(str)}</span>`;
    else if (dec) out += `<span class="tok-dec">${esc(dec)}</span>`;
    else if (kw) {
      out += `<span class="tok-kw">${kw}</span>`;
      if (name) out += (kw === "def" || kw === "class") ? `<span class="tok-fn">${esc(name)}</span>` : esc(name);
    } else if (num) out += `<span class="tok-num">${num}</span>`;
    last = idx + m.length;
    return m;
  });
  return out + esc(line.slice(last));
}

// ── API ───────────────────────────────────────────
async function runBuild({ keepSelection = false } = {}) {
  const spec = $("#spec").value.trim();
  if (!spec) { toast("서비스 설명을 입력해 주세요."); $("#spec").focus(); return; }
  if (spec !== state.builtSpec) state.answers = {};   // 설명이 바뀌면 이전 답변은 버린다

  const btn = $("#run");
  btn.disabled = true;
  setStatus("running", "빌드 중…", "");
  const t0 = performance.now();
  try {
    const res = await fetch("/api/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec, answers: state.answers }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    const sec = Math.max(0.1, (performance.now() - t0) / 1000);
    state.result = data;
    state.builtSpec = spec;
    if (!keepSelection || !data.items.some((i) => i.key === state.selectedKey)) {
      const firstQuestion = data.items.find((i) => i.status === "REVIEW" && i.question);
      state.selectedKey = (firstQuestion || data.items[0] || {}).key;
    }
    setStatus("done", "빌드 완료", `${sec.toFixed(1)}초 소요`);
    renderAll(!keepSelection);
  } catch (err) {
    setStatus("error", "빌드 실패", "");
    toast(`빌드 실패: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

function setStatus(kind, label, time) {
  const el = $("#status");
  el.className = `status-pill ${kind}`;
  el.querySelector("b").textContent = label;
  el.querySelector("span").textContent = time;
}

// ── 렌더링 ────────────────────────────────────────
function renderAll(animate) {
  renderLog(animate);
  renderSummary();
  renderInspect();
  renderTodo();
}

function badge(status) {
  return `<span class="badge b-${status}">${BADGE_ICON[status] || ""}${STATUS_TEXT[status] || status}</span>`;
}

function renderLog(animate) {
  const items = state.result?.items || [];
  $("#log").innerHTML = items.map((it, i) => {
    const cond = it.condition ? `<span class="cond">${esc(it.condition)} → </span>` : "";
    const ask = it.question && !it.question.answer ? '<span class="q">질문</span>' : "";
    return `
      <li class="log-row ${it.key === state.selectedKey ? "selected" : ""}" data-key="${it.key}"
          style="animation-delay:${animate ? i * 45 : 0}ms; ${animate ? "" : "animation:none"}">
        ${badge(it.status)}
        <span class="ref">${esc(it.label)}</span>
        <span class="desc" title="${esc((it.condition ? it.condition + " → " : "") + it.summary)}">${ask}${cond}${esc(it.summary)}</span>
        <svg><use href="#i-chevron"/></svg>
      </li>`;
  }).join("") || '<li class="log-empty">적용되는 항목이 없어요.</li>';
}

function renderSummary() {
  const r = state.result;
  const pending = r.pending_questions.length;
  $("#summary-text").innerHTML = esc(r.summary.text || "-") +
    (pending ? ` · <span class="ask" id="ask-link">확인 질문 ${pending}건</span>` : "");
}

function selectedItem() {
  return state.result?.items.find((i) => i.key === state.selectedKey);
}

function renderInspect() {
  const it = selectedItem();
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === state.tab));
  $(".tab-dot").hidden = !(it?.question && !it.question.answer);
  const box = $("#tab-content");
  if (!it) { box.innerHTML = '<p class="muted">빌드 로그에서 항목을 선택하면 근거가 여기에 표시돼요.</p>'; return; }
  if (state.tab === "original") box.innerHTML = renderOriginal(it);
  else if (state.tab === "checklist") box.innerHTML = renderImpl(it);
  else box.innerHTML = renderDecompiled(it);
  box.scrollTop = 0;
}

function renderDecompiled(it) {
  if (!it.decompiled?.code) return '<p class="muted">이 항목에는 디컴파일 코드가 없어요.</p>';
  const lines = it.decompiled.code.replace(/\n$/, "").split("\n");
  return `
    <div class="code-head">
      <h3>분석 로직 (일부)</h3>
      <span class="lang">Python <button id="copy-code" title="코드 복사"><svg><use href="#i-copy"/></svg></button></span>
    </div>
    <div class="code">${lines.map((l) => `<span class="ln">${highlight(l) || " "}</span>`).join("")}</div>
    <p class="code-note">이해를 돕는 비유 코드이며 법률 해석이 아니에요 · ${esc(it.decompiled.filename)}</p>`;
}

function renderQuestion(q) {
  return `
    <div class="question">
      <p class="q">${esc(q.text)}</p>
      <p class="h">${esc(q.help || "")}</p>
      <div class="opts">
        ${q.options.map((o) => `<button data-q="${q.id}" data-v="${o.value}" class="${q.answer === o.value ? "on" : ""}">${esc(o.label)}</button>`).join("")}
      </div>
    </div>`;
}

function renderOriginal(it) {
  const r = state.result;
  const first = it.records[0];
  const chips = [];
  if (it.obligation) chips.push(`<span class="chip ${it.obligation === "SHOULD" ? "should" : it.obligation === "MAY" ? "may" : "must"}">${OBLIGATION_KO[it.obligation] || it.obligation}</span>`);
  if (first) chips.push(`<span class="chip">수범자 · ${esc(first.addressee_ko)}</span>`);
  if (it.chain) chips.push(`<span class="chip ${it.chain.type.toLowerCase()}">penalty · ${it.chain.type}</span>`);
  if (it.externals.length) chips.push('<span class="chip ext">◈ EXTERNAL</span>');

  const texts = it.records.map((rec) => `
    <div class="law-text">
      <span class="ref">${esc(rec.ref_label)} · ${esc(rec.title)} · ${rec.source_page}쪽</span>
      ${esc(rec.text)}
      ${rec.children.length ? `<ol>${rec.children.map((c) => `<li>${esc(c.marker)} ${esc(c.text)}</li>`).join("")}</ol>` : ""}
    </div>`).join("");

  const chain = it.chain ? `
    <p class="sub-title">근거 체인 (${it.chain.type})</p>
    <div class="chain">${it.chain.nodes.map((n, i) => `
      ${i ? '<span class="chain-arrow"></span>' : ""}
      <div class="chain-node k-${n.kind}"><span class="dot"></span><span class="r">${esc(n.ref || "")}</span><span class="l">${esc(n.label)}</span></div>`).join("")}
    </div>` : "";

  const retrieved = r.retrieved.length ? `
    <p class="sub-title">RAG 검색 근거 (Chroma top-${r.retrieved.length})</p>
    <div class="retrieved">${r.retrieved.map((h) => `<span class="chip" title="${esc(h.snippet)}">${esc(h.ref_label)}<small>${h.score}</small></span>`).join("")}</div>` : "";

  return `
    ${it.question ? renderQuestion(it.question) : ""}
    <div class="art-head"><h3>${esc(it.label)}</h3><span class="art-title">${esc(it.summary)}</span></div>
    <div class="chips">${chips.join("")}</div>
    ${texts || '<p class="muted">Knowledge Base(인공지능기본법) 밖의 항목이라 원문이 없어요.</p>'}
    ${it.notes.length ? `<p class="sub-title">판정 근거</p><ul class="notes">${it.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    ${it.externals.length ? `<p class="sub-title">하위 규정 의존</p><div class="ext-box"><b>◈ EXTERNAL</b>${it.externals.map(esc).join("<br>")}<br>→ 상위 조문만으로 확정되지 않아요. 하위 규정 확인 필요</div>` : ""}
    ${chain}
    ${retrieved}
    <p class="sub-title">추출된 서비스 특성 (${esc(r.mode.feature_extractor)})</p>
    <ul class="notes">${(r.features.evidence.length ? r.features.evidence : ["근거 문구 없음"]).map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`;
}

function renderImpl(it) {
  if (!it.checklist.length) {
    return `<h3>구현 체크리스트</h3><p class="muted" style="margin-top:10px">이 항목은 판정·안내 항목이라 구현 체크리스트가 없어요.</p>`;
  }
  return `<h3>구현 체크리스트 · ${esc(it.label)}</h3>
    <ul class="impl">${it.checklist.map((c, i) => {
      const id = `impl:${it.key}:${i}`;
      const on = state.checks.has(id);
      return `<li class="${on ? "done" : ""}"><span class="check ${on ? "on" : ""}" data-check="${id}"><svg><use href="#i-check"/></svg></span><span class="t">${esc(c)}</span></li>`;
    }).join("")}</ul>`;
}

function renderTodo() {
  const todo = state.result?.todo || [];
  $("#todo").innerHTML = todo.map((t) => {
    const id = `todo:${t.title}`;
    const on = state.checks.has(id);
    const tag = t.status === "CONDITIONAL" ? '<span class="tag">조건부</span>' : "";
    return `
      <li class="${on ? "done" : ""}">
        <span class="check ${on ? "on" : ""}" data-check="${id}"><svg><use href="#i-check"/></svg></span>
        <span class="t">${esc(t.title)}${tag}</span>
        <span class="d">${esc(t.desc)}</span>
      </li>`;
  }).join("") || '<li><span></span><span class="d">빌드를 실행하면 점검 항목이 표시돼요.</span></li>';
}

// ── 이벤트 ────────────────────────────────────────
function updateCounter() {
  $("#counter").textContent = `${$("#spec").value.length}/500`;
}

function bindEvents() {
  $("#spec").addEventListener("input", updateCounter);
  $("#spec").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) runBuild();
  });
  $("#run").addEventListener("click", () => runBuild());

  $("#load-example").addEventListener("click", () => {
    if (!state.examples.length) return;
    state.exampleIndex = (state.exampleIndex + 1) % state.examples.length;
    const ex = state.examples[state.exampleIndex];
    $("#spec").value = ex.spec;
    updateCounter();
    toast(`예시 ${ex.id} · ${ex.name}`);
    runBuild();
  });

  $("#log").addEventListener("click", (e) => {
    const row = e.target.closest(".log-row");
    if (!row) return;
    state.selectedKey = row.dataset.key;
    document.querySelectorAll(".log-row").forEach((r) => r.classList.toggle("selected", r === row));
    renderInspect();
  });

  $("#summary").addEventListener("click", (e) => {
    if (e.target.id !== "ask-link") return;
    const it = state.result.items.find((i) => i.question && !i.question.answer);
    if (!it) return;
    state.selectedKey = it.key;
    state.tab = "original";
    renderLog(false);
    renderInspect();
  });

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    state.tab = t.dataset.tab;
    renderInspect();
  }));

  $("#tab-content").addEventListener("click", async (e) => {
    const opt = e.target.closest("[data-q]");
    if (opt) {
      state.answers[opt.dataset.q] = opt.dataset.v;
      await runBuild({ keepSelection: true });
      return;
    }
    if (e.target.closest("#copy-code")) {
      try {
        await navigator.clipboard.writeText(selectedItem().decompiled.code);
        toast("코드를 복사했어요.");
      } catch { toast("복사할 수 없는 환경이에요."); }
    }
  });

  document.addEventListener("click", (e) => {
    const box = e.target.closest("[data-check]");
    if (!box) return;
    const id = box.dataset.check;
    state.checks.has(id) ? state.checks.delete(id) : state.checks.add(id);
    saveChecks();
    box.classList.toggle("on");
    box.closest("li").classList.toggle("done");
  });

  document.querySelectorAll(".nav-item").forEach((n) => n.addEventListener("click", () => {
    if (n.dataset.view === "home") return;
    toast(`'${n.textContent.trim()}' 화면은 준비 중이에요.`);
  }));
  $("#bell").addEventListener("click", () => toast("새 알림이 없어요."));
}

async function init() {
  bindEvents();
  try {
    state.examples = await (await fetch("/api/examples")).json();
  } catch { state.examples = []; }
  if (state.examples.length) {
    $("#spec").value = state.examples[0].spec;   // 첫 화면: 시안과 같은 예시로 바로 빌드
    updateCounter();
    runBuild();
  }
}

init();
