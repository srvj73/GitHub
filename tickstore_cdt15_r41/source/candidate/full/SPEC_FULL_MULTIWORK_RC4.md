# SPEC FULL MULTIWORK RC4

## Objective
Eliminate RC3 parent-loop publication starvation while preserving fail-closed canonical publication.

## Invariants
- Frozen RC1 core remains byte-identical.
- Exactly one dedicated publisher process mutates the canonical destination.
- Canonical publication is forbidden until worker MONTH_VERIFIED proves the full monthly SHA-256.
- Parent source pin opens before worker spawn and remains open through publication/final reconciliation.
- Publisher opens an additional overlapping source pin for the month it is publishing.
- Worker START is prequeued only after the parent pin and canonical classification are established.
- Worker build/hash and publisher activity overlap.
- Source is one physical forward pass per month.
- No day ACK barrier.
- Resume accepts exactly one valid day pair from RC4, RC3 or RC2R3; conflicts block.
- SAFE_STOP checks worker row-group/scan-chunk boundaries and publisher day boundaries.

## Required Windows gates before production
- RC1 Windows regression 39/39 PASS.
- RC4 unit tests 19/19 PASS.
- Static RC4 audit PASS.
- 22-worker source-pin/build/resume smoke PASS.
- New async publisher overlap smoke PASS.
- Real-source bounded productivity canary before full owner release.
