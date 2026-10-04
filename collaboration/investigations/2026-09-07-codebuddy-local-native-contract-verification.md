# CodeBuddy Local Native Contract Verification

Date: 2026-09-07
Scope: verify the installed CodeBuddy CLI against the frozen v1 native contract
Implementation: none

## 1. Result summary

The installed native surface is usable for a bounded, non-interactive CLI
invocation and can directly modify a file in the exact process cwd. The safest
file-edit mapping observed was `--permission-mode acceptEdits` with
`--tools Read,Edit`, without `--add-dir`, `--sandbox`, or
`--dangerously-skip-permissions`.

The evidence does not prove that this mapping provides a complete DSH
write-capable coding executor: command/test execution, absolute-path boundary
enforcement, child-process cleanup, and durable session behavior remain
incomplete or unverified.

Final gate verdict:

    PARTIALLY READY – SPECIFIC NATIVE DEBT REMAINS

This artifact does not declare Milestone 5, create an implementation plan, or
authorize a CodeBuddyPlugin.

## 2. Test environment and safety boundary

Installed product:

    package: @tencent-ai/codebuddy-code
    version: 2.143.0
    executable: D:\Program Files\node-js\codebuddy.cmd

All mutation probes ran only in this disposable repository:

    D:\PythonProject\dsh-runtime\.tmp-codebuddy-native-check\repo

The repository contained only a local Git metadata directory and probe files.
The DSH Runtime repository was never used as CodeBuddy's cwd. No parent or
unrelated repository was supplied with `--add-dir`. No `--sandbox` and no
`--dangerously-skip-permissions` were used.

## 3. Exact invocation evidence

Version/help verification:

    codebuddy.cmd --version
    codebuddy.cmd --help

The help output confirms:

- `--print` is non-interactive and exits after producing a response.
- `--output-format` supports `text`, `json`, and `stream-json` in print mode.
- `--input-format` supports `text` and `stream-json` in print mode.
- `--max-turns` bounds agentic turns.
- `--permission-mode` supports `acceptEdits`, `bypassPermissions`, `default`,
  `plan`, `dontAsk`, and `auto`.
- `--tools` restricts built-in tools; `Read,Edit` is accepted.
- `--add-dir` grants additional directory access.
- `--no-session-persistence` is available.
- `--sandbox` is an alternate execution mode and was intentionally not used.

Successful no-tool authentication probe:

    codebuddy.cmd --print --output-format json --input-format text \
      --max-turns 1 --no-session-persistence --tools "" \
      --permission-mode plan \
      "Reply exactly AUTH_PROBE_OK. Do not use tools or modify files."

Observed: exit code `0`; a successful result containing `AUTH_PROBE_OK`.

Successful stdin probe:

    stdin text | codebuddy.cmd --print --output-format text --input-format text \
      --max-turns 1 --no-session-persistence --tools "" \
      --permission-mode plan

Observed: exit code `0`; output `STDIN_PROBE_OK`.

## 4. Authentication readiness

Classification: `READY`

The local CLI completed a non-interactive model turn from a disposable cwd,
using the existing local authentication/configuration state. No interactive
login prompt occurred. No credential, token, cookie, or authentication value
was printed or recorded.

The exact credential source was not inspected. The evidence proves reuse of
the existing authenticated state for `--print`, not the provenance or future
stability of that state.

## 5. Output and exit contract

### Text output

With `--output-format text`, a successful bounded invocation returned only the
final text in the probes. The mutation probe returned:

    MUTATION_PROBE_OK

and exited with code `0`.

### JSON output

With `--output-format json`, the successful probe was parseable as a top-level
JSON array rather than a single JSON object. It contained four events with
types:

    message, reasoning, message, result

The final result event had:

    subtype: success
    is_error: false
    result: JSON_PROBE_OK

The result also contained a session identifier and usage information. This is
enough to identify a successful final result, but the full event-array schema
and its stability are not frozen by this verification.

### Error and exit behavior

An invalid model probe printed a native service error to stderr and returned
exit code `0`. A `--max-turns 1` probe printed `Max turns (1) exceeded`, also
returned exit code `0`, and left the target file unchanged.

Therefore exit code alone is not a sufficient future failure signal. A future
normalization would need to inspect the settled output/error stream and the
native result shape. No new result DTO is introduced here.

Classification:

    successful text output: PASS
    successful JSON result: PARTIAL
    failed execution exit semantics: PARTIAL
    stable error schema: NOT VERIFIED
    stream-json: NOT VERIFIED (not required by the current evidence)

## 6. Same-cwd mutation gate

The disposable repository was launched with cwd:

    D:\PythonProject\dsh-runtime\.tmp-codebuddy-native-check\repo

Before invocation:

    marker.txt = before-codebuddy

Mutation invocation:

    codebuddy.cmd --print --output-format text --input-format text \
      --max-turns 3 --no-session-persistence \
      --tools Read,Edit --permission-mode acceptEdits \
      "In the current working directory, edit marker.txt by replacing the
       exact line before-codebuddy with after-codebuddy. Do not access any
       other path and do not run commands. After the edit, reply exactly
       MUTATION_PROBE_OK."

Observed:

- process-backed invocation exited with code `0`;
- output was `MUTATION_PROBE_OK`;
- `marker.txt` became `after-codebuddy`;
- an external PowerShell read of the same cwd immediately saw the change;
- Git reported `marker.txt` as an untracked file in that same repository;
- `git worktree list` showed only the disposable repository worktree;
- no sandbox or `--add-dir` argument was present.

Same-cwd mutation classification: `PASS`.

This proves direct mutation in the supplied cwd. It does not prove that every
CodeBuddy tool or absolute path is confined to that cwd.

## 7. Authority mapping

### Documented behavior

- `--permission-mode acceptEdits` is a distinct permission mode intended for
  edit-capable operation.
- `--tools` can restrict the available built-in tools.
- `--add-dir` expands directory access and was omitted.
- `--dangerously-skip-permissions` is high risk and was omitted.
- `--sandbox` changes the execution location and was omitted to preserve the
  exact-cwd contract.

### Observed behavior

The following combination successfully performed the harmless file edit:

    --permission-mode acceptEdits
    --tools Read,Edit
    no --add-dir
    no --sandbox
    no --dangerously-skip-permissions

With `--tools Read,Edit`, a prompt requiring `Get-Location` produced
`BASH_DENIED`; the command tool was not available. This confirms a useful
tool-level restriction for the file-only probe.

An outside-cwd sentinel read was attempted without `--add-dir`. In both
`plan` and `acceptEdits` modes, the non-interactive run returned a denial. The
native explanation said approval was required and unavailable, and explicitly
did not claim a path-boundary rule. This is not sufficient proof of a hard
cwd-only read boundary.

### Mapping conclusion

Evidence-backed file-edit mapping:

    DSH allow_workspace_write=True, file-only probe
      -> --permission-mode acceptEdits --tools Read,Edit
      -> no --add-dir, no --sandbox, no dangerous bypass

This mapping is `PARTIAL` for the intended primary coding workflow because
tests and terminal commands were not enabled or safely constrained here. A
mapping that includes Bash/terminal access, or a guarantee that absolute paths
outside cwd are denied, is not frozen by this investigation.

The read-only Codex verifier remains outside this native CodeBuddy mapping and
continues to use the existing read-only Runtime path.

## 8. Bounded lifecycle and settlement

Normal print-mode probes completed as a single process-backed invocation and
returned a terminal result before the shell command completed. Successful
probes included text, JSON, stdin, and the same-cwd mutation task.

The max-turn probe used `--max-turns 1`. It produced `Max turns (1) exceeded`,
returned exit code `0`, and did not modify `maxturn-marker.txt`. This proves a
native max-turn bound is observable and prevents the requested second step in
that probe.

The process was launched directly in the disposable cwd without sandbox or
worktree options. No alternate worktree was listed by Git.

Classification:

    normal print settlement: PASS
    max-turn bound: PASS
    process-backed bounded shape: PASS
    terminal result/error normalization: PARTIAL
    child-process behavior: NOT VERIFIED
    background-process survival: NOT VERIFIED
    session persistence on disk: NOT VERIFIED

The `--no-session-persistence` option was included in all probes. The result
still carried an in-memory session identifier; durable disk persistence was
not independently inspected. The option is therefore documented and used,
but its complete persistence semantics remain a native debt.

## 9. Cancellation and cleanup

The CLI help exposes no print-mode native interrupt operation. The separate
in-process server declarations mentioned by the prior investigation were not
selected or tested as the primary direction.

A disposable stream-input process was started with no input, confirmed to be
still running after a short wait, and the top-level process was explicitly
terminated. The top-level process exited. Process enumeration for child
relationships was denied by the local environment, so child survival and
complete process-tree cleanup could not be established.

Cancellation/cleanup classification: `PARTIAL`.

The evidence supports external termination of the top-level CLI process. It
does not prove that terminating the parent always settles all descendants or
that a CLI-native interrupt is available. Existing DSH Executor timeout and
cleanup behavior may be able to govern the top-level process, but acceptable
descendant semantics remain a deferred native verification item.

## 10. Area classification

| Area | Classification | Evidence boundary |
|---|---|---|
| non-interactive invocation | PASS | `--print` completed text, JSON, and stdin probes |
| authentication readiness | PASS | non-interactive model turn succeeded |
| bounded max-turn shape | PASS | max-turn exceeded and prevented edit |
| output schema | PARTIAL | JSON event array/result observed; stability not frozen |
| exit semantics | PARTIAL | native failures observed with exit code 0 |
| same-cwd mutation | PASS | disposable marker changed and was externally visible |
| workspace authority mapping | PARTIAL | file-only mapping works; hard cwd boundary unproven |
| process settlement | PASS | normal print invocations settled and exited |
| cancellation / cleanup | PARTIAL | top-level termination works; descendants unverified |
| session persistence behavior | PARTIAL | flag documented/used; disk persistence not checked |

No native behavior observed in this verification contradicted the desired v1
contract, so no area is classified as `FAIL`. Missing evidence is classified
as `PARTIAL` or `NOT VERIFIED`.

## 11. Remaining native debt and gate decision

The following prevent `READY FOR MINIMAL IMPLEMENTATION DESIGN`:

1. Prove or explicitly constrain outside-cwd and absolute-path access.
2. Decide whether terminal/test execution is required and establish a safe,
   bounded tool mapping for it.
3. Freeze the smallest stable JSON/text/error normalization contract.
4. Verify child-process and background-process behavior under parent timeout.
5. Verify whether `--no-session-persistence` prevents durable state for the
   intended invocation.

Authentication and direct same-cwd file mutation are no longer blockers for a
future design. The remaining items are specific native contract debt, not a
Runtime architecture gap.

Final verdict:

    PARTIALLY READY – SPECIFIC NATIVE DEBT REMAINS

## 12. Files created or changed

Created:

- `collaboration/investigations/2026-09-07-codebuddy-local-native-contract-verification.md`

Temporary disposable verification workspace was removed after evidence
collection. No production file, existing test, `PROJECT_STATE.md`, Runtime
abstraction, TaskKind, Planner, CodexPlugin, or CodeBuddyPlugin was changed.
