"""Run a private, user-maintained holdout set without copying documents into Git."""

import argparse
import json
import time
from pathlib import Path

from app.evaluation import score_case, summarize_cases
from app.nodes.rule_extract import rule_extract
from app.services.extraction import run_pipeline
from app.tools.document_reader import read_document


def main() -> int:
    parser = argparse.ArgumentParser(description="评估规则提取效果；原件与标准答案只在本机读取")
    parser.add_argument("manifest", type=Path, help="私有 JSON 测评清单的路径")
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        parser.error("清单必须包含非空 cases 数组")
    reports = []
    for item in cases:
        case_id = str(item["id"])
        documents = []
        for source in item["documents"]:
            path = Path(source["path"])
            if not path.is_absolute():
                path = manifest.parent / path
            path = path.resolve()
            documents.append({"name": path.name, "role": source["role"], "data": path.read_bytes()})
        started = time.perf_counter()
        result = run_pipeline(documents, "rules", reader=read_document, rule_engine=rule_extract, ai_engine=None)
        report = score_case(item["expected"], result["fields"])
        reports.append(report)
        problems = [f"{key}:{entry['status']}" for key, entry in report["fields"].items()
                    if entry["status"] not in {"correct", "correct_blank"}]
        print(f"{case_id}: {'全对' if report['all_correct'] else ', '.join(problems)}；{time.perf_counter() - started:.1f} 秒")
        for warning in result["warnings"]:
            print(f"  读取提示：{warning}")
    summary = summarize_cases(reports)
    print(f"整票全对：{summary['all_correct_cases']}/{summary['cases']}")
    print("字段：", "，".join(f"{key} {value}" for key, value in summary["fields"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
