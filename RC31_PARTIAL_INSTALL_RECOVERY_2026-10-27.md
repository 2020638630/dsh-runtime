# rc.31 partial-install recovery exercise — 2026-10-27

## Boundary

This is a controlled local failure/recovery test for the frozen rc.31 / official rc.4 kit extracted from the final ZIP. It uses only new isolated paths under `D:\DeepSeekHarness\evidence-relocation-artifacts-20261025\rc31-partial-install-recovery-20261027`. Existing daily, rc.30, rc.31 live-trial and ZIP-install Homes were not selected as targets. No model request was sent and formal D2 ExecuteGate remains `NOT_CLAIMED`.

## Procedure and observed result

1. A test-only `pnpm-fail.cmd` returned exit code 19. The installer reached its pnpm step after extracting Runtime, creating its Python venv, installing bundled wheels and writing the Profile. It then failed with `pnpm install failed with exit code 19`. Both `home-failed` and `runtime-failed` existed; the Profile `package.json` also existed. This confirms that a failed install can leave partial target directories.
2. Retrying the same paths with real pnpm stopped before overwrite: `Refusing to overwrite existing path: ...\home-failed`.
3. A new pair, `home-recovered` and `runtime-recovered`, installed successfully from the same extracted kit using the exact official rc.4 runner. The installer reported Runtime `d3af857bb87babb0f96b87adc2839f8761b45eba`, plugin rc.31 and that no connection file/credential was copied into Home or kit.
4. A bounded, no-model Host probe against the recovered Profile returned authenticated page 200 (38,144 bytes), Session list 200 (zero sessions), anonymous evidence 401 and stderr 0. The probe child Host was stopped afterward.

**PASS for fresh-path recovery from this injected pnpm failure.** The safe operator action is to preserve the partial directories and error output, diagnose the cause, then install into newly named paths. The installer refuses a same-path retry. This does not prove safe repair in place, cleanup/uninstall, recovery from every failure point or migration of Sessions/credentials. The failed and recovered paths were retained for review.
