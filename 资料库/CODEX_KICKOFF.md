# DSH Runtime --- Codex Kickoff

将下面内容作为与 Codex 开始 Milestone 0 时的首条消息。

------------------------------------------------------------------------

我们准备正式开始 DSH Runtime 项目。

项目的设计背景、已经讨论确定的架构原则、Phase 1 范围和命名约定，都整理在
`CODEX_CONTEXT.md` 中。

请先完整阅读 `CODEX_CONTEXT.md`，然后检查当前 Repository
的实际代码结构。

这一轮先不要修改任何代码，也不要创建新的架构实现。

你的第一个任务是完成 **Milestone 0 --- Repository Analysis**。

请基于"实际代码"而不是仅根据 `CODEX_CONTEXT.md` 中的目标架构，分析：

1.  当前 Repository 的真实目录结构和模块职责。
2.  `api / core / services / retrievers / schemas`
    等现有模块之间的依赖关系。
3.  哪些现有代码可以直接保留。
4.  哪些能力可以被未来的 DSH Runtime 复用。
5.  哪些地方与计划中的 `dsh / runtime / plugins / workspace`
    存在职责重叠。
6.  当前有哪些明显的强耦合、环境耦合或物理路径耦合。
7.  如果引入 DSH Runtime，最小侵入式的演进路径是什么。
8.  哪些设计现在没有必要做，避免为了未来扩展而提前抽象。

特别注意以下原则：

-   DSH owns the loop.
-   Everything below DSH is bounded.
-   Everything is replaceable.
-   Memory stores semantics, not environment.
-   Local LLM is optional.
-   Plugins grow from real requirements.
-   Do not abstract before evidence.
-   Build the skeleton first.
-   不要为了"架构漂亮"重写已有可用代码。
-   不要在没有第二个真实实现之前引入 Factory / Provider / 多层
    Interface。

分析完成后，请先向我汇报你的发现，并给出你建议的最小迁移方案。

暂时不要实施迁移。

等我确认 Milestone 0 的分析结果之后，我们再一起决定 Milestone 1 --- DSH
Runtime Skeleton 应该如何落地。
