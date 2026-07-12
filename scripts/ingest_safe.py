"""
安全入库脚本 - 支持断点续传和索引验证

用法：
    uv run python scripts/ingest_safe.py data/datasets/scl/texts/
    uv run python scripts/ingest_safe.py --resume data/datasets/scl/texts/
    uv run python scripts/ingest_safe.py --split-mode legal --batch-size 1000 data/datasets/scl/texts/
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Set

from app.rag.document_loader import load_and_split
from app.rag.vector_store import add_documents, get_collection_count, search


# 检查点文件路径
CHECKPOINT_DIR = "./data/checkpoints"
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "ingest_checkpoint.json")


def load_checkpoint() -> Set[str]:
    """加载已处理的文件列表"""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("processed_files", []))
    return set()


def save_checkpoint(processed_files: Set[str]):
    """保存已处理的文件列表"""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "processed_files": list(processed_files),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_processed": len(processed_files)
        }, f, ensure_ascii=False, indent=2)


def get_files_to_process(path: str, batch_size: int = 1000) -> List[str]:
    """获取待处理的文件列表（支持断点续传）"""
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
        return []

    # 加载检查点，排除已处理的文件
    processed = load_checkpoint()
    files_to_process = [f for f in files if f not in processed]

    # 限制批次大小
    return files_to_process[:batch_size]


def verify_index() -> bool:
    """验证索引完整性"""
    try:
        count = get_collection_count()
        if count == 0:
            print("警告：集合为空")
            return False

        # 测试不带 where 的查询
        results = search("测试查询", top_k=1)
        if not results:
            print("警告：查询返回空结果")
            return False

        print(f"索引验证通过：{count} 条记录，查询正常")
        return True
    except Exception as e:
        print(f"索引验证失败: {e}")
        return False


def ingest_batch(files: List[str], split_mode: str = "default") -> int:
    """入库一批文件"""
    total = 0
    processed = load_checkpoint()

    for i, file_path in enumerate(files):
        print(f"[{i+1}/{len(files)}] 正在处理: {Path(file_path).name}")
        try:
            docs = load_and_split(file_path, split_mode=split_mode)
            add_documents(docs)
            print(f"  入库 {len(docs)} 个片段")

            # 更新检查点
            processed.add(file_path)
            save_checkpoint(processed)

            total += len(docs)
        except Exception as e:
            print(f"  失败: {e}")
            # 保存检查点后继续
            save_checkpoint(processed)
            continue

    return total


def main():
    # 解析命令行参数
    split_mode = "default"
    batch_size = 1000
    resume = False
    args = sys.argv[1:]

    if "--split-mode" in args:
        idx = args.index("--split-mode")
        if idx + 1 < len(args):
            split_mode = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            print("错误: --split-mode 需要指定模式 (default/legal)")
            sys.exit(1)

    if "--batch-size" in args:
        idx = args.index("--batch-size")
        if idx + 1 < len(args):
            batch_size = int(args[idx + 1])
            args = args[:idx] + args[idx + 2:]

    if "--resume" in args:
        resume = True
        args.remove("--resume")

    if not args:
        print("用法: uv run python scripts/ingest_safe.py [--split-mode default|legal] [--batch-size N] [--resume] <路径>")
        sys.exit(1)

    path = args[0]

    # 如果不是续传模式，清空检查点
    if not resume and os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("已清空检查点，重新开始")

    # 获取待处理文件
    files = get_files_to_process(path, batch_size)
    if not files:
        print("没有需要处理的文件")
        return

    print(f"准备处理 {len(files)} 个文件（分段模式: {split_mode}）")

    # 执行入库
    start_time = time.time()
    total = ingest_batch(files, split_mode)
    elapsed = time.time() - start_time

    print(f"\n入库完成：{total} 个片段，耗时 {elapsed:.1f}s")

    # 验证索引
    print("\n验证索引完整性...")
    if verify_index():
        print("索引验证通过")
    else:
        print("警告：索引验证失败，可能需要重新入库")


if __name__ == "__main__":
    main()
