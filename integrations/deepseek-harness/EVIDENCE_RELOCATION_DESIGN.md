# Historical evidence relocation design (proposal)

Status: design only. The current authenticated route accepts only a Manifest whose absolute `workspace_changes.diff_content_ref` resolves to the `diff.patch` in the selected evidence root. The read-only `check-evidence-home.mjs` detects an incompatible copied root. Neither command nor route repairs historical evidence.

`pnpm test:terminal-evidence` fixes the current fail-closed behavior as a regression: an original run reads, its byte-identical copied run is rejected, a wrong parent is rejected, and a missing run returns no evidence. The future relocation implementation must add explicit receipt cases rather than weakening this original-path check.

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

## Read contract

The Host first follows today's strict original-path check. On mismatch, it may consider a relocation receipt only when the run directory and files are bounded regular files inside the selected evidence root. It must validate receipt schema, identities, the exact original Diff reference, all recorded hashes, and a fixed relative `diff.patch` name. It reads via bound handles to avoid a path swap between validation and content reads. Missing, malformed, oversized, symlinked, conflicting or digest-mismatched receipts fail closed. The authenticated Session ownership check remains unchanged.

If accepted, the route returns a separate relocation status (for example `verified_copy`) alongside the unchanged Manifest and Diff. The drawer must display that this is a migrated copy and keep the model verdict and snapshot attribution labels distinct. If the original root is still available, compare its current digest inventory with the receipt when migrating; replay later must not require the original disk to remain mounted.

## Acceptance before implementation is enabled

1. No-model tests for exact copy, missing original path after copy, omitted receipt, altered Manifest/Diff/trace/receipt, swapped identities, oversized files, links, directory replacement, concurrent writer and interrupted migration. The original run bytes and old Home must remain unchanged in every case.
2. Authenticated route tests: parent Session ownership, anonymous 401, wrong child 404, valid migrated copy with explicit provenance, invalid copy unavailable. The UI must never present a migrated copy as original-path evidence.
3. Fresh isolated official Host install and old-session drawer replay on the proposed Host version. Compare visible tabs, labels and terminal status with the original root. A bounded real task is required only if the change also touches task execution or reviewer behavior.
4. The migration utility is separate from installation and never runs automatically during a Host update. The user selects the source and destination Homes; the tool refuses overwrites and writes an audit receipt outside the package.

Until all four gates pass, retain the original evidence root and use the read-only diagnostic before historical replay.
