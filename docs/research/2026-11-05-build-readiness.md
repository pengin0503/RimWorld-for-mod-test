# Candidate RimWorld 1.7.4995 Linux readiness (2026-11-05)

The test-only host's current qualified adapter is strictly pinned to
`1.7.4985 rev1269`. This task does **not** replace it or infer compatibility
from a version number.

## Read-only eligibility probe

`tools/build_readiness.py` checks the known fixed R2 identity-object keys
under the existing private `Game-Linux/` prefix and fetches **only**
`Game-Linux/Version.txt` after confirming it is a small non-empty object.
It does not download the 906 MB runtime, change the bucket, read other MODs,
register a new Adapter, change cache eligibility or invoke the Worker.

Public-safe responses contain only:

- `targetBuild=1.7.4995`
- `state`: `readyForAudit`, `differentBuild`, `missingIdentityFiles`,
  `invalidVersion`, or `blocked`
- counts for the fixed identity key set
- `qualified=false` in **all** cases.

The `readyForAudit` state means that the candidate Version.txt matches and
the small required identity-file set was listed. It **does not** establish that
the assets are valid, compatible, or qualified.

A main-only manual GitHub workflow `linux-private-build-readiness.yml`
performs this step after its PR has been merged. R2 read-only secrets are
exposed only during that step; no game or private files enter the repository
or Actions artifacts. Public CI uses only synthetic FakeR2 tests.

## Acceptance still required to support 1.7.4995

1. The owner updates the authorized private Linux game snapshot; read-only
   credentials cannot create or replace an R2 snapshot.
2. The fixed readiness gate confirms Version.txt and identity-key availability.
3. On an isolated private snapshot, audit each Assembly hash, runtime native
   version, Worker API binding, and differences against the current adapter.
4. Re-run A/B/map against an independent official headless reference with
   fixed inputs and inspect exact diagnostic differences. Treat each scope and
   configuration separately; do not borrow old qualification results.
5. Only after evidence exists, create a separate adapter with the *observed*
   hashes and case-limited qualifications. Ensure unknown-build tests still
   block as designed. Re-run full public CI and private acceptance.
6. D and C remain experimental unless independently qualified under the
   candidate build. Windows remains frozen.

No candidate hash, new build readiness result, real-game execution,
qualification, or version change is claimed by this PR.
