# Standalone Harness adapter (work in progress)

This private package is the migration staging area for DSH Runtime's Python governance bridge and future Host/Web plugin. It is not installable product software yet. The source was copied from the user's private Harness candidate and must retain the existing wire protocol, durable policy pin, FIFO worker transport, and fail-closed semantics while removing all private Harness core hooks.

The first gate, `pnpm typecheck`, passes against public `@deepseek-ai/*@0.2.1-rc.2` packages. The original governance protocol, session pin and worker transport now compile without private Harness core types. `pnpm test:admission` verifies six process-start ordering cases: allow once, policy block, worker failure, bridge exception, pre-cancellation and cancellation during evaluation. The launch callback is a sentinel; these tests do not start Python or prove the worker's real policy/audit behavior.

The next gates are a live isolated Python worker test with durable pin and audit evidence; provider `start()` integration that calls `startGoverned`; official Host read-only and write tasks; terminal Manifest; cancellation and uninstall. Do not register a live provider until the worker deny/timeout/failure cases prove that no Runtime process starts. D2 ExecuteGate remains `NOT_CLAIMED`.
