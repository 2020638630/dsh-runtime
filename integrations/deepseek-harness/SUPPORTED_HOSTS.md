# Official Host support matrix

Updated 2026-10-25. This matrix describes observed evidence, not a version range or an automatic upgrade policy. All entries use the unmodified official `@deepseek-ai/dsh` Host. D2 ExecuteGate is `NOT_CLAIMED`.

| Host | Plugin / Runtime source | Evidence reached | Use status |
| --- | --- | --- | --- |
| `0.2.1-rc.2` | Plugin `0.1.0-rc.21`; Runtime `d3af857` | Isolated real `repository_change` completed/PASS, dual terminal traces, audit and three-tab drawer; r10 Host preflight candidate has fresh install, no-model Web and six prewrite checks | Private isolated candidate; daily switch not claimed here |
| `0.2.1-rc.3` | Plugin probe `0.1.0-rc.22`; Runtime `d3af857` | Artifact inventory, typecheck/build/focused tests, fresh install, authenticated Web, anonymous evidence denial, six-workspace old-session UI sample and authentic historical drawer replay | No-model compatibility probe only; no new model task or daily qualification |
| `0.2.1-rc.3` | Relocation plugin `0.1.0-rc.30`; Runtime `d3af857` | Exact rc.3 dependency alignment, clean inventory, focused tests, separate Home install, config dump, authenticated Web, anonymous denial, parent-owned relocated evidence HTTP replay, old-session three-tab drawer visual replay with historical-copy label, and six-workspace historical UI sample in an isolated Home. | Experimental no-model candidate; no rc.30 model-backed qualification or daily replacement |

The rc.3 inventory found nine imported package metadata/version changes and no changed imported code/type artifact digest. The Host runner lock/dependencies changed, so the focused no-model gate ran. This observation does not authorize a future rc.4 or a different install of rc.3: installer/launcher checks the exact package metadata and artifact digests from its own Manifest. Keep the known-good pinned Host and Home available until the proposed replacement meets the appropriate [update gate](HOST_COMPATIBILITY_GATE.md).

Historical Runtime Manifests store an absolute Diff reference. A copied evidence root cannot be assumed portable. The read-only Home diagnostic reports whether one run is ready at a given root; original evidence bytes must remain intact.

The rc.30 record is in `RC30_RC3_ALIGNMENT_2026-10-25.md` at the candidate root. A metadata-aligned plugin install is a necessary package boundary check, not evidence that the worker/reviewer chain passes under that install.

