"""
render_traces.py — Print traces in a form a human can actually read.

    python src/render_traces.py --sample error_analysis/sample_seed_20260905.json
    python src/render_traces.py --trace-id tr_xxxxxxxxxxxx --with-chunks

This is the open-coding workbench. It shows, per trace: the question, the loss
summary, the retrieved chunks (form / edition / clause and optionally the chunk
text the model actually saw), and the raw output. Nothing is scored and nothing
is labelled — labelling is the human's job and happens in notes.md.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from tracing import read_traces, TRACE_PATH


def render(trace: dict, with_chunks: bool = False, chunk_chars: int = 900) -> str:
    lines = []
    add = lines.append
    add("=" * 88)
    add(f"{trace['trace_id']}   {trace['ts_utc']}   {', '.join(trace.get('tags', []))}")
    add("=" * 88)
    add(f"Q  : {trace['input']['question']}")
    add(f"LOSS: {trace['input']['loss_summary']}")
    add(f"REF : {trace['input']['claim_ref']}   channel={trace['input']['channel']}")
    add(f"MODEL: {trace['model']['name']} temp={trace['model']['temperature']} "
        f"finish={trace['model'].get('finish_reason')} "
        f"total_ms={trace['timing']['total_ms']}")
    add("")
    add("RETRIEVED:")
    for c in trace["retrieval"]["chunks"]:
        add(f"  {c['rank']}. {c['chunk_id']:<26} score={c['score']:.5f} "
            f"v={c.get('vector_rank')} b={c.get('bm25_rank')}  "
            f"{c.get('form_number')} ed.{c.get('edition_date')}  {c.get('clause_id')}")
    if with_chunks:
        from ingest import resolve_chunk
        strategy = trace["retrieval"].get("strategy", "structure_aware")
        add("")
        add("CHUNK TEXT AS SEEN BY THE MODEL:")
        for c in trace["retrieval"]["chunks"]:
            r = resolve_chunk(c["chunk_id"], strategy=strategy)
            body = (r["text"] if r else "<<UNRESOLVED>>")[:chunk_chars]
            add(f"  --- {c['chunk_id']} ({c.get('form_number')} ed.{c.get('edition_date')}) ---")
            for ln in body.splitlines():
                add(f"    {ln}")
            add("")
    add("")
    add("OUTPUT:")
    for ln in trace["output"]["raw"].splitlines():
        add(f"  {ln}")
    add("")
    add(f"is_refusal={trace['output']['is_refusal']}  "
        f"cited={trace['output']['cited_chunk_ids']}")
    if trace.get("error"):
        add(f"ERROR: {trace['error']}")
    add("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", help="path to a sample_seed_*.json file")
    ap.add_argument("--trace-id", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--log", default=TRACE_PATH)
    ap.add_argument("--with-chunks", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    traces = {t["trace_id"]: t for t in read_traces(args.log)}

    if args.sample:
        with open(args.sample, encoding="utf-8") as fh:
            wanted = json.load(fh)["selected_trace_ids"]
    elif args.trace_id:
        wanted = args.trace_id
    elif args.all:
        wanted = list(traces)
    else:
        raise SystemExit("Pass --sample, --trace-id or --all.")

    out = "\n".join(
        render(traces[t], with_chunks=args.with_chunks) for t in wanted if t in traces
    )
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"written: {args.out}  ({len([t for t in wanted if t in traces])} traces)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
