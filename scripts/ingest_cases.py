"""导入 LeCaRD 案例数据集

用法:
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest_cases.py
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest_cases.py --limit 500
"""

import glob
import json
import sys

from langchain_core.documents import Document

from app.rag.vector_store import add_documents


def import_cases(limit: int = 2000):
    """导入裁判文书案例到向量库."""
    base = "data/lecard_temp/data/candidates"
    patterns = [
        f"{base}/candidates1/*/*.json",
        f"{base}/similar_case/candidates2/*/*.json",
    ]

    all_files = []
    for pat in patterns:
        all_files.extend(glob.glob(pat))

    files = all_files[:limit]
    print(f"总计 {len(all_files)} 份案例，本次导入前 {len(files)} 份")

    docs = []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                case = json.load(f)
        except Exception:
            continue

        name = case.get("ajName", "")
        facts = case.get("ajjbqk", "")  # 案件基本情况
        analysis = case.get("cpfxgc", "")  # 裁判分析过程
        result = case.get("pjjg", "")  # 判决结果

        # 组合为可检索文本
        text = f"【案例】{name}\n【案情】{facts[:800]}\n【分析】{analysis[:500]}\n【结果】{result[:300]}"
        if len(text) < 50:
            continue

        doc = Document(
            page_content=text,
            metadata={
                "source": f"LeCaRD/{name}.txt",
                "case_name": name,
                "case_id": case.get("ajId", ""),
                "type": "case",
            },
        )
        docs.append(doc)

    if docs:
        add_documents(docs)

    print(f"导入完成: {len(docs)} 份案例")


if __name__ == "__main__":
    limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--limit" else 2000
    import_cases(limit)
