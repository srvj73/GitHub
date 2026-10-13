# D4 S0_CERT_PATH_ASSOCIATION — promotion candidate — 2026-09-30

This immutable package candidate is derived from parent package SHA-256 `8DE8EC4B311B94F1A0B5412CB1C5C2D5AD9049C0D1BC66A4EA721BF74877E7DD`.

Scope:
- replace candidate/release engine with reviewed nested-path microfix;
- add one regression test to `tests/` and `tests_release/`;
- keep physical core test count at 93 (92 historical + 1 regression);
- add partial-path drift coverage within the same regression method;
- retain D4/D5/FULL authorization as false.

Reviewed engine identities:
- candidate `E1CE7EA6DCF0A88A9A8D9AAF42BAD73973AA469DFB3D3B25DB76ECA91B03BD0F`
- release `186F865AB3BD4343D3B9925EDD3C542290A64F0A332F6CA59047CFCEB9827B4C`
- patch `C8EE0EE05CAC582B9DA82EB29428646AD162CE72F971DF6F179EF2A3BDB40C8E`
- external verdict `A549D624A6F6E9E4CFF0A08FCA84033D2A77145AAFA8856C378B7C7F70A73442`

External verdict: `ASTRA_D4_CODE_DELTA_REVIEW=PASS`, `PROMOTION_PREP_ELIGIBLE=YES`,
`D4_RERUN_AUTHORIZED=NO`, `D5_AUTHORIZED=NO`, `FULL_AUTHORIZED=NO`.

Four minor findings are bound into the target promotion-prep qualification rather than treated as
package-promotion blockers. No in-place mutation of the currently promoted package is authorized.
