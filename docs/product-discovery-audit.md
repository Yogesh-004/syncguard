# SyncGuard Product Discovery Audit

> Research phase. No code changed. Vendor claims tagged [DOCUMENTED] (from cited primary sources), [INFERENCE] (reasonable reading), [UNKNOWN] (could not verify). No statistics invented; quantitative claims carry sources.

## 1. Executive Summary

Cross-system entity inconsistency is a real, painful, well-documented engineering problem: the same customer exists differently in CRM, ERP, billing, support and warehouse, and reconciling those versions is where money is lost (misattributed orders, duplicate outreach, failed syncs). The industry serves it with two heavyweight patterns — enterprise MDM suites (Reltio, Informatica, IBM, Ataccama, SAP MDG) and batch entity-resolution services (AWS ER, Splink/Zingg) — plus adjacent reverse-ETL (Census/Hightouch) and observability (Monte Carlo/GX) layers. The durable gap is NOT matching accuracy: it is the **last mile of trust for small teams** — explainable match evidence, contradiction-safe decisions, human review sized to capacity, and safe write-back with verification, all runnable locally without a multi-week enterprise deployment. SyncGuard's defensible core is therefore narrower than its current surface: an **explainable match-review and safe-resolution system**, not an MDM platform. Verdict: **NARROW**.

## 2. Real-World Problem

A customer `C10482 / Ravi Kumar / ravi@gmail.com / +91 9876543210` in CRM becomes `10482 / RAVI KUMAR / 9876543210` in ERP and `C-10482 / Ravi K. / NULL phone` in accounting after years of manual entry, migrations, and acquisitions. Concretely: (1) What goes wrong — duplicates inflate reporting, conflicting attributes feed billing/support, sync jobs overwrite good values with stale ones, schema renames silently degrade pipelines. (2) Why — no shared keys across systems, human entry variance, acquisitions, batch ETL without contracts. (3) Who — integration/data engineers get paged; data stewards queue-review; ops/finance eat the consequences. (4) Consequences — misattributed revenue, duplicate communications, compliance exposure on merged identities, toil. (5) Detection today — downstream complaints, reconciliation SQL, observability alerts, steward sampling. (6) Resolution — steward queues, survivorship rules, manual merges, write-back jobs. (7) Human load — the central cost driver: every ambiguous pair needs eyes (see §13). (8) Wrong decision — a false merge corrupts every downstream consumer and is expensive to unwind (unmerge + re-point transactions + notify consumers) [DOCUMENTED — thedatagovernor playbook]. (9) Evidence required — which records, which fields agreed/conflicted, which rule/threshold fired, who approved, before/after values. (10) Audit — who/when/why for compliance and rollback.

## 3. Problem Taxonomy

| Problem | Entity Resolution | MDM | Data Quality | Integration | Observability | Reconciliation |
|---|---|---|---|---|---|---|
| Are A and B the same entity? | CORE | uses | — | — | — | uses |
| Which value wins per field (survivorship)? | — | CORE | uses | — | — | uses |
| Is the data valid/complete? | input | input | CORE | — | monitors | input |
| Moving data between systems reliably | — | publishes | — | CORE | monitors | — |
| Is the pipeline/data healthy? | — | — | tests | — | CORE | — |
| Which side is right + who approves + write-back | uses ER | stewardship | — | executes | — | CORE |

Entity Resolution ends at the link decision; MDM adds golden records, governance and stewardship; Integration moves bytes; Observability watches health; Reconciliation (SyncGuard's actual behavior) sits at the seam: **decide → explain → human-review → safely write back → verify → audit**. Brutal honesty: SyncGuard currently mixes ER + reconciliation + sync-reliability + observability-lite + stewardship-lite. The sync-back-to-CRM ambition overlaps reverse ETL (Census/Hightouch own this); golden-record/survivorship logic is absent (we flag conflicts, never compose a golden record); warehouse-scale observability is owned by Monte Carlo/GX. Too many categories for one product — hence NARROW.

## 4. Existing Systems

Summary table (details in §§6–11):

| System | Solves officially | Matching | Human review | Write-back | Deployment | Limitation that matters |
|---|---|---|---|---|---|---|
| Reltio | Multidomain MDM, golden records | Rules + FERN LLM, cleanse→match→merge real-time | Steward queues, merge preview | Publishers to downstream | SaaS | Enterprise scope/price; weeks to value [INFERENCE] |
| Informatica MDM | Trusted 360 view | Exact+fuzzy, automerge vs manual-merge thresholds | Data Steward workbench, ActiveVOS BPM | Coexistence/centralized sync, key mapping | SaaS/on-prem | Setup-heavy, weeks–months [DOCUMENTED thresholds; INFERENCE on effort] |
| IBM Match 360 | 360 customer view | Probabilistic+deterministic+rules, Watson scoring | ML-enhanced steward tasks | APIs to consuming apps | Cloud Pak for Data bundle | Requires IBM stack; batch-first [DOCUMENTED + vendor-neutral confirmation] |
| Ataccama ONE | MDM + data quality/governance | Matching plans, automated/manual/proposal modes, stable master IDs | Web App, proposals, merge preview, rematch | Native services, exports | SaaS/on-prem/hybrid | Model-driven project = implementation effort [DOCUMENTED] |
| AWS Entity Resolution | Match/link records across stores | Rule/ML/fuzzy workflows, S3→S3 | None (building block, not MDM) [DOCUMENTED FAQ] | None (you post-process) | AWS batch | No stewardship/golden record; needs Glue/S3 plumbing |
| SAP MDG | Governed creation/change in SAP landscapes | Consolidation match + mass processing | Change-request approval chains (BRF+) | Replication + key mapping | SAP stack | SAP-centric; governance effort IS the project [DOCUMENTED practitioner] |
| Splink/Zingg/dedupe | Linkage modeling | Fellegi-Sunter / active learning | None built-in | None | Self-hosted lib | No API/graph/monitoring/ownership [DOCUMENTED] |
| Monte Carlo/GX/Soda | Health/validity | — | — | — | SaaS/OSS | Detect, don't resolve; $50K+ for managed [DOCUMENTED practitioner pricing] |
| Census/Hightouch | Warehouse→SaaS activation | External-ID matching | Row-level sync logs | Rate-limited sync w/ retries | SaaS | Activation, not entity truth; circular-loop + quota pain [DOCUMENTED practitioner] |

## 5. Existing Architecture Comparison

Common backbone: SOURCES → INGEST → CLEANSE/NORMALIZE → CANDIDATE GEN (blocking) → COMPARE/SCORE → DECIDE (bands) → GOLDEN RECORD (survivorship) → GOVERN (steward) → PUBLISH/SYNC → OBSERVE. Everyone implements this spine; they differ at the ends: AWS ER stops after DECIDE (writes link table to S3); Splink stops after SCORE (you own the rest); MDM suites extend through GOVERN+PUBLISH; observability watches from outside; reverse ETL starts at a modeled table and ends at the SaaS API. SyncGuard's spine matches through DECIDE+REVIEW+SYNC-ATTEMPT but has no GOLDEN RECORD node and its SYNC node is mock-only — i.e., it is an ER-plus-review-plus-sync-attempt system, closest to "AWS ER + steward queue + Census-style push with dry-run," self-hosted.

## 6. Reltio Architecture

```
SOURCES (internal/external/third-party)
  → Reltio Data Cloud ingestion → profile-level CLEANSERS (on the fly)
  → MATCH (rules builder / FERN LLM / relevance scoring / token generators)
  → MERGE (crosswalks aggregated into winning profile; URIs preserved → unmerge)
  → SURVIVORSHIP (real-time materialized view on read: Operational Values per survivorship rules)
  → Data graph (canonical model, relationships) → APIs / Kafka / Salesforce connectors
```
[DOCUMENTED — docs.reltio.com match/merge/survivorship; relevance scoring + thresholds control decisions.]

## 7. AWS Entity Resolution Architecture

```
S3 inputs → Glue crawler/catalog → schema mapping (typed match keys)
  → matching workflow (rule waterfall w/ exact+fuzzy Cosine/Levenshtein/Soundex, or ML)
  → Match ID + rule per matched set → S3 output link table
  → (you) Athena/Redshift/EMR golden-record pipeline + Step Functions orchestration
```
[DOCUMENTED — AWS docs + reference architectures.] Explicitly NOT MDM: no stewardship, no golden record, batch analytics pattern [DOCUMENTED — third-party FAQ summarizing AWS positioning; treat vendor-confirmation as INFERENCE].

## 8. Ataccama Architecture

```
SOURCES → MDM Engine (cleanse/validate/match/merge per model-driven plan)
  → instance layer → matching (auto / manual / proposals-hybrid; stable master IDs)
  → merging (rule-based blocks) → master layer (golden records, multiple domain views)
  → steward Web App (merge preview, rematch, bulk proposal resolution) → native services/exports
```
[DOCUMENTED — Ataccama MDM docs: proposals auto-generate on ambiguity; identities stable; merges of distinct master IDs need approval.]

## 9. Informatica Architecture

```
SOURCES → staging → cleanse → MATCH (exact+fuzzy columns, rule sets, automerge vs manual-merge thresholds)
  → auto-merged / steward queue (ActiveVOS BPM) / skip
  → consolidation (Best Version of Truth, cell survivorship, cross-reference tables)
  → publish (registry / consolidation / coexistence-bidirectional / centralized patterns)
```
[DOCUMENTED — Informatica match/merge slides + integration-architecture article, incl. coexistence conflict/race handling and sync-loop avoidance.]

## 10. IBM Match 360 Architecture

```
SOURCES → Cloud Pak for Data → match (probabilistic Fellegi-style weights + deterministic + rules, per-type weights/thresholds)
  → 360 entities → attribute-composition survivorship → steward governance tasks → APIs
```
[DOCUMENTED — IBM docs: "no perfect matching system… define business tolerance for missed vs false matches; stewards inspect and feedback" — the cost-asymmetry doctrine in vendor form. Requires Cloud Pak; batch-first [DOCUMENTED + INFERENCE].]

## 11. Other Relevant Systems

- **SAP MDG:** change-request (validate → duplicate-check → approve → activate → replicate + key-map). Governance IS the product; consolidation handles legacy dupes first. SAP-centric [DOCUMENTED practitioner guide].
- **Splink/Zingg/dedupe:** Fellegi-Sunter m/u weights + blocking + EM estimation; DuckDB-local to Spark-100M. Library only: no API/graph/monitoring/stewardship [DOCUMENTED].
- **Monte Carlo / GX / Soda / Elementary:** freshness/volume/schema/distribution/lineage monitoring + pipeline-time expectations. Detect ≠ resolve [DOCUMENTED practitioner comparison; $50K+ managed pricing per practitioner article — treat pricing as INFERENCE-risky, directionally useful].
- **Census/Hightouch (reverse ETL):** warehouse model → field mapping → rate-limited sync with retries + row-level logs. Pain documented first-hand: quota burnout with no notification, change-detection state bugs, circular CRM↔warehouse loops, 3000-line bespoke sync scripts before adoption [DOCUMENTED practitioner posts].
- **Tilores (API-native ER):** resolution at ingestion, query-time context; "MDM weeks–months, API ER days" [vendor source — treat timelines as INFERENCE, directionally consistent with independent practitioner reports].

## 12. Common Industry Architecture

All serious systems share: standardize → block → compare → score → **banded decision (auto / review / reject)** → provenance-preserving merge/survivorship → governed publish → monitoring with overturn tracking. The universal constants: (a) false merges cost more than misses [DOCUMENTED ×3 independent sources], (b) review-band width is a staffing decision, (c) unmerge/rollback is designed upfront, (d) thresholds are tuned against labeled pairs and monitored (overturn rate, match-rate spikes).

## 13. Real Engineering Pain Points

Recurring, sourced: "why are these duplicated / why did the integration overwrite this / sync succeeded but data still wrong / which source is correct / how do we safely merge / audit this / detect schema change before prod breaks" — respectively answered by: steward queues + survivorship (IBM/Reltio/Ataccama), Census row-level logs + field validation errors, change-detection + loop guards, source-priority survivorship, dry-run/impact preview + approval, audit trails, GX schema expectations + Monte Carlo drift detection. The unanswered middle: a *small* team gets enterprise answers (hire stewards, buy MDM/Monte Carlo) or library answers (own the ops) — nothing in between that is local, explainable, and safe to write back with.

## 14. Evidence-Based Gaps

1. **Explainable match-review for small/self-hosted teams.** Evidence: enterprise timelines (weeks–months) vs API-ER (days) [Tilores, INFERENCE]; 3000-line bespoke sync scripts [practitioner, DOCUMENTED]; $50K+ observability pricing [practitioner, MEDIUM confidence on numbers]. Existing: Splink (no review/persistence), AWS ER (no review). Opportunity: local review queue + evidence + thresholds. Confidence: HIGH.
2. **Pre-write safety (dry-run + verification + idempotent push).** Evidence: silent quota burnout, circular loops, "sync succeeded but wrong" pain [DOCUMENTED practitioner]. Existing: Census row logs (diagnose after), nothing local that previews + verifies before claiming success. Opportunity: dry-run/verify as first-class. Confidence: MEDIUM.
3. **Contradiction-first decisions (veto on identifier conflict).** Evidence: false-merge-destructiveness doctrine [DOCUMENTED ×3]; our measured veto (trusted-ID → NO_MATCH). Existing: negative match rules exist in Informatica (tunable, enterprise-gated). Opportunity: safe defaults, not novel science. Confidence: MEDIUM.
4. **Schema-drift-gated matching.** Evidence: "dashboards dark Monday, pipeline green" [DOCUMENTED practitioner]. Existing: GX expectations + Monte Carlo drift (detect, don't gate matching). Opportunity: tie drift severity to match degradation. Confidence: LOW (adjacent, not core).

## 15. SyncGuard Current Architecture Audit

FastAPI + SQLAlchemy (sources/records/matches/conflicts/resolutions/sync-jobs/audit) + Celery/Redis + React. Pipeline: ingest (CSV/JSON/REST) → normalize → multi-pass blocking → LR(7 feats) → evidence+decision engines (tiers, veto, cap 0.99, risk/auto) → field conflicts → resolution → dry-run → mock push → verify → audit; demo/benchmark/live isolated.

## 16. What We Got Right

Evidence-first decisions with contradiction veto (industry doctrine, independently validated); banded tiers + auto only on clean agreement (matches Informatica automerge/manual-merge + review-band doctrine); dry-run before push + verification + idempotency (addresses reverse-ETL pain directly); append-only audit with before/after; measured eval with leakage-corrected honesty; local reproducible stack.

## 17. What We Got Wrong

No golden record/survivorship (flags conflicts, never composes truth — the MDM core); sync is mock-only (a demo of a capability, not the capability); benchmark/live asymmetry history (fixed, but legacy rows persist); phone-region default US (documented, still a default that can surprise); O(n²) with record cap (honest, but not a scale story); demo/benchmark/live triplication adds conceptual surface.

## 18. What Should Be Removed

Mock-sync ORCID-style claims anywhere they imply real writes (keep mock, keep labels); legacy compute endpoints duplicating `/matches` (`/match`, `/matching/run` — RETHINK: keep one); demo-metric fallbacks that could be mistaken for product metrics; any future golden-record lite attempts that duplicate steward-reviewed resolution.

## 19. What Should Be Changed

Frame tiers as review-band sizing (steward capacity), not just thresholds; add unmerge/rollback story (currently missing — industry requires it); make auto-policy per-field source-priority configurable (currently conservative-global); readiness probe already exists — extend to worker/Redis.

## 20. Candidate Product Directions

A. **Merge-review queue for messy customer data** (narrow ER + evidence + steward queue, local). B. **Pre-write safety gate for syncs** (dry-run/verify/idempotency as a service in front of any connector). C. **Schema-gated match monitor** (drift severity → match degradation alerts). D. Full MDM-lite (rejected: duplicates Reltio/Informatica badly). E. Reverse-ETL competitor (rejected: Census/Hightouch own it; our push is mock).

## 21. Recommended Product Direction

A, with B as the second act: own "decide → explain → review → safely resolve" for customer records in small-team data stacks.

## 22. What SyncGuard Should NOT Become

Generic CRM/ETL/warehouse/BI/catalog; generic MDM (golden-record governance at enterprise scope); generic fuzzy-matching library (Splink owns); reverse-ETL platform (Census/Hightouch own); warehouse observability (Monte Carlo/GX own); LLM-explained anything (deterministic evidence is the differentiator).

## 23. Data Requirements

Entities (customers w/ name/email/phone/address/ID across ≥2 systems), field-level conflicts incl. contradictions, missingness, duplicates with stable IDs for ground truth, schema versions over time (rename/type drift), timestamps, sync attempts with failures/retries, steward decisions. Ground truth: pair labels + auto-safety labels. No dataset selected until direction approved (per instructions).

## 24. Recommended Future Architecture

CORE: ingestion connectors + canonical records + normalization + shared blocking + LR/explainable scorer + evidence/decision/risk/auto + field conflicts + review queue + dry-run/idempotent push + verification + append-only audit + lineage. OPTIONAL: product-pair adapters, extra passes. REMOVE: duplicate compute endpoints, demo fallbacks in live paths. WAIT: golden-record composer, unmerge (design now, build later), real connectors, multi-tenancy, Prometheus/Grafana.

## 25. Success Metrics

Auto precision = 1.0 on labeled eval; zero contradiction autos; review-band precision/recall; steward overturn rate; time-to-detect schema drift; push verification rate; rollback availability. Never aggregate F1 alone (cost asymmetry).

## 26. Risks

Narrowness deflates demo "wow" (mitigate: hard-negative demos); mock push must never be mistaken for capability; benchmark leakage history requires permanent pair-split discipline; single-maintainer scope creep.

## 27. Open Questions

Real-connector pilot (which CRM first)? Steward-capacity-based default band widths? Unmerge semantics for already-synced destinations? Pricing/packaging irrelevant yet — park.

## 28. Sources

AWS Entity Resolution docs + blog + reference architectures (aws.amazon.com, docs.aws.amazon.com); Reltio match/merge/survivorship docs (docs.reltio.com); IBM Match 360 + InfoSphere matching/survivorship docs (ibm.com/docs); Informatica match/merge slides + integration architecture article (informatica.com); Ataccama MDM matching/model docs (docs.ataccama.com); SAP MDG practitioner guide (thedatagovernor.com) + SAP community usare; Splink docs + Tilores comparisons (tilores.io, mojang analytical docs); Pistack self-hosted ER guide; Monte Carlo/GX/Soda practitioner comparison (ai-de.net) + Monte Carlo OSS blog; Matia/Census reverse-ETL pain posts; Stacksync conflict-resolution guide; practitioner playbooks (thedatagovernor MDM matching/survivorship, PipeCode MDM, Datrick merge-review, knowledgelib ERP/MDM). Vendor timelines/pricing treated as directional [INFERENCE] unless quoted from docs.
