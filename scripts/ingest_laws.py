"""批量导入法律法规数据集（taburise/Chinese-Laws-folk 格式）

用法:
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/ingest_laws.py
"""

import glob
import os
import re
import sys
from pathlib import Path

from langchain_core.documents import Document

from app.rag.vector_store import add_documents, clear_collection, get_collection_count


def parse_law_file(filepath: str) -> list[Document]:
    """解析一个法律 TXT 文件，每行一个法条 → LangChain Document 列表."""
    law_name = Path(filepath).stem  # 文件名即法律名称
    docs = []

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # 格式: 《法律名》第X条规定，……内容……
            # 文件名已包含法律名，这里提取条号
            match = re.match(r"《[^》]+》第([^条]+)条(?:规定)?[，,](.+)", line)
            article = match.group(1) if match else ""
            doc = Document(
                page_content=line,
                metadata={
                    "source": f"{law_name}.txt",
                    "law_name": law_name,
                    "article": article,
                },
            )
            docs.append(doc)
    return docs


def main():
    laws_dir = "data/laws_temp"
    if not os.path.isdir(laws_dir):
        print(f"目录不存在: {laws_dir}")
        sys.exit(1)

    # 清空旧数据
    old_count = get_collection_count()
    if old_count > 0:
        print(f"清空旧数据 ({old_count} 条)...")
        clear_collection()

    # 遍历所有法律文件
    files = sorted(glob.glob(os.path.join(laws_dir, "*.txt")))
    print(f"找到 {len(files)} 部法律")

    total = 0
    for fp in files:
        try:
            docs = parse_law_file(fp)
            if docs:
                add_documents(docs)
                total += len(docs)
        except Exception as e:
            print(f"  失败: {Path(fp).name} — {e}")

    print(f"\n总计入库 {total} 条法条 (共 {len(files)} 部法律)")


if __name__ == "__main__":
    main()
