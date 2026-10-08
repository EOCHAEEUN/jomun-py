"""Independently reviewed QA answers: question accuracy and unsupported-claim rate.

Run after filling docs/qa_review_20261008.json with one review per generated answer.
"""
import argparse
import json
from pathlib import Path


def score(results: dict, reviews: list[dict]) -> dict:
    answers = {row["id"]: row for row in results["cases"]}
    audited = {row["id"]: row for row in reviews}
    if len(answers) != len(results["cases"]) or len(audited) != len(reviews):
        raise ValueError("중복된 평가 문항 ID가 있습니다.")
    if answers.keys() != audited.keys():
        raise ValueError(f"답변·검토 문항 불일치: 답변만 {sorted(answers.keys() - audited.keys())}, "
                         f"검토만 {sorted(audited.keys() - answers.keys())}")

    total_claims = unsupported = correct = ungrounded_answers = 0
    contradicted = uncited = 0
    excluded = []
    for case_id, review in audited.items():
        if not answers[case_id].get("answer"):
            raise ValueError(f"답변이 없습니다: {case_id}")
        if review.get("valid") is False:
            if not review.get("reason"):
                raise ValueError(f"제외 사유가 없습니다: {case_id}")
            excluded.append(case_id)
            continue
        if review.get("valid") is not True:
            raise ValueError(f"valid가 불리언이 아닙니다: {case_id}")
        if not isinstance(review.get("answer_correct"), bool):
            raise ValueError(f"answer_correct가 불리언이 아닙니다: {case_id}")
        claim_rows = review.get("claims")
        if not isinstance(claim_rows, list) or not claim_rows:
            raise ValueError(f"주장 검토가 없습니다: {case_id}")
        if any(not row.get("text") or not isinstance(row.get("supported"), bool)
               or not row.get("basis") for row in claim_rows):
            raise ValueError(f"주장 근거 또는 판정이 없습니다: {case_id}")
        if any(row.get("kind") not in ("contradicted", "uncited")
               for row in claim_rows if not row["supported"]):
            raise ValueError(f"근거 부족 주장의 유형이 없습니다: {case_id}")
        claims = len(claim_rows)
        bad = sum(not row["supported"] for row in claim_rows)
        contradicted += sum(row.get("kind") == "contradicted" for row in claim_rows)
        uncited += sum(row.get("kind") == "uncited" for row in claim_rows)
        correct += review["answer_correct"]
        total_claims += claims
        unsupported += bad
        ungrounded_answers += bad > 0

    count = len(reviews) - len(excluded)
    return {
        "questions_total": len(reviews),
        "questions_scored": count,
        "excluded": excluded,
        "answer_correct": correct,
        "answer_accuracy": round(correct / count, 3) if count else None,
        "factual_claims": total_claims,
        "unsupported_claims": unsupported,
        "contradicted_claims": contradicted,
        "uncited_claims": uncited,
        "unsupported_claim_rate": round(unsupported / total_claims, 3) if total_claims else None,
        "answers_with_unsupported_claim": ungrounded_answers,
        "answers_with_unsupported_claim_rate": round(ungrounded_answers / count, 3) if count else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("docs/qa_heldout_answers_20261008.json"))
    parser.add_argument("--review", type=Path, default=Path("docs/qa_review_20261008.json"))
    args = parser.parse_args()
    results = json.loads(args.results.read_text(encoding="utf-8"))
    reviews = json.loads(args.review.read_text(encoding="utf-8"))
    print(json.dumps(score(results, reviews), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
