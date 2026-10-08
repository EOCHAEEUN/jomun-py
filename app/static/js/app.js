// 조문.py — 화면 동작 (SPEC 입력 → /api/build → BUILD 로그 → INSPECT)
const $ = (sel) => document.querySelector(sel);

const state = {
  result: null,
  builtSpec: "",
  answers: {},          // 되묻기 답변 {question_id: value}
  selectedKey: null,
  tab: "original",
  examples: [],
  exampleIndex: 0,
  checks: loadChecks(),
};

const STATUS_TEXT = {
  MATCH: "해당 가능성", REQUIRED: "의무", REVIEW: "검토 필요", CONDITIONAL: "조건부 의무",
  SHOULD: "노력 의무", OPPORTUNITY: "지원 가능", OUT_OF_SCOPE: "적용 제외", INFO: "참고",
};
const OBLIGATION_KO = { MUST: "하여야 한다", SHOULD: "노력하여야 한다", MAY: "할 수 있다", MUST_NOT: "하여서는 아니 된다" };
const CONDITION_KO = {
  "IF HIGH_IMPACT_AI": "고영향 AI에 해당하면",
  "IF 완전히 자동화된 결정": "완전히 자동화된 결정이면",
  "IF 적용 제외 대상이 아니면": "적용 제외 대상이 아니면",
  "IF 실제와 구분 어려운 결과물": "실제와 구분하기 어려운 결과물이면",
  "IF 정보주체가 거부·설명 요구": "정보주체가 거부·설명을 요구하면",
  "IF 정보주체 요구": "정보주체가 요구하면",
  "IF 자동화평가 · 정보주체 요구": "자동화평가에 해당하고 정보주체가 요구하면",
  "IF 민감정보 해당": "민감정보에 해당하면",
};
function conditionText(condition) { return CONDITION_KO[condition] || condition.replace(/^IF /, ""); }
function itemLabel(it) { return it.label === "HIGH_IMPACT_AI" ? "고영향 AI 해당 여부" : it.label; }
function statusText(it) {
  return it.status === "CONDITIONAL" && it.obligation === "SHOULD" ? "조건부 노력 의무" : STATUS_TEXT[it.status] || it.status;
}

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

// ── API ───────────────────────────────────────────
async function runBuild({ keepSelection = false } = {}) {
  const spec = $("#spec").value.trim();
  if (!spec) { toast("서비스 설명을 입력해 주세요."); $("#spec").focus(); return; }
  if (spec !== state.builtSpec) state.answers = {};   // 설명이 바뀌면 이전 답변은 버린다

  const btn = $("#run");
  btn.disabled = true;
  setStatus("running", "점검 중…", "");
  try {
    const res = await fetch("/api/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec, answers: state.answers }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    state.result = data;
    state.builtSpec = spec;
    if (!keepSelection || !data.items.some((i) => i.key === state.selectedKey)) {
      const firstQuestion = data.items.find((i) => i.status === "REVIEW" && i.question);
      state.selectedKey = (firstQuestion || data.items[0] || {}).key;
    }
    setAiNotice(data.mode.feature_extractor);
    const sourceNote = data.rag.mode === "chroma" ? "6종 문서 기준" : "규칙만 모드";
    setStatus("done", "점검 완료", sourceNote);
    renderAll(!keepSelection);
  } catch (err) {
    setStatus("error", "점검 실패", "");
    toast(`점검 실패: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

// 이 도구 자체의 AI 사용 고지 — 생성형 AI(LLM)를 실제로 쓸 때만 그렇게 알린다
function setAiNotice(extractor) {
  $("#ai-notice").textContent = extractor === "llm"
    ? "생성형 AI(LLM)로 서비스 설명에서 특성을 추출해요"
    : "키워드 규칙 기반 자동 분석 도구예요 (생성형 AI 미사용)";
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
  renderInspect();
  renderTodo();
}

function renderLog(animate) {
  const items = state.result?.items || [];
  $("#log").innerHTML = items.map((it, i) => {
    const cond = it.condition ? `${esc(conditionText(it.condition))}, ` : "";
    const doc = it.doc !== "AIACT" ? `${esc(it.doc_short)} · ` : "";
    return `
      <li class="log-row ${it.key === state.selectedKey ? "selected" : ""} ${it.status === "REQUIRED" || it.status === "REVIEW" ? "priority" : ""}" data-key="${esc(it.key)}"
          style="animation-delay:${animate ? i * 45 : 0}ms; ${animate ? "" : "animation:none"}">
        <span class="ref">${doc}${esc(itemLabel(it))}</span>
        <span class="desc"><span class="status-word">${esc(statusText(it))}</span><span class="sep"> — </span>${cond}${esc(it.summary)}</span>
        <svg><use href="#i-chevron"/></svg>
      </li>`;
  }).join("") || '<li class="log-empty">적용되는 항목이 없어요.</li>';
  $("#ask-link").hidden = !state.result?.pending_questions?.length;
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
  else box.innerHTML = renderImpl(it);
  box.scrollTop = 0;
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

function renderDeveloperBrief(it) {
  const condition = it.condition ? `<p class="dev-condition">적용 조건: ${esc(conditionText(it.condition))}</p>` : "";
  const actions = it.checklist || [];
  const preview = actions.length ? `
    <h4>${it.condition ? "조건이 충족되면 반영할 작업" : "제품에 반영할 작업"}</h4>
    <ol class="dev-actions">${actions.slice(0, 3).map((action) => `<li>${esc(action)}</li>`).join("")}</ol>
    <button class="dev-more" data-open-checklist>전체 작업 ${actions.length}개 보기</button>` : "";
  const prompt = it.question ? `<h4>설계에서 먼저 결정할 사항</h4>${renderQuestion(it.question)}` : "";
  if (!condition && !preview && !prompt) return "";
  return `<section class="dev-brief"><h3>개발 관점</h3>${condition}${prompt}${preview}</section>`;
}

function renderOriginal(it) {
  const r = state.result;
  const first = it.records[0];
  const details = [];
  if (first) details.push(`수범자: ${esc(first.addressee_ko)}`);
  if (it.obligation) details.push(`조문의 표현: ${esc(OBLIGATION_KO[it.obligation] || it.obligation)}`);

  const texts = it.records.map((rec) => `
    <div class="law-text ${rec.verbatim ? "" : "summary"} k-${rec.doc_kind.toLowerCase()}">
      <span class="ref"><b class="src">${esc(rec.doc_short)}</b>${rec.verbatim ? `${esc(rec.ref_label)} · ${esc(rec.title)}` : "요약 · 2차 자료 (원문 아님)"} · ${rec.source_page}쪽</span>
      ${rec.verbatim ? "" : `<strong class="sum-title">${esc(rec.summary)}</strong>`}
      ${esc(rec.text)}
      ${rec.children.length ? `<ol>${rec.children.map((c) => `<li>${esc(c.marker)} ${esc(c.text)}</li>`).join("")}</ol>` : ""}
      ${rec.en ? `<details class="en"><summary>English · ${esc(rec.en.ref)}</summary>${esc(rec.en.text)}</details>` : ""}
    </div>`).join("");

  const chain = it.chain ? `
    <p class="sub-title">근거 체인 (${it.chain.type})</p>
    <div class="chain">${it.chain.nodes.map((n, i) => `
      ${i ? '<span class="chain-arrow"></span>' : ""}
      <div class="chain-node k-${n.kind}"><span class="dot"></span><span class="r">${esc(n.ref || "")}</span><span class="l">${esc(n.label)}</span></div>`).join("")}
    </div>` : "";

  const retrieved = renderFoundBy(it, r.rag);

  return `
    <div class="art-head"><h3>${esc(itemLabel(it))}</h3><span class="art-title">${esc(it.summary)}</span></div>
    ${renderDeveloperBrief(it)}
    ${details.length ? `<p class="legal-meta">${details.join(" · ")}</p>` : ""}
    ${it.notes.length ? `<p class="sub-title">판정 이유</p><ul class="notes">${it.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    <p class="sub-title">근거 조문</p>
    ${texts || '<p class="muted">데이터 범위(6종) 밖의 항목이라 원문이 없어요.</p>'}
    ${it.externals.length ? `<p class="sub-title">하위 규정 의존</p><div class="ext-box"><b>◈ EXTERNAL</b>${it.externals.map(esc).join("<br>")}<br>→ 이번 데이터 6종만으로는 확정되지 않아요. 해당 규정 확인 필요</div>` : ""}
    <details class="technical-details"><summary>판단 과정 자세히</summary>
      ${chain}
      ${retrieved}
      <p class="sub-title">서비스 설명에서 확인한 표현</p>
      <ul class="notes">${(r.features.evidence.length ? r.features.evidence : ["근거 문구 없음"]).map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
    </details>`;
}

// 이 항목이 빌드 로그에 오른 경로: RAG 검색 → (참조 확장) → 규칙 검증 / 기본 규칙
// 출처 표시: 인공지능기본법은 조문 번호만, 다른 문서는 문서명 + 조문 번호, 해설은 '해설 · 주제'
function srcLabel(h) {
  if (h.doc_short === h.ref_label) return `<em>${esc(h.doc_short)}</em>${h.title ? ` · ${esc(h.title.split(":")[0])}` : ""}`;
  return `${h.doc_short && h.doc_short !== "인공지능기본법" ? `<em>${esc(h.doc_short)}</em> ` : ""}${esc(h.ref_label)}`;
}

function renderFoundBy(it, rag) {
  const src = srcLabel;
  const paths = [];
  if (it.baseline) paths.push('<li><span class="how base">기본 규칙</span>검색 결과와 상관없이 항상 확인하는 항목이에요.</li>');
  if (rag.mode !== "chroma") {
    paths.push('<li><span class="how off">규칙만</span>벡터 DB가 비어 있어 검색 없이 규칙만으로 판정했어요. <code>python -m scripts.ingest</code></li>');
  } else {
    it.found_by.forEach((f) => paths.push(f.how === "search"
      ? `<li title="${esc(f.title)}"><span class="how search">검색</span>${src(f)} <small>‘${esc(f.query)}’ 쿼리 · 유사도 ${f.score}</small></li>`
      : `<li title="${esc(f.title)}"><span class="how expand">참조 확장</span>${src(f)} <small>← ${esc(f.from)}에서</small></li>`));
  }
  const rejected = it.rejected.length ? `
    <p class="sub-title">검색 후보였지만 규칙이 기각한 조문</p>
    <ul class="found rejected">${it.rejected.map((x) => `<li><span class="how no">기각</span>${esc(x.label)} <small>${esc(x.reason)}</small></li>`).join("")}</ul>` : "";
  const funnel = rag.mode === "chroma" ? `
    <p class="sub-title">RAG 후보 → 규칙 검증</p>
    <p class="funnel">쿼리 ${rag.queries.length}개 · 검색 ${rag.n_hits} + 참조 확장 ${rag.n_expanded} = 후보 ${rag.n_candidates}개 → 빌드 로그 근거로 쓰인 조문 ${rag.n_used}개</p>
    <div class="retrieved">${rag.top.map((h) => `<span class="chip ${h.used ? "used" : ""}" title="‘${esc(h.query)}’ 쿼리${h.used ? " · 빌드 로그 근거로 쓰임" : " · 규칙 검증에서 쓰이지 않음"}">${srcLabel(h)}<small>${h.score}</small></span>`).join("")}</div>` : "";
  return `
    <p class="sub-title">이 항목을 찾은 경로</p>
    <ul class="found">${paths.join("") || "<li>-</li>"}</ul>
    ${rejected}${funnel}`;
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

  $("#ask-link").addEventListener("click", () => {
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
    if (e.target.closest("[data-open-checklist]")) {
      state.tab = "checklist";
      renderInspect();
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
    if (n.dataset.view === "library") { showSources(); return; }
    toast(`'${n.textContent.trim()}' 화면은 준비 중이에요.`);
  }));
  $("#bell").addEventListener("click", () => toast("새 알림이 없어요."));
}

// 법령 라이브러리 → 이번 프로젝트의 데이터 범위(6종)를 INSPECT 영역에 보여준다
async function showSources() {
  try {
    const sources = await (await fetch("/api/sources")).json();
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    $("#tab-content").innerHTML = `
      <h3>데이터 범위 · ${sources.length}종</h3>
      <p class="muted" style="margin:6px 0 12px">이 문서들 안에서만 판정해요. 범위 밖 규정은 EXTERNAL로 표시돼요.</p>
      <ul class="sources">${sources.map((s) => `
        <li><b>${esc(s.short)}</b><span class="kind k-${s.kind.toLowerCase()}">${esc(s.kind)}</span>
          <p>${esc(s.title)}</p><small>${esc(s.authority)} · 시행 ${esc(s.effective)} · ${esc(s.role)}</small></li>`).join("")}</ul>`;
  } catch { toast("데이터 목록을 불러오지 못했어요."); }
}

async function init() {
  bindEvents();
  try { setAiNotice((await (await fetch("/api/health")).json()).feature_extractor); } catch { /* 기본 문구 유지 */ }
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
