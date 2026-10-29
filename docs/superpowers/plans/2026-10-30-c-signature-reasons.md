# C signature reasons execution plan

User authorized implementation of PR36 design. Execute inline; no subagents.
Spec: ../specs/2026-10-30-c-signature-review-design.md.

1. Add fixed reason classification and multi-error synthetic tests; observe RED then GREEN. No arbitrary names in publication.
2. Connect reasons to public methods without relaxing validation; preserve C0=false and existing safety limits. Run existing suites in CI.
3. Merge tested changes and run main-only static audit. Identify actual unreadable causes from fixed enums.
4. Resolve only evidence-backed issues. Candidate atoms require module/assembly/arity evidence; never infer from reason labels. Record unresolved evidence explicitly.

Stage 1 accepted on main: audit40976428615 confirms unsupportedTypeAtom for all five groups.
Stage 2: fixed candidate metadata records must identify matching TypeDef/TypeRef scope and generic arity, bind them to module hash, and publish fixed IDs only. Candidate match does not automatically extend TYPE_ATOMS.
