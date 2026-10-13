# DSH Runtime Project State

Current Version:
v0.1.0-m7

Current Milestone:
D2-C10-C3 — Cross-repository dispatch acceptance and Runtime output-bound repair

Status:
IN PROGRESS — local repair verified; dynamic D2 acceptance pending


## D2-C10-C3 current cross-project status (2026-10-14)

- DeepSeekHarness C3 dispatch-sidecar implementation is locally accepted on branch codex/d2-c10-c3-qualification-20261014 at HEAD 69342f31c31313ad705aec7721a85888382502e3: focused tests 54/54 and Host build passed; the target worktree remains clean.
- The latest D2 run d2-business-545bd0ccaa0b49ebaf20bed6e263ebf8 used one Runtime call and settled with the CodeBuddy output-bound error. No native terminal TaskState or safe worker trace was delivered. The DSH case also violated its first-action contract by reading the target before calling Runtime. Post-failure read-only reconciliation found no target file changes. This run is not a qualified PASS and its identity is consumed.
- The DSH patch used the wrong CodeBuddy safe-trace key. The expected key is DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR. The Runtime default stream bound was 100,000 characters; the exact observed count and worker turn count are unavailable.
- Local Runtime repair now separates total stream chars from final assistant output, supports an opt-in DSH_CODEBUDDY_MAX_STREAM_CHARS ceiling up to 1,000,000, rejects invalid limits, removes this DSH-only setting from the child environment, and reports bounded non-content counters on overflow. Final assistant output remains capped at 100,000 characters.
- Current Runtime regression: 503 passed; git diff --check passed. Four code/test files are modified locally and uncommitted. The Harness R8 gate does not pin the modified bootstrap and CodeBuddy plugin files, so any next run using these files must be documented as a user-authorized manual continuation, not an automated gate PASS.
- Detailed runbook evidence: D:\DeepSeekHarness\c3-e4-codebuddy-d2\runbook\d2-c3-runtime-output-bound-repair-and-reconciliation-2026-10-14-r2.md and d2-project-completion-backlog-2026-10-14-r3.md. Continue with a fresh identity/series and one new Runtime call; never reuse the consumed 545 identity.
- PR #1 and #12 remain drafts and unmerged. The upstream-sync worktree's five pre-existing modifications remain preserved. No commit, push, or remote update was made.

Completed milestones:

- Milestone 1 — DSH Runtime Skeleton: CLOSED
- Milestone 2 — External Capability Integration: IMPLEMENTATION COMPLETE; real-service verification DEFERRED / ENVIRONMENT_BLOCKED
- Milestone 3 — Bounded Planner-Driven Task Continuation: CLOSED / VERIFICATION PASS
- Milestone 4 — Read-only Repository Analysis Workflow: CLOSED / VERIFICATION PASS
- Milestone 5 — Repository Change Workflow: CLOSED / REVIEW PASS / VERIFICATION PASS
- Milestone 6 — Real-Host Qualification and Closeout: COMPLETE / CLOSED
- Milestone 7 — DeepSeekHarness Cross-Language Qualification and Closeout: COMPLETE / CLOSED

Formal regression baseline:

    M7 deterministic                  3 passed
    related DSH-Runtime               9 passed
    full regression                 117 passed

    M7 adapter compile/import         PASS
    DSH-Runtime git diff --check      PASS
    DeepSeekHarness git diff --check  PASS

Milestone 5 closure:

- M5-A minimal implementation design: complete.
- M5-B1 — business-intent terminal Decision semantics: REVIEW PASS / FROZEN.
- M5-B2 — bounded CodeBuddy primary executor: REVIEW PASS / FROZEN.
- M5-B3 — minimal production assembly and caller: REVIEW PASS / FROZEN.
- M5-B4-F1 — per-invocation authority handoff: REVIEW PASS / CLOSED.
- M5-B4 — deterministic end-to-end verification: REVIEW PASS / CLOSED.
- The proven workflow is REPOSITORY_CHANGE → CodeBuddy primary executor → same-workspace mutation → Planner continuation → Codex read-only verifier → DSH_VERIFICATION: PASS / FAIL → Planner terminal Decision → DSHController-owned TaskState completion or failure.
- REPOSITORY_ANALYSIS remains strictly read-only and owned by Codex. REPOSITORY_CHANGE is an independent write-capable business intent.
- M5 callers use allow_workspace_write=True and max_iterations=2. CodeBuddy receives write authority=True; the Codex verifier receives write authority=False.
- TaskState.allow_workspace_write is the caller authority ceiling. Decision.allow_workspace_write is the per-invocation authority request or narrowing. The Controller computes effective authority only; Planner may narrow authority but may not elevate beyond the TaskState ceiling.
- CodeBuddy Bash permission remains strictly Bash(python:*), CodeBuddyPlugin concrete/private ownership remains unchanged, and the existing read-only Codex verifier is reused.
- Workspace remains a logical operating boundary; M5 makes no hard-filesystem-confinement claim. CodeBuddy process-tree cleanup and cancellation settlement are closed contracts.
- M5 has no repair/retry loop, third action, WorkflowEngine, Coordinator, Provider Router, or equivalent new architecture.

M5 environment debt:

- At M5 closeout, real-host CodeBuddy/Codex verification was deferred environment debt and was not an M5 deterministic acceptance blocker.
- That deferred real-host qualification was subsequently resolved by Milestone 6, without reopening M5 frozen contracts.

M5 reopen gate:

- No further M5 implementation is authorized by default.
- Reopening an M5 owner requires new executable evidence that directly contradicts a frozen M5 assumption or contract. Do not reopen a reviewed/frozen owner based only on hypothetical expansion or an environment-debt item.

Milestone 6 closeout:

- M6-A — design: REVIEW PASS / FROZEN.
- M6-B1 — real-host qualification boundary: REVIEW PASS / FROZEN.
- M6-B2 — deterministic qualification: 25 cases passed / REVIEW PASS / FROZEN.
- M6-B3 — real-host qualification: PASS / REVIEW PASS / FROZEN.
- M6-B4 — final deterministic verification: PASS / FROZEN.
- Final deterministic evidence: focused/related 64 passed; qualification 25 passed; combined focused set 89 passed; full regression 117 passed; compile/import PASS; git diff --check PASS.
- Final production configuration: CodeBuddy default max_turns=12; REPOSITORY_CHANGE allow_workspace_write=True, max_iterations=2, timeout_seconds=900.0; global TaskState default timeout=30.0 seconds.
- Authority, permissions, and workflow contracts remain unchanged: caller authority ceiling and per-invocation narrowing; generic Controller effective-authority calculation; Planner ownership; CodeBuddy Bash(python:*); Codex read-only authority; plugin ownership; two-action REPOSITORY_CHANGE workflow; logical workspace boundary; no retry, repair, or third action.
- Reviewed final real-host evidence: CodeBuddy=1 invocation; Codex=1 invocation; TaskState=completed; iteration=2; DSH retries=0; repair=0; third action=0; total elapsed=224.269 seconds.
- MILESTONE 6 = COMPLETE / CLOSED.

Milestone 7 closeout:

- M7-A / M7-A-F1 — design boundary: DSH-Runtime workflow / semantic gap NONE; DeepSeekHarness → Python invocation gap MINIMAL GAP. The resolved boundary is DeepSeekHarness / Node → existing subprocess seam → one-shot Python adapter → existing DSH-Runtime production bootstrap. DeepSeekHarness remains the external qualification / invocation owner; DSH-Runtime remains the production workflow owner.
- M7-B1 — deterministic cross-language success: DeepSeekHarness / Node / Vitest → LocalSubprocessRuntime → one Python process → production bootstrap → deterministic CodeBuddy → deterministic Codex → completed TaskState → Node observation. CodeBuddy=1 with authority=True; Codex=1 with authority=False; workspace mutation +m7_full_flow.txt with exact content DSH_M7_DETERMINISTIC_FULL_FLOW; Codex mutation none; sequence CodeBuddy → Codex; external actions=2; retry=0; repair=0; third action=0; TaskState completed at iteration=2 with error=None.
- M7-B2 — real-host cross-language success: DeepSeekHarness → Node subprocess seam → Python DSH-Runtime → real CodeBuddy → real Codex → terminal TaskState → DeepSeekHarness observation. Real CodeBuddy=1 invocation, elapsed=45.502 seconds, effective authority=True; real Codex=1 invocation, elapsed=149.080 seconds, effective authority=False; workspace mutation +m7_real_host_full_flow.txt with exact content DSH_M7_REAL_HOST_FULL_FLOW; unexpected mutation none; Codex mutation none; sequence CodeBuddy → Codex; TaskState completed at iteration=2 with error=None; retry=0; repair=0; third action=0.
- M6 real-host evidence did not substitute for M7-B2; M7-B2 specifically qualified the new DeepSeekHarness → Python boundary.
- M7-B3 — deterministic Harness-visible failure semantics: CodeBuddy → Codex → task_failed, with Codex final verifier line DSH_VERIFICATION: FAIL. TaskState failed at iteration=2 with error=Codex verification reported FAIL. Settled business failure is exit 0 + one terminal failed TaskState JSON + empty stderr; adapter / transport failure is non-zero exit + stderr diagnostic + empty stdout. Retry=0, repair=0, and third action=0 are derived from the actual trace.
- M7-B4 — final deterministic verification: M7-B1=1 passed; M7-B3=2 passed; combined deterministic M7=3 passed; related DSH-Runtime=9 passed; full regression=117 passed; all M7 Python adapters compile/import PASS; DSH-Runtime and DeepSeekHarness git diff --check PASS. M7-B2 was not rerun during B4; frozen PASS evidence was preserved; real CodeBuddy/Codex calls during B4=0.
- Milestone 7 preserves the existing authority model, two-action REPOSITORY_CHANGE workflow, one-shot JSON test/harness bridge, and no retry, repair, third action, Coordinator, Router, or WorkflowEngine architecture. MILESTONE 7 = COMPLETE / CLOSED.

D2-C9 governance closeout:

- D2-C9-O-F1 — Governed Route Applicability Foundation: IMPLEMENTED / QUALIFIED.
- D2-C9-O1 — governed one-shot pre-start enforcement wiring: IMPLEMENTED / QUALIFIED.
- D2-C9-O2 — real governance to production start composition: IMPLEMENTED / QUALIFIED.
- D2-C9-O2-F1 — qualification harness portability and deterministic transport-failure coverage: IMPLEMENTED / PASS.
- D2-C9-O — governed pre-start enforcement and real composition qualification: COMPLETE / CLOSED.
- The qualified production boundary is trusted Host composition → explicit governed-route binding → Runtime governed/non-governed distinction → fixed-v1 governance evaluation and enforcement → provider.start() only for EXECUTION_ELIGIBLE.
- BLOCKED, governance FAILURE, unavailable evaluator, taskKind mismatch, transport failure, and audit persistence failure fail closed before provider execution; ordinary routes bypass governance while the service is mounted.
- Selection Policy v2, model-facing task_kind, repository_inspection production authority, continuable governance, retry/fallback/restart, and multiwriter audit remain closed and were not introduced by D2-C9-O.

D2-C10 Selection Policy v2 qualification:

- D2-C10-A — Selection Policy v2 / multi-workload governed routing design: DESIGN READY / REVIEW PASS.
- D2-C10-B1 — pair-keyed governed applicability foundation: IMPLEMENTED; pair bindings remain separate from the C9-O production route resolver.
- D2-C10-B2 — Selection Policy v2 artifact / authorization / session-pin isolation: IMPLEMENTED / QUALIFIED.
- The v2 artifact uses policy_id=selection-v2, policy_version=2, artifact_schema_version=1, and authorizes repository_change plus repository_inspection through the existing policy AND deployment enabled_workloads intersection.
- Gate → Audit → Enforcement qualification permits an authorized inspection candidate only as a governance-layer fact; no production inspection binding, selector, provider dispatch, or pair-binding resolver was introduced.
- v2 session create/resume requires the exact identity; v1 pins cannot auto-upgrade, wrong hashes fail closed, and one v2 pin remains workload-independent.

D2-C10-B3-F1 DSH-scoped workload selector exposure correction:

- Generic one-shot tool-subagent instances no longer expose `task_kind` by default.
- The explicit trusted Host config `workloadProposal: dsh-runtime` enables the closed selector only on one-shot DSH composition; the standard preset `dsh_runtime` row carries it and remains disabled until a copied preset explicitly enables the row.
- Forced `task_kind` on a disabled or continuable instance fails before provider start; opt-in omission/change/inspection transport is unchanged, and the provider owns the omitted `repository_change` default.
- The B1 pair registry, Selection Policy v2, C9-O legacy route, inspection production authority, continuable governance, DSH Runtime workflow, GovernanceBridge/Python worker, and retry/fallback/restart remain unchanged.
- Focused F1 selector/tool regressions: 98 passed; related shared service, DSH provider, and bridge regressions: 95 passed.
- D2-C10-B3-F1 = IMPLEMENTED / PASS.

Milestone 4 closure:

- The first concrete DSH workflow was read-only Repository Analysis.
- The caller expresses TaskKind.REPOSITORY_ANALYSIS, not a plugin, provider, or concrete capability.
- TaskState owns caller/task input and rejects REPOSITORY_ANALYSIS plus allow_workspace_write=True during construction.
- SimplePlanner maps Repository Analysis to CodexPlugin; default tasks retain Echo compatibility.
- Existing Controller, Executor, Plugin, Registry, WorkspaceManager, and CodexPlugin ownership was sufficient.
- Successful invocation remains distinct from successful task completion: last_invocation_result is evaluated by the post-result Planner before the terminal Decision commits TaskState.result and COMPLETED.
- The executable local-stub workflow proves two Planner calls, one settled invocation, and TaskState.iteration == 1.

Non-claims and deferred work:

- Milestone 5 did not claim real CodeBuddy/Codex service verification; that was deferred at M5 closeout and was subsequently qualified under M6.
- M5 does not authorize broader workspace confinement, retry/repair behavior, a third action, or new workflow/coordinator/router architecture.

## Current next project gate

D2-C10-C3 local implementation and deterministic acceptance are complete; the cross-repository live dispatch acceptance remains in progress. The latest attempt failed before delivering a terminal TaskState, and the target was clean after reconciliation. The next action is a fresh user-authorized manual continuation with the repaired Runtime stream handling and corrected trace configuration. Do not claim automated gate PASS until the Runtime source pins cover the modified files. Previously closed M7 and D2-C9 owners remain closed.