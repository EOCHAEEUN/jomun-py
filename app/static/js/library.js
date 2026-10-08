// library.js — 법령 라이브러리: 태깅 레코드로 만든 조문 관계도 (/api/graph → d3-force)
//
// 화면: 왼쪽 필터(문서 · 예시 경로 · 조문 찾기 · 관계 종류) │ 가운데 관계도 │ 오른쪽 조문 상세
// 레이아웃은 처음 한 번만 계산한다. 필터는 숨기기만 해서 노드 위치(머릿속 지도)가 바뀌지 않는다.
(function () {
  const DOC_COLOR = { AIACT: "#2c4fc9", DECREE: "#13897a", BKL: "#c07a1c", PIPA: "#b0457a", CREDIT: "#2f6a8f" };
  const DOC_PREFIX = { DECREE: "시행령 ", PIPA: "개인정보 ", CREDIT: "신용정보 " };
  const ENTITY = {
    actor: { color: "#3a3f48", name: "수범자" },
    condition: { color: "#d9822b", name: "적용 조건" },
    delegation: { color: "#7655ee", name: "위임·고시" },
    term: { color: "#6c7482", name: "정의 용어" },
    extlaw: { color: "#9aa1ab", name: "외부 법률" },
  };
  // out: 선택한 노드가 출발점일 때의 이름, in: 도착점일 때의 이름
  const EDGE = {
    IMPLEMENTS: { name: "시행령 구체화", color: "#13897a", on: true, out: "구체화하는 법 조문", in: "구체화한 시행령" },
    SANCTION: { name: "제재 경로", color: "#e04a3c", on: true, out: "제재 경로 (다음 단계)", in: "이 단계로 이어지는 조문" },
    EXPLAINS: { name: "해설", color: "#c07a1c", dash: "5 3", on: true, out: "해설 대상 조문", in: "해설 요약" },
    REFERS: { name: "참조", color: "#8f98a5", on: true, out: "이 조문이 참조", in: "이 조문을 참조" },
    PART_OF: { name: "상위·하위 조문", color: "#c6ccd4", on: true, out: "상위 조문", in: "하위 조문" },
    REQUIRES: { name: "적용 조건", color: "#d9822b", dash: "2 3", on: true, out: "적용 조건", in: "이 조건이 붙은 조문" },
    DELEGATES: { name: "위임·고시", color: "#7655ee", dash: "5 3", on: true, out: "위임", in: "위임한 조문" },
    APPLIES_TO: { name: "수범자", color: "#5a6270", dash: "2 3", on: false, out: "수범자", in: "이 수범자의 의무" },
    CITES: { name: "외부 법률 인용", color: "#a3a9b3", dash: "1.5 3", on: false, out: "인용한 외부 법률", in: "인용한 조문" },
    DEFINES: { name: "용어 정의", color: "#6c7482", on: false, out: "정의한 용어", in: "정의한 조문" },
    USES_TERM: { name: "용어 사용", color: "#c3c8cf", dash: "1.5 3", on: false, out: "쓰는 정의 용어", in: "이 용어를 쓰는 조문" },
  };
  const WEAK = ["USES_TERM", "APPLIES_TO"];   // 허브로 몰리는 관계 — 배치와 노드 크기에는 거의 반영하지 않는다
  const PRESETS = [
    { id: "ARTICLE_2_4", name: "고영향 AI 판단", sub: "제2조제4호 · 가~카목 · 해설" },
    { id: "ARTICLE_34_1", name: "고영향 사업자 책무", sub: "제34조① · 시행령 제27조" },
    { id: "ARTICLE_31_1", name: "AI 사용 사전 고지", sub: "제31조① · 시행령 제23조 · 과태료" },
    { id: "ARTICLE_36_1", name: "국내대리인", sub: "제36조① · 시행령 제29조" },
    { id: "ARTICLE_43_1", name: "과태료", sub: "제43조 · 제재 경로" },
    { id: "PIPA_37-2_1", name: "자동화된 결정", sub: "개인정보 보호법 제37조의2" },
  ];
  const ANCHOR = { AIACT: [0, 0], DECREE: [430, 10], BKL: [-380, -150], PIPA: [-360, 260], CREDIT: [-80, 330] };
  const OBLIGATION = { MUST: ["의무", "must"], MUST_NOT: ["금지", "must"], SHOULD: ["노력 의무", "should"], MAY: ["할 수 있음", "may"] };

  const S = {
    data: null, nodes: [], edges: [], byId: new Map(), adj: new Map(), vis: new Set(),
    docOn: new Set(), edgeOn: new Set(), selected: null, preset: null, loading: null, ready: false,
  };
  let svg, view, zoom, edgeSel, nodeSel;

  const el = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isProv = (id) => S.byId.get(id)?.kind === "provision";
  const color = (n) => (n.kind === "provision" ? DOC_COLOR[n.doc] || "#6c7482" : ENTITY[n.kind].color);
  const radius = (n) => 4 + Math.min(8, Math.sqrt(n.deg) * 1.7);

  function shortLabel(n) {
    if (n.kind !== "provision") return n.label;
    if (n.doc === "BKL") return `해설 · ${(n.summary || "").split(":")[0]}`;
    return (DOC_PREFIX[n.doc] || "") + n.label;
  }

  // ── 데이터 ─────────────────────────────────────
  async function open() {
    if (S.ready) return;
    if (!S.loading) S.loading = load();
    await S.loading;
  }

  async function load() {
    if (!window.d3) {
      el("lib-detail").innerHTML = `<p class="muted">관계도를 그리는 라이브러리를 불러오지 못했어요.</p>`;
      return;
    }
    try {
      S.data = await (await fetch("/api/graph")).json();
    } catch {
      el("lib-detail").innerHTML = `<p class="muted">관계도를 불러오지 못했어요. 잠시 후 다시 열어 주세요.</p>`;
      S.loading = null;
      return;
    }
    S.nodes = S.data.nodes.map((n) => ({ ...n, short: shortLabel(n) }));
    S.byId = new Map(S.nodes.map((n) => [n.id, n]));
    S.edges = S.data.edges.map((e) => ({ ...e, s: e.source, t: e.target }));
    for (const e of S.edges) {
      for (const [a, b, dir] of [[e.s, e.t, "out"], [e.t, e.s, "in"]]) {
        if (!S.adj.has(a)) S.adj.set(a, []);
        S.adj.get(a).push({ edge: e, other: b, dir });
      }
    }
    for (const n of S.nodes) n.deg = (S.adj.get(n.id) || []).filter((x) => !WEAK.includes(x.edge.type)).length;
    S.data.docs.filter((d) => d.count).forEach((d) => S.docOn.add(d.id));
    Object.entries(EDGE).forEach(([k, v]) => v.on && S.edgeOn.add(k));

    renderStats();
    renderSide();
    layout();
    draw();
    applyFilter();
    S.ready = true;
    fitAll(false);
    if (S.pending) focus(S.pending);
  }

  const fitAll = (animate = true) => fit(S.nodes.filter((n) => S.vis.has(n.id)), animate, 0.03);

  // ── 배치 (한 번만 계산) ─────────────────────────
  // 조문은 문서별 자리(법률 가운데 · 시행령 오른쪽 · 해설 왼쪽)로, 연결 노드는 이어진 조문들의 가운데로 끈다
  function anchor(n) {
    if (n.kind === "provision") return ANCHOR[n.doc] || [0, 0];
    if (!n.anchor) {
      const docs = (S.adj.get(n.id) || []).map((x) => S.byId.get(x.other)).filter((o) => o?.kind === "provision");
      n.anchor = docs.length ? [d3.mean(docs, (o) => ANCHOR[o.doc][0]), d3.mean(docs, (o) => ANCHOR[o.doc][1])] : [0, 0];
    }
    return n.anchor;
  }

  function layout() {
    const strength = { PART_OF: 0.8, CITES: 0.6, DEFINES: 0.4, EXPLAINS: 0.35, SANCTION: 0.3, IMPLEMENTS: 0.2,
      REFERS: 0.18, REQUIRES: 0.12, DELEGATES: 0.08, APPLIES_TO: 0.005, USES_TERM: 0.002 };
    const dist = { PART_OF: 22, CITES: 30, DEFINES: 38 };
    S.nodes.forEach((n, i) => {             // 시작 위치를 고정해 매번 같은 그림이 나오게
      const [ax, ay] = anchor(n), ang = i * 2.399963, r = 10 + (i % 29) * 5;
      n.x = ax + Math.cos(ang) * r;
      n.y = ay + Math.sin(ang) * r;
      n.cr = n.kind === "provision" ? radius(n) + 5 : Math.min(42, n.label.length * 5 + 12);
    });
    const links = S.edges.map((e) => ({ source: e.s, target: e.t, type: e.type }));
    const sim = d3.forceSimulation(S.nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance((l) => dist[l.type] || 52).strength((l) => strength[l.type] ?? 0.1))
      .force("charge", d3.forceManyBody().strength((d) => (d.kind === "provision" ? -40 - d.deg * 5 : -110)).distanceMax(260))
      .force("collide", d3.forceCollide((d) => d.cr).strength(0.9))
      .force("x", d3.forceX((d) => anchor(d)[0]).strength((d) => (d.kind === "provision" ? 0.1 : 0.05)))
      .force("y", d3.forceY((d) => anchor(d)[1]).strength((d) => (d.kind === "provision" ? 0.1 : 0.05)))
      .stop();
    for (let i = 0; i < 500; i++) sim.tick();
  }

  // ── 그리기 ─────────────────────────────────────
  function draw() {
    svg = d3.select("#lib-graph");
    svg.selectAll("*").remove();
    const defs = svg.append("defs");
    for (const [k, v] of Object.entries(EDGE)) {
      defs.append("marker").attr("id", `lib-arr-${k}`).attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5)
        .attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto")
        .append("path").attr("d", "M0,1.5 L9,5 L0,8.5 z").attr("fill", v.color);
    }
    view = svg.append("g");
    const edgeLayer = view.append("g");
    nodeSel = view.append("g").selectAll("g").data(S.nodes).join("g")
      .attr("class", (n) => ["n", n.kind === "provision" ? "" : "ent", n.deg >= 7 ? "major" : ""].join(" "))
      .attr("transform", (n) => `translate(${n.x},${n.y})`)
      .on("click", (ev, n) => { ev.stopPropagation(); setPreset(null); focus(n.id, false); });
    nodeSel.append("title").text((n) => (n.kind === "provision" ? `${n.doc_short} ${n.label} — ${n.summary || n.title}` : n.label));

    const prov = nodeSel.filter((n) => n.kind === "provision");
    prov.append("circle").attr("r", radius).attr("fill", color);
    prov.append("text").attr("class", "lbl").attr("x", (n) => radius(n) + 4).attr("y", 4).text((n) => n.short);

    const ent = nodeSel.filter((n) => n.kind !== "provision");
    ent.append("rect");
    ent.append("text").attr("class", "lbl").attr("text-anchor", "middle").attr("y", 4).attr("fill", color).text((n) => n.label);
    ent.each(function (n) {
      const w = this.querySelector("text").getComputedTextLength() + 16;
      n.hw = w / 2;
      n.hh = 11;
      d3.select(this).select("rect").attr("x", -n.hw).attr("y", -n.hh).attr("width", w).attr("height", n.hh * 2)
        .attr("rx", n.hh).attr("stroke", color(n));
    });

    edgeSel = edgeLayer.selectAll("line").data(S.edges).join("line")
      .attr("class", "e").attr("stroke", (e) => EDGE[e.type].color)
      .attr("stroke-dasharray", (e) => EDGE[e.type].dash || null)
      .attr("marker-end", (e) => `url(#lib-arr-${e.type})`)
      .each(function (e) { placeEdge(this, e); });

    zoom = d3.zoom().scaleExtent([0.25, 4]).on("zoom", (ev) => {
      view.attr("transform", ev.transform);
      svg.classed("zoomed", ev.transform.k >= 1.3);
    });
    svg.call(zoom).on("dblclick.zoom", null).on("click", () => select(null));
  }

  function placeEdge(line, e) {
    const a = S.byId.get(e.s), b = S.byId.get(e.t);
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
    const cut = (n) => (n.kind === "provision" ? radius(n) + 2
      : Math.min(n.hw / (Math.abs(dx / len) || 1e-6), n.hh / (Math.abs(dy / len) || 1e-6)) + 2);
    const ca = Math.min(cut(a), len / 2), cb = Math.min(cut(b), len / 2);
    line.setAttribute("x1", a.x + (dx / len) * ca);
    line.setAttribute("y1", a.y + (dy / len) * ca);
    line.setAttribute("x2", b.x - (dx / len) * cb);
    line.setAttribute("y2", b.y - (dy / len) * cb);
  }

  // ── 필터 · 선택 ─────────────────────────────────
  function applyFilter() {
    const vis = new Set(S.nodes.filter((n) => n.kind === "provision" && S.docOn.has(n.doc)).map((n) => n.id));
    for (const e of S.edges) {
      if (!S.edgeOn.has(e.type)) continue;
      if ((isProv(e.s) ? vis.has(e.s) : true) && (isProv(e.t) ? vis.has(e.t) : true)) {
        if (!isProv(e.s)) vis.add(e.s);
        if (!isProv(e.t)) vis.add(e.t);
      }
    }
    S.vis = vis;
    edgeSel.style("display", (e) => (edgeVisible(e) ? null : "none"));
    nodeSel.style("display", (n) => (vis.has(n.id) ? null : "none"));
    select(S.selected && vis.has(S.selected) ? S.selected : null);
  }

  const edgeVisible = (e) => S.edgeOn.has(e.type) && S.vis.has(e.s) && S.vis.has(e.t);

  function neighbors(id) {
    return new Set((S.adj.get(id) || []).filter((x) => edgeVisible(x.edge)).map((x) => x.other));
  }

  function select(id) {
    S.selected = id && S.byId.has(id) ? id : null;
    const nb = S.selected ? neighbors(S.selected) : new Set();
    nodeSel.classed("sel", (n) => n.id === S.selected)
      .classed("nb", (n) => nb.has(n.id))
      .classed("dim", (n) => !!S.selected && n.id !== S.selected && !nb.has(n.id));
    edgeSel.classed("hot", (e) => !!S.selected && (e.s === S.selected || e.t === S.selected))
      .classed("dim", (e) => !!S.selected && e.s !== S.selected && e.t !== S.selected);
    if (!S.selected) setPreset(null);
    renderDetail();
  }

  function focus(id, zoomTo = true) {
    const n = S.byId.get(id);
    if (!n) return;
    if (!S.vis.has(id)) {                    // 숨겨 둔 문서의 조문이면 그 문서를 다시 켠다
      if (n.kind === "provision") S.docOn.add(n.doc);
      renderSide();
      applyFilter();
    }
    select(id);
    if (zoomTo) fit([n, ...[...neighbors(id)].map((x) => S.byId.get(x))]);
  }

  // trim: 전체 보기에서는 양 끝 몇 %의 동떨어진 점을 빼고 맞춘다 (화면이 너무 작아지지 않게)
  function fit(list, animate = true, trim = 0) {
    const pts = list.filter(Boolean);
    const box = el("lib-graph").getBoundingClientRect();
    if (!pts.length || !box.width) return;
    const xs = pts.map((n) => n.x).sort(d3.ascending), ys = pts.map((n) => n.y).sort(d3.ascending);
    const [x0, x1] = [d3.quantileSorted(xs, trim), d3.quantileSorted(xs, 1 - trim)];
    const [y0, y1] = [d3.quantileSorted(ys, trim), d3.quantileSorted(ys, 1 - trim)];
    const w = Math.max(x1 - x0, 120) + 180, h = Math.max(y1 - y0, 120) + 80;   // 오른쪽 라벨 자리까지
    const k = Math.min(2.2, Math.min(box.width / w, box.height / h));
    const t = d3.zoomIdentity.translate(box.width / 2 - k * (x0 + x1 + 90) / 2, box.height / 2 - k * (y0 + y1) / 2).scale(k);
    (animate ? svg.transition().duration(450) : svg).call(zoom.transform, t);
  }

  // ── 왼쪽 패널 ───────────────────────────────────
  function renderStats() {
    const st = S.data.stats, docs = S.data.docs.filter((d) => d.count).length;
    el("lib-stats").innerHTML = `<span>조문<b>${st.provisions}</b></span><span>관계<b>${st.edges}</b></span><span>문서<b>${docs}종</b></span>`;
  }

  function lineSample(type) {
    const v = EDGE[type];
    return `<svg class="lib-sw" viewBox="0 0 24 8" aria-hidden="true"><line x1="0" y1="4" x2="24" y2="4" stroke="${v.color}" stroke-width="2"${v.dash ? ` stroke-dasharray="${v.dash}"` : ""}/></svg>`;
  }

  function renderSide() {
    const byType = S.data.stats.by_type;
    const docs = S.data.docs.filter((d) => d.count);
    const presets = PRESETS.filter((p) => S.byId.has(p.id));
    el("lib-side").innerHTML = `
      <section>
        <h3>문서</h3>
        ${docs.map((d) => `
          <label class="lib-toggle"><input type="checkbox" data-doc="${d.id}" ${S.docOn.has(d.id) ? "checked" : ""}>
            <span><i class="lib-dot" style="background:${DOC_COLOR[d.id] || "#6c7482"}"></i>${esc(d.short)}</span><span class="n">${d.count}</span></label>`).join("")}
        <p class="lib-hint">영문본은 원문 병기용이라 관계도에서 뺐어요.</p>
      </section>
      <section>
        <h3>자주 찾는 조문</h3>
        <div class="lib-presets">${presets.map((p) => `
          <button type="button" data-preset="${p.id}" aria-pressed="${S.preset === p.id}"><b>${esc(p.name)}</b><small>${esc(p.sub)}</small></button>`).join("")}
        </div>
      </section>
      <section class="lib-search">
        <h3><label for="lib-q">법령 및 조문 찾기</label></h3>
        <input id="lib-q" type="search" placeholder="법령명, 조문명, 키워드를 검색하세요." autocomplete="off">
        <ul class="lib-results" id="lib-results"></ul>
      </section>
      <section>
        <h3>관계</h3>
        ${Object.entries(EDGE).map(([k, v]) => `
          <label class="lib-toggle"><input type="checkbox" data-edge="${k}" ${S.edgeOn.has(k) ? "checked" : ""}>
            <span>${lineSample(k)}${esc(v.name)}</span><span class="n">${byType[k] || 0}</span></label>`).join("")}
      </section>
      <section>
        <h3>연결 노드</h3>
        <div class="lib-legend">${Object.values(ENTITY).map((v) => `<span><i class="lib-pill" style="border-color:${v.color}"></i>${v.name}</span>`).join("")}</div>
      </section>`;
  }

  function setPreset(id) {
    S.preset = id;
    document.querySelectorAll("[data-preset]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.preset === id)));
  }

  function searchNodes(q) {
    const norm = (s) => String(s ?? "").toLowerCase().replace(/\s+/g, "");
    const key = norm(q);
    if (!key) return [];
    const hits = S.nodes.filter((n) => [n.short, n.label, n.title, n.summary, n.text, n.doc_short].some((v) => norm(v).includes(key)));
    const head = (n) => (norm(n.short).includes(key) || norm(n.label).includes(key) ? 0 : 1);
    return hits.sort((a, b) => head(a) - head(b)).slice(0, 8);
  }

  function renderResults() {
    const q = el("lib-q").value;
    const hits = searchNodes(q);
    el("lib-results").innerHTML = !q.trim() ? "" : hits.length
      ? hits.map((n) => `<li><button type="button" class="lib-link" data-node="${esc(n.id)}">${esc(n.short)}<small>${esc(n.summary || n.title || ENTITY[n.kind]?.name || "")}</small></button></li>`).join("")
      : `<li class="lib-hint">찾는 조문이 없어요.</li>`;
  }

  // ── 오른쪽 상세 ─────────────────────────────────
  function renderDetail() {
    const box = el("lib-detail");
    const n = S.selected && S.byId.get(S.selected);
    if (!n) { box.innerHTML = renderScope(); return; }
    const head = n.kind === "provision" ? renderProvision(n) : `
      <div class="art-head"><span class="eyebrow">${esc(ENTITY[n.kind].name)}</span><h3>${esc(n.label)}</h3>
        <span class="art-title">연결된 조문 ${neighbors(n.id).size}개</span></div>`;
    box.innerHTML = head + renderRelations(n);
  }

  function renderScope() {
    const docs = S.data ? S.data.docs : [];
    return `
      <div class="art-head"><span class="eyebrow">데이터 범위</span><h3>이 문서들 안에서만 판정해요</h3>
        <span class="art-title">관계도의 점을 누르면 원문과 연결 근거가 여기에 나와요. 범위 밖 규정은 EXTERNAL로 표시돼요.</span></div>
      <ul class="sources">${docs.map((s) => `
        <li><b><i class="lib-dot" style="background:${DOC_COLOR[s.id] || "#c3c8cf"}"></i>${esc(s.short)}</b><span class="kind k-${s.kind.toLowerCase()}">${esc(s.kind)}</span>
          <p>${esc(s.title)}</p><small>${esc(s.authority)} · 시행 ${esc(s.effective)} · ${esc(s.role)}${s.count ? ` · 관계도 조문 ${s.count}개` : ""}</small></li>`).join("")}</ul>`;
  }

  function renderProvision(n) {
    const chips = [];
    if (OBLIGATION[n.obligation]) chips.push(`<span class="chip ${OBLIGATION[n.obligation][1]}">${OBLIGATION[n.obligation][0]}</span>`);
    if (n.addressee && n.addressee !== "OTHER") chips.push(`<span class="chip">${esc(n.addressee_ko)}</span>`);
    if (n.penalty === "DIRECT") chips.push(`<span class="chip direct">직접 제재</span>`);
    if (n.penalty === "INDIRECT") chips.push(`<span class="chip indirect">간접 제재</span>`);
    if (n.verbatim === false) chips.push(`<span class="chip ext">요약 · 원문 아님</span>`);
    return `
      <div class="art-head"><span class="eyebrow"><i class="lib-dot" style="background:${color(n)}"></i>${esc(n.doc_short)}${n.page ? ` · ${n.page}쪽` : ""}</span>
        <h3>${esc(n.doc === "BKL" ? n.summary : `${n.label} ${n.title}`)}</h3>
        ${n.doc !== "BKL" && n.summary ? `<span class="art-title">${esc(n.summary)}</span>` : ""}</div>
      ${chips.length ? `<div class="chips">${chips.join("")}</div>` : ""}
      <div class="law-text${n.verbatim === false ? " summary" : ""}">${esc(n.text)}</div>`;
  }

  function renderRelations(n) {
    const rel = S.adj.get(n.id) || [];
    const groups = [];
    for (const [type, v] of Object.entries(EDGE)) {
      for (const dir of ["out", "in"]) {
        const items = rel.filter((x) => x.edge.type === type && x.dir === dir);
        if (!items.length) continue;
        const shown = items.slice(0, 12);
        groups.push(`
          <section class="lib-rel">
            <h4><i style="background:${v.color}"></i>${esc(v[dir])}<span>${items.length}</span>${S.edgeOn.has(type) ? "" : `<em>관계도에서 숨김</em>`}</h4>
            <ul>${shown.map((x) => {
              const o = S.byId.get(x.other);
              return `<li><button type="button" class="lib-link" data-node="${esc(o.id)}">${esc(o.short)}<small>${esc(o.summary || o.title || ENTITY[o.kind]?.name || "")}</small></button><span class="via">${esc(x.edge.via)}</span></li>`;
            }).join("")}${items.length > shown.length ? `<li class="lib-hint">외 ${items.length - shown.length}개</li>` : ""}</ul>
          </section>`);
      }
    }
    return groups.length ? `<h4 class="sub-title">연결 근거</h4>${groups.join("")}` : `<p class="muted">연결된 조문이 없어요.</p>`;
  }

  // ── 이벤트 ─────────────────────────────────────
  function bind() {
    el("lib-side").addEventListener("change", (e) => {
      const t = e.target;
      if (t.dataset.doc) t.checked ? S.docOn.add(t.dataset.doc) : S.docOn.delete(t.dataset.doc);
      if (t.dataset.edge) t.checked ? S.edgeOn.add(t.dataset.edge) : S.edgeOn.delete(t.dataset.edge);
      if (S.ready && (t.dataset.doc || t.dataset.edge)) applyFilter();
    });
    el("lib-side").addEventListener("click", (e) => {
      const preset = e.target.closest("[data-preset]");
      if (preset && S.ready) { focus(preset.dataset.preset); setPreset(preset.dataset.preset); return; }
      const link = e.target.closest("[data-node]");
      if (link && S.ready) focus(link.dataset.node);
    });
    el("lib-side").addEventListener("input", (e) => { if (e.target.id === "lib-q") renderResults(); });
    el("lib-side").addEventListener("keydown", (e) => {
      if (e.target.id !== "lib-q" || e.key !== "Enter") return;
      const first = searchNodes(e.target.value)[0];
      if (first) focus(first.id);
    });
    el("lib-detail").addEventListener("click", (e) => {
      const link = e.target.closest("[data-node]");
      if (link) focus(link.dataset.node);
    });
    el("lib-fit").addEventListener("click", () => S.ready && fitAll());
    el("lib-labels").addEventListener("click", (e) => {
      const on = e.currentTarget.getAttribute("aria-pressed") !== "true";
      e.currentTarget.setAttribute("aria-pressed", String(on));
      el("lib-graph").classList.toggle("labels", on);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && S.ready && !el("library").hidden) select(null);
    });
  }

  function start() {
    bind();
    // 주소가 …/#library (또는 #library:ARTICLE_31_1) 이면 바로 법령 라이브러리를 연다 (링크 공유·데모용)
    const [view, id] = decodeURIComponent(location.hash.slice(1)).split(":");
    if (view !== "library") return;
    S.pending = id || null;
    // The application opens the library from the URL after its view controller is ready.
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  window.JomunLibrary = { open, focus };
})();
