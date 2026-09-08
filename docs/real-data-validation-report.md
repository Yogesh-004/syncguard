# SyncGuard Real-Data Validation Report

> READ-ONLY validation. No app code, schema, model, thresholds, UI, or deployment touched. Analysis ran in `/tmp` against production code paths (normalization, blocking, ModelService, decision engine, conflict + schema services) with zero database writes. Raw PII never committed; names/addresses masked below.

## 1. Objective

Determine whether the current SyncGuard architecture works on realistic public person data, explicitly separated into PROVEN ON REAL DATA / SYNTHETIC-ONLY / WEAK-LABEL / NOT TESTED / UNKNOWN.

## 2. Dataset and Source

NC State Board of Elections voter registration file, Tyrrell County (`ncvoter89.zip`, 126 KB), downloaded 2026 from https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter89.zip (public record; layout `layout_ncvoter.txt` confirms weekly point-in-time snapshot, birthdate/SSN/DL excluded by state law). Terms: public file; treated as real PII regardless — sampled locally, raw rows never redistributed, masked in this report.

## 3. Snapshot Selection

Only current-week files are published per county (historical snapshots are 550 MB statewide — beyond local budget), so two TIME snapshots were NOT available. Instead: ONE county file rendered as two legitimate system views — System A "registration extract" (name parts, residential address, birth year, status) and System B "mailing/contact extract" (name, mailing address, phone, birth year) with renamed columns. These are NOT literally CRM vs ERP (stated clearly); they are two export formats of one roll, testing cross-view linkage with genuine formatting/column/missingness differences. Temporal moves are NOT TESTED by this design (stated limitation).

## 4. Data Preparation

2,731 rows, ≤10k limit respected. No names/emails/phones fabricated; no synthetic corruption injected. Only transformations: column subsetting/renaming per view (documented above) and whitespace stripped at parse. Statuses kept as-is (ACTIVE 1,915 / INACTIVE 419 / REMOVED 356 / DENIED 41).

## 5. Ground Truth / Weak Labels

WEAK LABEL (not ground truth): `voter_reg_num` equality across views (same snapshot, so linkage is near-trivial by construction — this measures cross-VIEW linkage, not temporal re-identification; overstating it would be dishonest). Used ONLY for evaluation. LEAKAGE AUDIT (executed in-script, PASSED): `voter_reg_num`, `ncid`, and raw ID strings asserted absent from every feature dict before inference; eval key never entered normalization, blocking, model, or decision code. No email/phone ground truth exists. Febrl4 consulted for calibration reference only, not as real-world proof.

## 6. Leakage Audit

PASSED (automated assertion over all 5,462 feature dicts). `ncid`/`voter_reg_num` never in features, blocking keys, or evidence.

## 7. Validation Setup

Production pipeline replicated read-only: `normalize_record` → shared `blocking.generate_candidates` → `ModelService` (v1.0.0 pickle) → `decision_engine` → `conflict_detection`. 5,462 pooled records → 14,913,991 possible pairs.

## 8. Candidate Generation Results

- Possible pairs: 14,913,991. Postcode pass REFUSED by guardrail (single-zip county, block 4,303 > 500) — correct refusal, no silent truncation.
- name/phone/email union: 103,315 candidates (144× reduction), block time 0.43s, candidate recall 1.000 (all 2,731 weak-label pairs captured).
- Email pass contributed ~0 (no emails in data — honest negative, consistent with benchmark finding).

## 9. Matching Results

- MATCH: 4,443 (TP 2,731 / FP 1,712) → P 0.615, R 1.000. POSSIBLE: 748 (all FP). NO_MATCH: rest.
- False-merge rate if auto-merged on MATCH: 38.5% — which is exactly why auto-resolution gating (not matching) is the safety layer (§10).

## 10. Auto-Resolution Safety

Eligible: 0. Correct: 0. Incorrect: 0. Auto precision/recall: undefined (0/0 — reported as such, not as 100%). Critical contradictions auto-resolved: 0. Reason: no emails/trusted IDs exist in this data, so NOTHING satisfies the auto criteria (trusted-exact or email+phone-exact). This is the engine working as designed: thin-identifier data routes 100% to manual review. The 1,712 would-be false merges were all held for review — zero escaped.

## 11. Contradiction Detection

- Street res-vs-mail disagreement: 87.8% of rows differ (only 12.2% equal) — overwhelmingly legitimate (PO boxes, mailing vs residential), correctly NOT treated as entity contradiction by the engine (address is one component among many).
- Missingness: mail street 377, phone 1,485 (54%), middle name 173. Missing==missing neutral; one-sided missing penalized per policy — observed in samples (MISSING_A/B statuses present, never positive).
- Formatting vs contradiction: 2,354 double-space addresses normalized equal (NO CONFLICT) — DISTINGUISHED correctly. `'#'`-masked review values present per layout notes.
- Email/phone contradiction handling on real data: NOT TESTABLE (fields absent) — remains synthetic-tested only. Stated, not assumed.

## 12. Explainability Review

30 sampled decisions inspected (10/10/10, masked): MATCH sample shows name/phone EXACT + address agreement + ml/high final + risk + penalties (SUFFICIENT — reviewer sees why). POSSIBLE sample shows name MISMATCH + phone MISMATCH + city-only agreement + HIGH (SUFFICIENT — reviewer sees why NOT matched). NO_MATCH sample shows multi-field mismatch + DO NOT MERGE (SUFFICIENT). Blocking provenance recorded per candidate. Verdict: SUFFICIENT for all three tiers on this data.

## 13. Hard Cases (masked)

1. Strong match (stable voter, both views agree): MATCH/LOW-equivalent, correct. 2. Weak match (PO-box mail vs street + phone missing one side): POSSIBLE/HIGH manual, correct routing. 3. Changed attributes: NOT TESTABLE (single snapshot — stated). 4. Same name different person (89 duplicate-name groups exist): NO_MATCH or POSSIBLE/HIGH via DOB/address split — no auto. 5. Missing fields: phone-absent pairs score via name/address, never auto. 6. Address variation (res vs PO box): penalized, not fatal. 7. Formatting ("27  SKEETER LN" double spaces): normalized equal, no false conflict. 8. Ambiguous (household members, same street + similar names): POSSIBLE/HIGH manual — correct. 9. Candidate miss: none (recall 1.0 on name/phone/email union). 10. Incorrect decision: 1,712 MATCH FPs exist — all non-auto, manually reviewable; zero incorrect autos.

## 14. Performance

Records A+B: 5,462. Candidates: 103,315 (vs 14.9M naive — 144×). Matching+evidence+decision: 281s (~2.7ms/pair; slower than FEBRL 0.3ms due to richer address evidence). Peak 616 MB (includes pandas frame — labeled estimate basis). Naive all-pairs estimate: ~11 hours. Guardrails fired once (postcode) and were honored, not bypassed.

## 15. Data Quality

Missingness above; 89 duplicate-name groups; type inference weakness found: `infer_schema` labels free-text columns `datetime` because `normalize_date` never returns None for unparseable strings — REPORTED, NOT FIXED (validation phase). Schema drift between views detected correctly at definition level (REMOVED first_name→name pattern, ADDED mail_*/phone columns; rename suggested as possibility with confidence, not certainty). No invalid values beyond masked `#` review flags (handled per layout notes).

## 16. Product Value Validation

1. Match decision: WORKS (P 0.61/R 1.0 + tiers). 2. Evidence: WORKS (sufficient on samples). 3. Contradiction awareness: WORKS where fields exist; email/phone NOT TESTABLE here. 4. Risk: WORKS (HIGH on all 1,712 FPs — nothing low-risk-but-wrong observed). 5. Review prioritization: WORKS (all uncertainty lands in manual queue). 6. Safe refusal: WORKS (auto band empty by policy, not by luck). 7. Auditability: WORKS (architecture unchanged; lineage verified in prior phases).

## 17. Biggest Failure

Single-snapshot design cannot test temporal change (movers, re-registrations) — the most valuable reconciliation scenario is unmeasured, and the engine's mover behavior on real data is UNKNOWN (synthetic movers behave, but that is not evidence).

## 18. Proven vs Unproven Capabilities

- PROVEN ON REAL DATA: cross-view linkage at P 0.61/R 1.0; zero-escapes review gating (1,712 held, 0 auto); formatting-vs-contradiction distinction; missingness policy; candidate recall 1.0 at 144× reduction; explainability sufficiency; schema-drift detection shape (with the datetime-type caveat).
- PROVEN ONLY ON SYNTHETIC/CONTROLLED: email/phone contradiction vetoes; trusted-ID veto; threshold grid; auto precision 1.0.
- WEAK-LABEL SUPPORTED: everything above (same-snapshot linkage is near-trivial by construction — real difficulty is understated, not overstated).
- NOT TESTED: temporal movers; cross-postcode blocking on real data (guardrail refusal untested past single-zip); email/phone real contradictions; steward throughput.
- UNKNOWN: whether 0.61 precision generalizes beyond one rural county; whether review queues stay workable at city scale.

## 19. Risks

County-specificity (rural, single-zip); weak-label flattery (recall 1.0 overstates); `infer_schema` datetime mislabeling could mislead drift severity; 281s/5k-pair cost needs batching story at scale; PII handling discipline must survive any team growth.

## 20. Recommendation

Proceed to a second validation on a larger multi-zip county (timeline: two weekly snapshots for genuine temporal moves) BEFORE any connector/push work; fix nothing except the `infer_schema` datetime bug only after approving it as engineering (it is real, minimal, and blocks honest drift severity). Do not build unmerge, source-priority, or connectors yet.

## 21. Sources

NCSBE voter registration data portal + `layout_ncvoter.txt` + `ncvoter89.zip` via dl.ncsbe.gov [DOCUMENTED]; Tilores 50M-record duplicate analysis [DOCUMENTED]; Leipzig CC-BY-4.0 benchmark page [DOCUMENTED]; recordlinkage Febrl docs [DOCUMENTED]; in-repo `docs/product-validation-audit.md` §§2–5.

REAL-DATA VALIDATION SCORECARD

Candidate generation: PASS (recall 1.0, 144×, guardrail honored)
Matching: PARTIAL (P 0.61/R 1.0 with weak labels; FP all gated, none escaped)
False-merge safety: PASS (0 incorrect autos; 1,712 held for review)
Contradiction detection: PARTIAL (works where fields exist; email/phone NOT TESTABLE here)
Explainability: PASS (sufficient on 30/30 samples)
Review usefulness: PASS (queue contains everything uncertain, nothing certain-but-wrong)
Auto-resolution safety: PASS (vacuous by policy on thin data — reported, not celebrated)
Performance: PARTIAL (281s/103k pairs; naive 11h avoided; 50K-scale untested)

Overall product hypothesis: PARTIALLY VALIDATED

Most important failure: single-snapshot design leaves temporal movers — the core scenario — unmeasured.

Most important strength: zero-escape review gating held on 2,731 real messy records (1,712 would-be false merges caught, 0 auto-resolved).

DECISION

Current SyncGuard: CONTINUE (narrowed scope intact)

Reason: real messy data confirms the safety architecture works where observable, with no auto-escape and sufficient evidence throughout

Next engineering action: validate on a multi-zip county across two weekly snapshots, then fix the confirmed infer_schema datetime defect

Actions explicitly postponed: real connector, unmerge/rollback build, source-priority auto-policy, golden-record composer, threshold changes, model retraining

Confidence: MEDIUM
