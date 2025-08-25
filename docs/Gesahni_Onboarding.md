# Gesahni Onboarding & Ethos Design

## 🚀 Principles for Futuristic Onboarding
1. **Conversational, not form-based**
   - Onboarding should feel like *meeting someone*, not “creating an account.”
   - Every input comes from a question asked by Gesahni in natural language.

2. **Immediate payoff**
   - Instead of “fill out data now, maybe benefit later,” show value in the moment.
   - E.g. they pick “music” → within onboarding, Gesahni plays a track.

3. **Seamless defaults**
   - Assume as much as possible.
   - Only ask for things that personalize experience (name, tone, interests).
   - Everything else (like timezone, device info) you infer automatically.

4. **Multi-modal wow factor**
   - Camera scan, voice sample, maybe avatar creation.
   - Feels like stepping into a sci-fi movie.

5. **Evolving onboarding**
   - Not everything has to happen at first login.
   - Some personalization steps (like “link Spotify” or “add grandma to memory vault”) can pop up *just in time* when the user triggers that feature.

---

## 🧩 Shaping the Flow with That Mindset

**Step 1 – Meeting Gesahni**
- Instead of a static welcome, Gesahni greets in voice + text.
- *“Hi, I’m Gesahni. Before we get rolling, tell me: what should I call you?”*
- Boom, instantly feels alive.

**Step 2 – Tone & Persona**
- *“Do you like me more formal, casual, or playful?”*
- This isn’t a preference buried in settings — it’s part of the relationship.

**Step 3 – Futuristic ID (Camera Scan)**
- Offer camera/voice scan.
- Instead of framing it as “security” or “profile picture,” frame it as **presence in your assistant’s world**.
- *“Let’s take a quick scan so I know when it’s you.”*
- Could turn that into a stylized avatar right away → instant sci-fi feel.

**Step 4 – Interests as Capabilities**
- Rather than a boring list, make it dynamic:
  *“I can run your smart home, manage music, track your fitness, and save family memories. What should I focus on first?”*
- User clicks chips. Gesahni replies with a promise:
  *“Got it. I’ll make music your priority.”*

**Step 5 – Memory & Seamlessness**
- *“Want me to remember things for you — like your favorite settings, family stories, or ongoing projects? You can always wipe it anytime.”*
- Present it as part of the “seamless future” story, not just data storage.

**Step 6 – First Action Demo**
- Immediately show off. If they picked “music,” start a track.
- If “smart home,” turn on/off a demo device (even a virtual toggle if no device connected).
- If “family stories,” preload one demo transcript and show how search works.

**Step 7 – Close with Futuristic Framing**
- Instead of “Done,” end with:
  *“That’s it. From now on, don’t think about it — just ask, and I’ll handle the rest.”*

---

## 🔥 How This Makes Onboarding Unique
- It’s **dialogue-driven** instead of form-driven.
- It has a **“wow moment”** (scan/avatar) baked in.
- It’s **immediate value-first**: you see the assistant *do something* before you even leave onboarding.
- It reinforces the **vision of seamless future**: Gesahni doesn’t ask you to configure settings; it learns as you go.

---

## 🏗️ Minimal Implementation Skeletons

**Frontend chaining (register → login)** still applies. After first login, route to `/onboarding`.

```ts
// after login
const me = await api.whoami();
if (!me.onboarding_complete) router.replace("/onboarding");
```

**Onboarding state machine (pseudo):**
```ts
state = greet -> tone -> interests -> (scan?) -> first_action -> done
onSelectInterests: doDemo(interests); // show don’t tell
onFirstActionConfirm: await api.createReminder(...); toast("Handled");
onDone: await api.markOnboardingComplete(); router.replace("/app");
```

**Feature request capture (fallback):**
```ts
if (intent === "unknown") {
  await api.createFeatureRequest({ text, user_id });
  reply("Not yet. I queued it and will update you when it ships.");
}
```

---

## 🏁 60-Minute Build Checklist
- [ ] Route `/onboarding` with the 5 short steps above.
- [ ] Add `onboarding_complete` boolean to users.
- [ ] Implement one **instant demo** per interest (music/sample, smart-home/virtual toggle, projects/auto note, family/record card).
- [ ] Add **“make it recurring”** chip to first successful action.
- [ ] Add **feature-request** endpoint + DB table.
- [ ] Add **“What I’m handling”** page (simple list of reminders/automations).
- [ ] Instrument TTFW & Silent-win metrics.
