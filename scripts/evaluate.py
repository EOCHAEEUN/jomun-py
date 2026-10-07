# evaluate.py — Naive RAG vs RAG + Rule Engine 비교
#
# 실행:  python -m scripts.evaluate      (먼저 python -m scripts.ingest)
#
# Naive RAG       : 서비스 설명으로 바로 유사도 검색 → 상위 결과의 고영향 영역(제2조4호 ○목)을 정답으로 본다
# RAG + Rule      : 특성 추출 → Rule Engine 판정 결과
# 지표
#   domain_acc    : 고영향 영역(목) 판정 정확도
#   hit@3         : 정답 조문이 상위 3개(Naive) / 빌드 로그 근거(Rule) 안에 있는가
#   status_acc    : 조문별 판정 상태(MATCH/REQUIRED/CONDITIONAL/…)가 정답과 일치하는 비율 (Rule만)
import json

from app.config import DATA_DIR, EVAL_PATH
from app.engine.pipeline import run_build
from app.rag.store import get_collection, search

MOK = "ARTICLE_2_4_"


def naive(spec: str) -> dict:
    hits = search(spec, k=5)
    ids = [h["id"] for h in hits]
    domain = next((i for i in ids[:3] if i.startswith(MOK)), None)
    return {"top3": ids[:3], "domain": domain}


def rule(spec: str) -> dict:
    result = run_build(spec)
    statuses = {it["label"]: it["status"] for it in result["items"]}
    record_ids = {r["id"] for it in result["items"] for r in it["records"]}
    domain = next((r["id"] for it in result["items"] if it["key"] == "art2_4" for r in it["records"]), None)
    penalties = {it["label"]: (it["chain"] or {}).get("type") for it in result["items"]}
    return {"statuses": statuses, "records": record_ids, "domain": domain, "penalties": penalties}


def main():
    if get_collection() is None:
        raise SystemExit("Chroma가 비어 있습니다. 먼저 `python -m scripts.ingest`를 실행하세요.")
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    rows, totals = [], {"naive_domain": 0, "rule_domain": 0, "naive_hit": 0, "rule_hit": 0,
                        "status_ok": 0, "status_all": 0}

    for case in cases:
        gold = case["gold"]
        n, r = naive(case["spec"]), rule(case["spec"])
        naive_hit = any(g in n["top3"] for g in gold["retrieval"])
        rule_hit = any(g in r["records"] for g in gold["retrieval"])
        ok = sum(1 for label, s in gold["statuses"].items() if r["statuses"].get(label) == s)
        ok += sum(1 for label in gold.get("absent", []) if label not in r["statuses"])
        ok += sum(1 for label, p in gold.get("penalty", {}).items() if r["penalties"].get(label) == p)
        n_checks = len(gold["statuses"]) + len(gold.get("absent", [])) + len(gold.get("penalty", {}))

        totals["naive_domain"] += n["domain"] == gold["domain"]
        totals["rule_domain"] += r["domain"] == gold["domain"]
        totals["naive_hit"] += naive_hit
        totals["rule_hit"] += rule_hit
        totals["status_ok"] += ok
        totals["status_all"] += n_checks
        rows.append({
            "id": case["id"], "name": case["name"],
            "gold_domain": gold["domain"], "naive_domain": n["domain"], "rule_domain": r["domain"],
            "naive_top3": n["top3"], "naive_hit@3": naive_hit, "rule_hit": rule_hit,
            "status": f"{ok}/{n_checks}",
            "mismatch": {k: (v, r["statuses"].get(k)) for k, v in gold["statuses"].items()
                         if r["statuses"].get(k) != v},
        })

    short = lambda x: (x or "-").replace(MOK, "2-4-")
    print(f"{'케이스':<28}{'정답 영역':<10}{'Naive':<10}{'Rule':<10}{'N hit@3':<9}{'R hit':<7}상태")
    for row in rows:
        print(f"{row['id']} {row['name'][:24]:<25}{short(row['gold_domain']):<10}{short(row['naive_domain']):<10}"
              f"{short(row['rule_domain']):<10}{'O' if row['naive_hit@3'] else 'X':<9}"
              f"{'O' if row['rule_hit'] else 'X':<7}{row['status']}")
        if row["mismatch"]:
            print("     불일치:", row["mismatch"])
    n = len(cases)
    summary = {
        "cases": n,
        "naive_domain_acc": round(totals["naive_domain"] / n, 2),
        "rule_domain_acc": round(totals["rule_domain"] / n, 2),
        "naive_hit@3": round(totals["naive_hit"] / n, 2),
        "rule_hit": round(totals["rule_hit"] / n, 2),
        "rule_status_acc": round(totals["status_ok"] / totals["status_all"], 2),
    }
    print("\n요약:", summary)
    out = DATA_DIR / "eval" / "results.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"결과 저장 → data/eval/{out.name}")


if __name__ == "__main__":
    main()
