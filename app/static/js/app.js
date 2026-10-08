(() => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const icon = (name) => `<svg aria-hidden="true"><use href="#icon-${name}"/></svg>`;
  const state = { view:"home", mode:"build", query:"", result:null, selected:0, shown:4, sort:"relevance", tab:"guide", graph:null, graphLoading:null, answers:{}, attachment:"", attachmentName:"", checks:new Set(), busy:false };
  const statusName = {MATCH:"RELATED",REQUIRED:"REQUIRED",CONDITIONAL:"CONDITIONAL",REVIEW:"REVIEW",SHOULD:"REVIEW",OPPORTUNITY:"REFERENCE",INFO:"REFERENCE",OUT_OF_SCOPE:"REFERENCE"};
  const statusKo = {MATCH:"관련 영역 확인",REQUIRED:"적용 대상 (필수 검토)",CONDITIONAL:"조건부 적용",REVIEW:"추가 검토 필요",SHOULD:"권고 사항",OPPORTUNITY:"활용 가능",INFO:"참고 사항",OUT_OF_SCOPE:"적용 범위 밖"};
  const statusClass = (s) => ({REQUIRED:"required",MATCH:"review",CONDITIONAL:"conditional",REVIEW:"review",SHOULD:"review"}[s] || "reference");
  const records = (item) => Array.isArray(item?.records) ? item.records : [];
  const current = () => state.mode === "build" ? state.result?.items?.[state.selected] : state.result?.sources?.[state.selected];
  const firstRecord = (item) => records(item)[0] || null;
  const lawLabel = (item) => {
    const r = firstRecord(item);
    if (r) return r.ref_label || item.label || item.summary;
    return item.label === "HIGH_IMPACT_AI" ? "고영향 AI 해당 여부" : (item.label || item.summary || "관련 근거");
  };
  const articleName = (item) => {
    const r = firstRecord(item);
    return r?.doc_short || item.doc_short || "관련 법령";
  };
  function toast(message) {
    const t = $("#toast"); t.textContent = message; t.classList.add("show");
    clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 3600);
  }
  function renderAttachment() {
    document.querySelectorAll(".attachment-pill").forEach(el => {
      el.hidden = !state.attachment;
      el.innerHTML = state.attachment ? `${icon("clip")} ${esc(state.attachmentName)} <button type="button" data-remove-attachment>첨부 제거</button>` : "";
    });
  }
  function showView(view, id) {
    state.view = view;
    $("#home-view").hidden = view !== "home";
    $("#results-view").hidden = view !== "results";
    $("#library").hidden = view !== "library";
    if (view === "library") {
      showLibraryGraph();
      window.JomunLibrary?.open().then(() => { if (id) window.JomunLibrary?.focus(id); });
      history.replaceState(null, "", id ? `#library:${encodeURIComponent(id)}` : "#library");
    } else if (view === "home") history.replaceState(null, "", location.pathname);
    window.scrollTo({top:0,behavior:"auto"});
  }
  function decideMode(query) {
    if (/(우리|저희|회사|만들|개발|운영|제공하는|사용하는|활용하는|서비스가|해외 서비스|채용 AI가|대출 AI)/.test(query)) return "build";
    if (/(면접|채용|대출|신용|의료|추천|쇼핑|상담|평가|분석)/.test(query) && !/(무엇|뭐|왜|뜻|정의|의무|규정|조문|목적|기준)/.test(query)) return "build";
    return "ask";
  }
  async function api(path, body) {
    const res = await fetch(path, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    let data; try { data = await res.json(); } catch { data = {}; }
    if (!res.ok) { const error = new Error(typeof data.detail === "string" ? data.detail : "분석 요청을 처리하지 못했습니다.");error.status=res.status;throw error; }
    return data;
  }
  async function submit(query, preferredMode, preserve=false) {
    if (state.busy) return;
    const q = query.trim();
    if (!q) { toast("질문이나 서비스 설명을 입력해 주세요."); return; }
    const payload = q + state.attachment;
    let mode = preferredMode || decideMode(q);
    if (mode === "build" && payload.length > 500) {
      toast("서비스 점검 입력은 500자까지 가능합니다. 내용을 줄이거나 법률 질문으로 입력해 주세요."); return;
    }
    if (mode === "ask" && payload.length > 1000) { toast("법률 질문은 1000자까지 가능합니다."); return; }
    const buttons = document.querySelectorAll(".submit-button");
    state.busy=true;buttons.forEach(b => {b.disabled = true;b.classList.add("loading");b.setAttribute("aria-label","분석 중");});
    try {
      let data;
      if (mode === "build") data = await api("/api/build",{spec:payload,answers:preserve ? state.answers : {}});
      else {
        try { data = await api("/ask",{question:payload}); }
        catch (error) {
          if (error.status !== 502 && error.status !== 503) throw error;
          data = await api("/api/law-search",{question:payload});
          toast("답변 생성 연결이 없어 관련 조문 원문을 표시합니다.");
        }
        if (!data.sources?.length) {
          data = await api("/api/law-search",{question:payload});
          toast("답변 근거가 없어 관련 조문 원문을 표시합니다.");
        }
      }
      const previousKey = preserve ? current()?.key : null;
      state.query=q;state.mode=mode;state.result=data;
      state.selected=previousKey ? Math.max(0,data.items.findIndex(item=>item.key===previousKey)) : 0;
      state.shown=Math.max(4,state.selected+1);state.sort="relevance";state.tab="guide";
      if (!preserve) {state.answers={};state.checks=new Set();}
      $("#home-input").value=q;$("#result-input").value=q;
      renderResults();
      showView("results");
      if (mode === "build") ensureGraph().then(() => renderGuide()).catch(() => {});
    } catch (e) { toast(e.message || "잠시 후 다시 시도해 주세요."); }
    finally { state.busy=false;buttons.forEach(b => {b.disabled = false;b.classList.remove("loading");b.setAttribute("aria-label","분석 시작");}); }
  }
  function sortedItems() {
    const list = state.mode === "build" ? state.result.items.map((v,i) => ({v,i})) : (state.result.sources || []).map((v,i) => ({v,i}));
    if (state.sort === "status" && state.mode === "build") {
      const weight = {REQUIRED:0,MATCH:1,REVIEW:2,CONDITIONAL:3,SHOULD:4,INFO:5,OPPORTUNITY:6,OUT_OF_SCOPE:7};
      list.sort((a,b) => (weight[a.v.status] ?? 9) - (weight[b.v.status] ?? 9) || a.i-b.i);
    }
    return list;
  }
  function renderResults() {
    const items = sortedItems();
    $("#evidence-count").textContent = state.mode === "build" ? `${items.length}개의 관련 근거가 확인되었습니다.` : `${items.length}개의 답변 근거가 확인되었습니다.`;
    $("#sort-button").hidden = state.mode !== "build";
    $("#sort-button").textContent = state.sort === "relevance" ? "관련도순⌄" : "판정순⌄";
    $("#evidence-list").innerHTML = items.slice(0,state.shown).map(({v,i},n) => state.mode === "build" ? `
      <button class="evidence-card ${i===state.selected?"selected":""}" type="button" data-evidence="${i}" aria-pressed="${i===state.selected}">
        <span class="card-index">${n+1}</span><span class="card-content"><span class="card-top"><span>${esc(articleName(v))}</span><span class="status-badge status-${statusClass(v.status)}">${statusName[v.status] || "REFERENCE"}</span></span><h3>${esc(lawLabel(v))}</h3><p>${esc(firstRecord(v)?.summary || v.summary)}</p></span><span class="card-arrow">${icon("chevron")}</span>
      </button>` : `
      <button class="evidence-card ${i===state.selected?"selected":""}" type="button" data-evidence="${i}" aria-pressed="${i===state.selected}">
        <span class="card-index">${n+1}</span><span class="card-content"><span class="card-top"><span>${esc(v.document || "근거 문서")}</span><span class="status-badge status-reference">SOURCE</span></span><h3>${esc(v.article || v.source_id || "관련 조문")}</h3><p>${esc(v.content)}</p></span><span class="card-arrow">${icon("chevron")}</span>
      </button>`).join("") || '<div class="empty-state">관련 근거가 없습니다.</div>';
    $("#more-button").hidden = items.length <= state.shown;
    renderGuide();
  }
  function renderGuide() {
    const guide = $("#guide-content"), graph = $("#graph-content");
    guide.hidden = state.tab !== "guide"; graph.hidden = state.tab !== "graph";
    document.querySelectorAll("[data-guide-tab]").forEach(b => {const active=b.dataset.guideTab===state.tab;b.classList.toggle("active",active);b.setAttribute("aria-selected",String(active));});
    if (state.tab === "graph") {renderGraphTab();return;}
    const item = current();
    if (!item) { guide.innerHTML = '<div class="empty-state"><h3>근거를 찾지 못했습니다</h3><p>다른 질문으로 다시 점검해 주세요.</p></div>'; return; }
    if (state.mode === "ask") { renderAnswer(item); return; }
    const rec = firstRecord(item);
    const related = records(item).slice(0,4);
    const note = (item.notes || []).filter(Boolean);
    const checklist = [...(item.checklist || [])];
    const todo = (state.result.todo || []).filter(t => t.key === item.key);
    for (const t of todo) if (!checklist.some(x => x.includes(t.title))) checklist.push(`${t.title} — ${t.desc}`);
    const info = note.length ? note.join(" ") : item.summary;
    const key = `${state.query}:${item.key}`;
    guide.innerHTML = `
      <div class="guide-card">
        <div class="guide-law-head">${icon("doc")}<div><p class="law-source">${esc(articleName(item))}</p><h3>${esc(lawLabel(item))}</h3><p>${esc(rec?.summary || item.summary)}</p></div><div class="guide-law-actions"><span class="status-badge status-${statusClass(item.status)}">${statusName[item.status] || "REFERENCE"}</span>${rec?.id ? `<button class="outline-button" type="button" data-open-law="${esc(rec.id)}">${icon("link")}조문 원문 보기</button>` : ""}</div></div>
        <div class="guide-block"><h4>${icon("doc")}판정 상태</h4><div class="status-alert ${statusClass(item.status)}"><span>!</span><div><b>${esc(statusKo[item.status] || "관련 근거")}</b><p>${esc(item.summary || rec?.summary || "")}</p></div></div></div>
        <div class="guide-block"><h4>${icon("info")}적용 이유</h4><p>${esc(info)}</p></div>
        <div class="guide-bottom"><div class="mini-panel"><h4>${icon("check")}개발 체크리스트</h4><ul class="checklist">${checklist.length ? checklist.map((c,i) => {const checked=state.checks.has(`${key}:${i}`);return `<li><input type="checkbox" id="check-${i}" data-check="${i}" ${checked?"checked":""}><label for="check-${i}">${esc(c)}</label></li>`}).join("") : '<li>이 항목에 지정된 추가 작업이 없습니다.</li>'}</ul></div><div class="mini-panel"><h4>${icon("network")}근거 체인</h4><ol class="chain-list">${related.map((r,i) => `<li><span class="chain-number">${i+1}</span><button type="button" data-open-law="${esc(r.id)}">${esc(r.ref_label || r.title)}<small>${esc(r.summary || r.title)}</small></button></li>`).join("") || '<li>연결된 세부 조문이 없습니다.</li>'}</ol></div></div>
        ${item.question?.options?.length ? `<div class="guide-block followup"><h4>${icon("info")}추가 확인이 필요해요</h4><p>${esc(item.question.text)}</p><div class="answer-options">${item.question.options.map(o=>`<button type="button" data-answer-id="${esc(item.question.id)}" data-answer="${esc(o.value)}" ${item.question.answer===o.value?"class='active'":""}>${esc(o.label)}</button>`).join("")}</div></div>` : ""}
        <details class="source-details"><summary>조문 내용 펼쳐 보기</summary><p>${esc(rec?.text || "표시할 조문 원문이 없습니다.")}</p></details>
      </div>${renderGraphPreview(item)}`;
  }
  function renderAnswer(source) {
    const all = state.result.sources || [];
    $("#guide-content").innerHTML = `<div class="guide-card"><div class="guide-law-head">${icon("doc")}<div><p class="law-source">${esc(source.document)}</p><h3>${esc(source.article || "법령 답변")}</h3><p>${esc(source.content?.slice(0,130))}</p></div></div><div class="guide-block"><h4>${icon("info")}법률 질문 답변</h4><div class="answer-block">${esc(state.result.answer)}</div></div><div class="guide-block"><h4>${icon("doc")}근거 원문</h4><p>${esc(source.content)}</p></div><div class="guide-bottom"><div class="mini-panel"><h4>인용 출처</h4>${all.map((s,i)=>`<div class="source-row"><span class="chain-number">${i+1}</span><button type="button" data-evidence="${i}">${esc(s.document)} · ${esc(s.article)}</button></div>`).join("")}</div></div></div>`;
  }
  async function ensureGraph() {
    if (state.graph) return state.graph;
    if (!state.graphLoading) state.graphLoading = fetch("/api/graph").then(r => {if (!r.ok) throw Error("관계도를 불러오지 못했습니다.");return r.json();}).then(data => {state.graph=data;return data;}).finally(()=>state.graphLoading=null);
    return state.graphLoading;
  }
  function graphSelection(item) {
    const graph = state.graph;
    const primary = firstRecord(item);
    if (!graph || !primary) return null;
    const byId = new Map(graph.nodes.map(node => [node.id, node]));
    const root = byId.get(primary.id);
    if (!root) return null;
    const relevant = new Set(records(item).map(record => record.id));
    const neighbors = graph.edges
      .filter(edge => edge.source === root.id || edge.target === root.id)
      .map(edge => ({
        node: byId.get(edge.source === root.id ? edge.target : edge.source),
        type: edge.type,
      }))
      .filter(entry => entry.node)
      .sort((a, b) =>
        Number(relevant.has(b.node.id)) - Number(relevant.has(a.node.id)) ||
        Number(b.node.kind === "provision") - Number(a.node.kind === "provision") ||
        a.node.id.localeCompare(b.node.id)
      );
    const seen = new Set(neighbors.map(entry => entry.node.id));
    for (const record of records(item).slice(1)) {
      const node = byId.get(record.id);
      if (node && !seen.has(node.id)) {
        neighbors.push({node, type:"REFERS"});
        seen.add(node.id);
      }
    }
    return {root, neighbors:neighbors.slice(0, 8)};
  }
  function renderGraphPreview(item, expanded = false) {
    if (!state.graph) return "";
    const g = graphSelection(item);
    if (!g) return "";
    const entries = g.neighbors.slice(0, expanded ? 8 : 6);
    const height = expanded ? 450 : 370;
    const rowGap = expanded ? 100 : 112;
    const rowStart = expanded ? 23 : 25;
    const rootY = Math.round(height / 2);
    const shorten = (value, max) => {const text = String(value || "").trim();return text.length > max ? text.slice(0,max - 1) + "…" : text;};
    const wrap = (value, max = 15) => {
      let text = String(value || "").trim().replace(/\s+/g, " ");
      const lines = [];
      while (text && lines.length < 2) {
        if (text.length <= max) { lines.push(text); text = ""; break; }
        const space = text.lastIndexOf(" ", max);
        const cut = space >= max - 4 ? space : max;
        lines.push(text.slice(0, cut).trim());
        text = text.slice(cut).trim();
      }
      if (text && lines.length === 2) lines[1] = lines[1].slice(0, max - 1) + "…";
      return lines;
    };
    const rootLabel = g.root.label || g.root.title || "선택한 조문";
    const rootDetail = g.root.summary || g.root.doc_short || "";
    const cards = entries.map((entry, index) => {
      const left = index % 2 === 0;
      const x = left ? 26 : 596;
      const y = rowStart + Math.floor(index / 2) * rowGap;
      const label = shorten(entry.node.label || entry.node.title, 11);
      const detail = wrap(entry.node.summary || entry.node.doc_short || entry.node.kind);
      const line = left
        ? `M 244 ${y + 42} C 290 ${y + 42}, 300 ${rootY}, 315 ${rootY}`
        : `M 505 ${rootY} C 540 ${rootY}, 556 ${y + 42}, 596 ${y + 42}`;
      return `<path d="${line}" fill="none" stroke="#b8cee7" stroke-width="1.6"/>
        <g class="graph-node" data-preview-node="${esc(entry.node.id)}" role="button" tabindex="0" aria-label="${esc(entry.node.doc_short || "관련 항목")} ${esc(entry.node.label || entry.node.title)}">
          <rect x="${x}" y="${y}" width="218" height="84" rx="12" fill="#fff" stroke="#dfe9f3"/>
          <circle cx="${x + 21}" cy="${y + 24}" r="7" fill="#7da7d6"/>
          <text x="${x + 37}" y="${y + 29}" fill="#213f64" font-size="15" font-weight="600">${esc(label)}</text>
          <text x="${x + 16}" y="${y + 53}" fill="#59738f" font-size="12.5">${esc(detail[0] || "")}</text>
          <text x="${x + 16}" y="${y + 70}" fill="#59738f" font-size="12.5">${esc(detail[1] || "")}</text>
        </g>`;
    }).join("");
    const rootLines = wrap(rootDetail, 14);
    const root = `<g class="graph-node" data-preview-node="${esc(g.root.id)}" role="button" tabindex="0" aria-label="${esc(g.root.doc_short || "선택한 조문")} ${esc(rootLabel)}">
      <rect x="315" y="${rootY - 55}" width="190" height="110" rx="15" fill="#eef5fd" stroke="#9bbde2" stroke-width="1.5"/>
      <text x="410" y="${rootY - 24}" text-anchor="middle" fill="#4a77a9" font-size="11.5" font-weight="600">${esc(shorten(g.root.doc_short, 15))}</text>
      <text x="410" y="${rootY + 1}" text-anchor="middle" fill="#17375d" font-size="17" font-weight="700">${esc(shorten(rootLabel, 11))}</text>
      <text x="410" y="${rootY + 25}" text-anchor="middle" fill="#4d6b8c" font-size="11.5">${esc(rootLines[0] || "")}</text>
      <text x="410" y="${rootY + 41}" text-anchor="middle" fill="#4d6b8c" font-size="11.5">${esc(rootLines[1] || "")}</text>
    </g>`;
    return `<section class="graph-preview ${expanded ? "expanded" : ""}" aria-label="관련 법령 관계도 미리보기">
      <div class="graph-preview-head">
        <div class="graph-preview-heading"><h4>관련 법령 관계도 미리보기</h4><p>선택한 조문과 직접 연결된 근거 ${entries.length}개</p></div>
        <div class="graph-preview-actions"><span class="graph-preview-mark" aria-hidden="true">${icon("network")}</span><button class="graph-preview-open" type="button" data-library="${esc(g.root.id)}">전체 화면으로 보기 ${icon("link")}</button></div>
      </div>
      <div class="graph-preview-stage"><svg class="graph-preview-canvas" viewBox="0 0 820 ${height}" role="img" aria-label="${esc(rootLabel)} 및 연결 근거 ${entries.length}개">${cards}${root}</svg></div>
      <p class="graph-preview-hint">조문을 선택하면 전체 관계도에서 연결 근거를 볼 수 있습니다.</p>
    </section>`;
  }
  function renderGraphTab() {
    const item=current();
    if (state.mode !== "build") {$("#graph-content").innerHTML='<div class="empty-state">서비스 점검 결과에서 관계도를 볼 수 있습니다.</div>';return;}
    if (!state.graph) {$("#graph-content").innerHTML='<div class="graph-card"><div class="empty-state">관계도를 불러오는 중입니다.</div></div>';ensureGraph().then(renderGraphTab).catch(e=>{$("#graph-content").innerHTML=`<div class="empty-state">${esc(e.message)}</div>`});return;}
    const preview=renderGraphPreview(item,true);
    $("#graph-content").innerHTML=preview || '<div class="empty-state">이 조문에 연결된 관계가 없습니다.</div>';
  }
  function renderArticleList(q="") {
    if (!state.graph) return;
    const n=q.trim().toLowerCase().replace(/\s/g,"");
    const rows=state.graph.nodes.filter(x=>x.kind==="provision"&&(!n||[x.label,x.title,x.summary,x.text,x.doc_short].some(v=>String(v||"").toLowerCase().replace(/\s/g,"").includes(n)))).slice(0,80);
    $("#article-list").innerHTML=rows.map(x=>`<div class="article-row"><div><b>${esc(x.doc_short)} ${esc(x.label)}</b><p>${esc(x.summary||x.title)}</p></div><button type="button" data-open-law="${esc(x.id)}">관계도 보기 →</button></div>`).join("") || '<div class="empty-state">찾는 조문이 없습니다.</div>';
  }
  async function showLibraryList() {
    $("#library-list-tab").classList.add("active");$("#library-graph-tab").classList.remove("active");
    $("#library-graph-view").hidden=true;$("#library-list-view").hidden=false;
    $("#library-list-view").innerHTML='<input id="article-search" class="article-search" type="search" placeholder="법령명, 조문, 키워드 검색"><div id="article-list"></div>';
    try {await ensureGraph();renderArticleList();} catch(e) {$("#article-list").innerHTML=`<div class="empty-state">${esc(e.message)}</div>`;}
  }
  function showLibraryGraph() {
    $("#library-list-tab").classList.remove("active");$("#library-graph-tab").classList.add("active");
    $("#library-graph-view").hidden=false;$("#library-list-view").hidden=true;
    window.JomunLibrary?.open();
  }
  function bind() {
    $("#go-home").addEventListener("click",()=>showView("home"));
    $("#bell").addEventListener("click",()=>toast("새 알림이 없습니다."));
    $("#profile").addEventListener("click",()=>toast("조문.py · AI Legal Build Checker"));
    $("#home-form").addEventListener("submit",e=>{e.preventDefault();submit($("#home-input").value);});
    $("#result-form").addEventListener("submit",e=>{e.preventDefault();submit($("#result-input").value);});
    document.querySelectorAll("[data-suggestion]").forEach(b=>b.addEventListener("click",()=>{ $("#home-input").value=b.dataset.suggestion;submit(b.dataset.suggestion,b.dataset.mode); }));
    document.querySelectorAll("[data-attach]").forEach(b=>b.addEventListener("click",()=>$("#text-file").click()));
    $("#text-file").addEventListener("change",async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>1000){toast("현재 텍스트 첨부는 450자 이내만 지원합니다.");return;}const content=await file.text();if(content.length>450){toast("현재 텍스트 첨부는 450자 이내만 지원합니다.");return;}state.attachment=`\n첨부 파일 ${file.name}: ${content}`;state.attachmentName=file.name;renderAttachment();toast(`${file.name} 내용을 입력에 추가했습니다.`);});
    document.addEventListener("click",e=>{if(!e.target.closest("[data-remove-attachment]"))return;state.attachment="";state.attachmentName="";$("#text-file").value="";renderAttachment();});
    $("#evidence-list").addEventListener("click",e=>{const b=e.target.closest("[data-evidence]");if(!b)return;state.selected=Number(b.dataset.evidence);renderResults();});
    $("#sort-button").addEventListener("click",()=>{state.sort=state.sort==="relevance"?"status":"relevance";renderResults();});
    $("#more-button").addEventListener("click",()=>{state.shown+=4;renderResults();});
    document.querySelectorAll("[data-guide-tab]").forEach(b=>b.addEventListener("click",()=>{state.tab=b.dataset.guideTab;renderGuide();}));
    $("#guide-content").addEventListener("click",guideClick);$("#graph-content").addEventListener("click",guideClick);
    [$("#guide-content"), $("#graph-content")].forEach(container => container.addEventListener("keydown", e => {
      if ((e.key !== "Enter" && e.key !== " ") || !e.target.matches("[data-preview-node]")) return;
      e.preventDefault();
      showView("library", e.target.dataset.previewNode);
    }));
    $("#guide-content").addEventListener("change",e=>{const c=e.target.closest("[data-check]");if(!c)return;const key=`${state.query}:${current().key}:${c.dataset.check}`;c.checked?state.checks.add(key):state.checks.delete(key);});
    $("#library-list-tab").addEventListener("click",showLibraryList);
    $("#library-graph-tab").addEventListener("click",showLibraryGraph);
    $("#library-list-view").addEventListener("input",e=>{if(e.target.id==="article-search")renderArticleList(e.target.value);});
    $("#library-list-view").addEventListener("click",e=>{const b=e.target.closest("[data-open-law]");if(b){showLibraryGraph();window.JomunLibrary?.open().then(()=>window.JomunLibrary?.focus(b.dataset.openLaw));}});
  }
  function guideClick(e) {
    const evidence=e.target.closest("[data-evidence]");if(evidence){state.selected=Number(evidence.dataset.evidence);renderResults();return;}
    const law=e.target.closest("[data-open-law],[data-library],[data-preview-node]");if(law){showView("library",law.dataset.openLaw||law.dataset.library||law.dataset.previewNode);return;}
    const answer=e.target.closest("[data-answer-id]");if(answer){state.answers[answer.dataset.answerId]=answer.dataset.answer;submit(state.query,"build",true);}
  }
  bind();
  if (location.hash.startsWith("#library")) {
    const id=decodeURIComponent(location.hash.split(":").slice(1).join(":"));showView("library",id||null);
  }
})();
