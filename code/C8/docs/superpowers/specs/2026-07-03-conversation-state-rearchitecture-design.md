# 多轮对话状态重构设计

## 背景

当前项目的多轮对话能力已经具备基础可用性，但真实链路中仍存在以下高频问题：

- 闲聊或无关输入可能污染会话状态
- 推荐列表模式与单菜模式没有被严格区分
- 指代消解过度依赖 `current_entity`
- 新话题切换容易被旧状态污染
- 推荐列表后的自然语言追问（如“它怎么做？”）无法稳定处理

现有实现本质上是“规则路由 + 规则补全 + 单实体状态 + 模型生成”。这套设计在简单追问场景下可工作，但在真实对话中缺乏足够的状态表达能力与歧义处理机制。

本次设计目标是将多轮对话从“补丁式字符串处理”升级为“结构化状态驱动 + 模型参与判定 + 受约束执行”的正式架构。

## 目标

本次重构聚焦以下四个目标：

1. 闲聊、无关问题、越界问题不再进入实体更新链路
2. 推荐列表模式与单菜模式分离建模
3. 指代消解不再由规则直接拍板，而是由模型基于结构化上下文参与判定
4. 多轮对话状态管理成为主流程正式环节，而不是检索前后的附属步骤

## 非目标

本次不包含以下内容：

- 重做知识库格式或重建数据 schema
- 重做向量索引实现
- 改变前端 UI 交互样式
- 重写现有生成模板整体风格
- 一次性替换全部旧逻辑，不保留迁移期开关

## 现状总结

当前真实链路位于以下模块：

- `code/C8/web_app.py`
- `code/C8/main.py`
- `code/C8/rag_modules/conversation_manager.py`
- `code/C8/rag_modules/generation_integration.py`

当前执行流程大致为：

1. Web 层接收请求
2. 解析序号引用
3. 路由与提取 `dish_name`
4. 基于 `current_entity` 做问题补全
5. 护栏判定
6. 检索
7. 生成
8. 写回对话状态

当前状态核心为：

- `messages`
- `current_entity`
- `current_intent`
- `last_recommendations`

当前问题集中在：

- `current_entity` 表达能力过弱
- 推荐列表状态没有正式进入自然语言引用解析
- 没有独立的“当前轮次是否允许进入状态系统”的前置准入层
- 规则已经在早期阶段过度做出语义结论

## 新架构概览

重构后的主流程调整为：

1. 序号引用解析
2. `Turn Qualification`
3. `Conversation State Builder`
4. `Reference Resolution`
5. `Resolution Guard`
6. `Execution Planning`
7. 执行动作
8. 条件状态写回

这意味着多轮对话逻辑将从“检索前的补全文本操作”升级为“决定本轮动作的主流程中枢”。

## 模块设计

### 1. Turn Qualification

职责：判断当前输入是否应该进入领域问答链路，以及本轮是否允许更新状态。

输出字段：

```json
{
  "turn_type": "domain_query | followup_query | recommendation_query | smalltalk | out_of_domain | uncertain",
  "should_retrieve": true,
  "should_update_topic_state": true,
  "should_update_entity_state": false,
  "should_run_reference_resolution": false,
  "response_mode": "retrieve_answer | ask_clarification | polite_direct_reply | graceful_refusal"
}
```

判定原则：

- `你好 / 谢谢 / 哈哈 / 你是谁` 归类为 `smalltalk`
- 明显与食谱无关的问题归类为 `out_of_domain`
- 推荐型问题归类为 `recommendation_query`
- 指代式、多轮追问型问题归类为 `followup_query`
- 规则和模型都无法稳定判断时归类为 `uncertain`

关键要求：

- `smalltalk` 与 `out_of_domain` 不进入实体写回
- `uncertain` 默认保守，不更新关键主题状态

### 2. Conversation State Builder

职责：将历史对话整理成结构化上下文，而不是让下游基于原始消息自行猜测。

建议生成四类结构：

```json
{
  "topic_state": {},
  "reference_state": {},
  "conversation_state": {},
  "resolution_constraints": {}
}
```

其中：

#### `topic_state`

```json
{
  "mode": "single_dish | recommendation_list | general_question | topic_switch_pending | none",
  "current_topic": null,
  "pending_topic": null,
  "last_topic_source": "explicit_query | resolved_followup | recommendation_selection | none"
}
```

#### `reference_state`

```json
{
  "current_dish": null,
  "recent_recommendations": [],
  "recent_topics": [],
  "last_confirmed_target": null
}
```

#### `conversation_state`

```json
{
  "last_user_query": "",
  "last_system_action": "none",
  "last_system_response_summary": "",
  "recent_turns": []
}
```

#### `resolution_constraints`

```json
{
  "allowed_reference_targets": [],
  "allow_default_selection": false,
  "must_clarify_if_ambiguous": true,
  "allow_topic_switch_detection": true
}
```

### 3. Reference Resolution

职责：在追问或模糊引用场景中，基于结构化状态让模型做受约束的判定。

核心原则：

- 规则层不再直接执行 `它 -> current_entity`
- 规则层负责收集候选对象与当前模式
- 模型负责在候选集合内做语义判定

模型输入应至少包括：

- 当前用户问题
- `topic_state`
- `reference_state`
- `conversation_state`
- `resolution_constraints`

模型输出格式：

```json
{
  "resolution_status": "resolved | ambiguous | topic_switch | no_reference_needed",
  "resolved_target": null,
  "target_source": null,
  "confidence": 0.0,
  "reason": "",
  "next_action": "retrieve_detail | ask_clarification | switch_topic | continue_general",
  "clarification_question": null
}
```

### 4. Resolution Guard

职责：校验模型输出合法性，防止模型越权猜测。

约束规则：

- 只能从 `allowed_reference_targets` 中选择引用对象
- 不允许凭空发明菜名
- 推荐列表模式默认不允许无证据默认选第一个
- 若 `must_clarify_if_ambiguous = true`，则必须返回澄清动作

### 5. Execution Planning

职责：将本轮准入结果与消解结果统一映射成最终动作。

可能动作：

- `retrieve_detail`
- `retrieve_list`
- `ask_clarification`
- `direct_smalltalk_reply`
- `guardrail_refusal`
- `switch_topic`

该层必须做到：

- 不再让路由结果直接驱动检索
- 而是让“会话上下文 + 判定结果”驱动最终执行动作

## 状态写回策略

当前系统的状态写回过于宽松，未来改为“条件写回”。

写回规则如下：

- `smalltalk`
  - 不写 `topic_state`
  - 不写 `reference_state.current_dish`

- `out_of_domain`
  - 不写主题状态
  - 不写实体状态

- `recommendation_query`
  - 写 `recent_recommendations`
  - 更新 `topic_state.mode = recommendation_list`
  - 不写 `current_dish`

- `explicit_single_dish`
  - 写 `current_dish`
  - 写 `current_topic`
  - 更新 `last_confirmed_target`

- `ambiguous_followup`
  - 不写新实体
  - 写入“待澄清动作”

- `resolved_followup`
  - 写 `last_confirmed_target`
  - 必要时更新 `current_dish`

## 与当前实现的差异

当前实现：

- 使用 `current_entity` 作为主状态
- 推荐列表只支持序号引用
- 代词消解靠规则替换
- 模型主要用于路由兜底、查询改写和回答生成

新方案：

- 使用结构化状态替代单实体状态
- 推荐列表进入正式引用候选集合
- 代词消解由模型基于结构判定
- 模型输出受系统约束校验
- 主流程正式引入“轮次准入”和“执行规划”

## 主流程变更

### 当前流程

1. 序号引用解析
2. 路由
3. 问题补全
4. 护栏
5. 检索
6. 生成
7. 状态写回

### 新流程

1. 序号引用解析
2. `Turn Qualification`
3. 构建结构化状态
4. 执行引用消解
5. 生成执行计划
6. 执行动作
7. 条件状态写回

结论：主流程必须变化，且变化属于架构层面的必要调整，而非局部优化。

## 兼容与迁移

建议重构时保留一段迁移期，避免一次性硬切全部旧逻辑。

迁移策略：

- 新增结构化状态，但保留旧状态字段兼容读取
- 为新引用消解链路提供 feature flag
- 在日志中并行记录旧逻辑与新逻辑的核心决策，便于比对
- 在集成测试稳定前，不删除旧逻辑的保底路径

## 测试策略

### 单元测试

新增测试覆盖：

- `Turn Qualification`
- `Conversation State Builder`
- `Resolution Guard`

### 集成测试

必须覆盖以下真实链路：

1. `今天吃什么？ -> 它怎么做？`
2. `你好 -> 蛋炒饭怎么做？`
3. `蛋炒饭怎么做？ -> 西湖醋鱼怎么样？`
4. `推荐三个菜 -> 第2个怎么做？`

### 真实慢测

新增一层全真实链路测试：

- 真实 app
- 真实 RAG 系统
- 真实知识库
- 真实会话状态
- 真实 LLM

该测试默认作为手动验收或慢测执行，不与快速单元测试混跑。

## 日志与可观测性

重构后日志至少应覆盖：

- 本轮 `turn_type`
- 是否允许更新状态
- 当前 `topic_state.mode`
- 候选引用对象集合
- 模型消解结果
- 约束校验结果
- 最终执行动作
- 写回状态摘要

这样失败时可以直接定位问题是在：

- 准入层
- 状态构建层
- 模型消解层
- 约束层
- 执行层

## 实施阶段

### Phase 1

引入 `Turn Qualification` 与条件状态写回。

目标：

- 闲聊/无关输入不再污染实体状态

### Phase 2

引入结构化状态构建器。

目标：

- 推荐列表模式与单菜模式被正式区分

### Phase 3

引入模型参与的引用消解与约束层。

目标：

- 替换掉直接 `它 -> current_entity` 的核心路径

### Phase 4

更新主流程并补真实集成测试。

目标：

- 用户真实失败路径被测试稳定覆盖

## 风险与应对

### 风险 1：模型输出波动

应对：

- 约束模型只能在候选集合内选
- 歧义场景默认澄清

### 风险 2：主流程改造范围较大

应对：

- 分阶段迁移
- 保留迁移期开关

### 风险 3：真实集成测试成本高

应对：

- 区分快速测试与慢测
- 将真实慢测作为关键回归与手动验收

## 验收标准

本次重构完成后，至少满足以下标准：

- `你好` 不会进入实体状态
- `今天吃什么？` 不会被记录为菜名
- 推荐列表后的 `它怎么做？` 不会乱指
- 新话题切换不会被旧 `current_entity` 污染
- 多轮决策关键节点可以通过日志完整追踪

## 结论

本次修改不是局部修补，而是将多轮对话从“检索前的小补全逻辑”升级为“主流程正式决策层”。

新的核心思想是：

- 规则负责整理事实与状态
- 模型负责在结构化上下文中做语义判定
- 系统负责约束模型输出并执行最终动作

这将使项目的多轮对话从脆弱的规则链路，演进为可扩展、可调试、可验证的正式对话架构。
