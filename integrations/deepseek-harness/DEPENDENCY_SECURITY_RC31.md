# rc.31 dependency security disposition

The plugin workspace pins zod 4.6.6 and overrides zod throughout its lockfile;
the rc.4 HTTP proxy's exact undici 8.11.2 dependency is overridden to 8.12.2.
Both updates remain within the original major version. The override is required
because rc.4 packages pin their dependencies, and preserves a single zod version
for values exchanged across package boundaries. The proxy override is limited to
the rc.4 package. Node 24 satisfies undici's >=22.19.0 requirement. The plugin
CI and a real loopback proxy/fetch test exercise this combination; they do not
prove compatibility with every Host configuration.

These are **pnpm workspace-root overrides**, not transitive package metadata.
When this plugin is installed into another Host, that Host's own lockfile and
root policy determine the resolved versions. Packaging the plugin does not force
the Host to honor these overrides. A new isolated Host installation must apply
and verify an appropriate root resolution, audit its actual production graph,
and pass Host compatibility and bounded acceptance before any delivery claim.
Node's bundled undici is separate from the npm package; updating this lockfile
does not update Node itself. The historical frozen kit remains unchanged.

The prior production audit reported these nine advisories. Package presence
alone does not establish exploitability in the active Host:

* [zod GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5): oversized invalid arrays can exhaust memory during validation.
* [undici GHSA-4qv8-2p9j-2685](https://github.com/advisories/GHSA-4qv8-2p9j-2685): an untrusted EventSource peer can exhaust parser memory.
* [undici GHSA-f72v-6w45-q472](https://github.com/advisories/GHSA-f72v-6w45-q472): fetch integrity metadata with mixed-case algorithm tokens can be bypassed.
* [undici GHSA-xjj6-f33q-929c](https://github.com/advisories/GHSA-xjj6-f33q-929c): a malicious fetch response with excessive content encodings and an early close can crash the process.
* [undici GHSA-4w7w-5xrc-9h26](https://github.com/advisories/GHSA-4w7w-5xrc-9h26): cross-origin redirects can poison a shared cache with the specified redirect/cache interceptor composition.
* [undici GHSA-2m5v-pch6-74hx](https://github.com/advisories/GHSA-2m5v-pch6-74hx): Agent drops a custom TLS identity callback, weakening custom verification.
* [undici GHSA-qrxm-fqhp-jwvm](https://github.com/advisories/GHSA-qrxm-fqhp-jwvm): a malicious TLS 1.2 peer can crash the client through certificate-changing renegotiation.
* [undici GHSA-9fm3-97px-rjf6](https://github.com/advisories/GHSA-9fm3-97px-rjf6): a malicious WebSocket peer can exhaust memory with PINGs under backpressure.
* [undici GHSA-55wc-3pg8-jfw6](https://github.com/advisories/GHSA-55wc-3pg8-jfw6): decompress composed with a throwing response handler can crash the process.

The proxy package installs an undici Agent as the global dispatcher; its own
documentation identifies cross-version coupling with Node's built-in fetch.
The loopback test exercises proxy routing, bypass, and disposal, but does not
establish reachability of each advisory or validate an externally installed Host.
An audit result is a graph snapshot, not a complete security acceptance.
