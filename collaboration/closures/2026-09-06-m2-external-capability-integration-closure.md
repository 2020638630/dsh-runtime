# Milestone 2 — External Capability Integration Closure

Date: 2026-09-06  
Overall status: `IMPLEMENTATION COMPLETE`  
Real-service verification: `DEFERRED`

## Milestone status

| Area | Status |
|---|---|
| 2-A.1 Source Investigation | COMPLETE |
| 2-A.2 Runtime Verification | COMPLETE |
| 2-A.3 Evidence Synthesis | COMPLETE |
| 2-B Minimal External Invocation Contract | COMPLETE |
| 2-C.1 Implementation Plan | COMPLETE |
| 2-C.2a Lifecycle Verification | PASS |
| 2-C.2b Runtime Semantic Hardening | PASS |
| 2-C.2c First Codex-backed Capability | PASS |
| 2-C.2d Real Integration Evidence Hardening | ENVIRONMENT_BLOCKED |

## Proven Runtime shape

```text
DSHController
  ↓
Executor
  ↓
Plugin.execute()
  ↓
Concrete bounded capability
  ↓
PluginResult
  ↓
TaskState
```

The following decisions are settled for Milestone 2:

- DSH owns the business loop.
- Executor owns Runtime timeout/cancellation governance.
- The concrete capability owns bounded internal mechanics.
- `Plugin.execute()` remains sufficient.
- `ExecutionHandle` remains unjustified.
- `ProcessManager` remains unjustified.
- Process lifecycle remains an optional execution fact.
- `workspace_id` remains logical identity.
- Authority is decided by DSH and mapped by the concrete capability.

## Codex evidence boundary

Real Codex `0.153.0` evidence proves:

```text
process startup
initialize
thread/start
ephemeral=true
cwd propagation
turn/start
bounded Executor timeout
process cleanup settlement
safe timeout result
```

The current account/service/network environment does not complete the real model turn. The following therefore remain externally blocked or unknown:

```text
successful real model turn
real final-answer delivery
native requested-write denial
real workspace-write side effect
interrupt acknowledgement
real descendant process-tree behavior
real completion/deadline race
```

These unknowns are not Runtime defects and must not be presented as such.

## Deferred verification gate

Do not reopen implementation merely because time has passed. Reopen real-integration verification only when a minimal real Codex turn reaches `turn/completed`.

When that gate is met, verify in this order:

1. Successful final-answer mapping.
2. Read-only requested-write behavior.
3. Workspace-write disposable side effect.
4. Real cancellation/interrupt, if practical.
5. Descendant process-tree behavior, if practical.

Any production change remains evidence-driven and must be the smallest correction to the existing owner.

## Explicit no-change decisions

The following remain deferred and are not required for Milestone 2 closure:

```text
ExecutionHandle
ProcessManager
Provider Framework
ExternalAgent
AgentExecutor
CodexAdapter
generic PermissionPolicy
generic process result model
streaming
resume
persistent session
multi-turn
rollback
diff
usage/cost accounting
```

## Verification baseline

Formal 2-C.2d full regression:

```text
.venv\Scripts\python.exe -m pytest -q
33 passed in 0.98s
```

## Next-session handoff

Milestone 2 implementation is closed. The next development session should treat Runtime design and the first bounded Codex capability as completed evidence-backed work, and should treat only the real-service verification items above as deferred. No architecture reopening or additional capability feature work is implied by this checkpoint.
