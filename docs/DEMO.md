# Saathi — Demo Script

All Hindi text below is copied verbatim from actual verified runs during
development (Phase 3 and Phase 6/7 testing against the real policy PDF and
real Gemini/Qdrant/Rime calls) — nothing here is fabricated for the script.

## 90-second scripted walkthrough

One scenario, played out in full, including the interrupt — this is the
single narrative to rehearse and deliver live. Timings are approximate and
based on observed pipeline latency (STT ~4–6s, retrieval ~1s, generation
~5–20s, TTS streaming ~2–7s) — narrate over the "thinking" gaps rather than
standing silently.

| Time | Beat | Hindi | English |
|---|---|---|---|
| 0:00–0:08 | **Presenter hook** | — | "Saathi is a voice-first Hindi companion for families navigating a hospital admission in real time. Watch what happens when I ask it about my father's ICU admission." |
| 0:08–0:13 | **User speaks** (press mic, ask) | *"मेरे पिताजी को अभी ICU में भर्ती किया गया है, मुझे क्या करना चाहिए?"* | "My father has just been admitted to the ICU, what should I do?" |
| 0:13–0:33 | **Thinking** (narrate over this) | *(status: "सोच रही हूं...")* | "It's transcribing the question, searching the actual policy PDF for relevant clauses, then composing a grounded answer — not a canned response." |
| 0:33–0:53 | **Saathi answers** (spoken + shown) | *"मैं समझ रही हूं, यह बहुत चिंता का समय है, पर आप घबराइए मत, मैं आपकी पूरी मदद करूंगी। आपकी policy के Section 4.2 के अनुसार emergency में भर्ती होने पर 24 घंटे के भीतर कंपनी या TPA को सूचित करना होता है। Section 3 के तहत ICU का खर्च आपके कुल Sum Insured का 2% प्रति दिन तक कवर होता है। अभी तुरंत हॉस्पिटल के TPA या Insurance Desk पर जाइए, पॉलिसी कार्ड दिखाइए और Emergency Cashless Pre-Authorization फॉर्म भरने को कहिए।"* | "I understand, this is a very anxious time, but please don't worry — I'll help you fully. Under Section 4.2 of your policy, the company or TPA must be notified within 24 hours of an emergency admission. Under Section 3, ICU expenses are covered up to 2% of your total Sum Insured per day. Go to the hospital's TPA or Insurance Desk right now, show your policy card, and ask them to fill out the Emergency Cashless Pre-Authorization form." |
| 0:53–0:58 | **Interrupt** — speak over her mid-sentence | *"रुको, cashless claim reject हो गया तो क्या करूं?"* | "Wait, what do I do if the cashless claim gets rejected?" |
| 0:58–1:00 | **Presenter callout** | — | "Notice — she stopped instantly and didn't finish her old sentence. That's real interruption, not a scripted pause." |
| 1:00–1:20 | **Saathi answers the new question** | *"मैं समझ रही हूं, यह बात सुनकर आपको बहुत तनाव हो रहा होगा, लेकिन घबराइए मत। आपकी policy की Section 4.3 के अनुसार, क्लेम क्यों रिजेक्ट हुआ है, इसका कारण बीमा कंपनी लिखित में देती है। ... आप अभी तुरंत अस्पताल के इंश्योरेंस डेस्क पर जाकर Rejection Letter की लिखित कॉपी मांगिए।"* | "I understand this must be very stressful, but don't worry. Under Section 4.3, the insurer must give the rejection reason in writing. ... Go to the hospital's insurance desk right now and ask for a written copy of the Rejection Letter." |
| 1:20–1:30 | **Wrap** | — | Point at the citation chip under her answer ("Policy page 8") — "Every answer is grounded and cited. She's not guessing." |

## Three scenarios for judges to try hands-on

After the scripted walkthrough, hand over the mic. All three were tested
and verified end-to-end against the real policy PDF during development.

1. **ICU admission** — *"मेरे पिताजी को अभी ICU में भर्ती किया गया है, मुझे क्या करना चाहिए?"*
   ("My father has just been admitted to the ICU, what should I do?")
2. **Cashless denial** — *"अस्पताल कह रहा है कि cashless claim reject हो गया है, अब मैं क्या करूं?"*
   ("The hospital is saying the cashless claim was rejected, what do I do now?")
3. **Room rent cap** — *"अस्पताल ने बहुत महंगा प्राइवेट रूम दिया है, क्या यह policy में cover होगा?"*
   ("The hospital gave a very expensive private room, will this be covered?")

Judges can also ask their own questions — Saathi retrieves from whatever
policy PDF is loaded, so answers stay grounded even off-script.

## Fallback if things go wrong live

Ranked by likelihood, based on what actually broke during development:

1. **Gemini free-tier daily quota exhausted (20 requests/day hit once
   already during testing).** Symptom: Saathi gets stuck on "सोच रही हूं..."
   indefinitely with no error shown. Fix: switch to the backup Gemini API
   key in `backend/.env` if one was provisioned before the demo slot, or
   fall back to the pre-recorded video immediately rather than let the
   silence run — judges' patience for a stuck loading state is short.
2. **Venue WiFi drops** (every API call — STT, LLM, embeddings, TTS — is a
   network round trip). Fix: same fallback — pre-recorded video.
3. **Mic permission denied / wrong input device selected.** Fix: reload the
   page, re-grant permission when prompted; check the OS-level default
   mic if it still fails silently.

**Pre-recorded fallback video:** `docs/demo-video.mp4` — ⚠️ **not recorded
yet as of this writing.** Per the working-deadline plan (6 PM IST target,
9 PM hard cutoff), the last hours before submission are reserved for
recording this. Update this path once it exists; do not submit without it
given the quota risk above is a *confirmed*, not hypothetical, failure mode.
