"""法律数据集下载脚本

支持下载 SCL（标准中国法律数据集）和 LeCaRD（法律案例检索数据集）。

用法:
    HF_ENDPOINT=https://hf-mirror.com uv run python scripts/download_dataset.py scl
    HF_ENDPOINT=https://hf-mirror.com uv run python scripts/download_dataset.py lecard
    HF_ENDPOINT=https://hf-mirror.com uv run python scripts/download_dataset.py all
"""

import os
import sys
from pathlib import Path

# 数据集配置
DATASETS = {
    "scl": {
        "repo_id": "twang2218/chinese-law-and-regulations",
        "description": "中国法律法规数据集（10K-100K 条）",
        "local_dir": "data/datasets/scl",
    },
    "lecard": {
        "repo_id": "mteb/LeCaRDv2",
        "description": "法律案例检索数据集（LeCaRD v2）",
        "local_dir": "data/datasets/lecard",
    },
}


def download_dataset(dataset_name: str) -> bool:
    """下载指定数据集。"""
    if dataset_name not in DATASETS:
        print(f"未知数据集: {dataset_name}")
        print(f"可用数据集: {', '.join(DATASETS.keys())}")
        return False

    config = DATASETS[dataset_name]
    print(f"正在下载 {config['description']}...")
    print(f"仓库: {config['repo_id']}")
    print(f"保存到: {config['local_dir']}")

    try:
        from huggingface_hub import snapshot_download

        # 创建本地目录
        local_dir = Path(config["local_dir"])
        local_dir.mkdir(parents=True, exist_ok=True)

        # 下载数据集
        snapshot_download(
            repo_id=config["repo_id"],
            repo_type="dataset",
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
        )

        print(f"✅ {dataset_name} 下载完成！")
        print(f"文件位置: {local_dir.absolute()}")
        return True

    except ImportError:
        print("错误: 需要安装 huggingface_hub")
        print("运行: uv add huggingface_hub")
        return False
    except Exception as e:
        print(f"下载失败: {e}")
        return False


def list_datasets():
    """列出可用数据集。"""
    print("可用数据集:")
    print("-" * 50)
    for name, config in DATASETS.items():
        local_dir = Path(config["local_dir"])
        status = "已下载" if local_dir.exists() and any(local_dir.iterdir()) else "未下载"
        print(f"  {name:10} - {config['description']}")
        print(f"             状态: {status}")
        print(f"             路径: {config['local_dir']}")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  uv run python scripts/download_dataset.py <数据集名称>")
        print("  uv run python scripts/download_dataset.py list")
        print()
        list_datasets()
        return

    command = sys.argv[1].lower()

    if command == "list":
        list_datasets()
    elif command == "all":
        success_count = 0
        for name in DATASETS:
            if download_dataset(name):
                success_count += 1
        print(f"\n完成: {success_count}/{len(DATASETS)} 个数据集下载成功")
    elif command in DATASETS:
        download_dataset(command)
    else:
        print(f"未知命令: {command}")
        print(f"可用命令: list, all, {', '.join(DATASETS.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()
