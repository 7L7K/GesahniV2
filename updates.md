# GesahniV2 Story‑Mode – Working Spec (Updated)

## 📝 Master Summary

| Section                    | Key Decisions                                                                                                                                                                                                           | Why We Chose It                                                                                                                         | Cost Notes                                                                              |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Capture Strategy**       | • **Realtime Audio STT** (`gpt-4o-mini-transcribe`) to grab every word live.<br>• **Full‑duplex “Assistant” feel** → turn on TTS replies only in Story Mode.                                                            | • Feels like a natural convo (bot can clarify in the moment).<br>• Boosts transcript quality with instant follow‑ups (“Which cousin?”). | • STT \$0.006/min.<br>• TTS \$0.015/min.<br>• Total ≈ \$0.021–\$0.023/min with both on. |
| **Everyday Assistant**     | Keep current **Chat Completions** flow (HTTP) with cheap models (`gpt-3.5-turbo` or local LLaMA) for lights, timers, FAQs.                                                                                              | • Lowest cost for day‑to‑day.<br>• No audio overhead unless user explicitly speaks.                                                     | Same as today (fractions of a cent per 1K tokens).                                      |
| **Storage & Metadata**     | • Save raw transcript JSONL per session.<br>• Tag speaker, timestamps, confidence.<br>• Filename pattern `stories/YYYY‑MM‑DD‑slug.jsonl`.                                                                               | • Easy lookup, keeps timeline intact.                                                                                                   | Plan cold‑storage / auto‑archive to control disk.                                       |
| **Summarization Pipeline** | Nightly cron:<br>1. Chunk transcripts (800–1 K tokens).<br>2. Summarize with `gpt‑3.5‑turbo` (cheap).<br>3. Embed + upsert to ChromaDB.                                                                                 | • Fast search & recall.<br>• Cheap summarizer keeps bill low.                                                                           | Pennies per night.                                                                      |
| **Memory Retrieval**       | Extend `route_prompt`:<br>• Detect “recall\_story” intent.<br>• Query ChromaDB → return passage + source.                                                                                                               | Makes assistant “remember” and cite Grandma’s words.                                                                                    | Vector search is local → free.                                                          |
| **Cost‑Saving Levers**     | • Cache common TTS phrases locally.<br>• Trigger TTS only on low STT confidence, topic shift, or user cue.<br>• Use local Whisper fallback if privacy / cost demands.<br>• Batch summaries, no live GPT for every line. | Cuts TTS bill by 50 – 70 %.                                                                                                             | —                                                                                       |
| **Future Upgrades**        | • Emotion tagging & speaker diarization.<br>• LoRA fine‑tune for Grandma’s tone (with consent).<br>• UI playback with waveform & jump‑to markers.                                                                       | Adds richness & soul over time.                                                                                                         | Optional add‑ons later.                                                                 |

---

## 🗺️ Implementation Road‑map (Next Steps)

1. **Scaffold `/ws/storytime`** endpoint with audio → STT → TTS loop.
2. **Save transcripts** in `stories/`, append JSONL live.
3. **Nightly `summarize_stories.py`** cron (chunk, summarize, embed).
4. **Intent hook** in `route_prompt` to search & cite memories.
5. **Add cost guards**: local cache for canned TTS, confidence‑based talkback.
6. **Later**: UI playback, emotion tags, fine‑tune voice clone.

---

> **Last updated:** 2025‑08‑03 — Use this doc to log future decisions, tweaks, and lessons learned.
