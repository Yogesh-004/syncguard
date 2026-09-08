# Phase 4.5 Audit — Why 100% Happens

## Root cause
1. `MatchingEngine.compute_score` returns raw `predict_proba` as `confidence` (up to 0.9999999) with no contradiction check.
2. Decision is a single cut (`>=0.6 → MATCH`) on that number — a conflicting email/phone never blocks MATCH.
3. Frontend renders `(confidence*100).toFixed(1)` verbatim → "99.9%"/"100.0%"; users read it as verified identity.
4. No separate concepts: model_score == confidence == decision basis; no risk/auto_resolvable/verification-state split; "SYNC_VERIFIED" (destination read-back) is the only verified label and is correctly scoped, but nothing stops a 99% MATCH with a conflicting email from auto-resolve recommendation paths.
5. Evidence ticks exist but are display-only — the decision never consumes them.

## Fix (no rebuild)
New `evidence_engine.py` (field statuses + similarities) + `decision_engine.py` (ML score + evidence + penalties → final_confidence capped 0.99, decision, risk, auto_resolvable, recommendation). Pipeline + APIs persist the full decision record (migration 003 for queryable columns). Frontend displays decision/confidence/risk/auto_resolvable from backend with capped formatting. Benchmark re-evaluation picks thresholds from validation grid.
