# Historical evidence relocation design (proposal)

Status: experimental implementation in the isolated `codex/evidence-relocation-20261025` branch. The qualified daily candidate still accepts only a Manifest whose absolute `workspace_changes.diff_content_ref` resolves to the `diff.patch` in the selected evidence root. Nothing migrates automatically. The original evidence root remains required for the qualified daily entry.

`pnpm test:terminal-evidence` covers original reads, copied-root rejection without a receipt, receipt-verified replay, altered Diff/trace/receipt rejection, wrong parent, missing run and parent ownership. `pnpm test:copy-terminal-evidence` covers the explicit copier. These focused tests do not yet qualify a daily release.

## Goal and invariant

Allow a user to move an independent Home and still open an old settled Runtime drawer while retaining the original `evidence-manifest.v1.json` and `diff.patch` **byte for byte**. A copied file must never silently acquire the label of a fresh Runtime run. The original run, workspace, reviewer verdict and audit remain as recorded; relocation provenance is separate.

## Proposed copy receipt

A trusted, explicit migration command copies one run into a new Home only when the destination run directory is absent. It reads the source Manifest, Diff, lifecycle marker and trace artifacts from bounded regular files, rejects links and escapes, checks the run/workspace identities, and verifies every copied byte against its source. It writes a separate `evidence-relocation.v1.json` in the destination, never in the source. Proposed receipt fields:

| Field | Meaning |
| --- | --- |
| `schema_version`, `run_id`, `workspace_id` | Fixed format and original identities. |
| `source_diff_content_ref` | Exact historical absolute reference in the original Manifest. |
| `manifest_sha256`, `diff_sha256` | Digests of the original bytes and their destination copies. |
| `source_run_fingerprint` | Digest of a sorted path/digest inventory of the bounded source run artifacts. |
| `copied_artifacts` | Sorted relative names and SHA-256 values copied into this run. No arbitrary absolute target paths. |
| `created_at` | Migration time, explicitly separate from Runtime task time. |

The receipt is an integrity statement about the copy, **not** a signature or independent proof that the source Runtime task was correct. If a malicious actor can alter both the source and receipt, these hashes alone cannot establish authenticity. Do not represent them as such.

The experimental installed command is `dsh-runtime-copy-evidence --source-evidence-root ABS_SOURCE_EVIDENCE --target-evidence-root ABS_EMPTY_TARGET_EVIDENCE --run-id dsh-runtime-UUID --workspace-id SESSION_ID` (`node scripts/copy-terminal-evidence.mjs` from source). It copies one settled run only, refuses an existing target run, rejects symbolic and multiply linked files, and leaves any interrupted `.dsh-evidence-copy-*` staging directory visible for diagnosis. It does not clean that directory automatically. The caller must create the destination evidence root and arrange the corresponding Session migration separately. It copies the bounded top-level artifacts plus the Runtime-owned `safe-trace-<run-id>` directory, retaining original file bytes. Never point an active daily Profile at an experimental target.

## Read contract

The Host first follows today's strict original-path check. On mismatch, it may consider a relocation receipt only when the run directory and files are bounded regular files inside the selected evidence root. It must validate receipt schema, identities, the exact original Diff reference, all recorded hashes, and a fixed relative `diff.patch` name. It reads via bound handles to avoid a path swap between validation and content reads. Missing, malformed, oversized, symlinked, conflicting or digest-mismatched receipts fail closed. The authenticated Session ownership check remains unchanged.

If accepted, the route returns `relocation: { status: 'verified_copy', createdAt }` alongside the unchanged Manifest and Diff. The drawer displays a historical-copy label and explains that hashes do not prove task correctness. The copier compares source and destination bytes at migration time; replay later does not require the original disk to remain mounted.

## Acceptance before implementation is enabled

1. No-model tests for exact copy, missing original path after copy, omitted receipt, altered Manifest/Diff/trace/receipt, swapped identities, oversized files, links, directory replacement, concurrent writer and interrupted migration. The original run bytes and old Home must remain unchanged in every case.
2. Authenticated route tests: parent Session ownership, anonymous 401, wrong child 404, valid migrated copy with explicit provenance, invalid copy unavailable. The UI must never present a migrated copy as original-path evidence.
3. Fresh isolated official Host install and old-session drawer replay on the proposed Host version. Compare visible tabs, labels and terminal status with the original root. A bounded real task is required only if the change also touches task execution or reviewer behavior.
4. The migration utility is separate from installation and never runs automatically during a Host update. The user selects the source and destination Homes; the tool refuses overwrites and writes an audit receipt outside the package.

Until all four gates pass, retain the original evidence root and use the read-only diagnostic before historical replay.
