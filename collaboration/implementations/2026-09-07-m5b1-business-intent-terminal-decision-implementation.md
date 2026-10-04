# M5-B1 — Business Intent & Terminal Decision Contract Implementation

Date: 2026-09-07
Status: M5-B1 IMPLEMENTATION COMPLETE
Scope: business intent, Planner sequencing, strict verifier terminal semantics
Native CodeBuddy execution: not performed

## 1. Scope and non-scope

This slice implements only the approved M5-B1 semantic Runtime extension. It
does not implement M5-B2, M5-B3, or M5-B4.

    Milestone 5 implementation complete: NOT DECLARED

No CodeBuddyPlugin was created, CodeBuddy was not registered, no native
CodeBuddy execution was performed, and `PROJECT_STATE.md` was not changed.

## 2. Production files changed

Changed only the authorized B1 footprint:

    dsh_runtime/state.py
    dsh_runtime/planner.py
    dsh_runtime/controller.py

Changes:

- Added `TaskKind.REPOSITORY_CHANGE = "repository_change"`.
- Preserved the M4 `REPOSITORY_ANALYSIS` read-only invariant.
- Required `allow_workspace_write=True` and `max_iterations >= 2` for
  `REPOSITORY_CHANGE`; the global default budget remains unchanged.
- Extended production `SimplePlanner` with the deterministic CodeBuddy ->
  Codex -> terminal sequence.
- Added a bounded verifier prompt containing the original goal, current
  workspace/read-only instructions, independent verification instructions,
  and the exact verdict-line contract.
- Extended existing `Decision` backward-compatibly with
  `terminal_success=True` and `terminal_error=None`.
- Extended only the existing Controller terminal branch so Planner can commit
  either terminal success or terminal failure while Controller remains the
  final TaskState owner.

Unchanged as required:

    dsh_runtime/runtime/plugin.py
    dsh_runtime/runtime/executor.py
    dsh_runtime/runtime/registry.py
    dsh_runtime/workspace/manager.py
    dsh_runtime/plugins/codex.py
    dsh_runtime/plugins/echo.py

No CodeBuddy plugin file was added.

## 3. TaskKind contract

`REPOSITORY_CHANGE` is distinct from `REPOSITORY_ANALYSIS`.

    REPOSITORY_ANALYSIS
      -> strictly read-only

    REPOSITORY_CHANGE
      -> requires allow_workspace_write=True
      -> requires max_iterations >= 2

The existing default `max_iterations=1` is preserved for DEFAULT and M4
compatibility. The first M5 caller uses a two-invocation budget: one builder
action and one verifier action.

## 4. Planner sequence

Production `SimplePlanner` now returns:

    REPOSITORY_CHANGE, iteration 0
      -> Decision(plugin="codebuddy", params={"prompt": task.goal})

    REPOSITORY_CHANGE, iteration 1
      -> Decision(plugin="codex", params={"prompt": bounded verifier prompt})

    REPOSITORY_CHANGE, iteration 2
      -> terminal Decision from the verifier's final non-empty line

The Controller still calls Planner after each successful settled invocation;
no workflow-specific Controller branch or coordinator was added.

## 5. Strict verifier-marker parsing

The Planner does not scan the whole verifier report. It normalizes line endings
through `splitlines()`, removes blank lines, strips surrounding whitespace on
each non-empty line, and interprets only the final non-empty line.

Exact accepted values are:

    DSH_VERIFICATION: PASS
    DSH_VERIFICATION: FAIL

Mapping:

    final non-empty line == DSH_VERIFICATION: PASS
      -> terminal success Decision

    final non-empty line == DSH_VERIFICATION: FAIL
      -> terminal failure Decision

    anything else, including quoted/earlier markers, trailing text, missing
    marker, malformed marker, or empty output
      -> terminal failure with "invalid verifier result"

This preserves the distinction:

    successful Codex invocation != verification PASS

## 6. Terminal Decision and Controller semantics

Existing `Decision(plugin=None)` retains terminal-success behavior, so DEFAULT,
M3 continuation, and M4 behavior remain compatible.

For a post-invocation terminal Decision:

    terminal_success=True
      -> Controller calls task.apply_success(last_invocation_result)

    terminal_success=False
      -> Controller calls task.apply_failure(terminal_error)

The initial terminal-decision safety path remains an immediate task failure.
Plugin failure, timeout, caller cancellation, maximum iterations, and existing
terminal success handling remain unchanged.

The business contract is therefore:

    CodeBuddy native success
      != repository-change task success

    CodeBuddy settled success
      -> Codex settled verification
      -> Planner terminal PASS Decision
      -> TaskState.COMPLETED

## 7. Tests changed

Only `tests/test_runtime.py` was extended. No existing test was deleted,
weakened, skipped, or rewritten to accommodate M5.

Added coverage for:

- valid `REPOSITORY_CHANGE` authority and two-invocation budget;
- rejection without write authority;
- rejection with fewer than two iterations;
- CodeBuddy-first then Codex-second production Planner routing;
- verifier prompt goal, workspace, read-only, and independent-review content;
- exact final non-empty PASS line with surrounding whitespace;
- FAIL marker terminal task failure;
- malformed, missing, quoted, non-final, and empty verdict rejection;
- deterministic CodeBuddy -> Codex -> terminal PASS completion with exactly two
  invocations;
- deterministic verifier FAIL becoming `TaskStatus.FAILED` after two
  invocations.

The existing initial-terminal safety test remains in place and covers the
backward-compatible default terminal fields.

## 8. Verification results

Focused B1-related Runtime and semantic-hardening tests:

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_runtime_semantic_hardening.py
    42 passed in 0.25s

Full regression:

    .venv\Scripts\python.exe -m pytest -q
    59 passed in 1.25s

The full suite confirms existing M1–M4 behavior remains passing while adding
the B1 semantic coverage.

## 9. Design deviation

None. The implementation follows the approved B1 design:

    existing TaskState -> existing Controller -> existing Planner seam
    + distinct TaskKind
    + backward-compatible terminal Decision outcome

No Runtime owner was duplicated or generalized. CodeBuddy native mechanics,
permission mapping, process-tree cleanup, registry wiring, and end-to-end
native verification remain future slices.

## 10. Remaining M5 slices

Not started:

    M5-B2 — bounded CodeBuddyPlugin capability
    M5-B3 — registry/workflow wiring
    M5-B4 — deterministic end-to-end verification

M2 real Codex service verification remains independently deferred /
environment-blocked. M5-B1 does not change that status.

## 11. Final status

    M5-B1 IMPLEMENTATION COMPLETE
    Milestone 5 COMPLETE: NO

Per authorization, stop after B1 implementation, tests, and this artifact.
