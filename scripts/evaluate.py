# evaluate.py — 단계별 평가: ① 검색 → ② 규칙 판정 → ③ 최종 빌드
#
# 실행:  python -m scripts.evaluate              (먼저 python -m scripts.ingest)
#        python -m scripts.evaluate --snapshot   (docs/eval_snapshot.json 갱신)
#
# 평가셋
#   dev      data/eval/cases.json          규칙을 만들면서 본 케이스 (개발용)
#   held-out data/eval/heldout_cases.json  엔진 수정 전에 따로 써 둔 케이스 (v1) — 실패 분석에 쓰여 이제 '본 데이터'
#   held-out v2 data/eval/heldout_v2_cases.json  v1 실패를 고치기 전에 새로 써 둔 케이스 — 결과를 보고 엔진을 고치지 않는다
#
# 지표 (서로 다른 단계를 따로 잰다 — 정답 레코드를 규칙이 직접 넣는 순환 지표는 쓰지 않는다)
#   ① 검색 Hit@3        정답 조문(gold.retrieval)이 검색 상위 3개 안에 드는 비율 (정답 조문 단위)
#        naive          서비스 설명 그대로 1회 검색
#        enriched       설명 + 특성별 법률 용어 쿼리, 쿼리마다 상위 3개
#      후보 재현율       실제 파이프라인 후보(쿼리마다 top-k + 참조 확장)에 정답 조문이 들어간 비율 · 평균 후보 수
#   ② 규칙 판정 정확도   검색 없이(rules-only) 특성 추출 → Rule Engine 판정이 정답 상태와 맞는 비율
#   ③ 최종 빌드 정확도   RAG 후보 → Rule Engine 검증까지 거친 빌드 로그가 정답 상태와 맞는 비율
#      케이스 완전 일치   한 케이스의 모든 점검이 맞은 비율
#   참고: 고영향 영역 정확도 — naive 상위 3개 중 첫 ○목 vs 최종 빌드의 ○목
#
# 상태 점검 = gold.statuses(라벨별 상태) + gold.absent(나오면 안 되는 라벨) + gold.penalty(제재 경로)
# ③에서 틀린 점검은 ②의 결과로 원인을 나눈다: ②도 틀림 → 특성·규칙 / ②는 맞음 → 검색
import argparse
import json
from datetime import date

from app.config import DATA_DIR, EMBEDDING_PROVIDER, EVAL_PATH, RETRIEVAL_TOP_K
from app.engine.features import extract
from app.engine.pipeline import run_build
from app.rag.retriever import SEARCH_FILTER, retrieve_candidates
from app.rag.store import get_collection, search

HELDOUT_PATH = DATA_DIR / "eval" / "heldout_cases.json"
HELDOUT_V2_PATH = DATA_DIR / "eval" / "heldout_v2_cases.json"
SNAPSHOT_PATH = DATA_DIR.parent / "docs" / "eval_snapshot.json"
MOK = "ARTICLE_2_4_"
K = 3


def _build_view(result: dict) -> dict:
    return {
        "statuses": {it["label"]: it["status"] for it in result["items"]},
        "penalties": {it["label"]: (it["chain"] or {}).get("type") for it in result["items"]},
        "domain": next((r["id"] for it in result["items"] if it["key"] == "art2_4"
                        for r in it["records"] if r["id"].startswith(MOK)), None),
    }


def _checks(gold: dict, view: dict) -> list[dict]:
    out = []
    for label, want in gold["statuses"].items():
        out.append({"check": label, "want": want, "got": view["statuses"].get(label)})
    for label in gold.get("absent", []):
        out.append({"check": f"{label} 없음", "want": None, "got": view["statuses"].get(label)})
    for label, want in gold.get("penalty", {}).items():
        out.append({"check": f"{label} 제재", "want": want, "got": view["penalties"].get(label)})
    for c in out:
        c["ok"] = c["want"] == c["got"]
    return out


def evaluate_case(case: dict) -> dict:
    spec, gold = case["spec"], case["gold"]
    features, _ = extract(spec)

    # ① 검색
    naive_ids = [h["id"] for h in search(spec, k=K, where=SEARCH_FILTER)]
    enriched = retrieve_candidates(spec, features, k=K)
    pipeline_rag = retrieve_candidates(spec, features, k=RETRIEVAL_TOP_K)
    g = gold["retrieval"]
    retrieval = {
        "gold": g,
        "naive_top3": naive_ids,
        "naive_hits": [x for x in g if x in naive_ids],
        "enriched_hits": [x for x in g if x in enriched.hits],
        "candidate_hits": [x for x in g if x in (pipeline_rag.candidates or set())],
        "n_candidates": len(pipeline_rag.candidates or ()),
    }

    # ② 규칙만 / ③ RAG → 규칙
    rules_only = _build_view(run_build(spec, use_rag=False))
    final = _build_view(run_build(spec))
    rule_checks, final_checks = _checks(gold, rules_only), _checks(gold, final)
    for rc, fc in zip(rule_checks, final_checks):
        fc["cause"] = None if fc["ok"] else ("검색" if rc["ok"] else "특성·규칙")

    naive_domain = next((i for i in naive_ids if i.startswith(MOK)), None)
    return {
        "id": case["id"], "name": case["name"], "spec": spec,
        "retrieval": retrieval,
        "domain": {"gold": gold["domain"], "naive": naive_domain, "final": final["domain"]},
        "rule_checks": rule_checks,
        "final_checks": final_checks,
    }


def summarize(rows: list[dict]) -> dict:
    gold_n = sum(len(r["retrieval"]["gold"]) for r in rows)
    rule = [c for r in rows for c in r["rule_checks"]]
    final = [c for r in rows for c in r["final_checks"]]
    pct = lambda a, b: round(a / b, 2) if b else None  # noqa: E731
    return {
        "cases": len(rows),
        "retrieval_hit@3_naive": pct(sum(len(r["retrieval"]["naive_hits"]) for r in rows), gold_n),
        "retrieval_hit@3_enriched": pct(sum(len(r["retrieval"]["enriched_hits"]) for r in rows), gold_n),
        "candidate_recall": pct(sum(len(r["retrieval"]["candidate_hits"]) for r in rows), gold_n),
        "avg_candidates": round(sum(r["retrieval"]["n_candidates"] for r in rows) / len(rows), 1),
        "rule_accuracy": pct(sum(c["ok"] for c in rule), len(rule)),
        "final_accuracy": pct(sum(c["ok"] for c in final), len(final)),
        "final_case_exact": pct(sum(all(c["ok"] for c in r["final_checks"]) for r in rows), len(rows)),
        "domain_acc_naive": pct(sum(r["domain"]["naive"] == r["domain"]["gold"] for r in rows), len(rows)),
        "domain_acc_final": pct(sum(r["domain"]["final"] == r["domain"]["gold"] for r in rows), len(rows)),
        "checks": len(final),
        "errors_by_cause": {
            "검색": sum(1 for c in final if c["cause"] == "검색"),
            "특성·규칙": sum(1 for c in final if c["cause"] == "특성·규칙"),
        },
    }


def run(split_paths: dict) -> dict:
    out = {}
    for split, path in split_paths.items():
        rows = [evaluate_case(c) for c in json.loads(path.read_text(encoding="utf-8"))]
        out[split] = {"summary": summarize(rows), "rows": rows}
    return out


def print_report(results: dict) -> None:
    ox = lambda b: "O" if b else "X"  # noqa: E731
    for split, res in results.items():
        print(f"\n━━ {split} ━━")
        print(f"{'케이스':<28}{'검색 naive':>10}{'enriched':>10}{'후보':>6}{'② 규칙':>8}{'③ 최종':>8}")
        for r in res["rows"]:
            rv, g = r["retrieval"], len(r["retrieval"]["gold"])
            rc = sum(c["ok"] for c in r["rule_checks"])
            fc = sum(c["ok"] for c in r["final_checks"])
            n = len(r["final_checks"])
            print(f"{r['id']:<4}{r['name'][:22]:<24}{len(rv['naive_hits'])}/{g:<8}{len(rv['enriched_hits'])}/{g:<8}"
                  f"{rv['n_candidates']:>5}{rc:>5}/{n:<3}{fc:>5}/{n:<3}{ox(fc == n)}")
            for c in r["final_checks"]:
                if not c["ok"]:
                    print(f"      ✗ {c['check']}: 정답 {c['want']} · 결과 {c['got']} (원인: {c['cause']})")
        s = res["summary"]
        print(f"  ① 검색 Hit@3  naive {s['retrieval_hit@3_naive']} → enriched {s['retrieval_hit@3_enriched']}"
              f"  · 후보 재현율 {s['candidate_recall']} (평균 후보 {s['avg_candidates']}개)")
        print(f"  ② 규칙 판정 정확도 (검색 없이)   {s['rule_accuracy']}")
        print(f"  ③ 최종 빌드 정확도 (RAG → 규칙)  {s['final_accuracy']}  · 케이스 완전 일치 {s['final_case_exact']}")
        print(f"  참고 · 고영향 영역 정확도  naive {s['domain_acc_naive']} → 최종 {s['domain_acc_final']}")
        print(f"  틀린 점검의 원인  {s['errors_by_cause']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true", help="docs/eval_snapshot.json 갱신")
    args = ap.parse_args()
    col = get_collection()
    if col is None:
        raise SystemExit("Chroma가 비어 있습니다. 먼저 `python -m scripts.ingest`를 실행하세요.")

    results = run({"dev": EVAL_PATH, "heldout": HELDOUT_PATH, "heldout_v2": HELDOUT_V2_PATH})
    print_report(results)

    meta = {"date": date.today().isoformat(), "embedding": EMBEDDING_PROVIDER, "top_k": RETRIEVAL_TOP_K,
            "hit_k": K, "chunks": col.count(), "feature_extractor": run_build("AI", use_rag=False)["mode"]["feature_extractor"]}
    out = DATA_DIR / "eval" / "results.json"
    out.write_text(json.dumps({"meta": meta, **results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n상세 결과 → data/eval/{out.name}")
    if args.snapshot:
        snap = {"meta": meta, **{split: {"summary": r["summary"],
                                         "cases": {row["id"]: [c["check"] for c in row["final_checks"] if not c["ok"]]
                                                   for row in r["rows"]}}
                                 for split, r in results.items()}}
        SNAPSHOT_PATH.parent.mkdir(exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"스냅샷 → docs/{SNAPSHOT_PATH.name}")


if __name__ == "__main__":
    main()
