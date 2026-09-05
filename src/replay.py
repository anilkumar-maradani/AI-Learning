"""
replay.py — Rebuild and re-run one request from its trace alone.

    python src/replay.py --trace-id tr_xxxxxxxxxxxx

"From the trace alone" means: this module never re-runs retrieval and never
looks at the original question object. It reads the trace line, resolves each
stored chunk_id back to its text, reassembles the context block in the stored
rank order with the stored scores, rebuilds the user turn from the stored
prompt version, and calls the stored model with the stored parameters.

Before replaying it checks three things and reports each one:

  1. ``prompt.system_sha256`` still matches the registry entry for that version
     (prompt drift).
  2. ``index_fingerprint`` still matches the live collection (index drift).
  3. Every stored chunk_id still resolves (chunk deletion).

Any of these failing does not stop the replay; it is printed as a caveat, which
is the honest reporting the exercise asks for.
"""

import argparse
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import prompts
from tracing import get_trace, index_fingerprint, TRACE_PATH
from claims_agent import build_user_message, call_model


def rebuild_context(trace: dict) -> tuple[str, list[str]]:
    """
    Reconstruct the exact context block from stored chunk_ids + scores.

    Mirrors ``generation.format_context`` field for field. The scores come from
    the trace, not from a fresh retrieval run, so a drifted retriever cannot
    silently change the replayed prompt.
    """
    from ingest import resolve_chunk

    strategy = trace["retrieval"].get("strategy", "structure_aware")
    parts, missing = [], []
    for c in trace["retrieval"]["chunks"]:
        resolved = resolve_chunk(c["chunk_id"], strategy=strategy)
        if resolved is None:
            missing.append(c["chunk_id"])
            continue
        parts.append(
            f"--- CHUNK ---\n"
            f"chunk_id: {c['chunk_id']}\n"
            f"form_number: {c.get('form_number') or 'UNKNOWN'}\n"
            f"clause_id: {c.get('clause_id') or 'N/A'}\n"
            f"source_file: {c.get('source_file') or 'UNKNOWN'}\n"
            f"score: {c['score']:.4f}\n"
            f"text:\n{resolved['text']}\n"
        )
    return "\n".join(parts), missing


def preflight(trace: dict) -> list[str]:
    """Return a list of caveats. Empty list means a clean, faithful replay."""
    caveats = []

    version = trace["prompt"]["version"]
    try:
        live = prompts.prompt_fingerprint(version)
    except KeyError as exc:
        return [f"PROMPT MISSING: {exc}"]

    if live["system_sha256"] != trace["prompt"]["system_sha256"]:
        caveats.append(
            f"PROMPT DRIFT: system prompt {version!r} has changed since this trace "
            f"(trace {trace['prompt']['system_sha256'][:12]} vs "
            f"registry {live['system_sha256'][:12]})."
        )
    if live["user_template_sha256"] != trace["prompt"]["user_template_sha256"]:
        caveats.append(f"PROMPT DRIFT: user template {version!r} has changed.")

    live_fp = index_fingerprint()
    if trace.get("index_fingerprint") and live_fp != trace["index_fingerprint"]:
        caveats.append(
            f"INDEX DRIFT: collection fingerprint is {live_fp}, trace recorded "
            f"{trace['index_fingerprint']}. Chunk text may differ."
        )
    return caveats


def replay(trace: dict, verbose: bool = True) -> dict:
    caveats = preflight(trace)
    context, missing = rebuild_context(trace)
    if missing:
        caveats.append(f"CHUNKS UNRESOLVED: {missing}")

    user_message = build_user_message(
        trace["prompt"]["version"],
        context,
        trace["input"]["claim_ref"],
        trace["input"]["loss_summary"],
        trace["input"]["question"],
    )
    model = trace["model"]
    result = call_model(
        prompts.get_system_prompt(trace["prompt"]["version"]),
        user_message,
        {
            "name": model["name"],
            "temperature": model["temperature"],
            "max_tokens": model["max_tokens"],
            "top_p": model.get("top_p", 1.0),
            "seed": model.get("seed"),
        },
    )

    original = trace["output"]["raw"]
    replayed = result["raw"]
    identical = original.strip() == replayed.strip()
    ratio = difflib.SequenceMatcher(None, original, replayed).ratio()

    out = {
        "trace_id": trace["trace_id"],
        "caveats": caveats,
        "chunks_replayed": len(trace["retrieval"]["chunks"]) - len(missing),
        "identical": identical,
        "similarity": round(ratio, 4),
        "original": original,
        "replayed": replayed,
        "user_message": user_message,
        "error": result["error"],
    }

    if verbose:
        print("=" * 78)
        print(f"REPLAY OF {trace['trace_id']}   (recorded {trace['ts_utc']})")
        print("=" * 78)
        print(f"question      : {trace['input']['question']}")
        print(f"claim_ref     : {trace['input']['claim_ref']}")
        print(f"prompt version: {trace['prompt']['version']} "
              f"(sha {trace['prompt']['system_sha256'][:12]})")
        print(f"model         : {model['name']}  temp={model['temperature']} "
              f"top_p={model.get('top_p')} max_tokens={model['max_tokens']} "
              f"seed={model.get('seed')}")
        print(f"chunks        : {[c['chunk_id'] for c in trace['retrieval']['chunks']]}")
        print(f"scores        : {[c['score'] for c in trace['retrieval']['chunks']]}")
        print()
        print("PREFLIGHT")
        if caveats:
            for c in caveats:
                print(f"  ! {c}")
        else:
            print("  ok — prompt hash, index fingerprint and all chunk_ids match.")
        print()
        print("-" * 78)
        print("ORIGINAL OUTPUT (from the trace)")
        print("-" * 78)
        print(original)
        print()
        print("-" * 78)
        print("REPLAYED OUTPUT (regenerated from the trace alone)")
        print("-" * 78)
        print(replayed)
        print()
        print("-" * 78)
        print(f"identical: {identical}    similarity: {ratio:.4f}")
        if not identical:
            print("\nUNIFIED DIFF (original -> replayed)")
            for line in difflib.unified_diff(
                original.splitlines(), replayed.splitlines(),
                fromfile="original", tofile="replayed", lineterm="", n=1,
            ):
                print(line)
        print("=" * 78)

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace-id", required=True)
    ap.add_argument("--log", default=TRACE_PATH)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    trace = get_trace(args.trace_id, args.log)
    if trace is None:
        raise SystemExit(f"trace_id {args.trace_id} not found in {args.log}")

    out = replay(trace)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"\nwritten: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
