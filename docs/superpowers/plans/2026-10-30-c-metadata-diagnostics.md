# C metadata diagnostics Implementation Plan

> Execute inline with superpowers:executing-plans. No subagents (user instruction).

**Goal:** Identify remaining unsupported signature positions and nested metadata identities without publishing unknown names; then re-audit and establish case-specific C0 evidence.
**Architecture:** Preserve the fixed-input/hash boundary. Add bounded positional diagnostics computed by the publisher and canonical nested names in the scanner. A fixed candidate catalog may test hypotheses; matching never auto-adopts a public atom or qualifies C.
**Tech Stack:** Python 3.12, .NET 10, Linux, GitHub Actions.
**Spec:** ../../research/2026-10-30-c-expanded-atoms-audit.md (approved continuation).

## Constraints and rulings

Fixed eight inputs, 64 MiB/file, 128 MiB total, existing parser/process budgets, R2 read-only, no raw names/logs/assets published. Windows features frozen. C0 remains false until same-context independent observations are established. User authorizes continuous implementation/merge; no approval pauses or subagents.

## Review focus

Unknown strings never reach positional diagnostics; cyclic/deep metadata rejects; nested types cannot alias top-level types; candidate use requires correct assembly/arity/hash; unreadable unused overload does not block a distinct proven case.

### Task 1: bounded signature and metadata diagnostics

- [ ] RED: tests/test_signature_diagnostics.py verifies return/parameter/generic paths, no private values, depth/size bounds and identity binding.
- [ ] Implement tools/signature_diagnostics.py and integrate publisher diagnostics without weakening signature validation.
- [ ] RED: synthetic C# tests verify nested definition/reference canonical names and wrong-assembly candidate rejection.
- [ ] Implement MetadataIdentity helper and use it in SignatureProvider/CandidateCatalog. Named nodes carry only validated metadata kind/scope/depth, not arbitrary extra fields.
- [ ] Test fixed hypotheses ienumerator (CoreLib), filter-ui-state (Assembly-CSharp nested ThingFilterUI+UIState). They are candidate IDs, not adopted atoms.
- [ ] GREEN: related Python tests and synthetic C# scanner via local SDK or CI. Review diff, merge green PR.

### Task 2: actual inputs and follow-on evidence

- [ ] Run main private audit, inspect fixed public diagnostics and candidate matches, record exact input hashes/bytes and case-specific blockers.
- [ ] Adopt only confirmed candidate names under existing user authorization, with RED→GREEN unknown-name rejection tests, CI, merge and real re-audit.
- [ ] Use verified API signatures to design bounded dynamic reachability checks. Never implement independent qualification by copying product predicates. Continue dynamic checks only on established input/context/stop contracts.
- [ ] If reachability/context/independent observation cannot be established, record concrete case-specific stop reasons; do not register qualification.
