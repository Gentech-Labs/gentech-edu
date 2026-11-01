# Reproducing the RAG-9 environment

**Why this file exists:** RAG-9's numbers are only worth something if someone else can re-run them. The run
used a scratch venv that would have been pruned and lost — that is how a measurement becomes a story.

## Rebuild

```bash
python3 -m venv ragvenv
./ragvenv/bin/pip install -r scripts/requirements-rag9.txt
./ragvenv/bin/python scripts/rag9-run.py
```

**Size:** ~186 MB installed. **No GPU. No API key. No embedding endpoint.**

## What is pinned and why

| Package | Why it is here |
|---|---|
| `fastembed==0.9.1` | embedding without torch — ONNX runtime, so a 186 MB install instead of ~2 GB |
| `onnxruntime==1.31.1` | the inference runtime under fastembed |
| `numpy==2.5.4` | cosine similarity only — no vector DB, because 811 chunks does not need one |
| `tokenizers`, `huggingface-hub` | model download and tokenisation |
| `py-rust-stemmers` | fastembed's sparse/BM25 helper (not exercised yet) |

## Models used (downloaded on first run, cached in the HF home)

- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` — multilingual baseline
- `BAAI/bge-small-en-v1.5` — the English-only contrast that scored **0/8 on Nepali queries**

## Traps recorded while building this

1. **Do not use an English-only model on a bilingual corpus and then measure only English questions.** That
   test passes and the system is still useless to a Nepali speaker. It is the bias that produced my first,
   wrong result.
2. **A question whose answer is not literally in the corpus measures nothing.** Verify every expected answer
   as a substring at load time and drop the failures loudly — 0 dropped here out of 20, checked.
3. **`fastembed` needs no torch.** `sentence-transformers` would have pulled ~2 GB for the same embeddings on
   CPU. On a box with no GPU, ONNX is the correct choice.
4. **Chunk size cannot be chosen from one language.** Fixed-1200 won English; structural-2600 was the only
   config non-zero on Nepali. Measure both, report both.

## What this environment cannot do
A bigger multilingual model (`e5-large`, `bge-m3`) is 2.2 GB+ and was **not** installed or run. That
measurement belongs on Forge's 8GB card — see `01-HANDOFFS/gentech-to-forge/2026-10-28-local-inference-benchmark-3070.md`.
