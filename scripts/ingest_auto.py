"""
全自动入库脚本 - 支持进度条、失败日志、断点续传

用法：
    uv run python scripts/ingest_auto.py data/datasets/scl/texts/
    uv run python scripts/ingest_auto.py --resume data/datasets/scl/texts/
    uv run python scripts/ingest_auto.py --split-mode legal data/datasets/scl/texts/
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Set

from app.rag.document_loader import load_and_split
from app.rag.vector_store import add_documents, get_collection_count, search


# 路径配置
CHECKPOINT_DIR = "./data/checkpoints"
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "ingest_checkpoint.json")
LOG_FILE = os.path.join(CHECKPOINT_DIR, "ingest_errors.log")
PROGRESS_FILE = os.path.join(CHECKPOINT_DIR, "ingest_progress.json")


def log_error(file_path: str, error: str):
    """记录错误日志"""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {file_path}: {error}\n")


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
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_processed": len(processed_files)
        }, f, ensure_ascii=False, indent=2)


def save_progress(processed: int, total: int, chunks: int, errors: int):
    """保存进度信息"""
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "processed": processed,
            "total": total,
            "chunks": chunks,
            "errors": errors,
            "percentage": round(processed / total * 100, 2) if total > 0 else 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, f, ensure_ascii=False, indent=2)


def print_progress_bar(processed: int, total: int, chunks: int, errors: int, width: int = 50):
    """打印进度条"""
    percentage = processed / total * 100 if total > 0 else 0
    filled = int(width * processed / total) if total > 0 else 0
    bar = "#" * filled + "-" * (width - filled)

    # 清除当前行并打印进度
    sys.stdout.write("\r")
    sys.stdout.write(f"Progress: [{bar}] {percentage:.1f}% ({processed}/{total}) | chunks: {chunks} | errors: {errors}")
    sys.stdout.flush()


def get_all_files(path: str) -> List[str]:
    """获取目录下所有文件"""
    p = Path(path)
    if p.is_file():
        return [str(p)]
    elif p.is_dir():
        return [
            str(f)
            for f in p.glob("*")
            if f.suffix.lower() in (".pdf", ".docx", ".doc", ".txt")
        ]
    else:
        print(f"路径不存在: {path}")
        return []


def ingest_auto(path: str, split_mode: str = "default", resume: bool = False):
    """全自动入库"""
    # 获取所有文件
    all_files = get_all_files(path)
    if not all_files:
        print("没有找到文件")
        return

    total_files = len(all_files)

    # 加载或清空检查点
    if resume:
        processed = load_checkpoint()
        print(f"续传模式：已处理 {len(processed)} 个文件")
    else:
        processed = set()
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
        print("全新开始")

    # 计算待处理文件
    files_to_process = [f for f in all_files if f not in processed]
    remaining = len(files_to_process)

    if remaining == 0:
        print("所有文件已处理完成")
        return

    print(f"总文件: {total_files} | 待处理: {remaining} | 分段模式: {split_mode}")
    print("-" * 80)

    # 开始入库
    start_time = time.time()
    total_chunks = 0
    error_count = 0

    for i, file_path in enumerate(files_to_process):
        try:
            # 加载并分段
            docs = load_and_split(file_path, split_mode=split_mode)

            # 入库
            add_documents(docs)

            # 更新统计
            chunks = len(docs)
            total_chunks += chunks

            # 更新检查点
            processed.add(file_path)
            save_checkpoint(processed)

            # 保存进度
            save_progress(
                processed=len(processed),
                total=total_files,
                chunks=total_chunks,
                errors=error_count
            )

            # 打印进度条
            print_progress_bar(
                processed=len(processed),
                total=total_files,
                chunks=total_chunks,
                errors=error_count
            )

        except Exception as e:
            error_count += 1
            error_msg = str(e)
            log_error(file_path, error_msg)

            # 记录到检查点（跳过此文件）
            processed.add(file_path)
            save_checkpoint(processed)

            # 保存进度
            save_progress(
                processed=len(processed),
                total=total_files,
                chunks=total_chunks,
                errors=error_count
            )

            # 打印进度条
            print_progress_bar(
                processed=len(processed),
                total=total_files,
                chunks=total_chunks,
                errors=error_count
            )

    # 完成
    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"入库完成！")
    print(f"  总文件: {total_files}")
    print(f"  已处理: {len(processed)}")
    print(f"  总片段: {total_chunks}")
    print(f"  错误数: {error_count}")
    print(f"  耗时: {elapsed:.1f}s ({elapsed/60:.1f}分钟)")

    # 验证索引
    print("\n验证索引完整性...")
    try:
        count = get_collection_count()
        results = search("测试查询", top_k=1)
        if results:
            print(f"索引验证通过：{count} 条记录")
        else:
            print(f"警告：查询返回空结果，但有 {count} 条记录")
    except Exception as e:
        print(f"索引验证失败: {e}")

    # 显示错误日志位置
    if error_count > 0:
        print(f"\n错误日志: {LOG_FILE}")


def main():
    # 解析命令行参数
    split_mode = "default"
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

    if "--resume" in args:
        resume = True
        args.remove("--resume")

    if not args:
        print("用法: uv run python scripts/ingest_auto.py [--split-mode default|legal] [--resume] <路径>")
        sys.exit(1)

    path = args[0]

    print("=" * 80)
    print("全自动入库脚本")
    print("=" * 80)

    ingest_auto(path, split_mode, resume)


if __name__ == "__main__":
    main()
