# Phase 5C — Presence Semantics Design

> DESIGN ONLY. No application code, schema, migration, API, frontend, model, threshold, or deployment artifact was created or modified to produce this document. The only file created is this design document. Grounded in `docs/product-discovery-audit.md`, `docs/product-validation-audit.md`, `docs/real-data-validation-report.md`, `docs/temporal-validation-report.md`, `docs/phase5a-schema-fix.md`, and `docs/phase5b-appearance-disappearance-validation.md`.

## 1. Purpose

Define the domain semantics of *presence* — what it means for an entity to be observed in one, both, or neither side of a SyncGuard comparison — before any implementation. Phase 5B proved the matcher holds singleton records out of auto-merge (0 escapes) but confirmed the product cannot tell a reviewer that an entity is absent from a snapshot. This document closes that definitional gap so a future minimal implementation has exact semantics to build against, with conservative defaults that make unsafe interpretations structurally unrepresentable.

## 2. Definitions

- **Snapshot**: an ingested, immutable view of one source at one declared time (e.g., System A = 2024 extract). Snapshots are inputs, never mutated.
- **Comparison**: one bounded A-vs-B evaluation over two declared snapshots plus a declared scope (job-scoped).
- **Presence**: the observation, within one comparison, of whether a record (or resolved entity) was observed in snapshot A, snapshot B, both, or neither — qualified by scope and ingestion completeness.
- **Identity decision**: the pairwise matcher output (MATCH / POSSIBLE_MATCH / NO_MATCH) — a statement about two records, never about snapshot membership.
- **Scope**: the declared boundaries of a comparison (sources, snapshot timestamps, geography, filters, source configuration). Scope is what makes an absence observation interpretable.
- **Completeness**: whether each snapshot side was successfully and fully ingested (COMPLETE / PARTIAL / FAILED). Absence is only interpretable under COMPLETE.

## 3. Presence States

Exactly four states. No others — every candidate addition was rejected below as either scope metadata, completeness metadata, or an identity/review concern in disguise.

| State | Meaning | What SyncGuard knows | What SyncGuard does NOT know | Safe to expose | Implies business action |
|---|---|---|---|---|---|
| `BOTH_PRESENT` | Record/entity observed in A and B within declared scope | Membership on both sides | Whether the two sides are the same real-world entity (that is the identity dimension) | Yes, with scope label | No |
| `ONLY_IN_A` | Observed in A; no corresponding record observed within B's declared scope | A-side membership + B-side non-observation under scope + COMPLETE ingestion | Whether the entity ceased to exist, moved out of scope, changed keys, or was missed upstream | Yes, with the exact neutral wording of §10 | No |
| `ONLY_IN_B` | Mirror of `ONLY_IN_A` | B-side membership + A-side non-observation under scope + COMPLETE ingestion | Whether the entity is new, moved into scope, changed keys, or is a re-registration | Yes, with neutral wording | No |
| `UNKNOWN` | Presence not determinable from available evidence | That evidence is insufficient, and why (scope mismatch, partial/failed ingestion, excluded record) | Everything about membership | Yes — exposing bounded ignorance is safer than forcing a binary | No |

Rejected additions: `DELETED` / `NEW` (business conclusions, §6); `SCOPE_EXCLUDED` (a scope-filter fact, carried in scope metadata, not a presence state); `PENDING` (a review state, §4); per-side `NOT_OBSERVED` (collapses into `UNKNOWN` with a reason code — the reason, e.g. `SOURCE_FAILED` vs `SCOPE_MISMATCH` vs `RECORD_EXCLUDED`, is carried as the observation's basis, not as distinct states).

## 4. Identity Separation

Adopted: presence, identity decision, and review state are three orthogonal dimensions. The separation is correct because Phase 5B measured them varying independently: the same `ONLY_IN_A` record can carry NO_MATCH-only (safe rejection), POSSIBLE (ambiguous), or MATCH (false positive held at HIGH) — presence did not predict identity output, and identity output must not rewrite presence.

- **PRESENCE**: `BOTH_PRESENT` / `ONLY_IN_A` / `ONLY_IN_B` / `UNKNOWN` (record- or entity-level, §7).
- **IDENTITY DECISION**: `MATCH` / `POSSIBLE_MATCH` / `NO_MATCH` (pairwise only; `NO_MATCH` never upgrades to an absence claim and never downgrades one).
- **REVIEW STATE**: `PENDING` / `REVIEWED` / `RESOLVED` / `REJECTED` / `DEFERRED` (workflow position of a review item, applicable to match pairs, conflicts, and presence observations uniformly).

Interaction rule: dimensions JOIN at the review surface (a reviewer sees presence + identity + review state together) but never collapse — no pipeline step may write an identity decision into a presence field or vice versa, and resolution of an identity pair must not auto-resolve a presence observation (different claim, different evidence).

## 5. Snapshot Scope

A comparison is uninterpretable without its scope, so scope is a mandatory, persisted part of every comparison (see §11 audit). Minimum scope metadata: source A/B identifiers, snapshot A/B timestamps, geographic coverage per side, applied filters per side, source-configuration version per side, and per-side completeness (§15).

Scope rules:

1. `ONLY_IN_A` / `ONLY_IN_B` may only be derived where both sides report COMPLETE ingestion; otherwise `UNKNOWN`.
2. Absence is evaluated ONLY within the intersection-relevant scope: a record whose attributes place it outside B's declared scope (e.g., County Y record vs B covering County X only) yields `UNKNOWN` with basis `SCOPE_MISMATCH`, never `ONLY_IN_A`-as-disappearance.
3. Any mid-comparison scope change (filter edit, geographic change, config change) invalidates derived presence observations for that comparison; they must be re-derived, never patched.
4. Scope must be reviewer-visible wherever a presence state is displayed (§18): a state without its scope label is a defect, not a display choice.

## 6. Absence Semantics

Three strictly separated claims:

- **OBSERVED ABSENCE** (`ONLY_IN_A` / `ONLY_IN_B`): "no corresponding record was observed within the declared scope of a completely ingested snapshot." This is all SyncGuard may ever claim on its own evidence.
- **PROVEN DELETION**: a business fact SyncGuard MUST NEVER assert from snapshot comparison alone. Required evidence (if a future phase ever permits the claim): an explicit deletion signal from the source system itself (tombstone/API delete event) PLUS human confirmation — comparison evidence is necessary but never sufficient.
- **UNKNOWN**: the default whenever completeness, scope, or record eligibility fails (§§14–16).

SyncGuard must never natively claim `DELETED`, `REMOVED`, `NEW CUSTOMER`, or `NEW ENTITY`. Neutral terms (`ONLY_IN_A`, `ONLY_IN_B`) are safer because Phase 5B demonstrated that 93.7% apparent singletons were scope artifact, not lifecycle events — any lifecycle vocabulary would have been wrong 19 times out of 20 on real data. Lifecycle language may only ever appear as human-entered resolution annotations, never as system output.

## 7. Record vs Entity Semantics

Presence belongs PRIMARILY to the **record within a snapshot** (raw record identity = source-native key as ingested; normalized form inherits it). Rationale: record membership is directly observable without inference, so record-level presence is cheap, exact, and pre-match derivable.

Entity-level presence is DERIVED post-match and must be represented distinctly: when matching links A-record-1 to B-record-2 under changed keys, the records may each read `ONLY` at record level while the resolved entity reads `BOTH_PRESENT`. The design therefore keeps two fields that must never share a column: `record_presence` (observed, per snapshot record) and `entity_presence` (interpreted, per resolved entity, with the linking evidence cited). A record may disappear while its entity persists under a new record ID — that case reads: record `ONLY_IN_A`, entity `BOTH_PRESENT` via link, reviewer sees both, no contradiction.

## 8. Matching Interaction

Recommended: hybrid — **derive record presence → match → interpret entity presence → joint review** (a constrained form of alternative C, with A's cheap derivation folded in).

- Alternative A (presence → matching → decision) is rejected as stated: gating matching on presence would let absence suppress identity comparison, hiding the very cross-entity false matches Phase 5B measured (2.3% forced-match rate must remain observable).
- Alternative B (matching → presence classification) is rejected: presence is set membership, not a match output; deriving it from matcher results lets blocking failures masquerade as absence.
- Adopted C-hybrid: record presence derives independently from snapshot membership (needs only normalized record sets + scope + completeness); identity matching runs unmodified and ungated; entity presence is interpreted after matching by joining record presence with identity links; all three meet only at review. This preserves the Phase 5B measurement intact (matcher behavior unchanged and still falsifiable) while adding the missing semantic layer beside it, not inside it.

## 9. Conflict Interaction

`ONLY_IN_A` / `ONLY_IN_B` are NOT conflicts. A conflict asserts two present values disagree; absence asserts non-observation — different evidence, different reviewer question, different resolution. Absence-as-conflict would also poison conflict metrics (contradiction precision) with non-contradictions.

Semantics: presence observations are a **separate reviewable observation class** — informational by default (visible in comparison summary and audit), individually reviewable on demand, never auto-escalated to conflict severity. If a future policy wants absence review queues, that is a review-routing rule over observations, not a conflict type.

## 10. Review Interaction

Reviewer-facing contract: every presence display carries state + scope + basis, in fixed neutral copy:

- `BOTH_PRESENT` — "Observed in both Snapshot A and Snapshot B within the declared scope."
- `ONLY_IN_A` — "Present in Snapshot A; no corresponding record was observed within Snapshot B's declared scope. This does not mean the entity was deleted."
- `ONLY_IN_B` — mirror wording ("…does not mean this is a new customer/entity.").
- `UNKNOWN` — "Presence could not be determined: <basis>. No conclusion should be drawn."

The trailing sentence is mandatory, not stylistic: it is the UI enforcement of invariants 1–2 (§24). Terminology decision: keep the `ONLY_IN_A` / `ONLY_IN_B` tokens as the stable labels (reviewers learn exact tokens faster than prose), with the explanatory sentence permanently attached — never the lifecycle words of §6.

## 11. Audit Interaction

Minimum auditable presence record (per observation, bound to its comparison): comparison ID, scope snapshot reference (hash/version, per §5), record reference (internal record ID only — never raw PII, §21), presence state, basis/reason code (for `UNKNOWN`: which gate failed), observed-at timestamp, and evaluator/pipeline version. Rationale for minimum: reproducibility (re-derive the same state from scope + snapshots) and accountability (who/what claimed what, when) without PII retention. Everything else (field values, match scores, reviewer notes) lives in its existing audit home and is joined by ID, not duplicated.

## 12. Future Synchronization Safety

Presence semantics must make the following UNSAFE actions structurally inexpressible without additional policy objects that do not yet exist:

- `ONLY_IN_A` must NOT be consumable as `DELETE FROM B`; `ONLY_IN_B` must NOT be consumable as `INSERT INTO A`. The observation schema carries no directive field, so no future consumer can mistake an observation for an instruction.
- Safe future behavior requires, at minimum, all three beyond presence: (a) a per-field source-priority/survivorship policy, (b) explicit human approval of the generated write plan (dry-run first, per existing product doctrine), and (c) a designed unmerge/rollback path BEFORE the first presence-driven write (industry doctrine: reversal designed upfront — discovery audit §12). Until all three exist, presence observations terminate at review and audit.

## 13. Human-in-the-Loop

Presence observations are **automatically informational** (derived for every in-scope record, no human needed) and **individually reviewable** (a reviewer may open, annotate, defer, or dismiss them). They are NOT resolvable into match outcomes and NOT actionable into writes.

Legitimate human decisions, kept minimal: `ACKNOWLEDGE` (seen, no concern), `DEFER` (revisit in a later comparison — covers temporarily-absent suspicion without asserting it), `ESCALATE` (route to full identity review, e.g. suspected key-change case). Rejected: `CONFIRM DELETED` / `CONFIRM NEW` (system must not offer buttons for claims it cannot evidence — §6), and any `SYNC`/`DELETE`/`CREATE` action (no directive authority, §12).

## 14. Edge Cases

| # | Case | Presence state | Basis / note |
|---|---|---|---|
| 1 | Record ID changed, same entity, relinked by match | Record: `ONLY` per side; Entity: `BOTH_PRESENT` | §7 split; link cited |
| 2 | Same entity, new record ID, NOT relinked (missed match) | Record: `ONLY` per side; Entity: `UNKNOWN` | Must not claim two entities; flag link-uncertainty |
| 3 | Duplicate records (same side, same entity) | Each record assessed independently; entity `BOTH_PRESENT` if any side links | Duplicates are an identity problem, not presence |
| 4 | Many A → one B | Records: each A `BOTH_PRESENT` (counterpart observed); entity cardinality noted in review, not in presence | Presence is membership, not cardinality |
| 5 | One A → many B | Mirror of 4 | Same reason |
| 6 | Source filter changes between snapshots | `UNKNOWN` (`SCOPE_MISMATCH`) for affected cohort | Scope rule §5.2 |
| 7 | Geographic scope changes | `UNKNOWN` (`SCOPE_MISMATCH`) for out-of-intersection records | Scope rule §5.2 |
| 8 | Record temporarily absent (reappears later) | `ONLY_*` in that comparison only; comparisons never revise each other's observations | Observations are comparison-scoped facts, not entity attributes |
| 9 | Malformed record (parse failure) | `UNKNOWN` (`RECORD_EXCLUDED`) | §16 |
| 10 | Record excluded due to schema failure | `UNKNOWN` (`RECORD_EXCLUDED`) | Must never read `ONLY` — §16 |
| 11 | Partial snapshot (incomplete file) | `UNKNOWN` (`PARTIAL_INGESTION`) for the affected side's non-observed records | §15 |
| 12 | Incomplete ingestion (job failed mid-way) | `UNKNOWN` (`PARTIAL_INGESTION`) | Same gate |
| 13 | Source outage (snapshot missing) | `UNKNOWN` (`SOURCE_FAILED`); no comparison should be derived at all | §15 |
| 14 | Permission failure on source | `UNKNOWN` (`SOURCE_FAILED`) | Indistinguishable from outage by design |
| 15 | Snapshot timestamp mismatch (stale vs fresh) | Derive only with mismatch prominently labeled in scope; policy may force `UNKNOWN` beyond a staleness bound (open question, §27) | Scope metadata carries both timestamps |
| 16 | Late-arriving records (post-snapshot) | Belong to the next comparison, never patched into a closed one | Comparisons immutable once derived |

When evidence is insufficient, `UNKNOWN` with a basis code — never a forced binary.

## 15. Failure vs Absence

Precise gate, evaluated per side before any `ONLY_*` derivation:

- Source successfully and completely ingested (COMPLETE) + record absent within scope → `ONLY_IN_A` / `ONLY_IN_B` (observed absence).
- Source unavailable, permission failure, or snapshot missing (FAILED) → `UNKNOWN` (`SOURCE_FAILED`); a comparison with a FAILED side should not derive presence at all.
- Source partially ingested (PARTIAL) → `UNKNOWN` (`PARTIAL_INGESTION`) for every non-observed record on that side. Partial ingestion NEVER becomes absence (invariant 4).

Completeness is itself a recorded, auditable comparison attribute — the gate must be inspectable, not implicit.

## 16. Data Quality Interaction

Malformed, unparseable, or schema-excluded records are invisible to membership tests through no fault of the entity — therefore they yield `UNKNOWN` (`RECORD_EXCLUDED`), never `ONLY_*`. The Phase 5B-era question ("Snapshot B contains a record but schema inference fails — report `ONLY_IN_A`?") is answered NO: reporting absence would convert a pipeline failure into a false business signal and corrupt the false-disappearance metric (§17). Excluded-record counts are reported alongside presence rates so reviewers see the `UNKNOWN` mass and its cause.

## 17. Metrics

Adopted (all reliably measurable from comparison outputs): `BOTH_PRESENT` / `ONLY_IN_A` / `ONLY_IN_B` / `UNKNOWN` rates with scope labels; `UNKNOWN` basis breakdown (scope vs ingestion vs exclusion); presence observation coverage (% in-scope records with a derived state); scope-excluded rate. Rejected-or-deferred: false disappearance / false appearance rates — not directly measurable without labeled lifecycle ground truth (which Phase 5B proved we lack); permitted ONLY as sampled audit metrics (human-adjudicated spot samples, reported with sample size, never as pipeline KPIs).

## 18. UX Semantics

No UI modified (design only). Eventual communication contract per state — label + explanation + scope context + evidence + warning + allowed actions:

- `BOTH_PRESENT`: neutral label; scope line; evidence = counterpart record refs + identity decision; no warning; actions = none (informational).
- `ONLY_IN_A` / `ONLY_IN_B`: neutral `ONLY_IN_*` label; mandatory scope line ("Snapshot B: <source>, <timestamp>, <geography>"); evidence = completeness attestation + search basis (which keys/scopes were checked); mandatory warning sentence (§10); actions = ACKNOWLEDGE / DEFER / ESCALATE only (§13).
- `UNKNOWN`: label "Unknown presence"; basis-specific explanation; scope line; warning ("no conclusion"); actions = DEFER / ESCALATE.
- Global rule: presence displays always co-show the identity dimension for linked records (§4) so reviewers never mistake solitude for verdict.

## 19. API Contract

Conceptual (not final field names; design only, nothing implemented):

```
presence:
  state: ONLY_IN_A              # required: BOTH_PRESENT | ONLY_IN_A | ONLY_IN_B | UNKNOWN
  basis: SCOPE_SEARCH_COMPLETE  # required: reason/evidence-basis code
  comparison_id: ...            # required: joins scope, snapshots, audit
  observed_at: ...              # required
  scope:                        # required: source ids, snapshot timestamps,
    ...                         #   geographies, filters, config versions, completeness
  explanation: ...              # required: fixed neutral copy per §10
  record_ref: ...               # required: internal id only, no PII
  entity_ref: ...               # optional: present only when identity-linked
  links: ...                    # optional: identity decisions justifying entity_presence
```

Required vs optional: state, basis, comparison_id, observed_at, scope, explanation, record_ref are required (reproducibility minimum, §11); entity linkage is optional (absent exactly when the record is unlinked — the common singleton case).

## 20. Persistence Strategy

Comparison of alternatives:

- **Derived dynamically** (recompute on read): rejected — presence claims must be auditable history; recomputation after scope/config drift rewrites the past.
- **Persisted as observation rows bound to the comparison**: RECOMMENDED — one row per in-scope record per comparison (record_ref, record_presence, entity_presence + link refs, scope version, observed_at, basis). Immutable once the comparison closes (§14 case 8, §14 case 16). Cost is linear in comparison size and matches existing job-scoped persistence patterns.
- **Persisted as events** (append-only lifecycle log): rejected as over-engineering — events imply lifecycle semantics we explicitly refuse (§6); observations suffice until a proven-deletion signal ever exists.
- Association: with the COMPARISON (and thereby its scope), referencing records/entities by ID — never stored on the record row itself (which would confuse a comparison-scoped fact with a record attribute).

## 21. Security and Privacy

Validation data is real PII; the design minimizes exposure structurally: logs carry comparison/record IDs and counts only, never names/addresses/phones; reports and review surfaces mask direct identifiers ( Phase 5B masking convention: similarities, statuses, truncated zips, phone tails); audit metadata stores internal record refs, never raw field values (joinable by authorized review UI, not duplicative); presence basis codes and scope metadata contain zero PII by construction. Reviewers see evidence patterns (which fields agreed, at what similarity) rather than raw counterpart values wherever the decision allows — consistent with evidence-sufficiency findings (30/30 and 60/60 sufficient without raw PII).

## 22. Existing-System Comparison

Claims below are scoped to what the discovery audit documented ([DOCUMENTED] = from cited primary sources there; see `docs/product-discovery-audit.md` §28):

- **Reltio / Informatica / IBM / Ataccama (MDM suites)** [DOCUMENTED]: entity lifecycle lives in merge/survivorship governance — crosswalks preserve merged URIs enabling unmerge; survivorship rules compose the golden record; steward queues approve ambiguous merges. None derives "deleted" from snapshot absence; deletion is a governed operation (SAP MDG change-request chains make this explicit). Aligns with our refusal of deletion-by-absence (§6) and our unmerge-before-write rule (§12).
- **AWS Entity Resolution** [DOCUMENTED]: outputs a Match-ID link table to S3; no stewardship, no lifecycle, no presence — closest to our identity dimension in isolation, confirming presence must be a separate layer (it is absent there entirely).
- **Splink / Zingg / dedupe** [DOCUMENTED]: libraries ending at scores/links; no persistence of decisions at all — our persisted-observation choice (§20) is the deliberate product step beyond them.
- **Census / Hightouch (reverse ETL)** [DOCUMENTED practitioner pain]: row-level sync logs, quota burnout, circular CRM↔warehouse loops. Direct precedent for our "observations carry no directive authority" rule (§12): their loops are what happens when sync systems act on under-evidenced state.
- **Monte Carlo / GX / Soda (observability)** [DOCUMENTED]: GX expectations and drift detection gate pipelines on data health — precedent for our completeness gate (§15): absence claims, like pipeline runs, require a health precondition.

## 23. Domain Model

```
Comparison (id, created_at, pipeline_version)
 ├── Scope (sources, snapshot A/B refs + timestamps, geography/filters/config per side, completeness per side)
 ├── SnapshotRecordRefs (internal ids only)
 ├── PresenceObservations (record_ref, record_presence, entity_presence, basis, observed_at)
 ├── IdentityRelationships (pair refs, MATCH/POSSIBLE/NO_MATCH, evidence refs)
 ├── Conflicts (field-level, present-values-only — absence excluded)
 └── ReviewDecisions (target: pair | conflict | presence-observation; state machine §4)
```

Design drivers: scope is a first-class node (every prior misinterpretation traced to missing scope); presence and identity are sibling subtrees joined only at review; conflicts exclude absence by construction; review decisions address a typed target so resolving one dimension never silently resolves another.

## 24. Invariants

1. `ONLY_IN_A` never means DELETED. (`UNKNOWN`-by-default lifecycle; §6.)
2. `ONLY_IN_B` never means NEW CUSTOMER / NEW ENTITY. (Same.)
3. Source failure never becomes absence. (FAILED → `UNKNOWN`, §15.)
4. Partial ingestion never becomes absence. (PARTIAL → `UNKNOWN`, §15.)
5. Scope mismatch prevents disappearance claims. (`SCOPE_MISMATCH` → `UNKNOWN`, §5.)
6. Presence does not determine identity. (Orthogonal dimensions, §4; matcher ungated, §8.)
7. Presence does not override matching. (No write path between subtrees, §8/§23.)
8. Presence alone cannot trigger destructive synchronization. (No directive authority, §12.)
9. Every presence observation must carry its comparison scope. (No scopeless states displayed or stored, §§5/11.)
10. Unknown remains unknown when evidence is insufficient. (Forced binaries prohibited, §§3/14.)
11. Excluded records are never absent. (DQ failures → `UNKNOWN`, §16.)
12. Observations are immutable once their comparison closes. (History over revision, §§14/20.)

## 25. Minimum Implementation Scope

Smallest future build closing the confirmed gap — specified only, NOT built: backend — record-presence derivation over comparison membership + completeness gate (pure set logic on already-normalized records; matcher untouched); persistence — one `presence_observations` table bound to comparison id per §20; API — read-only presence block on the comparison response per §19; UI — presence labels with mandatory scope + warning copy per §§10/18; audit — minimum observation fields per §11; tests — derivation unit tests (scope/complete/partial/failed matrix), gate tests (PARTIAL→UNKNOWN), invariant tests (no `DELETED`/`NEW` token emittable), and a scope-mismatch regression (County-Y-vs-County-X case, §5). Nothing else: no write paths, no lifecycle states, no auto-actions.

## 26. Explicit Non-Goals

Presence semantics must NOT become: deletion prediction; customer lifecycle prediction; automatic deletion or insertion; a generic CDC/change-capture platform; a source-of-truth engine; a survivorship/golden-record composer (that MDM core stays absent by product strategy — discovery audit §17); or a confidence-scored "probably deleted" ranking (probabilistic lifecycle claims launder the exact overclaim this design exists to prevent).

## 27. Open Questions

1. Staleness bound: beyond what snapshot-timestamp skew must derivation force `UNKNOWN` (§14 case 15)? Needs steward input, not a guess.
2. Should `ESCALATE` auto-create identity review items or merely link them? Workflow-capacity question.
3. Sampled false-disappearance audits: what sampling cadence keeps the metric honest without steward overload?
4. Inter-county mover tracking as a future closed-population validation (§13 of Phase 5B) — prerequisite data work before any lifecycle claim is ever revisited.

## 28. Recommendation

Adopt the four-state model (`BOTH_PRESENT` / `ONLY_IN_A` / `ONLY_IN_B` / `UNKNOWN`) with orthogonal identity and review dimensions, scope-mandatory observations, completeness-gated derivation, persisted comparison-bound audit, and human ACKNOWLEDGE/DEFER/ESCALATE-only handling — then implement ONLY the minimum scope of §25 after review approval, with lifecycle vocabulary permanently excluded from system output.

## 29. Sources

`docs/product-discovery-audit.md` §§6–12, 28 (MDM/ER/reverse-ETL/observability architectures and doctrine); `docs/product-validation-audit.md` §§6–9 (two-snapshot construction, safety metrics); `docs/real-data-validation-report.md` §§5–15 (weak labels, leakage discipline, schema defect); `docs/temporal-validation-report.md` §§5–15 + §22 addendum (temporal metrics, defect fix); `docs/phase5a-schema-fix.md` (evidence-rule precedent for conservative-by-construction design); `docs/phase5b-appearance-disappearance-validation.md` §§3–14 (scope artifact, forced-match rates, gating behavior, confirmed gap).

---

PHASE 5C DECISION

Presence model:
Four-state record/entity presence (BOTH_PRESENT / ONLY_IN_A / ONLY_IN_B / UNKNOWN) orthogonal to identity decisions and review state, with scope-mandatory, completeness-gated, comparison-bound observations

Core invariant:
Absence is scope-relative non-observation, never a lifecycle claim.

What SyncGuard can safely claim:
That no corresponding record was observed within a completely ingested snapshot's declared scope.

What SyncGuard must NOT claim:
That an entity was deleted, is new, or should be created or removed anywhere.

Minimum implementation:
Read-only record-presence derivation with completeness gate, comparison-bound observation persistence, neutral review labels, and minimum audit fields — no write paths and no lifecycle states.

Implementation status:
DESIGN ONLY

Confidence:
HIGH
