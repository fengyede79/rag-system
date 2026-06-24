# 评测体系

这个目录用于给菜谱 RAG 项目提供一套可重复执行的评测基线。

包含三部分：

- `testset.json`
  统一格式的测试集，覆盖单轮、多轮、模糊相关、时间型未知、无关问题和边界混合问题。
- `dataset_builder.py`
  从现有菜谱中抽取代表性样本，并用模板扩展成 100 到 150 条测试样本。
- `run_evaluation.py`
  实际运行系统问答，生成规则评分结果，并可选接入大模型裁判评分。

建议用法：

```bash
python evaluation/run_evaluation.py --build-dataset --limit 12
python evaluation/run_evaluation.py --limit 12 --use-llm-judge
```

默认输出：

- `evaluation/testset.json`
- `evaluation/latest_report.json`
