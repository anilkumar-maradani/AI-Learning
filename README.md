# PolicyLens — Grounded Q&A over Homeowners Endorsements

PolicyLens is a small retrieval-augmented generation (RAG) system for insurance
policy endorsements. It indexes six synthetic homeowners endorsement forms
(HO-0304 … HO-0309), compares two chunking strategies, retrieves with a hybrid
BM25 + vector search, and answers questions with clause-level citations — or
refuses outright when the answer is not in the corpus.

Everything runs locally except the LLM call, which goes to Groq's free API.

---

## Quick start (Windows)

```powershell
git clone https://github.com/anilkumar-maradani/AI-Learning.git
cd AI-Learning
.\setup.ps1            # creates .venv, installs deps, builds the index
```

Then open `.env` and paste your Groq key (free at <https://console.groq.com/keys>):

```
GROQ_API_KEY=gsk_your_actual_key_here
```

Start asking questions:

```powershell
.\.venv\Scripts\Activate.ps1
python chat.py
```

> If PowerShell refuses to run the script:
> `powershell -ExecutionPolicy Bypass -File .\setup.ps1`

## Manual setup (Windows / macOS / Linux)

```bash
# 1. virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # macOS / Linux

# 2. dependencies (torch is ~2 GB — allow a few minutes)
pip install -r requirements.txt

# 3. API key
cp .env.example .env                # then edit .env

# 4. build the vector store (creates ./chroma_db, git-ignored)
python src/ingest.py
```

---

## What you can run

| Command | What it does |
|---------|--------------|
| `python chat.py` | Interactive console. Hybrid retrieval by default. Type `sources` after an answer to see every chunk that was used. |
| `python chat.py --mode vector --top-k 5` | Dense-only retrieval, 5 chunks. |
| `python src/evaluate_w4.py --strategy both` | Runs the 12-question golden set against vector-only and hybrid retrieval, prints hit-rate@3, p50/p90 latency, failure labels and a before/after table. No API key needed. |
| `python run_all.py` | Full pipeline: re-ingest, evaluate both chunkers on 8 known-answer questions, metadata-filter demo, 3 cited answers, 3 forced refusals. Writes `results.md`. Needs the API key. |
| `python src/hybrid_retrieval.py` | Smoke-test hybrid search on three sample queries. |

---

## How it works

```
endorsements/*.txt
      │
      ├─ naive_chunker            400-token sliding window, 50 overlap
      └─ structure_aware_chunker  split on SECTION / CLAUSE / EXCLUSION TABLE headers,
                                  exclusion rows glued to their table header,
                                  "[HO-0304 ed. 03-24] CLAUSE-ID" prefix embedded
      │
      ▼
ChromaDB (all-MiniLM-L6-v2, cosine)  ── two collections, one per chunker
      │
      ├─ vector search ───────┐
      └─ BM25 (rank-bm25) ────┤ RRF fusion (k=60) + exact-code rescue for "E-NN"
                              ▼
                     top-k chunks + metadata
                              │
                              ▼
        Groq · openai/gpt-oss-120b · temperature 0 · hard REFUSAL rule
```

### Chunk metadata

Every chunk carries `source_file`, `form_number`, `edition_date`, `policy_line`,
`chunk_id`, `clause_id`, `strategy`, `chunk_index`. `chunk_id` is resolvable
back to the stored text (`ingest.resolve_chunk`), which is what the citations
point at.

### Refusal gate

The system prompt requires a literal `REFUSAL:` response whenever the answer is
not present in the retrieved context; `generate_answer` flags it as
`is_refusal`. There is no "use your best judgment" escape hatch.

### Why hybrid retrieval

Dense embeddings blur rare identifiers — `E-17` sits almost on top of `E-11`
and `E-15` in embedding space because they share the same table context. BM25
weights rare exact tokens heavily. Fusing both rank lists fixes the exact-token
misses that vector-only retrieval produced on the golden set.

---

## Project layout

```
.
├── setup.ps1                  one-shot Windows setup
├── chat.py                    interactive console
├── run_all.py                 end-to-end evaluation → results.md
├── golden_set.jsonl           12 golden questions (form, clause, fragment, exact-token flag)
├── requirements.txt
├── .env.example               copy to .env
├── endorsements/              6 synthetic forms
│   ├── HO-0304_03-24.txt      water damage / supply-line coverage
│   ├── HO-0305_03-24.txt      named-storm deductible
│   ├── HO-0306_04-24.txt      mold & fungi exclusion
│   ├── HO-0307_04-24.txt      scheduled personal property
│   ├── HO-0308_05-24.txt      earth movement exclusion (broadened)
│   └── HO-0309_05-24.txt      business pursuits exclusion
└── src/
    ├── console.py             UTF-8 console output on Windows
    ├── chunkers.py            naive + structure-aware chunkers
    ├── ingest.py              ChromaDB ingest, metadata, resolve_chunk
    ├── retrieval.py           dense search, metadata filter, hit-in-top-5
    ├── hybrid_retrieval.py    BM25 + vector + RRF
    ├── generation.py          Groq client, grounding prompt, refusal detection
    ├── evaluate.py            8-question chunker comparison
    └── evaluate_w4.py         golden-set hit-rate@3 + failure labelling
```

`chroma_db/`, `.venv/`, `.env` and `__pycache__/` are git-ignored and created locally.

---

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | — | required for `chat.py` and `run_all.py` |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | any chat model available on Groq |

---

## Troubleshooting

- **`venv\Scripts\activate` not found** — a `venv/` created on macOS/Linux has
  `bin/` instead of `Scripts/` and cannot be reused on Windows. Delete it and
  run `setup.ps1` (which creates `.venv`).
- **`pip` fails on `uvloop`** — it has no Windows build; `requirements.txt`
  already skips it on Windows via an environment marker. Make sure you are
  installing from the current `requirements.txt`.
- **`ModuleNotFoundError: rank_bm25`** — `pip install rank-bm25` (already in
  `requirements.txt`).
- **`GROQ_API_KEY is not set`** — create `.env` from `.env.example`, or set it
  in the shell: `$env:GROQ_API_KEY = "gsk_..."` (PowerShell) /
  `export GROQ_API_KEY=gsk_...` (bash).
- **First run is slow** — the `all-MiniLM-L6-v2` embedding model is downloaded
  once (~90 MB) and cached by Hugging Face.

## Scope

Only the six endorsement files are indexed; the base policy wording library is
intentionally not part of the corpus, so questions about it are expected to be
refused.
