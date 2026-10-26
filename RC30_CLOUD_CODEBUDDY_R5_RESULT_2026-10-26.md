# rc.30 second Windows device CodeBuddy/API reviewer run

Date: 2026-10-26. This is one bounded, non-D2 `repository_change` trial on the Wuying Windows Server 2022 cloud desktop, using the private rc.30 Profile against unmodified official `@deepseek-ai/dsh@0.2.1-rc.3`. The CodeBuddy worker was pinned to `deepseek-v4.1-flash`; the reviewer and inspector used the configured SiliconFlow API agent. This record does not authorize a daily, stable or public release. Formal D2 ExecuteGate remains `NOT_CLAIMED`.

## Source and transfer

- User-provided UI screenshots showed task `7242eeea-5a75-48f7-a4d9-ec96e2d4eac2` as `completed` / model reviewer `PASS`, with execution, change and audit tabs, one added target, and settled audit call `e6e3fc6e-234f-4f77-9616-d179a6b58f7f`.
- A separate read-only check on the cloud device reported exact comparison with ASCII `CLOUD_RC30_CODEBUDDY_OK` plus one LF, 24 bytes, and Git status only `?? cloud-rc30-codebuddy-r5.txt`. The parent receipt and reviewer text said 25 bytes; that count was wrong, while the independent byte check and transferred file agree on 24.
- The user transferred `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\handoff-codebuddy-r5-7242eeea.zip`. Local size: 6,611 bytes; local ZIP SHA-256: `d121a04af804d9f254ad5f6eab19cbf92149a05ad8fde383bac62221fe85c547`. The user independently read the cloud-side ZIP SHA-256 before shutdown; it exactly matched the local value, completing the transfer-integrity check. The archive has exactly ten files: the single run's Manifest, run state, Diff, Runtime call trace, two safe JSONL traces and two `.closed` markers, one governance audit file, and the target file. It contains no Home, Profile, connection JSON or key file.
- Extracted only after checking archive entry count, relative paths and per-entry size into `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\cloud-r5-raw-7242eeea`. The original cloud run, its target file and historical cloud installations were not changed or rerun.

## Independent local consistency check

The repository's read-only `integrations/deepseek-harness/scripts/verify-raw-host-run.mjs` exited 0 with `RAW_EVIDENCE_CONSISTENT` for this extracted run, its audit and the copied target file.

| Check | Result |
| --- | --- |
| Run | `dsh-runtime-7242eeea-5a75-48f7-a4d9-ec96e2d4eac2` |
| Task / verdict | `repository_change`, `completed`, `PASS` |
| Workspace | `session-cdca27a9-331b-4cb5-b143-3fced0273158` |
| Manifest SHA-256 | `f0abf5bef8ac6dfc7aea3c2b1b2ca372dd59e7c6516328cdce71f2350c737c4b` |
| Diff SHA-256 | `ba5c8c23079dc3106f6edd50b1e9651e781b7322cacadb2a90cf1e6677d797f0` |
| Worker safe trace | 6,462 bytes; SHA-256 `8ef18d3e884a300cd7a59be0cc8a09acb94ad48e43f8d6214a5fd8d653a7ada9`; `.closed` matched |
| API reviewer safe trace | 741 bytes; SHA-256 `98f3495f17510ee2a44163b1f6579a8c7a530599d1bc0aaa126cfe8bb916e915`; `.closed` matched |
| Audit | one governance `ALLOW` matching Session and task kind; terminal call trace matched |
| Target | `cloud-rc30-codebuddy-r5.txt`, 24 bytes; SHA-256 `f03448bc24bc7620c4994c99131786dd37fa6517e8cb39ec419ca384d99c5b90` |

The governance audit has no run ID, so its `ALLOW` links to this run by Session and task kind, not by a unique run field. The verifier checks bounded consistency of copied records and target bytes; it does not establish who authored the workspace delta, prove the model's semantic judgment, or constitute release approval. A full old-entry rollback exercise remains open. No D2 call was made or claimed.
