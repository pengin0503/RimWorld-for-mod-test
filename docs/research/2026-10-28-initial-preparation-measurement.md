# Initial R2 preparation measurement — 2026-10-28

Private run: https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40700088480

Measured SHA: `e6254e07d2b53ec68841344f8bf877ef8ec145f8` (PR #25; not merged).
Ubuntu 24.04 / Linux x86_64, Python 3.12, AWS CLI 2.37.13, game 1.7.4985 rev1269, bundled WaylithClr.

## Scope and acquisition

Resolve Harmony through the private R2 index and About.xml before payload acquisition. This run selected one MOD, four files, 2,549,516 bytes. This is the measured selection, not an assumption that older six-file selections are identical.

Prepare the first runtime once: 2,572 files, 906,177,653 bytes downloaded, zero cached; omit 100 debug/other-language files using the existing selector. The read-only Cloudflare API confirmed `Game-Linux/Data/Anomaly/` was empty before the run. No unrelated Workshop content, Windows game files, or user data were acquired.

The initial runtime is needed to confirm actual game loading and the snapshot produced by this acquisition. All subsequent checks reuse it. No asset, private index, path, or raw log is published or uploaded as an artifact. Credentials exist only in the preparation step; the A step has none.

## Runtime preparation timing

| Stage | Seconds |
|---|---:|
| R2 listing, selection and acquisition | 706.566 |
| Snapshot copy | 0.434 |
| Snapshot file enumeration and SHA-256 | 0.775 |
| Snapshot copy through protection and metadata collection | 1.258 |
| Acquisition start through completed snapshot | 707.831 |

Acquisition accounts for approximately **99.82%** of the measured runtime preparation. Its measurement includes AWS CLI process startup and connection establishment as well as the actual network transfer; it does not isolate them. Snapshot metadata persistence is included in the overall 707.831 seconds, but excluded from the snapshot subtotal.

These numbers exclude private-index/MOD preparation, Worker build and A validation. This is one cold-destination sample, with no controlled network or OS cache conditions. It establishes a bottleneck, not a speedup or a distribution of initial times.

## Validation and reuse

Calling prepare again returned `snapshotReused`. A / Core / English completed with `passed / completed / qualified`, actual MOD order matched, and validation took 9.780 seconds. This is not a B/C/D, map, UI, long-play, or Windows guarantee.

Public CI on the same SHA: https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40700094902 — all eight jobs succeeded. Linux Python 3.12 ran 268 tests, eight skipped. The six new summary/scope/flow tests and 43 existing acquisition-related tests also passed locally. The local full-suite attempt stalled at `test_gui_dir_links_game_and_mods_and_writes_private_config` and was stopped by the 120-second timeout (exit 137); no claim of local full-suite success is made, and no GUI change was attempted.

## Next optimization target

Optimize acquisition before snapshot copy/hash. The current source starts one AWS CLI process for every object and shares no HTTP connection between these processes. A persistent S3 SDK client is a candidate; raising concurrency alone is another possibility but can increase CPU/process pressure. A small, byte-capped, identical-object comparison can distinguish transport overhead without repeating the approximately 906 MB runtime download. No transport speedup is established by this baseline.
