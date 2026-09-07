# CodeBuddy Primary Execution + Codex Verification
# Workflow Feasibility / Contract Investigation

Date: 2026-09-07
Scope: investigate feasibility and the smallest evidence-backed future boundary
Implementation: none

## 1. Product requirement restated

The supplied product requirement is:

    Caller -> DSH task submission and governance
           -> CodeBuddy primary executor
           -> settled execution result and/or repository effect
           -> DSH Planner post-execution evaluation
           -> Codex independent final verifier, preferably read-only
           -> settled verification result
           -> DSH Planner terminal Decision
           -> DSH-owned TaskState terminal transition

The business roles are:

- CodeBuddy is the builder/executor. It performs coding work, repository
  mutation, and potentially command/test execution.
- Codex is the independent reviewer/verifier. It inspects the resulting
  workspace and reports whether the requested work is acceptable.
- DSH remains the business-loop, governance, orchestration, and final
  completion owner.

The user's available/reimbursed CodeBuddy usage is recorded as a product,
operational, and economic constraint. It justifies considering CodeBuddy as
the primary executor even where Codex capability overlap exists. It does not
justify a generic provider-routing abstraction.

No Milestone 5 is declared by this investigation.

## 2. Exact CodeBuddy product and invocation surface

The installed product is identified from local environment evidence:

    package: @tencent-ai/codebuddy-code
    package version: 2.143.0
    product name: CodeBuddy
    platform: CLI
    command: codebuddy / cbc
    package path:
      D:\Program Files\node-js\node_modules\@tencent-ai\codebuddy-code

The command entrypoint was found at:

    D:\Program Files\node-js\codebuddy.cmd

The PowerShell shim could not run because this environment disables script
execution. The .cmd launcher ran successfully:

    codebuddy.cmd --version
    2.143.0

Its help output identifies these relevant surfaces:

- Interactive mode is the default.
- -p / --print is a non-interactive mode that prints a response and exits.
- --output-format supports text, json, and stream-json for print mode.
- --input-format supports text and stream-json for print mode.
- --max-turns bounds the number of agentic turns.
- --permission-mode supports default, acceptEdits, bypassPermissions, plan,
  dontAsk, and auto.
- --dangerously-skip-permissions bypasses permission prompts and is explicitly
  high risk.
- --tools, --allowedTools, and --disallowedTools constrain tool access.
- --add-dir grants additional directory access.
- --sandbox supports container or E2B execution.
- --acp exposes Agent Client Protocol over stdio or streamable HTTP.
- --serve exposes Web UI, REST API, or ACP over HTTP SSE.
- --no-session-persistence disables session persistence.

The installed package also exposes an in-process server surface through its
server entrypoint. The local declaration describes:

    start(options) -> Server
    query(sessionId, input, options) -> QueryTicket
    interrupt(sessionId) -> Promise<void>
    subscribe(sessionId, listener)
    close(sessionId)

Its QueryOptions include cwd, permissionMode, model, maxTurns,
abortController, additionalDirectories, persistSession, sandbox, settings,
authentication, and tool controls. QueryResult includes runId, stopReason,
assistantText, and an optional errorMessage. The declared stop reasons are
completed, aborted, and error. The ticket resolves after the run settles, and
interrupt is documented as turn-level cancellation that resolves after
settlement.

This establishes a concrete automation-friendly product surface. It does not
yet select the future DSH integration surface. The likely choices are:

1. spawn the CLI in print mode as one bounded child-process invocation;
2. use a small Node-side wrapper around the in-process server surface; or
3. use ACP/serve, which introduces a longer-lived protocol/session boundary.

The repository currently contains no Python SDK binding or CodeBuddy wrapper,
so the choice remains an implementation-level open question.

## 3. CodeBuddy bounded native contract evidence

### Repository and installed-product evidence

Repository evidence:

- There is no CodeBuddy Plugin, registration, test, or repository-local
  configuration.
- Existing Runtime Plugin.execute() accepts one bounded invocation and returns
  one PluginResult.
- Existing Executor owns timeout, cancellation cleanup, settlement, and
  StopReason normalization.
- The older project context and handoffs mention CodeBuddy as a possible
  capability, but do not define a concrete task or contract.

Installed-product evidence:

- package.json describes CodeBuddy Code as a terminal coding tool that can
  understand codebases, edit files, run terminal commands, and handle
  workflows.
- The CLI has a non-interactive print mode, bounded max-turns, structured
  output modes, cwd-by-process launch semantics, permission modes, tool
  allow/deny controls, sandbox options, and session persistence controls.
- product.json identifies a CLI product named CodeBuddy, SaaS deployment,
  official endpoints, and CLI external-link authentication. It identifies
  bearer-token authentication metadata but does not prove that this machine
  is authenticated for a model run.
- The installed package's server type declarations expose settled query
  results and turn interruption, but those declarations are not yet a DSH
  integration or a live execution proof.

### Contract classification

    Invocation:
      Concrete CLI and in-process server surfaces identified.
      Non-interactive invocation is supported.

    Input:
      Prompt/input, process cwd or query cwd, model, max turns, permission
      mode, tool restrictions, additional directories, sandbox, environment,
      and authentication controls are available.

    Output:
      CLI text, JSON, or stream-JSON is available.
      In-process QueryResult has assistantText, runId, stopReason, and error.
      Exact print-mode JSON schema is not yet verified by a real run.

    Workspace:
      Product metadata and built-in tool surface support repository editing
      and terminal commands. Direct same-cwd mutation, sandbox/worktree
      behavior, hidden state, and writes outside cwd are not yet verified.

    Authority:
      Permission modes, tool restrictions, additional directories, and
      sandbox controls exist. The correct DSH mapping for primary write
      authority is not yet selected or tested.

    Lifecycle:
      max-turns and print exit provide a plausible bounded shape. Startup,
      completion, exit-code mapping, child-process tree, cleanup,
      cancellation, persistence, and background-process behavior are not
      yet verified for a DSH invocation.

The current evidence therefore supports feasibility, not a frozen native
contract. In particular, no real CodeBuddy task was started during this
investigation.

## 4. Existing Runtime seam compatibility

The already proven M3 semantic sequence is:

    Planner action A
      -> Executor
      -> settled PluginResult
      -> TaskState.last_invocation_result
      -> Planner post-result evaluation
      -> action B
      -> Executor
      -> settled PluginResult
      -> Planner
      -> terminal Decision

The current implementation supports the intended business loop:

- Controller already evaluates Planner decisions, executes one bounded
  invocation at a time, increments iteration after settlement, evaluates the
  Planner again after a successful invocation, and commits final success only
  after a terminal Decision.
- Executor is plugin-name agnostic. It already governs one bounded invocation
  regardless of whether the Plugin is CodeBuddy or Codex.
- Planner can already choose a second action after the first action settles.
- TaskState already carries goal, logical workspace, authority, iteration,
  max_iterations, last_invocation_result, and final result.
- WorkspaceManager already resolves a logical workspace to cwd.
- The workspace filesystem itself can naturally carry CodeBuddy's repository
  changes to a later invocation when both Plugins receive the same resolved
  cwd.

Already proven:

- the continuation and post-result semantics;
- the one-invocation Executor boundary;
- bounded invocation budget;
- latest-result handoff;
- logical workspace propagation;
- read-only Codex Repository Analysis;
- final result ownership;
- failure/timeout terminality.

Likely sufficient but not yet proven for CodeBuddy:

- a CodeBuddy child process or server query can settle inside Executor;
- CodeBuddy writes made in the resolved cwd are visible to Codex;
- DSH authority can be mapped to CodeBuddy's permission controls without
  weakening safety;
- CodeBuddy's final output can be normalized to PluginResult.

Actual missing Runtime capability:

- a concrete business intent and Planner sequence for builder then verifier;
- one concrete CodeBuddy Plugin implementation;
- a defined verification outcome contract.

No evidence requires Controller, Executor, WorkspaceManager, or a new
continuation owner to change. The intended CodeBuddy -> Planner -> Codex path
fits the existing Controller without a special-case completion shortcut.

## 5. CodeBuddy -> Planner -> Codex handoff contract

The minimum sufficient handoff should be:

    original task goal
      + same logical workspace / resolved cwd
      + settled CodeBuddy result or diagnostic
      -> Planner-generated verification prompt
      -> Codex in the same workspace with read-only authority

The resulting workspace is the durable effect that Codex must inspect. The
original goal tells Codex what was requested. The CodeBuddy textual result is
useful context but is not necessarily required if the workspace and original
goal are sufficient.

For the minimal workflow:

- TaskState.last_invocation_result can carry the latest CodeBuddy output to the
  post-CodeBuddy Planner.
- The Planner can construct the Codex verification prompt from task.goal,
  workspace identity, and optionally last_invocation_result.
- Codex can inspect the same logical workspace without a new artifact,
  history, or cross-action context object.
- Codex's later output overwrites last_invocation_result, while the final
  terminal Decision controls TaskState.result.
- A changed-file list, diff object, session identifier, or generic artifact
  envelope is not yet required by the supplied product workflow.

The key unresolved condition is workspace identity. This handoff works
unchanged only if CodeBuddy mutates the same resolved cwd. If CodeBuddy uses a
temporary worktree, remote sandbox, or hidden copy, the product must specify
how that result becomes visible to Codex. That evidence is not present.

## 6. Codex verifier reuse assessment

The existing CodexPlugin can likely be reused unchanged:

- It already performs a bounded one-shot invocation.
- It already accepts a prompt from Planner parameters.
- It already receives logical workspace-derived cwd.
- It already maps DSH read-only authority to approvalPolicy=never and no
  workspace-write sandbox.
- M4 already proves the normal production Planner -> CodexPlugin path for
  read-only Repository Analysis.

The verifier role can therefore be expressed by a Planner-generated prompt,
for example:

    inspect the requested implementation in the current workspace,
    check it against the original task,
    report failures or unresolved issues,
    do not modify the workspace

This is business-role information, not evidence for a new Runtime owner.

No new Codex Plugin mode is currently justified. No new verification TaskKind
is currently justified solely for the internal second action; a future
overall business intent may be needed to identify the CodeBuddy-builder
workflow, while Codex remains the selected verifier capability.

Logical workspace propagation can be reused unchanged. Final verification can
remain read-only. The remaining question is not Codex routing mechanics; it is
what the product means by a verifier report that contains issues.

## 7. Task-success and verification semantics

The workflow must preserve both distinctions:

    successful CodeBuddy invocation != successful task
    successful Codex invocation != successful task

The intended state sequence is:

    CodeBuddy settled success
      -> last_invocation_result
      -> Planner decides Codex verification
      -> Codex settled success
      -> last_invocation_result
      -> Planner terminal Decision
      -> Controller commits TaskState.result
      -> COMPLETED

The current Runtime can return a normal PluginResult text from Codex and let
the Planner decide whether to return a terminal Decision. A structured
verifier output is not required by the current Runtime seam.

However, the product acceptance boundary is incomplete. The owner must decide
what happens when Codex reports issues:

- terminal FAILED task;
- terminal COMPLETED task containing a negative review;
- human-review/pending outcome;
- another CodeBuddy repair action; or
- some other explicitly named behavior.

The supplied requirement establishes only primary execution followed by final
verification. It does not authorize a repair/retry loop such as:

    CodeBuddy -> Codex -> CodeBuddy -> Codex

That is a future product workflow, not an automatic consequence of
verification.

For deterministic future tests, a local CodeBuddy stub and the existing Codex
stub could prove:

- Planner selects CodeBuddy first;
- CodeBuddy receives goal, cwd, and write authority;
- CodeBuddy settles;
- iteration increments once;
- Planner sees the settled CodeBuddy result;
- Planner selects Codex second;
- Codex receives the same workspace and read-only authority;
- Codex settles;
- iteration increments again;
- Planner performs a final evaluation;
- terminal TaskState.result is committed only by the terminal Decision.

Those tests would prove Runtime sequencing, not model quality, real file
mutation, or the meaning of a natural-language verifier report.

## 8. Existing-owner impact matrix

    TaskState / TaskKind:
      CHANGE LIKELY.
      A distinct business intent is likely needed for CodeBuddy-primary
      execution plus Codex verification. It must remain distinct from the
      read-only REPOSITORY_ANALYSIS invariant. The budget requirement
      (normally at least two settled invocations) also needs an explicit
      caller/default decision.

    Planner:
      CHANGE LIKELY.
      Initial intent selects CodeBuddy; post-CodeBuddy evaluation creates the
      Codex verification Decision; post-Codex evaluation returns the terminal
      Decision. No new loop owner is indicated.

    CodeBuddyPlugin:
      CHANGE LIKELY.
      A new concrete bounded Plugin or a minimal product-specific wrapper is
      required because no CodeBuddy Plugin exists. It must own native launch,
      output parsing, permission mapping, timeout cleanup, and process/session
      settlement.

    PluginRegistry:
      CHANGE POSSIBLE BUT NOT YET JUSTIFIED.
      The existing registry can register a concrete plugin. A bootstrap or
      caller wiring change may be needed, but the registry semantics do not
      need redesign.

    CodexPlugin:
      NO CHANGE EXPECTED.
      A different Planner prompt and the existing read-only authority path
      appear sufficient. Native verifier-mode changes are not justified.

    Controller:
      NO CHANGE EXPECTED.
      Existing Planner action/terminal sequencing already carries the
      business loop and final task transition.

    Executor:
      NO CHANGE EXPECTED.
      Its one bounded invocation boundary is provider agnostic and already
      owns timeout/cancellation settlement.

    WorkspaceManager:
      NO CHANGE EXPECTED.
      Existing logical workspace to cwd propagation is sufficient if CodeBuddy
      and Codex share the same workspace. A different native worktree/sandbox
      contract would require new evidence first.

    ExecutionContext / PluginResult:
      NO CHANGE EXPECTED initially.
      Existing cwd, allow_workspace_write, output, error, cleanup_error, and
      StopReason fields cover the known minimum. A new field is not justified
      until CodeBuddy evidence requires it.

## 9. Smallest likely future production change

If the missing product questions are answered, the smallest likely delta is:

    distinct business TaskKind / caller intent
      + Planner sequencing for CodeBuddy -> Codex
      + one bounded CodeBuddyPlugin
      + existing CodexPlugin

The likely production files are:

- dsh_runtime/state.py, for the distinct business intent if the caller
  boundary requires it;
- dsh_runtime/planner.py, for the two action Decisions and final terminal
  evaluation;
- a new concrete dsh_runtime/plugins/codebuddy.py, for native CodeBuddy
  mechanics.

Registration/wiring may touch an existing assembly site if one is introduced,
but the current PluginRegistry itself is likely sufficient.

Expected unchanged owners:

- dsh_runtime/controller.py
- dsh_runtime/runtime/executor.py
- dsh_runtime/runtime/plugin.py
- dsh_runtime/workspace/manager.py
- dsh_runtime/plugins/codex.py

No WorkflowEngine, PipelineExecutor, TwoActionExecutor, AgentCoordinator,
CodeBuddyCodexCoordinator, Provider Framework, Agent Framework,
ExecutionHandle, ProcessManager, generic PermissionPolicy, or generic
CapabilityRequest is justified.

This is an evidence-based implementation boundary estimate, not an
implementation plan. No implementation is authorized by this document.

## 10. Deterministic verification strategy

The future acceptance evidence can be split into independent layers:

### Deterministic Runtime verification

Use M3-style bounded test Plugins or local stubs to prove the exact two-action
sequence, invocation budget, same workspace identity, result handoff, and
terminal result ownership. This requires no live model service.

### CodeBuddy local/native contract verification

Use a local fake CodeBuddy executable or deterministic Node wrapper that
emulates the selected headless surface. Capture:

- launched cwd;
- prompt/input;
- selected permission arguments;
- max-turn bound;
- output format;
- exit status;
- cancellation and cleanup behavior.

This proves the future Plugin's mapping and bounded mechanics, not CodeBuddy's
real model behavior.

### Codex deterministic verifier routing

Reuse the existing local app-server stub to prove that the second action:

- receives the same resolved cwd;
- receives read-only authority;
- receives the Planner-generated verification prompt;
- settles into PluginResult;
- is followed by a terminal Planner Decision.

### Real CodeBuddy service verification

Still required later for:

- authenticated non-interactive model execution;
- real repository mutation in the intended cwd;
- actual permission behavior;
- output/exit semantics under success and failure;
- process tree and background process behavior;
- timeout and interrupt behavior;
- session persistence or non-persistence behavior.

No real CodeBuddy task was started in this investigation.

### Real Codex service verification

Remains separate Milestone 2 verification debt. Its reopen gate remains a
minimal real Codex turn reaching turn/completed. This investigation did not
retry it and does not claim it is solved.

## 11. Live-service verification debt

CodeBuddy and Codex debts must remain separate:

    CodeBuddy debt:
      native task turn, write effect, authority enforcement, process cleanup,
      cancellation, output schema, authentication readiness, and same-workspace
      handoff.

    Codex debt:
      existing Milestone 2 real-service gate and the already listed unknowns
      around real final answer, native read-only denial, workspace-write effect,
      interrupt acknowledgement, process tree, and deadline race.

The existence of an installed CodeBuddy CLI does not close either live-service
debt and does not reopen Milestone 4.

## 12. Open product questions

Before implementation design, the product owner must answer:

1. Is the intended CodeBuddy surface CLI print mode, in-process server query,
   ACP, or another exact entrypoint?
2. Does CodeBuddy write directly into the DSH-resolved cwd, or does it create a
   sandbox/worktree whose result needs an explicit export?
3. What exact write authority may DSH grant, and how should it map to
   permission-mode, tools, add-dir, and sandbox controls?
4. What is the required CodeBuddy settled output: textual summary, structured
   JSON, exit code plus stdout, or workspace effect only?
5. Is one CodeBuddy print invocation with max-turns the intended bounded unit?
6. What should the business TaskKind/intent be called, and does it imply a
   two-invocation budget automatically?
7. Does Codex need CodeBuddy's textual summary, or are original goal plus
   resulting workspace sufficient?
8. What exact prompt should Planner send to the independent verifier?
9. What does a Codex report containing issues mean for TaskState: FAILED,
   COMPLETED-with-report, human review, or another explicit state?
10. Is repair/retry intentionally out of scope for the first version?
11. Must CodeBuddy and Codex use the same physical workspace, and how is that
    guaranteed?
12. What authentication/configuration source is allowed for unattended DSH
    execution?

Until these are answered, a future implementation could prove routing and
boundedness but could not honestly claim the full product acceptance contract.

## 13. Final verdict

    PROMISING BUT PRODUCT CONTRACT INCOMPLETE

The workflow is representable by the existing Runtime architecture:

    distinct business intent
      -> Planner selects CodeBuddy
      -> existing Controller / Executor
      -> settled CodeBuddy result and workspace effect
      -> Planner selects Codex
      -> existing read-only CodexPlugin
      -> Planner terminal Decision
      -> DSH-owned TaskState completion

The smallest likely future boundary is a distinct business intent, Planner
sequencing, and one concrete bounded CodeBuddyPlugin, while retaining the
existing Controller, Executor, WorkspaceManager, and CodexPlugin owners.

The verdict is not JUSTIFIED FOR MINIMAL IMPLEMENTATION DESIGN yet because
the selected CodeBuddy surface, same-workspace write semantics, authority
mapping, settled output contract, and Codex-negative-verification outcome are
not fully specified or live-verified.

## 14. Files changed during investigation

Added:

- collaboration/investigations/2026-09-07-codebuddy-execution-codex-verification-investigation.md

No PROJECT_STATE.md update was made. No Milestone 5 was declared. No
implementation plan was created.

## 15. Confirmation

No production code, tests, Runtime abstraction, CodeBuddyPlugin,
PluginRegistry registration, TaskKind, SimplePlanner branch, CodexPlugin, or
real Codex/CodeBuddy service invocation was changed or started by this
investigation.
