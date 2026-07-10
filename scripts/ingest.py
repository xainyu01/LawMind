"""法律文档入库脚本

用法:
    uv run python scripts/ingest.py data/docs/民法典节选.txt
    uv run python scripts/ingest.py data/docs/
    uv run python scripts/ingest.py --split-mode legal data/docs/
"""

import re
import sys
from pathlib import Path

from app.rag.document_loader import load_and_split
from app.rag.vector_store import add_documents

# 法律时效性元数据模板（根据文件名推断）
LEGAL_DOC_STATUS = {
    "民法典": {"effective_date": "2021-01-01", "status": "active"},
    "刑法": {"effective_date": "2021-03-01", "status": "active"},
    "劳动法": {"effective_date": "1995-01-01", "status": "active"},
    "合同法": {"effective_date": "1999-10-01", "status": "repealed", "repealed_date": "2021-01-01"},
    "婚姻法": {"effective_date": "1981-01-01", "status": "repealed", "repealed_date": "2021-01-01"},
    "继承法": {"effective_date": "1985-10-01", "status": "repealed", "repealed_date": "2021-01-01"},
}


def _infer_doc_status(file_path: str) -> dict:
    """根据文件名推断法律文档的时效性状态。"""
    filename = Path(file_path).stem
    for key, status in LEGAL_DOC_STATUS.items():
        if key in filename:
            return status
    return {"effective_date": "", "status": "active"}


def ingest_path(path: str, split_mode: str = "default") -> int:
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
        print(f"正在处理: {file_path} (分段模式: {split_mode})")
        try:
            docs = load_and_split(file_path, split_mode=split_mode)
            # 添加时效性元数据
            status_info = _infer_doc_status(file_path)
            for doc in docs:
                doc.metadata.update(status_info)
            add_documents(docs)
            print(f"  入库 {len(docs)} 个片段 (状态: {status_info['status']})")
            total += len(docs)
        except Exception as e:
            print(f"  失败: {e}")

    return total


if __name__ == "__main__":
    # 解析命令行参数
    split_mode = "default"
    args = sys.argv[1:]

    if "--split-mode" in args:
        idx = args.index("--split-mode")
        if idx + 1 < len(args):
            split_mode = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            print("错误: --split-mode 需要指定模式 (default/legal)")
            sys.exit(1)

    if not args:
        print("用法: uv run python scripts/ingest.py [--split-mode default|legal] <文件或目录路径>")
        sys.exit(1)

    count = ingest_path(args[0], split_mode=split_mode)
    print(f"\n总计入库 {count} 个片段")
