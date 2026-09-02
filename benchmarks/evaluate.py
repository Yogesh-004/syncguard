"""Evaluation helpers."""
from typing import Set, Tuple, Dict, List

def pair_key(a: str, b: str) -> Tuple[str,str]:
    return (a,b) if a < b else (b,a)

def compute_metrics(pred: Set[Tuple[str,str]], truth: Set[Tuple[str,str]]) -> Dict:
    tp = len(pred & truth)
    fp = len(pred - truth)
    fn = len(truth - pred)
    tn = None
    precision = tp / (tp + fp) if (tp+fp)>0 else 0.0
    recall = tp / (tp + fn) if (tp+fn)>0 else 0.0
    f1 = 2*precision*recall/(precision+recall) if (precision+recall)>0 else 0.0
    return {"precision": round(precision,4), "recall": round(recall,4), "f1": round(f1,4), "tp": tp, "fp": fp, "fn": fn, "pred_count": len(pred), "truth_count": len(truth)}

def confusion_matrix(pred: Set[Tuple[str,str]], truth: Set[Tuple[str,str]], total_pairs: int = None) -> Dict:
    m = compute_metrics(pred, truth)
    return {"TP": m["tp"], "FP": m["fp"], "FN": m["fn"], "TN": (total_pairs - m["tp"] - m["fp"] - m["fn"]) if total_pairs else None, **m}
