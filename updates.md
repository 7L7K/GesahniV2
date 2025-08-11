# GesahniV2 Story‑Mode – Working Spec (Updated)

## 📝 Master Summary

| Section                    | Key Decisions                                                                                                                                                                                                           | Why We Chose It                                                                                                                         | Cost Notes                                                                              |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Capture Strategy**       | • **Realtime Audio STT** (`whisper-1`) to grab every word live.<br>• **Full‑duplex “Assistant” feel** → turn on TTS replies only in Story Mode.                                                            | • Feels like a natural convo (bot can clarify in the moment).<br>• Boosts transcript quality with instant follow‑ups (“Which cousin?”). | • STT \$0.006/min.<br>• TTS \$0.015/min.<br>• Total ≈ \$0.021–\$0.023/min with both on. |
| **Everyday Assistant**     | Keep current **Chat Completions** flow (HTTP) with cheap models (`gpt-3.5-turbo` or local LLaMA) for lights, timers, FAQs.                                                                                              | • Lowest cost for day‑to‑day.<br>• No audio overhead unless user explicitly speaks.                                                     | Same as today (fractions of a cent per 1K tokens).                                      |
| **Storage & Metadata**     | • Save raw transcript JSONL per session.<br>• Tag speaker, timestamps, confidence.<br>• Filename pattern `stories/YYYY‑MM‑DD‑slug.jsonl`.                                                                               | • Easy lookup, keeps timeline intact.                                                                                                   | Plan cold‑storage / auto‑archive to control disk.                                       |
| **Summarization Pipeline** | Nightly cron:<br>1. Chunk transcripts (800–1 K tokens).<br>2. Summarize with `gpt‑3.5‑turbo` (cheap).<br>3. Embed + upsert to ChromaDB.                                                                                 | • Fast search & recall.<br>• Cheap summarizer keeps bill low.                                                                           | Pennies per night.                                                                      |
| **Memory Retrieval**       | Extend `route_prompt`:<br>• Detect “recall\_story” intent.<br>• Query ChromaDB → return passage + source.                                                                                                               | Makes assistant “remember” and cite Grandma’s words.                                                                                    | Vector search is local → free.                                                          |
| **Cost‑Saving Levers**     | • Cache common TTS phrases locally.<br>• Trigger TTS only on low STT confidence, topic shift, or user cue.<br>• Use local Whisper fallback if privacy / cost demands.<br>• Batch summaries, no live GPT for every line. | Cuts TTS bill by 50 – 70 %.                                                                                                             | —                                                                                       |
| **Future Upgrades**        | • Emotion tagging & speaker diarization.<br>• LoRA fine‑tune for Grandma’s tone (with consent).<br>• UI playback with waveform & jump‑to markers.                                                                       | Adds richness & soul over time.                                                                                                         | Optional add‑ons later.                                                                 |

---

## 🗺️ Implementation Road‑map (Next Steps)

1. [ ] **Scaffold `/ws/storytime`** endpoint with audio → STT → TTS loop. _Not present; current code only provides `/transcribe` for live STT._
2. [ ] **Save transcripts** in `stories/`, append JSONL live. _Current sessions write `sessions/<id>/transcript.txt`._
3. [ ] **Nightly `summarize_stories.py`** cron (chunk, summarize, embed). _Summaries triggered manually via `/sessions/{id}/summarize`; no cron yet._
4. [ ] **Intent hook** in `route_prompt` to search & cite memories. _Memory retrieval wiring still pending._
5. [ ] **Add cost guards**: local cache for canned TTS, confidence‑based talkback. _Not started._
6. [ ] **Later**: UI playback, emotion tags, fine‑tune voice clone. _Future work._

---

> **Last updated:** 2025‑08‑09 — Use this doc to log future decisions, tweaks, and lessons learned.

### 2025‑08‑11 Security & Compliance
- PII redaction before storage:
  - Vector store `add_user_memory` now redacts and stores substitution maps under `data/redactions/user_memory/<id>.json`.
  - `MemGPT.store_interaction` and `MemGPT.write_claim` redact content; maps are stored out‑of‑band.
  - Session transcripts are redacted before writing to `transcript.txt` and `stories/*.jsonl`.
- RBAC:
  - Admin endpoints require `admin` scope when JWT scopes are enforced (`ENFORCE_JWT_SCOPES=1`).
  - Pin writeback endpoint `/v1/history/pin` requires `pin` scope.
- Audit:
  - Audit log records who pinned what (`pin_interaction`, `pin_claim`).
- Backups:
  - New `POST /v1/admin/backup` produces AES‑256‑CBC encrypted archive. See `app/README_BACKUPS.md`.
