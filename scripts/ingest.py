"""法律文档入库脚本

用法:
    uv run python scripts/ingest.py data/docs/民法典节选.txt
    uv run python scripts/ingest.py data/docs/
"""

import sys
from pathlib import Path

from app.rag.document_loader import load_and_split
from app.rag.vector_store import add_documents


def ingest_path(path: str) -> int:
    p = Path(path)
    if p.is_file():
        files = [str(p)]
    elif p.is_dir():
        files = [
            str(f)
            for f in p.glob("*")
            if f.suffix.lower() in (".pdf", ".docx", ".doc", ".txt")
        ]
    else:
        print(f"路径不存在: {path}")
        return 0

    total = 0
    for file_path in files:
        print(f"正在处理: {file_path}")
        try:
            docs = load_and_split(file_path)
            add_documents(docs)
            print(f"  入库 {len(docs)} 个片段")
            total += len(docs)
        except Exception as e:
            print(f"  失败: {e}")

    return total


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: uv run python scripts/ingest.py <文件或目录路径>")
        sys.exit(1)

    count = ingest_path(sys.argv[1])
    print(f"\n总计入库 {count} 个片段")
