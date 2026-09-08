# Phase 5B — Appearance / Disappearance Validation

> VALIDATION ONLY. No app code, model, thresholds, schema, API, UI, or deployment touched. Analysis ran in `/tmp` (`phase5b_run.py`, `phase5b_tail.py`) against production code paths (schema inference, normalization, blocking, ModelService, decision engine) with zero database writes. Pipeline stopped before resolution/dry-run/push/sync. Raw voter PII never committed; persons masked below.

## 1. Objective

Determine how the CURRENT SyncGuard pipeline behaves when two real snapshots contain entities present in both, entities present only in the earlier snapshot, and entities present only in the later snapshot — and whether the product model distinguishes MATCH vs NO MATCH vs MISSING FROM SNAPSHOT vs NEW IN SNAPSHOT vs UNKNOWN. Absence is NOT assumed to mean deletion. No appearance/disappearance handling was implemented.

## 2. Dataset

- Source: NCSBE public voter files via `https://s3.amazonaws.com/dl.ncsbe.gov/data/Snapshots/` (public record; layout `layout_ncvoter.txt`; birthdate/SSN/DL excluded by state law). Same source and range-stream methodology as the prior temporal validation.
- Snapshots: `VR_Snapshot_20240101.zip` and `VR_Snapshot_20250101.zip` (Jan-1 yearly snapshots, 12 months apart). Source confirmed live this phase (HTTP 206 on range requests); cached population re-verified against live row 0 of both files (reg_num + name exact match) before analysis.
- Scope: leading 12,000 rows of each file = Alamance county, 90 columns each (all 12,000 rows per file report `county_desc = ALAMANCE`).
- Fields used (identical mapping to prior temporal run): first/midl/last name, parsed address components (house_num/dir/name/type/unit), city, zip, area_cd+phone_num, voter_status_desc. Excluded: voter_reg_num, ncid, county fields (eval-only), race/party/sex/districts.
- Sample: all 760 overlapping voter_reg_num + 1,000 A-only + 1,000 B-only per side → System A 1,760 / System B 1,760 (≤10k budget; same total size as prior temporal run; singleton cohorts enlarged 400 → 1,000 for false-match power; seeds 7/8/9/42–47 documented in script).
- Two-system framing: System A = 2024 extract, System B = 2025 extract (NOT literally CRM/ERP — stated).

## 3. Snapshot Scope

Both inputs are fixed 12,000-row file prefixes, i.e. a SCOPE sample, not a closed population. Consequence (measured, §5): only 760 of 12,000 rows (6.3%) overlap by voter_reg_num. The two yearly files order rows differently, so the prefixes are largely disjoint entity sets. A-only/B-only status here therefore means "present in this snapshot's fetched scope but not the other's" — it is dominated by scope artifact, not voter churn. All singleton findings below are valid as pipeline-behavior measurements (records with no true counterpart in the opposite sample) but carry NO business semantics (see §13).

## 4. Ground Truth

WEAK LABEL: `voter_reg_num` equality (760 overlap pairs), eval-only. Leakage audit (executed in-script, PASSED): `voter_reg_num`, `ncid`, and each row's own key string asserted absent from every feature dict before inference; positional IDs (`A-<i>`, `B-<i>`, mirroring production integer IDs) used throughout blocking/matching/features/evidence/decision. Thresholds frozen (no tuning on labels).

## 5. Population Changes

Full fetched population (12,000 + 12,000):

| Cohort | Count | Share of own snapshot |
|---|---|---|
| A∩B (present in both scopes) | 760 | 6.3% |
| ONLY_IN_A (A scope only) | 11,240 | 93.7% |
| ONLY_IN_B (B scope only) | 11,240 | 93.7% |

Analysis sample (1,760 + 1,760): overlap 760; singletons 1,000 + 1,000 per side.

Overlap case taxonomy (natural only, same rules as prior run): A_unchanged 572; A_unchanged+D_missing 155; B_changed_address 10 (+7 with missing); C_changed_other 4 (+6 with missing); E_format 4 (+2 with missing). Counts identical to the prior temporal run (same overlap set).

Neutral terminology: ONLY_IN_A / ONLY_IN_B (scope-relative), NEVER "deleted"/"new". Reason: §3 artifact dominates — calling them deleted/new customers would assert a business event the data cannot support. Within the analysis sample the statement "no true counterpart exists in the opposite sample" is TRUE by construction (key-disjoint), which is exactly the precondition needed to test forced-match behavior.

## 6. Overlap Matching

Candidate recall 1.000 (760/760, 0 lost to blocking). MATCH: 910 (TP 753 / FP 157) → P 0.8275, R 0.9947, F1 0.9034. POSSIBLE: 32 (TP 3). NO_MATCH: rest (4 truth pairs decided NO_MATCH, 0 blocked out).

Comparison with prior temporal validation (same overlap set, frozen thresholds):

| Metric | Prior | Phase 5B | Note |
|---|---|---|---|
| Candidate recall | 1.000 | 1.000 | identical |
| MATCH TP | 753 | 753 | identical (pairwise decisions independent of sample) |
| MATCH FP | 130 | 157 | +27 from larger singleton cohorts (more collision surface) |
| MATCH precision | 0.8528 | 0.8275 | FP-driven, expected |
| MATCH recall | 0.9947 | 0.9947 | identical |
| Incorrect auto-merges | 0 | 0 | identical |

By-case decisions identical to prior §9 (572/572 unchanged MATCH; 155/155 +D_missing MATCH; 17/17 movers MATCH; same 4 missed truth). No threshold change; no tuning.

## 7. A-Only Analysis

Per-record best outcome across all candidates for each of the 1,000 A-only records (any MATCH here is false by construction — no counterpart exists in System B sample):

- NO_MATCH only (correctly rejected everywhere): 974 (97.4%)
- POSSIBLE at best (ambiguous, manual review): 3
- ≥1 MATCH (incorrectly forced into a match): 22 records (2.2%)
- No candidate generated at all: 1
- FALSE MATCH pairs touching A-only: 15; of those, auto-resolvable: 0
- Risk on A-only MATCH pairs: HIGH 14, MEDIUM 1 (all 15 routed MANUAL REVIEW)

Signature of false matches (masked evidence): shared exact phone + partial postcode/city agreement overriding name MISMATCH (name sims 0.33–0.60 in 8/10 sampled; two common-name collisions at 0.84/0.93). Same household/shared-phone trap family as prior hard negatives. Confs 0.71–0.94 — confidence does NOT flag them; risk tier does (HIGH throughout).

## 8. B-Only Analysis

Symmetric result for 1,000 B-only records:

- NO_MATCH only: 972 (97.2%)
- POSSIBLE at best: 3
- ≥1 MATCH (incorrectly forced): 25 records (2.5%)
- FALSE MATCH pairs touching B-only: 23; auto-resolvable: 0
- Risk on B-only MATCH pairs: HIGH 22, MEDIUM 1 (all MANUAL REVIEW)

One B-only false match shows name STRONG_MATCH (0.94) + phone MISSING_A + street MISMATCH → MATCH 0.70 HIGH manual: common-name collision correctly denied auto. No asymmetry between A-only and B-only handling was observed.

## 9. False-Merge Analysis

- False matches involving A-only records: 15 pairs (22 records touched). Involving B-only: 23 pairs (25 records touched). All are MATCH-tier false positives held for MANUAL REVIEW at HIGH risk — none escaped the review gate.
- Incorrect automatic merges: 0 (auto band empty: 0 eligible, same policy outcome as both prior phases — no emails/trusted IDs in this data).
- Critical contradictions automatically resolved: 0.
- Had auto-resolution fired on MATCH tier, 38 pairs (≈157 overlap-FP + singleton-FP share) would have been false merges — which is why the gating layer, not the matcher, is the safety boundary. It held.

## 10. Hard Cases

60 masked cases inspected (exceeds the 10/category minimum): 10 A-only FALSE_MATCH, 10 A-only safe NO_MATCH, 10 B-only FALSE_MATCH, 10 B-only safe NO_MATCH, 10 overlap-unchanged MATCH, 10 overlap-changed MATCH/POSSIBLE.

- A-only FALSE_MATCH: candidate via postcode/name/phone blocks → MATCH on shared phone + partial address despite name MISMATCH → HIGH → MANUAL REVIEW, auto False. Verdict: SAFE (held) but WRONG tier (should be POSSIBLE/NO_MATCH — matcher overweights shared phones; noted, not fixed per phase rules).
- A-only / B-only safe NO_MATCH: candidates generated, all decided NO_MATCH across multi-field mismatch. Verdict: SAFE and CORRECT.
- Overlap unchanged MATCH: full-field EXACT, conf 0.99, MEDIUM (email BOTH_MISSING keeps risk off LOW), MANUAL REVIEW, auto False. Verdict: SAFE and CORRECT.
- Overlap changed MATCH/POSSIBLE: movers matched with address change exposed as field evidence; thin-evidence pairs refused to NO_MATCH. Verdict: SAFE and CORRECT.
- Explainability: every sampled decision defensible from displayed field evidence (status + similarity per field, risk, recommendation). SUFFICIENT.

## 11. Product Semantic Gap

Question: can the current system explicitly tell a reviewer "absent from Snapshot B" vs "matched to another record" vs "no reliable relationship found"?

Answer: NO. All pipeline outputs (tiers, evidence, conflicts, review queue) are pairwise: they describe relationships between two presented records. There is no per-record snapshot-presence signal, no "unmatched record" report, and NO_MATCH between a pair is indistinguishable from "counterpart absent" at the product surface. An ONLY_IN_A record that correctly matches nothing looks identical to a record whose counterpart was missed by blocking — the reviewer cannot tell "correctly alone" from "lost."

CURRENT PRODUCT GAP:
The pipeline has no absence semantics: it cannot assert or display that an entity is missing from a snapshot, so appearance/disappearance is unrepresentable in review, resolution, and audit outputs.

WHY IT MATTERS:
Without absence semantics, temporal reconciliation silently degrades into pairwise matching: genuine disappearances/appearances are invisible, reviewer effort cannot be directed to them, and any future write-back would have no safe basis for add/remove decisions. This is the single largest product-model gap found to date — larger than the schema-inference defect (Phase 5A), which affected reporting only.

No implementation was performed (phase rules); the gap is reported for a future engineering phase.

## 12. Performance

- A rows 1,760 / B rows 1,760 (pooled 3,520). Cross-system pairs (A×B): 3,097,600. Full pooled pairs: 6,193,440.
- Candidate pairs: 1,157,687 (reduction 5.3×; postcode blocks 1,148,689 over 13 blocks, largest 1,018; name 12,107; phone 704; email 0).
- Guardrail: default 500-block cap FIRED correctly (blocks 625/1,018/722 — denser multi-zip sample than prior run); measurement reran with explicit max_block_size=1500 + max_candidates=3M (experiment parameters, app untouched). No silent truncation.
- Blocking 6.7s. Matching+evidence+decision 1,270.6s (~1.1ms/pair). Total ~1,277s. Peak 6.1GB (harness-held verdicts over 1.16M pairs — labeled basis, not a product measurement).
- vs prior (501k pairs, 158–240s, 2.68GB): cost scaled ~linearly with candidate volume; no anomaly.

## 13. Limitations

- Absence CANNOT mean deletion here: 93.7% singleton rates are a prefix-scope artifact (§3), not churn. No business-semantics claim is supported.
- Records CAN move between counties: county exits/entries are invisible inside single-county scope and would masquerade as appearance/disappearance.
- Snapshot scope fully determines interpretation: ONLY_IN_X is scope-relative; a wider fetch would reclassify most singletons as overlap.
- Stable IDs are assumed persistent voter_reg_num across 12 months; re-registration edge cases could mislabel (never used for tuning).
- Registration/status changes affect appearance: the prefix is status-mixed (A scope: REMOVED 56%, ACTIVE 37%, INACTIVE 6%) — status transitions, not just person changes, move records across cohorts.
- Email/phone/trusted-ID paths remain synthetic-only; auto band empty by policy on this data.
- The data are SUFFICIENT for the pipeline-behavior question (forced-match rate, gating, evidence) but INSUFFICIENT for true business appearance/disappearance semantics — that requires a closed-population design (e.g., full-county fetch with inter-county move tracking).

## 14. Proven vs Unproven

- PROVEN ON REAL DATA (this phase): overlap matching at P 0.83/R 0.99 with zero-escapes gating incl. 2,000 singleton records; singleton forced-match rate ~2.3% (47/2,000 records) with 0 auto-resolved; HIGH-risk flagging on 36/38 singleton MATCH pairs; candidate recall 1.0 at 5.3×; explainability sufficiency on 60/60 hard cases; guardrail refusal honored under denser blocks.
- STILL SYNTHETIC-ONLY: email/phone/trusted-ID vetoes; auto precision.
- NOT TESTED: true business disappearance/appearance (closed population needed); 50K scale; steward throughput; urban rolls.
- UNKNOWN: singleton forced-match rate outside one county-prefix sample; whether HIGH-risk queue volume stays workable with larger singleton cohorts.

## 15. Recommendation

Accept the validation findings and approve a narrow semantic-extension design phase (NOT implementation): per-record snapshot-presence reporting (matched / unmatched-with-candidates / unmatched-no-candidate / absent-from-snapshot-scope) surfaced in review and audit, with scope-relativity explicitly labeled so absence is never presented as deletion. Do not build connectors, rollback, source-priority, retraining, threshold changes, or deployment.

## 16. Sources

NCSBE `dl.ncsbe.gov` snapshot index + `layout_ncvoter.txt` + `VR_Snapshot_20240101/20250101.zip` via S3 range requests (live-verified this phase, cache re-validated row-0 both files) [DOCUMENTED]; in-repo `docs/temporal-validation-report.md` §§2–9 (baseline metrics), `docs/real-data-validation-report.md` §§2–5 (methodology), `docs/phase5a-schema-fix.md` (accepted fix, schema behavior).

---

PHASE 5B SCORECARD

A∩B:
760

A-only:
11240 (population) / 1000 (sample)

B-only:
11240 (population) / 1000 (sample)

Temporal MATCH precision:
0.8275

Temporal MATCH recall:
0.9947

False matches involving A-only:
15 pairs (22 records)

False matches involving B-only:
23 pairs (25 records)

Incorrect automatic merges:
0

A-only semantic handling:
PARTIAL (pairwise-safe: 97.4% rejected, 0 auto; semantically blind: no absence signal)

B-only semantic handling:
PARTIAL (pairwise-safe: 97.2% rejected, 0 auto; semantically blind: no absence signal)

Product semantic gap:
YES

---

DECISION

Appearance/disappearance validation:
VALIDATED

Current product:
NEEDS SEMANTIC EXTENSION

Biggest finding:
The matcher holds singleton records out of auto-merge with zero escapes, but the product cannot tell a reviewer that an entity is absent from a snapshot.

Next engineering action:
Design (not build) scope-relative per-record presence reporting for the review and audit surfaces.

Explicitly postponed:
appearance/disappearance states, matching changes, threshold changes, connectors, rollback, source-priority policy, model retraining, deployment

Confidence:
MEDIUM
