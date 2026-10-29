# rc.31 code and evidence security review — 2026-10-28

Disposition: keep PR #3 in draft. The reproduced source defects below are fixed
by the commit containing this report. Dependency disposition and the treatment
of the original Runtime-only configuration changes remain owner decisions.
This is not approval to merge, promote a daily entry, retire a Harness branch,
publish a package, or execute formal D2. ExecuteGate remains `NOT_CLAIMED`.

## Reviewed identity and scope

The live GitHub API and remote refs agreed on base
`c17943541a4dc854c2ebc888ed112fb7721d9c53` and initial PR head
`993055511eeec3225f5237fadf987e29973446d8`: open draft, unmerged, 92 commits,
91 changed paths. The Python and Harness plugin workflows passed for both push
and pull_request at that head. `master` was unprotected and rulesets were empty.
Those original checks do not certify a subsequent fix commit; check its own CI.

The security review covered the API contract, credentials, transport, read
broker and role loop; bootstrap/planner/CLI changes; safe traces and evidence
assembly/read/copy; Host entry/configuration/client/authentication boundary;
installer, Host compatibility and raw-evidence utilities; dependency and CI
configuration; and the acceptance records. Tests were examined for the relevant
boundaries and run without provider credentials or a live model task. Historical
acceptance reports are observations for their recorded artifact, not new-head
qualification.

## Reproduced defects and fixes

1. **P1 — API read_file accepted an external file through a hardlink.** The
   opened handle's path remained inside the workspace while its inode also had
   an outside name. A temporary synthetic outside file linked as `README.md`
   was returned to the model-facing broker. The fix checks single-link identity
   before reading and includes link count in the post-read stability check.
   The regression verifies that no bytes are read from a rejected hardlink.
2. **P1 — NTFS named streams bypassed sensitive-filename filtering.**
   `.env:review` returned a synthetic private stream even though `.env` itself
   was rejected. The broker now rejects colons and drive-qualified paths before
   filesystem access. The Windows regression reproduced failure before the fix.
3. **P2 — Credential path policy used lexical ancestors.** A junction pointing
   to a Git repository's settings subdirectory hid the Git root from the
   credential catalog. The analogous Host Profile path could alias a directory
   inside Runtime source and pass the outside-source check. Runtime now checks
   physical parents as well as lexical parents and reads the physical path;
   Host compares physical source and credential locations. Both reject hardlink
   credential aliases. Separate Python and Host regressions failed before the
   fixes. This remains an operator-owned configuration boundary, not isolation
   from an adversarial process running under the same Windows account.
4. **P2 — HTTP response size was checked after full buffering.** A simulated
   6.25 MiB body consumed all 100 chunks before the 1,000,000-byte check rejected
   it. The transport now stops incremental consumption at that bound, closes
   the response, applies a total request deadline, and rejects error/redirect
   responses before reading their bodies. It explicitly requests identity
   encoding and rejects compressed responses to prevent decompression expansion.
   Tests cover early stop, closure, split successful JSON, auth failure,
   compression rejection and no redirect even with a redirect-enabled client.
   A gateway that ignores identity encoding will now fail closed; the new
   packaged candidate needs a separately authorized bounded live acceptance.

All reproductions used synthetic files or an in-memory HTTP transport. No real
credential contents were printed, committed, or submitted to a provider.

## Host / Runtime boundary and evidence conclusions

- Host selects the current Session/workspace, performs governance admission,
  and owns run IDs and evidence paths. The tool exposes task kind, prompt and
  description, not arbitrary provider endpoints or credential values.
- API role configuration contains connection references; the Runtime loads the
  external credential catalog. Only the two exact HTTPS gateway bases are
  allowed. Default HTTP clients disable redirects and environment proxies.
  API worker writes remain unavailable; reviewer/inspector use bounded reads.
- The official subprocess package scrubs sensitive parent variables and DSH
  variables. Explicit Profile environment values are still trusted operator
  input. Native CLI workers are not an OS security boundary against a hostile
  local process; external credentials and evidence roots need to remain private.
- The evidence route is registered through Host Connection authentication and
  checks parent Session ownership of the child. Trace schemas contain allowlisted
  metadata. The browser renders report and Diff content as React text.
- **Raw Diff and model verification text are not automatically secret-redacted.**
  Workspace evidence observes tracked and non-ignored files, with documented
  exclusions. Do not treat an entire Home, Diff or evidence bundle as safe to
  publish merely because the safe-event trace omits content.
- Copy receipts bind copied bytes and inventory, but are unsigned and do not
  authenticate the author. Governance ALLOW linkage remains Session + task kind,
  not run ID. Shared-workspace snapshots cannot prove exclusive actor attribution.
- The raw-host utility checks a bounded subset (identities, closure byte counts,
  target metadata and audit linkage); it does not itself validate every native
  trace event or reconstruct the patch. This review additionally ran the strict
  worker and API trace parsers against the actual second-device evidence.

## Original dirty Runtime overlap

The original checkout stayed at `f35b79d67f70df136997587809fb28a01b4a5e05`.
Each comparison used original HEAD, its working bytes, and candidate HEAD.
Merge previews were generated outside both repositories; none was applied.

| File | Reconciliation |
| --- | --- |
| `dsh_runtime/bootstrap.py` | Original dirty changes add bounded `DSH_CODEBUDDY_MAX_TURNS` and `DSH_CODEBUDDY_MAX_OUTPUT_CHARS` configuration. Candidate has API role setup but not those overrides. The text merge is clean, but this is still a behavior change requiring an explicit product choice. |
| `dsh_runtime/planner.py` | The original dirty-workspace/attribution prompt change is already included. The merge result equals candidate after newline normalization. Candidate also carries explicit role selection. |
| `dsh_runtime/plugins/codebuddy.py` | Run binding, closure marker, long Windows paths and late-init handling are already present. Turn/output override constants, hard limits, environment removal and larger JSON observer buffer are not fully ported. One three-way conflict is `_MODEL_ID` versus output-limit constants: a later port must retain both, preserving candidate model support and stdout settling changes. |
| `tests/test_codebuddy_plugin.py` | The original late-init regression is already included; the merge result equals candidate after newline normalization. Candidate has additional model/settling/CI tests. |

Do not replace these files wholesale with either version. In particular,
setting the two old local override variables on this candidate does not grant
the same effective Runtime limits. A separate port should preserve defaults,
validate upper bounds and reconcile Host-reported limits with actual settings.
No such port was silently included in this security fix.

Before/after status and byte hashes confirmed all 16 original Runtime dirty
files and all 108 files represented by 106 Harness dirty entries were unchanged.
The separate private integration checkout remained clean. The original four
file patches and three-way previews are retained locally, not published.

## Credentials and frozen evidence checks

The heuristic scan covered all **775 blobs reachable from the initial PR head**.
After excluding filename substrings mistakenly resembling token prefixes, its
20 matches were known fake-key literals across historical versions of
`tests/test_api_agent_contract.py`. No live credential was identified. This is
not an exhaustive absence proof, a scan of every external Home, or a review of
all unrelated local Git refs. No history was rewritten.

The frozen kit ZIP still hashes to
`323928F8FBE4272474D071C93772240171EA1214864272D3D258CCA0F6C0C9FB`.
Its plugin/runtime payload hashes match its Manifest and it still embeds Runtime
`d3af857bb87babb0f96b87adc2839f8761b45eba`. It does **not** contain these security
fixes. Keep its original bytes as historical evidence; produce a new versioned
artifact before a new delivery claim.

The second-device evidence ZIP still hashes to
`77E4D91EC3B93F001D812B39BE722C321CE6FA9EFBD4F86D3C9BBF8A4F4F6B26`.
The independent bounded checker again returned `RAW_EVIDENCE_CONSISTENT` with
the target verified at 22 bytes and SHA-256
`937a119b10c6e2140f4bb46c4e8221f51a9e1a1d935eca68774a523e55f2dd06`.
Strict trace parsers also returned available/complete: worker Read 1, Edit 2,
Write 1, Bash 1; reviewer read_file 1 and completed, matching the Manifest.
These results substantiate the old bounded run only.

## Open dependency finding and owner decisions

`pnpm audit --prod --json --registry=https://registry.npmjs.org/` reported
**9 advisories: 5 high, 4 moderate, 0 critical** against the candidate's production
dependency graph. This is a successful vulnerability query with findings, not
a clean audit. The configured mirror had no audit endpoint; that failed query
was retained separately.

- `zod@4.4.3` is direct and also used by official rc.4 packages. The reported
  patched version is 4.6.6. See [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5).
- `undici@8.11.2` is reached through
  `@deepseek-ai/dsh-subprocess@0.2.1-rc.4 -> @deepseek-ai/dsh-http-proxy@0.2.1-rc.4`.
  The eight reported advisories are patched in 8.12.2, including
  [cross-origin cache disclosure](https://github.com/advisories/GHSA-4w7w-5xrc-9h26).
  Package presence does not establish that each vulnerable feature is reachable
  in the current Host configuration. Reachability and a supported upgrade still
  require separate assessment.

Recommended next decisions, in order:

1. Select dependency remediation and a newly versioned private candidate as the
   next work item; retain the exact frozen rc.31 kit as historical evidence.
   Changing shared Host dependencies requires compatibility/install acceptance,
   not an unreviewed audit-fix override. Do not claim stable/public readiness.
2. Decide whether to port the remaining original CodeBuddy limit overrides into
   that candidate, or explicitly defer them and retain the current defaults.
3. Before any merge authorization, decide `master` protection, required Python
   and plugin checks, required human review and merge method. Recheck the exact
   base/head and current-head CI after those decisions. This review recommends
   retaining draft status while the dependency disposition is unresolved.
4. New package acceptance, daily-entry promotion, old Harness retirement and
   formal D2 are separate decisions. None follows automatically from source CI.

## Validation

Python full-suite results were **620 passed, 1 skipped**; the logs and plugin
suite logs are retained in the local review bundle. Node 24.19.0 and pnpm 11.25.0
passed typecheck, build, all 14 named CI
test scripts, and the additional raw-host verifier suite: 78 top-level Node
tests, no skips. Initial Node 20 / restricted-child-process failures are retained
as environment failures, not counted as passes. Python's symlink privilege skip
is distinct from the Windows junction, named-stream and hardlink regressions,
which ran. No live model trial, new installation or formal ExecuteGate was run.
