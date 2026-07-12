"""
RAGAS 风格的 RAG 评测脚本。

使用 DeepSeek 作为评判 LLM，评测指标：
- Faithfulness（答案忠实度）：答案中的每个声明是否被上下文支持
- Answer Relevancy（答案相关性）：答案与问题的相关程度
- Context Precision（上下文精确度）：检索到的上下文中相关比例
- Context Recall（上下文召回率）：标准答案被上下文覆盖的比例

用法：
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py
    HF_ENDPOINT=https://hf-mirror.com PYTHONPATH=. uv run python scripts/eval_ragas.py --dataset data/eval/custom.json
"""

import argparse
import json
import time
from typing import List, Dict

from openai import OpenAI

from app.core.config import settings
from app.rag.retriever import get_retriever
from app.rag.reranker import get_reranker
from app.rag.generator import get_generator

# ─── DeepSeek 评判 LLM ───────────────────────────────────────────────

judge_client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_BASE_URL,
)


def llm_judge(prompt: str) -> str:
    """调用 DeepSeek 进行评判。"""
    resp = judge_client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=1024,
    )
    return resp.choices[0].message.content.strip()


# ─── 指标计算 ─────────────────────────────────────────────────────────

def compute_faithfulness(answer: str, contexts: List[str]) -> float:
    """Faithfulness：答案中的声明是否被上下文支持。

    流程：提取答案中的声明 → 逐条检查是否被上下文支持 → 返回支持比例。
    """
    context_block = "\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))

    prompt = f"""请分析以下回答中的每个独立声明，并判断每个声明是否被提供的上下文支持。

【上下文】
{context_block}

【回答】
{answer}

请以 JSON 数组格式输出，每个元素包含：
- "claim": 声明内容
- "supported": true 或 false（是否被上下文直接支持）

只输出 JSON 数组，不要输出其他内容。示例：
[{{"claim": "...", "supported": true}}, {{"claim": "...", "supported": false}}]"""

    try:
        result = llm_judge(prompt)
        # 提取 JSON 部分
        start = result.find("[")
        end = result.rfind("]") + 1
        if start == -1 or end == 0:
            return 0.5
        claims = json.loads(result[start:end])
        if not claims:
            return 1.0
        supported = sum(1 for c in claims if c.get("supported", False))
        return supported / len(claims)
    except Exception as e:
        print(f"  [Faithfulness 评测异常: {e}]")
        return 0.5


def compute_answer_relevancy(question: str, answer: str) -> float:
    """Answer Relevancy：答案与问题的相关程度（0-1）。

    使用 LLM 对相关性打分。
    """
    prompt = """请评估以下回答与问题的相关性，给出 0-10 的整数分数。

评分标准：
- 0-2：回答完全无关或答非所问
- 3-4：回答部分相关但有大量无关内容
- 5-6：回答基本相关但不够精准
- 7-8：回答相关且较为精准
- 9-10：回答高度相关、精准、完整

【问题】
{question}

【回答】
{answer}

只输出一个 0-10 的整数分数，不要输出其他内容。"""

    try:
        result = llm_judge(prompt.format(question=question, answer=answer))
        score = int("".join(c for c in result if c.isdigit())[:2])
        return min(max(score / 10.0, 0.0), 1.0)
    except Exception as e:
        print(f"  [Answer Relevancy 评测异常: {e}]")
        return 0.5


def compute_context_precision(retrieved_contexts: List[str], ground_truth_contexts: List[str]) -> float:
    """Context Precision：检索到的上下文中，与标准答案上下文相关的比例。

    使用简单的文本重叠度判断相关性。
    """
    if not retrieved_contexts:
        return 0.0

    relevant_count = 0
    for ctx in retrieved_contexts:
        for gt_ctx in ground_truth_contexts:
            # 计算字符级重叠率
            overlap = sum(1 for ch in ctx if ch in gt_ctx)
            if overlap / max(len(ctx), 1) > 0.3:
                relevant_count += 1
                break

    return relevant_count / len(retrieved_contexts)


def compute_context_recall(retrieved_contexts: List[str], ground_truth: str) -> float:
    """Context Recall：标准答案中的关键信息被检索上下文覆盖的比例。

    使用 LLM 判断标准答案中的每个要点是否被上下文覆盖。
    """
    context_block = "\n".join(f"[{i+1}] {c}" for i, c in enumerate(retrieved_contexts))

    prompt = f"""请分析以下标准答案中的每个关键要点，并判断每个要点是否被检索到的上下文覆盖。

【检索到的上下文】
{context_block}

【标准答案】
{ground_truth}

请以 JSON 数组格式输出，每个元素包含：
- "point": 关键要点
- "covered": true 或 false（是否被上下文覆盖）

只输出 JSON 数组，不要输出其他内容。示例：
[{{"point": "...", "covered": true}}, {{"point": "...", "covered": false}}]"""

    try:
        result = llm_judge(prompt)
        start = result.find("[")
        end = result.rfind("]") + 1
        if start == -1 or end == 0:
            return 0.5
        points = json.loads(result[start:end])
        if not points:
            return 1.0
        covered = sum(1 for p in points if p.get("covered", False))
        return covered / len(points)
    except Exception as e:
        print(f"  [Context Recall 评测异常: {e}]")
        return 0.5


# ─── RAG 管线调用 ──────────────────────────────────────────────────────

def run_rag_pipeline(question: str) -> Dict:
    """执行完整的 RAG 管线：检索 → 重排序 → 生成。"""
    retriever = get_retriever()
    reranker = get_reranker()
    generator = get_generator()

    # 检索
    candidates = retriever.search(question, top_k=10)
    # 重排序
    reranked = reranker.rerank(question, candidates)
    # 过滤低相关性
    relevant = [r for r in reranked if r.get("rerank_score", 0) >= settings.MIN_RELEVANCE_SCORE]
    top_contexts = relevant[:5] if relevant else reranked[:5]

    # 生成
    result = generator.generate(question, top_contexts)

    return {
        "answer": result["answer"],
        "contexts": [c["content"] for c in top_contexts],
        "intent": result["intent"],
    }


# ─── 主流程 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAGAS 风格 RAG 评测")
    parser.add_argument(
        "--dataset", default="data/eval/legal_eval_dataset.json",
        help="评测数据集路径（JSON 格式）",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细输出")
    args = parser.parse_args()

    # 加载数据集
    with open(args.dataset, encoding="utf-8") as f:
        dataset = json.load(f)

    print("=" * 60)
    print("RAGAS 风格 RAG 评测")
    print("=" * 60)
    print(f"数据集: {args.dataset}")
    print(f"样本数: {len(dataset)}")
    print(f"LLM: {settings.LLM_MODEL}")
    print("=" * 60)

    results = []
    metrics_summary = {
        "faithfulness": [],
        "answer_relevancy": [],
        "context_precision": [],
        "context_recall": [],
    }

    for i, sample in enumerate(dataset):
        question = sample["question"]
        ground_truth = sample["ground_truth"]
        gt_contexts = sample.get("ground_truth_contexts", [ground_truth])

        print(f"\n[{i+1}/{len(dataset)}] {question}")

        # 执行 RAG 管线
        rag_result = run_rag_pipeline(question)
        answer = rag_result["answer"]
        retrieved_contexts = rag_result["contexts"]

        if args.verbose:
            print(f"  回答: {answer[:100]}...")

        # 计算指标
        faith = compute_faithfulness(answer, retrieved_contexts)
        relevancy = compute_answer_relevancy(question, answer)
        precision = compute_context_precision(retrieved_contexts, gt_contexts)
        recall = compute_context_recall(retrieved_contexts, ground_truth)

        metrics_summary["faithfulness"].append(faith)
        metrics_summary["answer_relevancy"].append(relevancy)
        metrics_summary["context_precision"].append(precision)
        metrics_summary["context_recall"].append(recall)

        print(f"  Faithfulness: {faith:.3f} | Relevancy: {relevancy:.3f} | "
              f"Precision: {precision:.3f} | Recall: {recall:.3f}")

        results.append({
            "question": question,
            "ground_truth": ground_truth,
            "answer": answer,
            "retrieved_contexts": retrieved_contexts,
            "metrics": {
                "faithfulness": faith,
                "answer_relevancy": relevancy,
                "context_precision": precision,
                "context_recall": recall,
            },
        })

        # 避免 API 限流
        time.sleep(1)

    # 汇总
    print(f"\n{'=' * 60}")
    print("评测汇总")
    print(f"{'=' * 60}")

    for metric, values in metrics_summary.items():
        avg = sum(values) / len(values) if values else 0
        print(f"  {metric:25s}: {avg:.3f}")

    overall = sum(sum(v) / len(v) for v in metrics_summary.values()) / len(metrics_summary)
    print(f"  {'overall (avg)':25s}: {overall:.3f}")
    print(f"{'=' * 60}")

    # 保存详细结果
    output_path = "data/eval/eval_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {m: sum(v) / len(v) for m, v in metrics_summary.items()},
            "overall": overall,
            "details": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
