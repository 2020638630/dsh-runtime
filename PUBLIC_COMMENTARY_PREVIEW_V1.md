# C1 public commentary preview v1

Scope: only completed Codex `agentMessage` items whose phase is `commentary`,
from the original repository-change Worker. This is public explanatory output,
not internal reasoning, token deltas, tool output, final answer or review evidence.
Both native thread and turn must already be known and match. Runtime invocation
scope must independently bind Worker role, Codex adapter, invocation index 1,
Run and Workspace. Index alone is not authority. Late callbacks after invocation
closure are ignored. Existing task settlement and manifests are unchanged.

## Capability and transport

New Host opts in only for repository_change with Codex Worker, when the Runtime
contains both activity.py and public_preview.py. It assigns a fresh UUID through
`DSH_RUNTIME_PUBLIC_PREVIEW_STREAM`; Runtime consumes it before native CLI launch,
and Codex/CodeBuddy overlays also strip it. Old Host supplies no capability, so
new Runtime emits no body frames. Old Runtime is not sent the capability. No
ordinary stderr diagnostic fallback receives these frames in the new Host.

Separate prefix `DSH_RUNTIME_PUBLIC_PREVIEW_V1 ` carries one ASCII-escaped JSON
object per line (maximum 4096 bytes). Envelope: v=1, runId, workspaceId, streamId,
type. Begin has only envelope. Message adds seq, invocationId, invocationIndex=1,
role=worker, adapter=codex, itemId, phase=commentary, atMs, text, truncated. End adds
lastSeq and dropped. Unknown fields/versions/identities/roles are rejected.
Sequence gaps, conflicts, missing begin/end and drain failures are visible as
incompleteness, never inferred as model progress or success.

## Independent memory budgets

- Runtime queue: 8 frames / 32 KiB, plus closing marker; 1024 UTF-8 bytes maximum
  per text, shortened further if escaped frame exceeds its limit.
- Deduplicate at most 128 distinct source item IDs per Run; further items dropped.
- Host: latest 8 messages / 16 KiB serialized message bytes; at most 32 Runs;
  terminal retention 30 minutes. Earlier evictions are not recoverable.
- Source IDs, queue, Host window and UI polling are independent from B activity
  storage. Sender writes share a per-Run serialization lock only to avoid interleaving
  frames on the pipe. Different Runtime processes or reused in-process Run
  contexts do not share this lock. Producers do not wait on pipe writes. Close waits at most
  200 ms; observation loss is allowed and never changes task outcome.

Authenticated `view=public-preview` uses the existing parent catalog ownership
check plus canonical evidence-root/Run/Workspace identity, returns a bounded full
window with no-store. No filesystem fallback, no recording in manifest, audit,
trace or B activity, no replay after Host restart. UI starts collapsed, fetches
only while expanded, renders escaped plain text with no Markdown/HTML/link
interpretation, and cancels stale reads on scope change/close.

This is not guaranteed redacted. Public commentary may contain sensitive text;
truncation and source filtering do not make it safe to share. Do not log bodies.
An empty/unavailable window does not prove inactivity or that a role never ran.
Linux synthetic validation is not Windows real CLI or daily-build acceptance.

## Backpressure boundary (not an independent transport)

B and C1 have independent producer queues and Host retention budgets, but share
stderr transport capacity. A stopped/slow Host reader may block a sender and
therefore delay or drop both B and C1 observation frames, including closing
markers. The per-Run lock does not make pipe writes nonblocking. This candidate
does not claim that C1 can never affect B delivery latency or completeness.
Task execution/settlement does not wait on the pipe; bounded close waits and
sender daemon exit permit completion even with an undrained or disconnected
pipe. Synthetic subprocess tests exercise both cases and validate received full
frames, not complete delivery. If independent B transport availability is an
acceptance requirement, C1 needs a separate transport before release. No Windows
nonblocking I/O change is made; Windows execution remains pending CI/real use.
