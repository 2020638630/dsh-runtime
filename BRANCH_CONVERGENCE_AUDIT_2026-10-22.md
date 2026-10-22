# 双仓分支收敛审查 — 2026-10-22

本审查先只读取本地历史与远端引用，之后完成 Runtime 候选及默认分支的普通快进推送。没有 fetch、merge、切换原工作树、清理或删除分支。两个原工作树的 Git 可见改动分别为 Runtime 16 项、Harness 106 项；这些未提交内容必须继续保留。D2 ExecuteGate 仍为 `NOT_CLAIMED`。

## 远端基线与已验证产物

| 仓库 | 远端默认分支（现场 `ls-remote --symref`） | 当前可用基线 | 未并入默认分支的内容 |
| --- | --- | --- | --- |
| 私有 Runtime | 审查时 `master` → `b57a829`；随后普通快进至 `aa3592c` | 官方 Harness 插件所用 Runtime 执行源码快照为 `fdaef4b`；当前候选与默认分支均包含该源码 | 先核对候选远端 SHA 并普通快进至 `aa3592c`，再核对 `master=b57a829`、候选 `aa3592c` 及祖先关系，以普通推送将 `master` 晋升至 `aa3592c`；未强推。 |
| 私有 Harness | `integration/dsh-runtime-d1-q2-closeout` → `819dc46` | 私有 Windows 0.2.1 回退分支为 `codex/vis-private-win-stable-prep-20261020` → `08d207d` | 私有 0.2.1 分支比默认分支前进 5 提交；私有默认分支比未修改官方 `0.2.1-rc.2` 基线 `687f282` 前进 64 提交，文件差异 241 个。 |

Harness 私有远端目前有 18 个分支，其中 7 个是 `codex/` 或 `integration/` 项目分支，其余为历史 Dependabot 分支。私有默认分支包含 Runtime 集成、Web 证据抽屉、Windows 发布修复和 D2 工程治理历史。独立插件的 Host/Web 与 Runtime 用户功能已经在未修改的官方 `@deepseek-ai/dsh@0.2.1-rc.2` 上验收；因此这些私有核心改动不再是本机插件试用的运行前提。私有分支仍提供 0.2.1 日常回退和可寻址工程历史，不能直接删除。

`codex/d2-c10-c3-qualification-20261014` 原工作树的已提交头是私有默认分支的祖先，但其 106 项 Git 可见未提交/未跟踪内容仍只在原工作树。`private/codex/d2-replayonly-repair-20261010` 另有 5 个未进入当前默认分支的提交；`private/codex/upstream-sync-20261012` 另有 1 个未进入当前默认分支的提交。它们属于保留/归档审查对象，不属于本轮用户插件路线。D2 不得因分支收敛被误报为已完成。

## 建议执行顺序

1. Runtime 候选已完成 532/532 全量 Python 测试，执行源码与 `fdaef4b` 试用快照一致；候选及私有 `master` 已普通快进至 `aa3592c`。原 Runtime 脏工作树仍保持原样。后续如继续推进，以新远端 SHA 为准。
2. 把官方 Harness 插件私有安装材料固定在可访问的私有发布位置，至少保留插件 TGZ、Runtime ZIP、哈希清单、安装/回退说明。当前本机材料在 `D:\DeepSeekHarness\vis-stable-release-artifacts\official-runtime-kit-20261022`，无凭据、会话或 Home。用另一目标机器/账户验收模型与登录态后再称跨环境稳定版。
3. 私有 Harness 0.2.1 保留为回退，直到官方插件并行使用稳定且负责人不再依赖该入口。之后为默认分支、私有 0.2.1、D2 独有提交制作不可变标签或归档引用，并核对所有 106 项原工作树内容已另行保存或明确保留；再提出具体远端分支删减清单。删除前须再次核对远端引用与依赖，不能把当前本地引用当成最新远端事实。

当前结论：**可以停止继续改私有 Harness 核心并以官方包 + 外部插件推进；现在还不宜把两个私有仓库压成单一远端分支或删除历史分支。** Runtime 已晋升默认分支；私有 Harness 0.2.1 和 D2 历史/脏工作树仍需保留。
