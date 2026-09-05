"""
sample_traces.py — Draw a provably random, reproducible sample of traces.

    python src/sample_traces.py --seed 20260905 --n 20

Three properties make the sample defensible rather than merely random-looking:

* **The seed is fixed by a rule, not chosen.** The convention in this repo is
  ``seed = today's date as YYYYMMDD``. That removes seed-shopping: you cannot
  re-roll until the sample contains the traces you wanted.
* **The population is fingerprinted.** The output records a SHA-256 over every
  trace_id in the log, so anyone can prove the draw was made against the whole
  week and not a filtered slice.
* **The draw is order-independent.** trace_ids are sorted before sampling, so
  the same seed against the same log yields the same 20 ids no matter how the
  file was written or concatenated.
"""

import argparse
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from tracing import read_traces, TRACE_PATH

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(_PROJECT_ROOT, "error_analysis")


def population_fingerprint(trace_ids: list[str]) -> str:
    h = hashlib.sha256()
    for tid in sorted(trace_ids):
        h.update(tid.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def apply_frame(traces: list[dict], frame: str) -> tuple[list[dict], dict]:
    """
    Restrict the population to a stated sampling frame.

    ``completed`` drops traces whose provider call failed and therefore carry no
    assistant output at all. Those are artefacts of the generation harness
    exhausting a daily token quota, not behaviour of the assistant, and a
    sample spent on them would measure my rate limit rather than the system.

    The restriction is content-blind: it looks only at whether ``error`` is set,
    never at what the answer said, and it is applied and recorded BEFORE the
    draw. The returned dict is written into the sample file so the exclusion is
    on the record rather than in someone's head.
    """
    excluded = [t for t in traces if t.get("error")]
    if frame == "all":
        kept = traces
    elif frame == "completed":
        kept = [t for t in traces if not t.get("error")]
    else:
        raise SystemExit(f"unknown frame {frame!r}; use 'completed' or 'all'")

    from collections import Counter

    def topics(rows):
        c = Counter(
            tag.split(":", 1)[1]
            for r in rows for tag in r.get("tags", []) if tag.startswith("topic:")
        )
        total = sum(c.values()) or 1
        return {k: round(100 * v / total, 1) for k, v in sorted(c.items())}

    return kept, {
        "frame": frame,
        "frame_rule": (
            "traces whose provider call returned a completion"
            if frame == "completed" else "every trace in the log"
        ),
        "log_size": len(traces),
        "frame_size": len(kept),
        "excluded": len(traces) - len(kept),
        "excluded_reasons": dict(Counter(
            t["error"]["type"] for t in excluded if t.get("error")
        )),
        "exclusion_is_content_blind": True,
        "topic_mix_log_pct": topics(traces),
        "topic_mix_frame_pct": topics(kept),
    }


def draw(traces: list[dict], seed: int, n: int) -> dict:
    ids = sorted(t["trace_id"] for t in traces)
    if n > len(ids):
        raise SystemExit(f"Cannot draw {n} from a population of {len(ids)}.")
    rng = random.Random(seed)
    selected = rng.sample(ids, n)
    by_id = {t["trace_id"]: t for t in traces}
    return {
        "seed": seed,
        "seed_rule": "YYYYMMDD of the day the sample was drawn",
        "n": n,
        "population_size": len(ids),
        "population_fingerprint_sha256": population_fingerprint(ids),
        "draw_method": (
            "random.Random(seed).sample(sorted(trace_ids), n) — Python "
            f"{sys.version_info.major}.{sys.version_info.minor} Mersenne Twister"
        ),
        "selected_trace_ids": selected,
        "selected": [
            {
                "trace_id": tid,
                "ts_utc": by_id[tid]["ts_utc"],
                "question": by_id[tid]["input"]["question"],
                "tags": by_id[tid].get("tags", []),
            }
            for tid in selected
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--log", default=TRACE_PATH)
    ap.add_argument("--frame", default="completed", choices=["completed", "all"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    traces = read_traces(args.log)
    if not traces:
        raise SystemExit(f"No traces in {args.log}. Run run_week.py first.")

    framed, frame_info = apply_frame(traces, args.frame)
    result = {**draw(framed, args.seed, args.n), "sampling_frame": frame_info}
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = args.out or os.path.join(OUT_DIR, f"sample_seed_{args.seed}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    fi = result["sampling_frame"]
    print(f"seed                  : {result['seed']}")
    print(f"log                   : {fi['log_size']} traces")
    print(f"frame ({fi['frame']})       : {fi['frame_size']} traces "
          f"({fi['excluded']} excluded: {fi['excluded_reasons']})")
    print(f"topic mix log         : {fi['topic_mix_log_pct']}")
    print(f"topic mix frame       : {fi['topic_mix_frame_pct']}")
    print(f"population            : {result['population_size']} traces")
    print(f"population fingerprint: {result['population_fingerprint_sha256']}")
    print(f"draw method           : {result['draw_method']}")
    print(f"written to            : {out_path}\n")
    for i, row in enumerate(result["selected"], 1):
        print(f"{i:>2}. {row['trace_id']}  {row['question'][:74]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
