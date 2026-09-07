# Codex Runtime Behavior Verification

验证日期：2026-09-05  
调查对象：`D:\DeepSeekHarness\deepseek-harness`  
验证范围：`packages/subagent/subagent-codex` 的现有 `real-product.spec.ts`，加上本机 Codex/Node/config 只读检查。  
重要边界：测试启动的是实际 `@openai/codex` app-server 进程，但模型 Responses API 使用 loopback fixture；因此本文的“实验确认”是 Codex app-server、协议、进程与 provider 行为确认，不是当前云端真实模型质量或账户服务行为确认。

## 1. Executive Summary

在兼容的 Node 24.19.0 下，上游现有 real-product 测试 7/7 通过。测试确认 provider 实际启动固定的 package-local `@openai/codex@0.149.1` wrapper，以 `app-server --stdio` 运行；调用经过 initialize、ephemeral thread、单次 turn，并由 `turn/completed` 或进程/取消路径结束。

已直接观察到：正常 run 在显式 `run.dispose()` 后进程树 quiescent；dangerous mode 可以在临时 workspace 中写文件；`never` 模式拒绝升级命令且不产生文件；取消会使 run 以 `aborted` 结束并最终回收进程树；进程被直接终止时 provider 返回安全的 process diagnostic。没有实验证据表明 provider 自带 invocation wall-clock timeout、resume 或 side-effect rollback。

现有测试并未覆盖所有文件操作、cwd 外路径、子进程创建、真实云端模型输出、phase:null、完整原始 JSON-RPC 抓包或长期挂起的默认 timeout；这些保持 Unknown。

## 2. Environment Snapshot

### 2.1 Runtime and installation

| Item | Observed value | Classification |
|---|---|---|
| Host `codex` on PATH | `codex-cli 0.153.0` | Confirmed by local command |
| DeepSeekHarness package | `@openai/codex@0.149.1` | Confirmed by package.json and test assertion |
| Resolved package.json | `D:\DeepSeekHarness\deepseek-harness\node_modules\.pnpm\@openai+codex@0.149.1\node_modules\@openai\codex\package.json` | Confirmed by `createRequire().resolve()` |
| Resolved wrapper | `...@openai\codex\bin\codex.js` under the same 0.149.1 package | Confirmed by resolution and test `codexEntry` |
| Test Node | `C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`, `v24.19.0` | Confirmed by local command |
| Host default Node | `D:\Program Files\node-js\node.exe`, `v20.14.0` | Confirmed by local command |
| Provider argv | `[process.execPath, codexEntry, 'app-server', '--stdio']` | Confirmed by `real-product.spec.ts` assertion |
| Host shell command | `codex --version` resolved the separately installed 0.153.0 binary | Confirmed by local command |

The upstream root declares Node `^22.19.0 || >=24.0.0`; running its tests under host Node 20 failed before app-server startup because `Promise.withResolvers` was unavailable. No source or test was changed; rerunning with bundled Node 24 fixed the test-runtime incompatibility.

### 2.2 Configuration and environment

The current user config is `C:\Users\Administrator\.codex\config.toml`; the observed non-secret settings include `model = "gpt-5.6-luna"`, `sandbox_mode = "workspace-write"`, `web_search = "indexed"`, and `windows.sandbox = "unelevated"`. `CODEX_HOME` was not set in the ordinary shell; the Codex desktop configuration includes a `CODEX_HOME` reference for its node-repl environment.

The real-product tests intentionally create a disposable `codex-home/config.toml` and pass explicit environment entries: `CODEX_HOME`, `HOME`, `XDG_CONFIG_HOME`, `PATH`, proxy overrides, and a fixture API key. The provider subprocess applies its credential/`DSH_*` scrub first and explicit `env` afterwards. The test fixture uses `requires_openai_auth = false` and loopback base URLs, so no user credential is required for those tests.

## 3. Experiments Performed

### EXP-2A2-01 — package/version/argv

**Question:** Which Codex package and executable does the provider actually use?

**Setup:** DeepSeekHarness package-local dependency; compatible Node 24.

**Action:** Resolve `@openai/codex/package.json`, run the package wrapper with `--version`, and run the existing real-product assertion.

**Observed Result:** Package/wrapper version is `0.149.1`; wrapper reports `codex-cli 0.149.1`; provider spawn spec is Node executable + package wrapper + `app-server --stdio`.

**Classification:** Confirmed by Experiment / Confirmed by Source and Config.

### EXP-2A2-02 — real app-server provider suite

**Question:** Does the provider work through a real app-server process and the expected protocol lifecycle?

**Action:**

```text
PATH=<bundled Node 24>;<bundled pnpm>;<existing PATH>
pnpm exec vitest run packages/subagent/subagent-codex/tests/real-product.spec.ts \
  --config vitest.config.ts --reporter=verbose
```

**Observed Result:** 1 test file passed; 7 tests passed; duration 31.61s. The suite observed real package startup, fixture Responses requests, provider results, handle outcomes, and `waitForExit()` quiescence.

**Classification:** Confirmed by Experiment, with loopback model-service boundary.

### EXP-2A2-03 — permission denial

**Question:** Does `never` prevent an escalated command/file side effect?

**Setup:** Disposable workspace; fixture instructs a command request; provider mode `never`.

**Observed Result:** Codex emitted an approval-related request; Codex logged that approval policy was Never and rejected escalated permissions; provider returned an error with safe `stage: turn; category: product-error`; the requested side-effect file did not exist.

**Classification:** Confirmed by Experiment.

### EXP-2A2-04 — explicit dangerous write

**Question:** Can an explicitly selected dangerous mode mutate its disposable workspace?

**Setup:** Disposable workspace; provider mode `dangerously-bypass-approvals-and-sandbox`; fixture returns a shell command that writes one file inside that workspace.

**Observed Result:** Run completed; target file existed and contained `bypass`. This confirms a real Codex process executed the requested write in the isolated workspace under the explicit dangerous mode.

**Classification:** Confirmed by Experiment.

### EXP-2A2-05 — process failure

**Question:** What happens when the live child is terminated externally?

**Setup:** Disposable workspace; fixture holds the Responses stream; test calls `harness.handles[0].terminate()`.

**Observed Result:** `child.done` produced exit facts; provider settled the run with empty output, `stopReason: error`, and a safe process diagnostic containing category `process` and the observed exit code/signal. The handle then reached `waitForExit() === true`.

**Classification:** Confirmed by Experiment.

### EXP-2A2-06 — cancellation

**Question:** Does abort settle the run and leave the app-server tree quiescent?

**Setup:** Disposable workspace; fixture holds the Responses stream; test aborts the request controller.

**Observed Result:** Run settled with `stopReason: aborted`; the test disposed the run and `waitForExit()` confirmed the process handle quiescent. The test does not independently capture the outbound `turn/interrupt` frame, so the wire-level receipt of that frame remains source-confirmed, not experiment-confirmed.

**Classification:** Run/result/process cleanup confirmed by Experiment; exact interrupt-frame receipt remains Unknown by Experiment.

### EXP-2A2-07 — service retry / timeout-relevant observation

**Question:** Does the app-server show an observable internal request retry or default execution timeout?

**Observed Result:** During the service/early-exit test, Codex stderr showed `stream disconnected - retrying sampling request (1/5 ...` through `(5/5 ...)`; that test completed in about 25.6s. This is direct evidence of an internal bounded retry sequence for the simulated stream disconnect. It is not evidence of a general wall-clock execution timeout. No provider invocation timeout was observed.

**Classification:** Retry observation confirmed by Experiment; general default execution timeout remains Unknown.

## 4. Lifecycle Verification

```text
provider start
  → real package-local app-server process starts
  → initialize / initialized
  → thread/start with ephemeral=true
  → turn/start with one text input
  → turn/completed or failure/cancellation
  → run result settlement
  → run.dispose()
  → terminate process tree / waitForExit()
```

The test suite confirms that every accepted run has a real subprocess handle and that the provider waits for whole-tree quiescence after disposal. The “one process, one ephemeral thread, one turn” shape is confirmed by source plus the suite's one-request/one-run setup and assertions. The tests do not independently dump every JSON-RPC frame, so exact frame order remains primarily source-confirmed.

Normal completion does not by itself serve as the teardown observation in the tested provider path: the tests explicitly call `run.dispose()` and then assert quiescence. The source's teardown closes the wire, ends stdin, terminates the child tree, waits for exit, and awaits `child.done`.

No Codex background/descendant process was observed in these runs. The subprocess implementation is nevertheless designed to manage descendants as a tree. “No descendant was observed” must not be upgraded to “Codex never creates descendants.”

## 5. Workspace / Side Effects

| Mode / experiment | Before state | Action requested | After state | Classification |
|---|---|---|---|---|
| `never` | Disposable workspace had no `approval-side-effect` | Request an escalated command/file operation | File absent; error diagnostic safe | Confirmed by Experiment |
| `dangerously-bypass-approvals-and-sandbox` | Disposable workspace had no `bypass-side-effect` | Execute a shell command writing `bypass` | File present with content `bypass` | Confirmed by Experiment |
| Read existing file | Not tested in this suite | — | — | Unknown |
| Modify existing file | Not tested in this suite | — | — | Unknown |
| Delete file | Not tested in this suite | — | — | Unknown |
| Create child process | Not tested directly | — | — | Unknown |
| Access cwd-outside path | Not tested directly | — | — | Unknown |

The dangerous write confirms side effects are possible when that mode is explicitly selected. No test evidence shows rollback after cancellation or failure; source and package documentation indicate no rollback behavior, but a cancellation-with-partial-write experiment was not performed.

## 6. Cancellation / Interrupt

**Source-confirmed behavior:** request abort invokes local cancellation, calls `CodexAppServerWire.interrupt()` when thread and turn IDs exist, and invokes the subprocess termination path. `turn/interrupt` is best effort; local settlement and process teardown remain authoritative.

**Experiment-confirmed behavior:** the cancellation test settles as `aborted`, and the process handle reaches whole-tree quiescence after disposal.

**Not directly observed:** a captured protocol transcript proving the `turn/interrupt` request was accepted by app-server; the final Codex turn status after that request; whether a real model had already performed a partial workspace mutation before cancellation.

## 7. Timeout-Relevant Observations

- There is no provider invocation wall-clock timeout in the exercised code path.
- `disposeGraceMs = 2000` in the tests is a process termination/cleanup grace, not execution timeout.
- The simulated stream-disconnect path showed 5 internal sampling retries over roughly 25.6s before the test reached its failure result. This is observable retry behavior, not a general execution deadline.
- A deliberately long-running turn was not allowed to run against a real remote model; no default Codex execution timeout was directly established.

**Classification:** provider timeout absence is Confirmed by Source; Codex default execution timeout is Unknown; internal retry behavior is Confirmed by Experiment for the simulated disconnect.

## 8. Result / Event Boundary

| Layer | Observed / known behavior | Classification |
|---|---|---|
| Codex emits | Real app-server emits JSON-RPC responses/notifications; in tested function-call paths it emits tool-related activity and terminal turn data | Confirmed by Source + product suite behavior |
| Harness observes | `CodexAppServerWire` observes matching thread/turn notifications, agent messages, terminal status, approval/input requests, and diagnostics | Confirmed by Source |
| Harness returns | Final `agentMessage` text with `phase:'final_answer'`; source fallback is latest `phase:null`; failed runs return safe diagnostic; raw stderr and process/tool details are not returned as parent output | Confirmed by Source; final answer path confirmed by Experiment |
| `final_answer` | Normal fixture completion returned the expected final text through provider | Confirmed by Experiment |
| `phase:null` | Compatibility fallback exists in source, but no test in this run emitted only `phase:null` | Source-confirmed / Experiment Unknown |
| commentary/reasoning/tool activity | Wire recognizes commentary and tool-related items, but provider output collector excludes them from returned result | Confirmed by Source |
| usage/token data | Fixture Responses payload contained usage, but this provider test did not return usage to the parent result | Fixture + Source confirmed; Codex real-service usage behavior not established |
| workspace diff/changed files | No diff is collected or returned by provider; dangerous-write test checks the filesystem directly | Confirmed by Source + Experiment |
| stderr | Raw app-server stderr was forwarded to host stderr; observed warnings included unknown fixture model, PowerShell shell snapshot warning, approval rejection, and retry messages | Confirmed by Experiment |

## 9. Failure Observations

| Trigger | Protocol / process behavior | Turn/result | Harness classification |
|---|---|---|---|
| Missing platform payload | Wrapper cannot start usable native payload | Startup failure | Safe `initialize/unknown`; no host CLI fallback (suite passed) |
| Permission denial under `never` | Approval request is declined/denied; simulated service then terminates turn | Non-completed turn | `turn/product-error` plus safe diagnostic |
| Simulated service error 503 | Responses stream/service reports error; Codex retries stream in observed path | Failure | `turn/service` safe diagnostic |
| Direct process termination | App-server closes before normal terminal result | Process outcome available | `process/process` diagnostic with exit facts |
| Explicit cancellation | Local abort + interrupt attempt + process teardown | Run resolves aborted | `aborted` |
| Completed without nonblank answer | Source checks collected output | Error | `invalid-result` |
| Unknown server request | Source fails closed | Error | Protocol/product error path |
| Invalid cwd | Source rejects missing cwd or cwd resolution failure before normal publication | No published run | Startup error; exact OS behavior for malformed existing path not experimentally tested |
| Invalid request | Text-only/non-empty validation rejects non-text, empty, or all-whitespace input | No run | Synchronous input validation error |

An unavailable/invalid model was not tested against a real remote provider. The test uses intentionally unknown fixture model names and observed Codex fallback metadata warnings, but that is not equivalent to a production invalid-model failure.

## 10. Session / Resume Findings

- Current DeepSeekHarness provider creates a fresh app-server and ephemeral thread per accepted run, then sends one `turn/start`; no resume or continuation call exists in the provider path. Confirmed by source and package test shape.
- The current test suite does not establish whether the Codex product, outside this provider, supports a reusable thread/session continuation API. That remains Unknown for this investigation.
- No evidence justifies a DSH resume contract.

## 11. Comparison with 2-A.1

| 2-A.1 Finding | 2-A.2 Observation | Result |
|---|---|---|
| Package-local wrapper, `app-server --stdio` | Wrapper resolved to package `@openai/codex@0.149.1`; `codex-cli 0.149.1`; 7/7 suite passed | Confirmed |
| Parent Session cwd is used | Existing suite creates disposable workspace and provider runs against it; dangerous write lands there | Confirmed |
| JSON-RPC stdin/stdout path | Real app-server-backed suite completes through provider; source still supplies exact frame details | Confirmed |
| stderr is auxiliary and forwarded | Real stderr warnings/retry/approval messages appeared in test output without changing the safe parent result boundary | Confirmed |
| Cancellation + tree teardown exist | Cancellation and direct termination tests passed; handles reached quiescence | Confirmed |
| No invocation wall-clock timeout | No timeout observed; simulated service path had internal retries | Refined: internal retry exists, general execution timeout still Unknown |
| One process/thread/turn, no resume | Real suite passed fresh-run cases; no continuation path exists | Confirmed |
| Dangerous permissions may mutate workspace | Dangerous write created a file; `never` prevented the denial case | Confirmed |
| Workspace diff not returned / no rollback | No diff returned; rollback not tested directly | Refined: diff absence confirmed, rollback still source/documentation-based |
| Final text only | Expected final sentinel returned; no phase:null experiment | Refined: final-answer path confirmed, fallback remains untested |
| Process outcome participates in failure | Direct termination returned safe process diagnostic with exit facts | Confirmed |

No contradiction with the 2-A.1 source investigation was found.

## 12. Remaining Unknowns

- Real cloud model behavior, model-specific tool decisions, and production authentication failures.
- Exact `turn/interrupt` wire acceptance and final product turn status under real cancellation.
- Long-running real turn behavior and any Codex default wall-clock deadline.
- Whether Codex creates descendants in particular tool/model/configuration paths.
- Read/modify/delete operations, child-process creation, and cwd-outside access under each permission/sandbox mode.
- Partial workspace mutations left after cancellation or process kill.
- `phase:null` fallback under a real app-server event sequence.
- Complete raw JSON-RPC event ordering and all usage/token fields as seen by the wire.
- Exact invalid-cwd OS error for an existing-but-invalid directory/path.
- Codex product-level session/thread continuation semantics outside this provider.

## 13. Evidence-backed Requirements

From the combined source/config and experiment evidence, DSH integration will need to account for:

- process lifetime and whole-tree teardown;
- parent-session cwd / workspace identity;
- explicit permission and sandbox mode;
- cancellation as both protocol interrupt attempt and process termination;
- distinction between execution timeout policy and disposal grace;
- process outcome separate from product/protocol failure;
- bounded result boundary: final text and safe diagnostics rather than raw stream passthrough;
- workspace side effects and the absence of automatic rollback;
- explicit no-resume behavior for the current provider path.

These are evidence-backed concerns only; no formal abstraction or interface is proposed here.

## 14. Still Not Justified

The following remain unsupported by this investigation and are not created:

- `AgentExecutor`
- `CLIExecutionCapability`
- `CodexAdapter`
- `CodeBuddyAdapter`
- generic `ExternalAgent` interface
- resume contract
- streaming contract
- Provider Framework
- Factory
- Event Bus
- Workflow DSL

## Verification Record

- Host Node 20 attempt: failed before experiment execution with `Promise.withResolvers is not a function`.
- Compatible Node 24 rerun: `7 passed`; no source/test modifications.
- No DSH Runtime production code was changed.
- No DeepSeekHarness production behavior was changed.
- All test workspaces were disposable and owned by the upstream test cleanup.

