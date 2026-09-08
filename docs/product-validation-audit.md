# SyncGuard Product Validation Audit

> Validation phase. NOTHING was implemented, modified, migrated, retrained, or deployed. All dataset claims verified against stated licenses/terms below. Synthetic vs real labeled honestly throughout.

## 1. Product Hypothesis

Small data/integration teams need explainable customer-record match review with contradiction-safe decisions and auditable resolution, runnable locally without enterprise MDM — and that this workflow can be proven on realistic public data.

## 2. Real Public Dataset Candidates

### A. NC Voter Registration snapshots (RECOMMENDED base)
- Source: NCSBE public files, https://dl.ncsbe.gov/ (weekly statewide + county snapshots) [DOCUMENTED].
- License/terms: public record, freely downloadable; use constrained by state terms + general PII care — public data, but real people. Do NOT redistribute raw rows; sample locally, publish only aggregates.
- Rows/cols: ~7.5M current registrants; ~60 columns (name, address, city/state/zip, DOB/age, party, status, timestamps).
- Identity fields: name ✓, address/city/state/zip ✓, DOB ✓, voter ID (stable across snapshots — weak ground truth for same-person-across-time). Email ✗, phone ✗ (not published).
- Duplicates: real duplicates exist — independent analysis of 50M voter records across 7 states found 394,396 duplicate registrations (~0.8%; NC 20,323, 0.32%) [DOCUMENTED — Tilores Research, Jan 2024, 2023 snapshot].
- Missing/variation: real entry variance (address formats, name punctuation, moves). Formatting variation: genuine.
- Privacy: REAL PII — sample ≤10k, never commit raw rows, mask in docs/UI demos.
- Suitability: HIGH for match-review workflow (real mess, real scale-down sample, snapshot-vs-snapshot = two legitimate system views). Limitation: no email/phone to exercise those comparators; no curated ground truth (voter-ID linkage is weak supervision, must be labeled as such).

### B. Leipzig NC Voters multi-source (5M/10M, CC-BY-4.0)
- Source: https://dbs.uni-leipzig.de/research/projects/benchmark-datasets-for-entity-resolution/ [DOCUMENTED, CC-BY-4.0, cite Rahm group + ADBIS2017].
- Real voter base + GeCo synthetic corruption, 5–10 duplicate-free sources, ground-truth clusters. Sizes (5M+) exceed local budget — usable only via small sampled slices (sampling breaks cluster completeness; must document).
- Suitability: MEDIUM — best ground truth available, but scale + synthetic corruption weaken the "real" claim.

### C. Febrl1–4 via recordlinkage (current)
- Source: Febrl generator datasets; Febrl4 = two files (originals/duplicates) = natural two-system linkage [DOCUMENTED].
- License: ANU Open Source (MPL-derived) for code+data files [DOCUMENTED].
- Characterization: SYNTHETIC with Zipf-distributed duplicates — must never be called real-world. Ground truth exact.
- Suitability: HIGH for calibration/regression, LOW for product proof.

### D. Leipzig real-world match tasks (Abt-Buy, Amazon-Google, DBLP-ACM/Scholar — CC-BY-4.0)
- Real product/citation records + curated mappings; paper notes product matching "not sufficiently solved with conventional attribute-similarity approaches" [DOCUMENTED — VLDB2010 evaluation].
- Limitation: products/citations, not customers — no email/phone/person identity. Already in repo. Suitability: MEDIUM (algorithm stress, not product proof).

### E. Rejected
- Raw multi-state voter mirrors / commercial people-search dumps: terms unclear or redistribution-prohibited — excluded.
- Any "customer CSV" from SEO listicles without provenance: excluded (no license trail).

## 3. Dataset Comparison

| Dataset | Real people | Email/phone | Ground truth | ≤10k/local | License clear | Product fit |
|---|---|---|---|---|---|---|
| NC snapshots | YES | NO | weak (voter-ID over time) | YES (sample) | public record, care needed | HIGH |
| Leipzig NC multi | base YES | NO | YES clusters | only sampled | CC-BY-4.0 | MEDIUM |
| Febrl4 two-file | NO (synthetic) | NO | exact | YES | ANUOS/MPL | calibration only |
| Abt-Buy etc. | n/a (products) | NO | YES | YES | CC-BY-4.0 | algorithm only |

## 4. Recommended Dataset

**NC voter snapshots (two weekly snapshots as System A / System B) for product proof + Febrl4 two-file for ground-truth calibration.** Why: the only public source of real person-record mess at local scale with a defensible two-system construction (time-separated snapshots show moves, re-registrations, formatting drift); honest about missing email/phone and weak labels. Blunt limitation: it cannot validate the email/phone comparators on real data — those stay synthetic-tested until a real-connector pilot.

## 5. Data Requirements Matrix

| Requirement | Available? | Evidence | Workaround |
|---|---|---|---|
| Identity matching | YES | Tilores 0.8% duplicate rate, our FEBRL eval | — |
| Name variation | YES | NCSBE entry variance; Febrl generator하면 | snapshot diffs |
| Email variation | NO (real) | not published | synthetic cases only, labeled |
| Phone variation | NO (real) | not published | synthetic cases only, labeled |
| Missing values | YES | registration gaps | — |
| Address variation | YES | moves + format drift | — |
| Duplicate records | YES | 0.32% NC rate | — |
| Conflicting attributes | YES | cross-snapshot moves/changes | — |
| Different identifiers | PARTIAL | voter ID stable; cross-system IDs absent | document |
| Updated records | YES | weekly snapshots | — |
| Cross-system disagreement | CONSTRUCTED | snapshot A vs B + field mapping | label as constructed views |
| Ground truth | WEAK | voter-ID linkage; Febrl exact for calibration | never overclaim |
| Schema differences | CONSTRUCTED | column subset/rename per view | label as constructed |

## 6. Realistic Cross-System Scenarios

All constructed test scenarios (NOT observations). System A = snapshot T, System B = snapshot T+8 weeks, field-mapped per view.

- **A. Correct match:** same name+DOB+address, voter ID stable → MATCH/LOW/SAFE. Evidence: exact name+DOB, same address.
- **B. Possible match:** name typo + moved county, same DOB → POSSIBLE/MEDIUM/MANUAL. Evidence: name 0.93, address mismatch, DOB exact.
- **C. No match:** different name+DOB+address → NO_MATCH/DO NOT MERGE.
- **D. Email contradiction:** N/A on real data (no emails) — synthetic case only, engine demotes to POSSIBLE/HIGH (measured T11).
- **E. Phone contradiction:** same limitation — synthetic only (measured: veto-safe).
- **F. Missing identifier:** record without DOB on one side → MISSING penalty, MEDIUM, manual.
- **G. Same name, different person:** "John Smith" ×2, different DOB/address → NO_MATCH (DOB veto path); same DOB + same city → POSSIBLE/HIGH manual (measured T08 pattern).
- **H. Same person, changed address:** voter-ID-linked mover → MATCH if name+DOB exact (address mismatch penalized, not fatal) or POSSIBLE if noisy.
- **I. Same person, changed phone:** not observable (no phones) — synthetic only.
- **J. Conflicting source values:** address A vs B with voter-ID link → field-level conflict, recommendation by completeness/recency rule, human picks.

## 7. Current Architecture Fit

- Candidate generation (multi-pass union + exhaustive fallback): FITS — snapshot-vs-snapshot works; small samples stay exhaustive (no blocking loss).
- Normalization: FITS names/addresses/dates; phone/email paths untestable on this data (kept, synthetic-covered).
- Field similarities: FITS; address-component evidence maps to mover cases.
- Missing values: FITS (neutral + penalty policy matches registration gaps).
- Contradictions: FITS structurally (DOB veto ≈ trusted-ID veto); email/phone vetoes unobservable here — flagged, not assumed.
- Confidence/tiers/risk/auto: FITS review-queue semantics; auto band will be thin on voter data (no emails/phones to satisfy auto criteria) — honest outcome: mostly MANUAL REVIEW, which is the correct product behavior for low-identifier data.
- Human review + resolution + dry-run + verify + audit: FITS unchanged.

## 8. Failure Modes

1. Thin-identifier data → auto band near-empty (not a bug; report review rate honestly). 2. Movers with typo'd names + new address may fall to NO_MATCH (missed match — embarrassing, not destructive; acceptable per cost doctrine). 3. Common-name + same-DOB collisions → POSSIBLE/HIGH manual (correct routing, needs steward capacity). 4. Voter-ID weak labels can be wrong (re-registration edge cases) — never tune thresholds on them. 5. PII mishandling (real people) — sampling + masking + no redistribution is mandatory, not optional.

## 9. Product Success Metrics

Primary (safety first): false-merge rate ≈ 0; contradiction auto-rate = 0; auto-resolution precision = 1.0; audit completeness = 100%; verification rate = 100%. Secondary: match recall, missed-match rate, contradiction detection rate, review rate + % of true matches/non-matches in review, evidence coverage = 100%, rollback availability. F1 explicitly de-emphasized (cost asymmetry). "Accuracy" banned as a headline metric.

## 10. Minimum Viable Workflow

Input (two snapshot views + mapping) → Match (tiers) → Explain (field evidence) → Review (queue, vetoes visible) → Resolve (pick/edit, validated) → Verify (dry-run + read-back) → Audit (append-only lineage). Per stage: input (CSV ≤10k, validated, UTF-8, headers checked) / output (persisted job-linked rows) / failure (explicit FAILED + reason, never silent) / safety (no auto on contradiction, no write without confirm+verify).

## 11. Next Phase Reassessment

1. Unmerge/rollback — LATER (design the semantics now: reversal + consumer notification are load-bearing per industry, but no merged downstream exists yet to unwind).
2. Source-priority auto-policy — LATER (current conservative-global auto is safe; per-field priority needs real steward input first).
3. Real connector — NOT NEEDED before validation on NC snapshots; a read-only two-snapshot validation is the correct next engineering step, not a write-capable CRM integration.

## 12. Must-Work Demo

"Two voter-roll snapshots, eight weeks apart": System A vs B, ~2k sampled rows. Show: clean match (stable voter), mover with typo (POSSIBLE + email-less evidence), common-name collision correctly refused (POSSIBLE/HIGH, no auto), one field conflict resolved by steward with dry-run + verify + audit. Close with the refusal case — the product's value is what it refuses to merge.

## 13. What We Still Do Not Know

Whether email/phone vetoes hold on real (non-synthetic) data; steward throughput on real review queues; snapshot-linkage label quality at scale; which CRM domain pilots first.

## 14. Recommendation

Validate on NC voter snapshots (sampled, masked, undisclosed rows) + keep Febrl4 for calibration; implement NOTHING until the validation measurements above reproduce on snapshots; then decide the single next build item (expected: read-only snapshot validation, not a connector).

## 15. Sources

NCSBE voter registration data portal + public FTP index (dl.ncsbe.gov) [DOCUMENTED]; Tilores Research duplicate-voter analysis Jan 2024 [DOCUMENTED]; Leipzig DB group benchmark datasets page, CC-BY-4.0 + VLDB2010 paper note [DOCUMENTED]; recordlinkage Febrl loader docs (synthetic generator characterization) [DOCUMENTED]; Febrl ANUOS/MPL license [DOCUMENTED]; DeepMatcher/Leipzig product-task note [DOCUMENTED]; industry doctrine sources per product-discovery-audit §28.

PRODUCT VALIDATION

Core hypothesis:
VALID (narrowed: review-queue product provable on snapshots; email/phone paths stay synthetic-tested)

Recommended dataset:
NC voter registration weekly snapshots (sampled) + Febrl4 for calibration

Why:
Only public real person-record mess at local scale with a defensible two-system construction and honest weak labels

Current architecture:
KEEP (with thin-evidence risk rule already added by truth audit)

Unresolved technical risk:
Email/phone contradiction behavior is synthetic-tested only until real-connector data exists

Next engineering phase:
Read-only two-snapshot validation measuring the §9 safety metrics; no connector, no writes

Features to postpone:
Real connector, unmerge/rollback build, source-priority auto-policy, golden-record composer

Confidence:
MEDIUM
