# Independent code-run OFF policy

The existing public watchdog now checks both execution gates. Every shutdown
attempt writes `false` to both gates, even if the first reply fails, then reads
both back independently. An accepted PATCH alone is not shutdown evidence.
`off_selftest` exercises these actual writes without enabling execution.

The original documentation-pilot program, its consumed marker and historical
transactions are unchanged. When the code gate is false, the original
documentation-pilot checks still decide whether the paid gate can remain on.

For a future code launch, `CW_CODEX_CODE_LEASE` must contain the closed schema
in `orchestrator_code_lease.py`: one package, immutable source/public revisions,
one opaque Work digest, exact source/public controller run IDs, fixed package
ceilings and a maximum 20-minute interval. No task text, application data or
credentials belong in this record. The public parent must be an active,
first-attempt owner run of `code-gateway.yml` on main with the matching SHA and
Work digest in its title. A variable renewal cannot extend that run's original
window. Malformed, missing, expired, terminal or unreadable evidence triggers OFF.

`code_watch` watches exactly its supplied public parent every 15 seconds with
an independent monotonic deadline. The scheduled five-minute fallback uses the
same policy. GitHub scheduling and API availability are not hard real-time
guarantees; failed readback reports unverified OFF rather than success.

This change installs the OFF side only. There is currently **no code lease
issuer or code-gateway workflow**, no enabling operation, provider credential,
model call or native Work dispatch in this module. A later trusted launcher
must separately verify its actual native Claim, lease, package budget and OFF
receipt before every provider request. A lease record alone grants no inference
or trading authority. The first native code Result remains unverified.

The offline CI runs 26 lease/OFF behavior tests plus 7 tests executing the actual
inline watchdog with inert API/clock fixtures. It also verifies the historical
paid-pilot program's exact unchanged digest. These tests do not call GitHub or
any model/provider.
