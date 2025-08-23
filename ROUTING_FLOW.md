# Gesahni Routing Flow & Decision Making

## Overview
When a user sends a prompt to Gesahni, the system follows a sophisticated routing decision tree to determine the best path for handling the request. This document explains the complete flow from prompt input to response generation.

## Main Entry Point: `route_prompt()`

The routing process starts in `app/router.py` with the `route_prompt()` function, which implements a priority-based decision tree.

## Decision Flow Diagram

```
User Prompt Input
       ↓
┌─────────────────────────────────────┐
│ 1. Input Validation & Preprocessing │
│    - Check for empty/whitespace     │
│    - Normalize prompt (lowercase)   │
│    - Count tokens                   │
│    - Apply token budget clamping    │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│ 2. Intent Detection                 │
│    - detect_intent(prompt)          │
│    - Returns: (intent, priority)    │
│    - Intent types:                  │
│      • smalltalk (greetings)        │
│      • control (device commands)    │
│      • recall_story (memory search) │
│      • chat (general conversation)  │
│      • unknown                      │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│ 3. Circuit Breaker Check            │
│    - If LLaMA circuit is open       │
│    - bypass_skills = True           │
│    - Forces model path only         │
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│ 4. Model Override Check             │
│    - If model_override provided     │
│    - Bypass all skills              │
│    - Force specific model (gpt/llama)│
└─────────────────────────────────────┘
       ↓
┌─────────────────────────────────────┐
│ 5. Priority Routing (in order)      │
│    a) Smalltalk (greetings)         │
│    b) Story Recall (memory search)  │
│    c) Home Assistant Commands       │
│    d) Answer Cache Lookup           │
│    e) Built-in Skills               │
│    f) Home Assistant (second chance)│
│    g) Cache (second chance)         │
│    h) Model Selection & Execution   │
└─────────────────────────────────────┘
```

## Detailed Routing Logic

### 1. Intent Detection (`app/intent_detector.py`)

The system uses a hybrid approach combining heuristics and semantic classification:

**Heuristic Matchers:**
- **Greetings**: Exact matches for "hi", "hello", "hey", etc.
- **Control Commands**: Regex patterns like "turn on", "switch off", "open", "close"
- **Story Recall**: Keywords like "what did i say", "recall", "remember"

**Semantic Classification:**
- Uses SBERT (Sentence Transformers) for semantic matching
- Compares against example intents: chat, control, recall_story, smalltalk, unknown
- Returns confidence score and priority (low/medium/high)

### 2. Priority-Based Routing

The router follows this strict priority order:

#### A) Smalltalk (Highest Priority)
```python
if intent == "smalltalk":
    skill_resp = await _SMALLTALK.handle(prompt)
    return skill_resp
```

#### B) Story Recall
```python
if intent == "recall_story":
    mems = safe_query_user_memories(user_id, prompt, k=k)
    if mems:
        return formatted_memory_response
```

#### C) Home Assistant Commands
```python
ha_resp = handle_command(prompt)
if ha_resp is not None:
    return ha_resp
```

#### D) Answer Cache
```python
cached = lookup_cached_answer(norm_prompt)
if cached is not None:
    return cached
```

#### E) Built-in Skills
The system checks against a catalog of skills with keyword matching:

**Skill Categories:**
- **Time/Date**: Clock, World Clock, Timer, Reminder
- **Weather**: Weather, Forecast
- **Math**: Math, Unit Conversion, Currency
- **Home Automation**: Lights, Cover, Fan, Climate, Vacuum, Door Lock
- **Media**: Music, Roku
- **Information**: News, Dictionary, Recipe, Search, Translate
- **Entertainment**: Joke, Status
- **Productivity**: Calendar, Notes, Notify, Scene, Script

**Skill Matching Process:**
```python
for entry in CATALOG:
    if isinstance(entry, tuple) and len(entry) == 2:
        keywords, SkillClass = entry
        if any(kw in prompt for kw in keywords):
            result = await _run_skill(prompt, SkillClass, rec)
            return result
```

#### F) Model Selection & Execution

If no skills match, the system proceeds to model selection:

### 3. Model Selection Logic

The system uses two different model selection approaches:

#### A) Deterministic Router (New)
When `DETERMINISTIC_ROUTER=true`:

```python
decision = route_text(
    user_prompt=prompt,
    prompt_tokens=tokens,
    retrieved_docs=None,
    intent=intent,
    attachments_count=attachments_count,
)
```

**Deterministic Routing Rules:**
- **Attachments**: Any images/files → `gpt-4.1-nano`
- **Ops (File Operations)**:
  - ≤2 files → `gpt-5-nano`
  - >2 files → `gpt-4.1-nano`
- **Long Prompts**: >240 tokens → `gpt-4.1-nano`
- **Long RAG Context**: >6000 tokens → `gpt-4.1-nano`
- **Heavy Keywords**: "code", "research", "analyze", etc. → `gpt-4.1-nano`
- **Heavy Intents**: "analysis", "research" → `gpt-4.1-nano`
- **Default**: `gpt-5-nano`

#### B) Legacy Model Picker
When deterministic router is disabled:

```python
engine, model = pick_model(prompt, intent, tokens)
```

**Legacy Rules:**
- **Heavy Prompts**: >30 words OR >1000 tokens OR heavy keywords → GPT
- **LLaMA Health**: If LLaMA unavailable → GPT fallback
- **Default**: LLaMA (if healthy)

### 4. Self-Check Escalation

After model selection, the system may escalate to a more powerful model if the initial response fails quality checks:

```python
text, final_model, reason, score, pt, ct, cost, escalated = (
    await run_with_self_check(
        ask_func=ask_gpt,
        model=decision.model,
        user_prompt=built_prompt,
        system_prompt=system_prompt,
        retrieved_docs=mem_docs,
        on_token=stream_cb,
        stream=bool(stream_cb),
        max_retries=max_retries,
    )
)
```

**Self-Check Process:**
1. Generate response with selected model
2. Evaluate response quality using heuristic scoring
3. If score < threshold (0.60), escalate to next tier
4. Repeat up to MAX_RETRIES_PER_REQUEST times

## Key Decision Factors

### 1. **Intent Priority**
- `smalltalk` (low priority) - Handled by skills
- `control` (high priority) - Home Assistant commands
- `recall_story` (medium priority) - Memory search
- `chat` (variable priority) - Model-based response

### 2. **Prompt Characteristics**
- **Length**: Token count and character count
- **Content**: Keywords, attachments, file operations
- **Complexity**: Intent classification confidence

### 3. **System State**
- **LLaMA Health**: Circuit breaker status
- **Cache Hits**: Previously answered questions
- **Skill Availability**: Built-in skill matches

### 4. **Budget & Performance**
- **Token Budgets**: Clamping excessive input
- **Cost Control**: Self-check escalation limits
- **Response Quality**: Escalation thresholds

## Example Routing Scenarios

### Scenario 1: "Hello there"
1. Intent: `smalltalk` (priority: low)
2. Route: SmalltalkSkill
3. Response: Greeting response

### Scenario 2: "Turn on the living room lights"
1. Intent: `control` (priority: high)
2. Route: Home Assistant command
3. Response: Device control response

### Scenario 3: "What's 15 * 23?"
1. Intent: `chat` (priority: medium)
2. Skills: MathSkill matches
3. Route: MathSkill
4. Response: "345"

### Scenario 4: "Explain quantum computing in detail"
1. Intent: `chat` (priority: high)
2. Skills: No matches
3. Model Selection: `gpt-4.1-nano` (heavy keywords)
4. Route: GPT model with self-check escalation

### Scenario 5: "What did we talk about yesterday?"
1. Intent: `recall_story` (priority: medium)
2. Route: Memory search
3. Response: Relevant past conversations

## Configuration & Tuning

### Environment Variables
- `DETERMINISTIC_ROUTER`: Enable new routing logic
- `INTENT_THRESHOLD`: Semantic classification confidence (default: 0.7)
- `SELF_CHECK_FAIL_THRESHOLD`: Escalation threshold (default: 0.60)
- `MAX_ESCALATIONS`: Maximum retries (default: 1)

### Hot-Reloadable Rules (`router_rules.yaml`)
- `MAX_SHORT_PROMPT_TOKENS`: 240
- `RAG_LONG_CONTEXT_THRESHOLD`: 6000
- `OPS_MAX_FILES_SIMPLE`: 2
- `SELF_CHECK_FAIL_THRESHOLD`: 0.60

## Monitoring & Analytics

The system tracks routing decisions through:
- **Metrics**: Prometheus metrics for each routing path
- **Telemetry**: Detailed request records with routing metadata
- **Logging**: Debug logs for routing decisions and model selection

Additional exported metrics relevant to routing and dependencies:
- `model_latency_seconds{model}`: p50/p95 via histogram_quantile
- `dependency_latency_seconds{dependency,operation}`: e.g., qdrant search/upsert
- `embedding_latency_seconds{backend}`: openai vs llama
- `vector_op_latency_seconds{operation}`: upsert/search/scroll/delete

This routing system ensures optimal resource usage while maintaining response quality and user experience.
