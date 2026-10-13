# TICKSTORE R9 FULL MULTIWORK RC4

RC4 addresses the RC3 production bottleneck observed after the first wave of months completed.

## Change

RC3 proved 22-way real build/hash concurrency, but the parent process synchronously validated and published a verified month before returning to the worker event loop. Replacement workers could be spawned yet remain blocked awaiting START, collapsing productive CPU usage during publication.

RC4 separates the pipeline:

1. Parent opens a write/delete-denying month pin and classifies canonical state.
2. START is prequeued before worker spawn; after the worker opens its overlapping pin it begins immediately.
3. Worker performs the same one-pass source SHA + parse + build path.
4. MONTH_VERIFIED is sealed by the parent and immediately queued to a dedicated publisher process.
5. A replacement month worker is started immediately.
6. The publisher remains the only canonical writer and publishes serially only after the full monthly source SHA has passed.

This overlaps canonical publication with continued worker build/hash activity without changing the frozen RC1 core or the canonical transaction protocol.

Scratch compatibility is fail-closed and ordered RC4 -> RC3 -> RC2R3; more than one complete revision pair for one day blocks.

No legacy full-history authorization, CSV deletion, format promotion or codec promotion is implied by this package.
