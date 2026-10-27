# rc.31 to rc.30 isolated return check — 2026-10-27

## Purpose and limits

The current installers deliberately refuse an existing Home or Runtime path. The supported private return path is to stop one isolated Host and start a separately installed, pinned older Host/Profile/Home. This check exercises that side-by-side route; it is **not** an in-place upgrade/uninstall or migration test, and no model task was sent.

## Evidence

- The rc.31/official rc.4 kit had installed into `rc31-kit-install-home-20261027` and completed one independently verified bounded task. Its target SHA-256 remained `8A57D149BC386C3773076D94ED2C25A08395BE1FCCA331A052FE02DE2B972F20`, and its settled Manifest SHA-256 remained `D7EADF7D8F6FD21E5198D6C1FD825B15D069B0E0F5EA63AD45F7F2473AC8CD03` after this return check.
- The unchanged rc.30 PS5.1-r3 kit ZIP still hashes to `25C8CBC1209256F4BBD141FD4713827EEC7B266670BA0002F4DC26E21E53A826`. Its exact official rc.3 runner and external connection file were present. Fresh target directories `rc31-rollback-rc30-home-20261027` and `rc31-rollback-rc30-runtime-20261027` did not exist before installation.
- The rc.30 installer completed into those fresh directories, reporting Runtime source `d3af857bb87babb0f96b87adc2839f8761b45eba`, official Host `@deepseek-ai/dsh@0.2.1-rc.3`, and plugin `0.1.0-rc.30`. Credentials were not copied into its Home or kit. Its Home is separate from both the rc.31 Home and the older private RC4 daily Home.
- An isolated no-model startup using that installed rc.30 Profile returned authenticated page 200 (38,144 bytes), `session/list` 200 (zero rows in the fresh Home), anonymous evidence 401 and stderr 0. The child Host exited with the probe. The rc.31 installed Profile remained at plugin `0.1.0-rc.31`, and its recorded run still existed.

## Result and remaining work

**PASS for a fresh, side-by-side local return to the pinned rc.30 package after rc.31 use.** This establishes a separate working fallback path without touching the existing RC4 daily entry. It does not prove preservation of an in-place upgraded Home, credential/session migration, automated rollback, uninstall, or a second-device return. Those are release engineering work, not implied by this check. Preserve all three Homes and the original dirty worktrees.
