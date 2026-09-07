# Next Concrete Goal Selection — Investigation / Evidence Gathering

Date: 2026-09-07
Scope: select the next concrete DSH Runtime workflow, if repository evidence justifies one
Implementation: none

## Decision

Recommended Next Concrete Goal: NONE YET

Reason:
No candidate currently has enough concrete workflow and repository/product
evidence to justify a new Runtime change.

The current closed state remains authoritative:

    Milestone 1: CLOSED
    Milestone 2: IMPLEMENTATION COMPLETE; REAL-SERVICE VERIFICATION DEFERRED / ENVIRONMENT_BLOCKED
    Milestone 3: CLOSED / VERIFICATION PASS
    Milestone 4: CLOSED / VERIFICATION PASS
    Full regression: 46 passed

This investigation does not reopen Milestone 2, 3, or 4, and does not create
an implementation plan for a future milestone.

## Evidence inspected

### Project and collaboration records

- PROJECT_STATE.md
- collaboration/closures/2026-09-06-m2-external-capability-integration-closure.md
- collaboration/closures/2026-09-06-m3-bounded-task-continuation-closure.md
- collaboration/closures/2026-09-07-m4c-readonly-repository-analysis-closure.md
- collaboration/implementations/2026-09-06-m4b-repository-analysis-workflow-implementation.md
- collaboration/plans/2026-09-06-m4-next-concrete-goal-selection.md
- collaboration/plans/2026-09-06-m4a-repository-analysis-minimal-implementation-design.md
- collaboration/plans/2026-09-06-m4a1-repository-analysis-readonly-invariant.md
- collaboration/investigations/2026-09-05-m2-a3-external-agent-evidence-synthesis.md
- collaboration/investigations/2026-09-05-m2-c2a-disposable-lifecycle-verification.md
- collaboration/investigations/2026-09-06-m2-c2d-real-codex-integration-evidence-hardening.md
- collaboration/sessions/2026-09-06-m4b-handover.md

### Repository implementation and tests

- dsh_runtime/state.py
- dsh_runtime/planner.py
- dsh_runtime/controller.py
- dsh_runtime/runtime/executor.py
- dsh_runtime/runtime/plugin.py
- dsh_runtime/runtime/registry.py
- dsh_runtime/workspace/manager.py
- dsh_runtime/plugins/codex.py
- dsh_runtime/plugins/echo.py
- tests/test_runtime.py
- tests/test_codex_plugin.py
- tests/test_disposable_lifecycle.py
- tests/test_runtime_semantic_hardening.py
- tests/codex_app_server_stub.mjs
- 资料库/CODEX_CONTEXT.md

There is no README or separate backlog file in the repository. The repository
contains no CodeBuddy implementation, CodeBuddy test, API/task-submission
adapter, second production capability, or task-level cancellation state.

### Verification during this investigation

The first full-regression invocation encountered one timing-sensitive failure
in the existing disposable-lifecycle test: cleanup completed and the expected
event sequence was observed, but elapsed time measured 18.86ms against a
20ms lower-bound assertion. The focused test was rerun successfully, followed
by a successful full regression:

    .venv\Scripts\python.exe -m pytest -q tests/test_disposable_lifecycle.py::test_timeout_delivers_cancel_and_waits_for_async_cleanup
    1 passed

    .venv\Scripts\python.exe -m pytest -q
    46 passed

No test or production file was changed in response. This timing observation
does not falsify a frozen Milestone 4 invariant and does not justify reopening
Milestone 4.

## Currently proven Runtime capability envelope

The executable envelope is:

    Caller
      -> TaskState
      -> DSHController
      -> Planner
      -> one bounded Executor invocation
      -> Plugin
      -> bounded PluginResult
      -> last_invocation_result
      -> post-result Planner
      -> terminal task result or next bounded action

The evidence establishes:

- DSHController owns the business loop, invocation budget, and terminal task
  transition.
- TaskState owns caller/task input, lifecycle, invocation count, final result,
  and the latest successful invocation result.
- Planner owns business-level action or terminal Decision selection.
- Executor owns one invocation's timeout, cancellation cleanup, settlement, and
  StopReason normalization.
- A concrete Plugin owns bounded native mechanics.
- Echo supplies the deterministic default path.
- CodexPlugin supplies one bounded, ephemeral, app-server-backed invocation.
- Logical workspace identity is resolved by WorkspaceManager and propagated as
  cwd.
- Repository Analysis is represented by TaskKind.REPOSITORY_ANALYSIS and is
  read-only at TaskState construction.
- The normal Repository Analysis path is:

      TaskKind.REPOSITORY_ANALYSIS
        -> production SimplePlanner
        -> CodexPlugin
        -> logical workspace / read-only authority
        -> bounded result
        -> last_invocation_result
        -> post-result Planner
        -> terminal Decision
        -> TaskState.result
        -> COMPLETED

- The local deterministic evidence records two Planner calls, one settled
  invocation, and TaskState.iteration == 1.
- M3 already proves A -> result -> Planner -> B continuation semantics,
  bounded invocation budget, terminal result ownership, and failure/timeout
  terminality. A possible future two-action workflow is not evidence of a
  missing continuation architecture.

## Workflow gap inventory

### Candidate A — CodeBuddy as a bounded capability

Actor / caller wants to:

Use CodeBuddy to accomplish a concrete coding or repository task through DSH.

Current Runtime can:

Run a bounded read-only Repository Analysis through the existing CodexPlugin,
and run the existing deterministic Echo capability. The Plugin boundary can
contain one bounded external invocation.

Current Runtime cannot:

Select or invoke CodeBuddy because no CodeBuddy contract, implementation,
registration, caller intent, or executable test exists in this repository.

Therefore the actual gap is:

No concrete CodeBuddy-specific business workflow has been identified. The
absence of a CodeBuddy Plugin is not itself a DSH workflow requirement.

Evidence classification:

- Repository evidence: CodeBuddy appears only as a possible/future capability
  in older context and handoff material. No concrete task, acceptance
  boundary, or implementation evidence exists.
- Product/native contract evidence: none in this repository.
- Assumption: CodeBuddy might offer useful coding behavior.
- Unknown: bounded inputs, settled output, workspace mutation, authority,
  timeout, cancellation, and process semantics.

Evaluation:

    Candidate: CodeBuddy as a bounded capability
    Concrete workflow: not named
    User/business value: unproven
    Repository evidence: insufficient
    External/product evidence: absent
    Already supported pieces: bounded Plugin seam, Executor governance
    Actual missing capability: a concrete CodeBuddy use case and native contract
    Likely existing owner: existing Plugin plus Planner, if later justified
    Minimum production change: unknown; likely one task-intent rule and one Plugin
    New owner required?: NOT JUSTIFIED
    New abstraction required?: NOT JUSTIFIED
    Deterministic verification possible?: only after a local bounded contract exists
    Real-service dependency: unknown for CodeBuddy; Codex real-service debt is separate
    Main uncertainty: what CodeBuddy uniquely contributes
    Verdict: NOT CURRENTLY JUSTIFIED

The same Repository Analysis workflow is already satisfied by CodexPlugin.
Therefore CodeBuddy is not currently justified merely as another provider.

### Candidate B — A real two-action workflow

Actor / caller wants to:

Achieve a useful result that genuinely requires Capability A, a settled result
or workspace effect, Planner evaluation, and Capability B.

Current Runtime can:

Execute bounded actions and pass the latest successful output through
last_invocation_result to the post-result Planner. M3 proves the ordering and
budget semantics with deterministic test capabilities.

Current Runtime cannot:

Identify a second production capability and business outcome that consume the
first action's result. The repository has only Echo and one-shot Codex; the
existing two-step test uses synthetic RecordingPlugin instances.

Therefore the actual gap is:

No useful two-action product workflow has been named. The Runtime continuation
seam is already present; the missing evidence is a business workflow, not a
generic continuation mechanism.

Evaluation:

    Candidate: first useful two-action workflow
    Concrete workflow: not named
    User/business value: potentially high, currently unproven
    Repository evidence: M3 continuation semantics are strong; product consumer is absent
    External/product evidence: none for a required A/B pairing
    Already supported pieces: Planner result handoff, bounded budget, workspace propagation
    Actual missing capability: a named second action with a required consumer contract
    Likely existing owner: Planner and existing Controller loop if later justified
    Minimum production change: unknown; possibly zero Runtime change
    New owner required?: NOT JUSTIFIED
    New abstraction required?: NOT JUSTIFIED
    Deterministic verification possible?: yes, after A and B are concretely named
    Real-service dependency: avoidable initially with local bounded doubles/stubs
    Main uncertainty: what business outcome cannot be completed by one Codex invocation
    Verdict: NOT CURRENTLY JUSTIFIED

CodeBuddy -> Codex is not selected: the repository provides no evidence that
CodeBuddy uniquely contributes a required first action, and adding that pair
would currently be capability-first speculation.

### Candidate C — Explicit write-capable repository workflow

Actor / caller wants to:

Perform a specifically authorized repository change and receive a final task
result.

Current Runtime can:

Propagate DSH authority through TaskState -> ExecutionContext -> CodexPlugin.
CodexPlugin already has a bounded native workspace-write mapping for a valid
ExecutionContext.

Current Runtime cannot:

Express a distinct, approved write-capable business task kind. M4 deliberately
rejects REPOSITORY_ANALYSIS plus allow_workspace_write=True because Repository
Analysis itself is read-only.

Therefore the actual gap is:

No concrete write business requirement, authorization source, or acceptance
boundary has been supplied. The missing item is product intent, not a generic
permission mechanism.

Evaluation:

    Candidate: explicitly authorized write-capable repository workflow
    Concrete workflow: analyze/change/return result, but no approved task kind or caller
    User/business value: plausible, not evidenced
    Repository evidence: native write mapping exists; real write side effect is unverified
    External/product evidence: real Codex write behavior remains blocked/unknown
    Already supported pieces: authority propagation and Codex native mapping
    Actual missing capability: concrete business intent and authorization boundary
    Likely existing owner: TaskState plus Planner, if a distinct task kind is approved
    Minimum production change: possibly one TaskKind/Planner branch; not authorized now
    New owner required?: NOT JUSTIFIED
    New abstraction required?: NOT JUSTIFIED
    Deterministic verification possible?: routing yes; real side effect no under current block
    Real-service dependency: required for native side-effect verification
    Main uncertainty: who authorizes mutation and what outcome is required
    Verdict: PROMISING BUT EVIDENCE INCOMPLETE

This candidate must not be implemented by weakening the M4 read-only invariant
or by reusing Repository Analysis with write authority.

### Candidate D — Caller-observable task cancellation

Actor / caller wants to:

Cancel an in-progress DSH task and observe a distinct task-level outcome after
bounded Plugin cleanup.

Current Runtime can:

Bound an invocation by timeout, cancel and settle Plugin cleanup, and propagate
outer caller cancellation through Executor. These behaviors are covered by
Codex/local lifecycle tests.

Current Runtime cannot:

Expose a distinct TaskState cancellation state or a caller/API operation that
requests cancellation. There is no task-level caller boundary in the
repository.

Therefore the actual gap is:

No concrete caller requires task cancellation semantics. Existing Executor
cancellation evidence does not establish a missing DSH task state.

Evaluation:

    Candidate: caller-observable task cancellation
    Concrete workflow: caller cancels a long-running DSH task
    User/business value: plausible safety feature, not currently demonstrated
    Repository evidence: invocation cleanup/propagation only; no caller boundary
    External/product evidence: none
    Already supported pieces: timeout, cleanup, outer cancellation propagation
    Actual missing capability: caller-triggered task-level meaning and state mapping
    Likely existing owner: Controller and TaskState, after a real caller exists
    Minimum production change: smallest caller-to-TaskState transition plus focused tests
    New owner required?: NOT JUSTIFIED
    New abstraction required?: NOT JUSTIFIED
    Deterministic verification possible?: yes, after a caller trigger exists
    Real-service dependency: avoidable with a local long-running Plugin
    Main uncertainty: who initiates cancellation and what state/output contract is required
    Verdict: NOT A RUNTIME GAP

### Candidate E — API/task-submission adapter or other gap

Actor / caller wants to:

Submit and observe DSH tasks through a product-facing boundary.

Current Runtime can:

Run directly constructed TaskState instances through DSHController.

Current Runtime cannot:

Provide an HTTP, CLI, or other product-facing task-submission adapter in this
repository.

Therefore the actual gap is:

An adapter may be absent, but no repository/product requirement names one.
Adding an adapter now would be a product-surface assumption rather than an
evidence-backed Runtime goal.

Verdict: NOT CURRENTLY JUSTIFIED.

## Candidate ranking

| Rank | Candidate | User value evidence | Runtime gap evidence | Existing-owner fit | Deterministic evidence | Real-service dependence | Verdict |
|---:|---|---|---|---|---|---|---|
| 1 | Explicit write-capable repository workflow | Plausible but no requirement | Native mapping exists, product intent absent | High | Partial; real side effect blocked | High for side-effect claims | PROMISING BUT EVIDENCE INCOMPLETE |
| 2 | Caller-observable task cancellation | Plausible safety value | No caller boundary; Executor behavior already exists | High after caller exists | Yes after caller exists | Low | NOT A RUNTIME GAP |
| 3 | First useful two-action workflow | Potentially high | No second production consumer | High; may need zero Runtime change | Yes after workflow is named | Low initially | NOT CURRENTLY JUSTIFIED |
| 4 | CodeBuddy capability | Unknown | No CodeBuddy-specific workflow or contract | Unknown | Unknown | Unknown | NOT CURRENTLY JUSTIFIED |
| 5 | API/task-submission adapter | Unknown | No product requirement | Unknown | Unknown | Low | NOT CURRENTLY JUSTIFIED |

The ranking does not justify a new milestone. Candidate C is strongest only in
the sense that the existing Codex authority mapping makes a future workflow
technically plausible; it still lacks the concrete caller intent and
authorization evidence required for selection.

## Unresolved evidence gaps

The following facts would unlock selection of a next goal:

1. A named caller/business task that must mutate a repository, including the
   authorization source, allowed scope, and expected final result.
2. A named two-action workflow with a concrete reason one existing Codex
   invocation is insufficient, plus the unique contribution of each action.
3. A real caller/API boundary that must cancel an in-progress task and the
   required observable state/result contract.
4. A CodeBuddy-specific workflow that cannot be satisfied by the existing
   CodexPlugin, together with CodeBuddy's bounded invocation, output,
   authority, timeout, cancellation, and process contract.
5. A product requirement for an API/task-submission adapter.

Real Codex service verification remains separate Milestone 2 verification
debt. Its reopen gate is still a minimal real Codex turn reaching
turn/completed. It is not evidence for a new product workflow by itself.

## Final required outcome

    Recommended Next Concrete Goal:
    NONE YET

    Strongest candidate:
    Explicit write-capable repository workflow

    Missing evidence:
    A concrete authorized business task, caller boundary, and acceptance
    criteria; real native write-side-effect evidence also remains blocked.

    What evidence would unlock selection:
    A concrete caller request naming the intended mutation and authority, or a
    concrete second-action/cancellation/CodeBuddy workflow with an executable
    acceptance boundary.

No production file, test file, or Runtime abstraction was changed during this
investigation.
