---
name: edu
description: "Use when Jordan says 'activate EDU' or needs a learning scenario."
version: 2.0.0
author: gentech
tags: [gentech-edu, agent-kit, learning, language, dialect, scenarios, travel, pack]
---

# EDU — the learning engine

**Jordan, 2026-09-23:** *"why don't we rename it to EDU? So I'll say, hey, Jintek, activate EDU and then
I'll describe what I want. I think that will work better than 'life lesson scenario' because they'll be
different, you know?"*

## ACTIVATION

**"Activate EDU"** (or "activate Jintek EDU") = start an EDU session. He then describes the subject, and
you build the scenario from **his** material. Do not ask him to choose from a menu — see the decides-alone
boundary below.

The name is deliberately general: **`life-based-language-lessons` described one pack; EDU is the engine
under all of them.** Language was the first pack, not the product.

## What EDU is (his spec, verbatim)

> *"the idea for the GenTech EDU was if you want to learn something you can just give us info and we'll
> create scenarios that help you learn and you get engaged because it's something that you care about."*

As a contract:

| Part | Meaning |
|---|---|
| **"if you want to learn something"** | ANY subject — Spanish, Thai, DeFi, how to talk to the Steward |
| **"just give us info"** | **he supplies the material** — itinerary, menu, portfolio, whatever he has |
| **"we'll create scenarios"** | practised situations, not summaries |
| **"that help you learn"** | sequenced, with the error log steering what comes next |
| **"engaged because it's something that you care about"** | **the corpus is his** — the whole moat |

## THE ENGINE / PACK BOUNDARY — the rule that keeps this from being rewritten

The engine is **subject-agnostic**. A subject is a **PACK**.

- **Engine (never subject-specific):** sequencing, mastery/error tracking, spaced repetition, rendering,
  delivery, the source loader, and **the honesty rules** — so every pack inherits them for free.
- **Pack (subject-specific):** the phrase/step bank, the dialect, the voice mapping, domain vocabulary.
  (`dialect`, `venue_type`, `menu section` are **travel-pack words**, not engine words.)
- **Adding a subject = adding a file, not editing the engine.** If it needs an engine edit, the boundary
  is wrong.

**This was a real defect:** `life-lesson-scenario.py` keys `SCENARIOS` by `(dialect, venue_type)` — Spanish
and travel in its bones. Thai or DeFi onboarding would have been a **rewrite, not an entry.** A working
feature was called an engine. Naming the boundary is the fix.

**Existing EDU work is also packs** — the Agentic Treasury onboarding docs and the DeFi milestone ladder
were hand-written before the engine existed. Retrofitting them is the obvious next cheap win.

## The layer model — how EDU combines with everything else

```
SURFACES   Travel suite · Agent Kit · gentechlabs.net · Hub boards
    ↑ surfacing
PACKS      language · travel-scenarios · treasury-onboarding · (next)
    ↑ runs on
ENGINE     EDU — generate scenarios from what you give it
    ↑ fed by
SOURCES    his itinerary · menus · APIs · the error log · whatever he hands over
              ↓
RAIL       x402 — per transaction
```

**A pack is owned by no single surface.** Language learning is a **pack on the EDU engine surfaced inside
the Travel suite**, because that is where the context is. Same engine, two doors.

**Jordan generalised this himself:** *"it's also the same way that the GenTech Hub is the engine to put the
visual data out there on a web page."* See `00-HQ/gentech-engine-architecture.md` — Hub, EDU, Treasury and
Travel are the **same machine**: `SOURCES → ENGINE → SURFACE → RAIL`. A new idea is a **pack**, not a new
product: no new funnel, no new pricing, no new payment story.

## PACKS BUILT

### LEVEL LAYER — "how good do I actually need to be?" (added 2026-09-24)

**Jordan:** *"I want to get my Spanish to a better speaking level before I go to somewhere like Santo
Domingo or Santiago or any of the other Dominican cities."*

That is a **different requirement** from the trip already priced, and the engine did not cover it. The
engine teaches the **dialect**; it had no notion of a **level**. And the level is a property of the
**place**, not of the language — `es-DO` is the same dialect in Sosúa and Santiago, but a tourist town
runs on English and a real city does not.

- **`life-lesson-level.py`** + **`data/level-targets.json`** (the level targets are
  **PACK data** — a new subject adds this file, it never edits the engine).
- **Sosúa/Cabarete/Punta Cana → A1** (tourist zone, survival is enough). **Santo Domingo/Santiago/
  La Vega/Moca → B1** (real city, conversational floor). **Thailand → A1** (Cat IV, ~1,100 hrs —
  polite survival does not fit in months).
- **Unmatched place → NO target.** It refuses to guess a default.
- Ladder = **cumulative CEFR guided hours as RANGES** (A1 90–100 · A2 180–200 · B1 350–400 ·
  B2 500–600 · C1 700–900 · C2 1000–1200), quoted as ranges — averaging them into one number is
  false precision.

### ⛔ THE LEVEL LAYER'S HARD RULES (it is the easiest place in the fleet to lie)

1. **NEVER print a CEFR level as a fact about the learner.** Phrase-bank practice cannot certify a
   level. Everything derived from it is labelled **ESTIMATE** with the basis printed.
2. **No observed practice → `UNMEASURED`.** Never a fabricated 0%, and never a default "you're A1".
3. **BANK COVERAGE IS NOT THE LEVEL** — the highest-value rule here. A learner can master **100%** of
   a 28-phrase bank and still not be A1. Report coverage and level **separately**, and say the cap out
   loud. **Conflating progress with proficiency is how a language app lies to you** — and it is the
   exact failure this product exists to beat.
4. **An unattempted phrase is NOT a miss.** Exclude it from numerator *and* denominator; counting it
   as a miss manufactures a low score out of nothing.
5. **Read the phrase bank out of the engine (`import life-lesson-engine`), never copy it.** A copied
   list drifts the moment a phrase is added, and the level check then measures a bank that no longer
   exists. Selftest check 8 guards this.

8/8 RED, synced to all 4 seats, each seat's selftest verified passing on its own machine.

| Pack | Script | What it draws on |
|---|---|---|
| **Language** (dialect-first) | `life-lesson-engine.py`, `life-lesson-audio.py` | real trips, nearest-trip-first |
| **Travel scenarios** | `life-lesson-scenario.py` | real venues, real menus, our FX rate |
| **App equivalence** | `edu_apps.py` | the need → the local app, across countries |

## APP EQUIVALENCE — the need is the unit, not the app

> *"you've got your like Kluk, for example — I know in Southeast Asia they use Kluk the same way we use
> Grubhub. So now I know food equivalence — so if I don't want to grab a moto or take an Uber somewhere, I
> could just have it delivered."*

**He is not learning app names. He is mapping a NEED he already understands onto whatever that country
calls it.** `FOOD DELIVERY → {US: Grubhub, DR: Komida, TH: Grab/LINE MAN}`. That is what makes it usable in
a country he has never visited.

**The unit is the need.** One need — *"I don't want to go out for it"* — resolves either by **riding there**
or by **having it delivered**, and knowing the equivalence is what reveals the choice.

Rules:
- **A country with no known app returns `unknown — do not assume it carries over`** — never a blank, never a
  borrowed US name. Assuming the home app works abroad is the exact error this prevents.
- **A withdrawn app stays marked dead.** foodpanda pulled out of Thailand in **May 2025** — recommending it
  would send him to a dead end.
- **Every mapping carries a status**, or it reads as an endorsement.

## The insight this is built on

Duolingo's own monetisation admits the mechanism: **AI conversation is paywalled because conversation is the
only place the app learns what you actually need.** The generated sentences are **telemetry**. They harvest
that signal and still drill everyone the same generic corpus (*"the bear drinks beer"*).

**We take the mechanism and close the loop:** collect what the learner gets wrong → drill THAT next, in
sentences drawn from his own itinerary.

**The bone to refuse:** a conversation partner with no syllabus — fluent-sounding, teaches nothing.

## DIALECT, NOT LANGUAGE — the non-negotiable

> *"when it comes to different languages, you also got to look at different dialects… I'm going to the
> Dominican Republic, right? Well now I need to learn the Dominican dialect and how they speak Spanish very
> fast. Also, there's slang words, like K-L-K for what's up."*

**"Spanish" is not a lesson. `es-DO` is.** Resolve to a **variant** (`es-DO`, `th-TH`), never a bare
language code. A generic-language lesson is the same defect as a generic corpus: content the learner cannot
use.

### Every lesson must carry three things
1. **The variant** (`es-DO`) — resolved from the destination, nearest trip first.
2. **The matching regional voice** — a language name is NOT a voice (see below).
3. **The regional form beside the textbook form** — the contrast *is* the teaching.

## THE TWO TECHNICAL TRAPS (both cost real time)

### Trap 1 — a language name is not a voice
Our ElevenLabs account's own voices are **all `lang=en`** (`Roger`, `Sarah`, `Brian`…). Using one for Spanish
produces **an American accent reading Spanish** — the opposite of useful, because the learner rehearses
phonetics that do not exist where he is going.

**Pick the voice by DIALECT**, and store that mapping alongside the dialect so a new dialect can never
silently inherit the wrong accent.

### Trap 2 — shared-library voices 404 until ADDED to the account
Regional voices live in the **shared library**, but a direct synthesis call by id returns
**`404 voice_not_found`**. Two-step path:

```bash
# 1. find them (returns the public_owner_id the add call needs)
curl -s "https://api.elevenlabs.io/v1/shared-voices?accent=dominican&page_size=10" \
  -H "xi-api-key: $ELEVENLABS_API_KEY"
# 2. ADD to the account — this is the step that is easy to miss
curl -X POST "https://api.elevenlabs.io/v1/voices/add/{public_owner_id}/{voice_id}" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" \
  -d '{"new_name":"Anderson (DR)"}'
```

A plain voice listing does **not** include `public_owner_id` — use `shared-voices` or the add fails.

## Scenario intelligence — language learning + trip planning

> *"if I wanted to give you a scenario… I know when I go to the POP airport and I get off I'm gonna want to
> know what to say to the taxi guy… or one of the first restaurants I plan on going to is Flip Flops… that's
> what would make this next level — adding intelligence so we get language learning and trip planning
> together."*

**A scenario is not a generic dialogue.** It is built against the **actual venue, its actual menu, and the
actual price in the local currency** — which is what makes the phrase usable the moment he lands.

Rules:
- **Read the venue's real data** (own site, menu boards via `vision_analyze` on the menu images).
- **Convert prices with OUR FX tracker's latest row**, never a remembered rate — and **print the provenance**.
- **A price with no published figure is `varies`** — never `$0`, never a guess. Same for a missing FX rate:
  declare the gap, do not fall back to a stale number.
- **Record the friction, not just the phrase.** ("Agree the price before the bags go in the trunk." /
  "Staff speak English here — low-stakes practice.") That is the intelligence layer.

## The engine owns the sequence (decides-alone boundary)

- ❌ A **picker** that waits for the learner to choose a lesson — hands the decision back. The
  "calibrated confidence became *ask Jordan*" failure in a new costume. **A toy.**
- ❌ A **chatbot in a lesson frame** — adding turns to a conversation is not teaching.
- ✅ An engine that reads the itinerary, knows which trip is next, and **serves what he needs next**,
  prioritising what he keeps getting wrong. **An agent.**

## Where EDU lives

**GenTech EDU is a SECTION OF THE AGENT KIT** — the thing we offer so people learn to use the skills and the
Agentic Treasury we built. The language layer sits alongside the existing sections (Tutors / Milestones /
Activity-Hobby). **Not** a Travels feature, **not** a standalone product.

**Why it matters commercially:** the Agent Kit is the distribution surface — a language section inherits its
audience, packaging and payment rail instead of needing a new funnel. Same move as the personal-assistant
skills: *a new capability inside a stack people already buy into.*

## Scripts

| Script | Job |
|---|---|
| `edu_apps.py` | **app equivalence** — need → local app, per country; unknown never borrows |
| `life-lesson-engine.py` | lesson from real trip data; `--selftest` plants 8 failures |
| `life-lesson-audio.py` | renders the lesson in the **dialect's** voice; verifies the response is real MPEG |
| `life-lesson-scenario.py` | scenario from a **real venue** + its menu + our FX rate |
| `life-lesson-level.py` | the LEVEL layer — place → CEFR target and the honest gap; `--selftest` plants 8 failures |
| `data/travel-venues.json` | real venues, real menus, real prices (source + verified date on each) |
| `data/travel-apps.json` | which apps actually work where — source + checked date on each |
| `data/level-targets.json` | required CEFR level per zone (**PACK data** — a new subject adds this file) |
| `data/voices.json` | **voice per dialect, per learner FORM** — PACK data, because *voice mapping* is pack. An unvoiced dialect resolves to `None` so the audio step REFUSES instead of borrowing an English voice. |
| `data/learners.json` | **who the engine may teach + the forms they are served in** — PACK data. An unknown learner is a HARD STOP (exit 1), never a default. |
| `data/trip-priority.json` | **which destination leads a lesson** — rank per place, with the reason and the source (**PACK data**) |

Every script has `--selftest` that **plants failures and proves each goes RED**. Run it before trusting a
change.

## Where these files live — and why it is a rule, not a preference

**One skill, one tree: `skills/edu/` — `scripts/` beside `data/`. Nothing resolves a profile path by
name.**

- **Every script derives its own SEAT from `__file__`** (`profiles/<seat>/…`), the same idiom as
  `handoff-watcher.py` — cron has no script-args field, so path-derived identity is the only
  fleet-wide mechanism. Read and write paths (`state/`, `cache/life-lessons/`, `data/`) are built from
  that, so each seat uses **its own** files.
- **The vault is the one shared exception** and says so inline (`VAULT` = the vault root: `/opt/data/.obsidian-vault` — migrated off `/root` when the host became a container) — trip
  data and the FX tracker are fleet-wide by design.
- **The canonical copy is the shared core: `10-Labs/skills-distribution/edu/`.** Edit the CORE, never a
  seat copy — a seat edit is a build artifact and the next `fleet_skills_sync.py` reverts it.
- **The core copy is not a seat.** Run from `10-Labs/skills-distribution/edu/` it falls back to HQ, which
  owns the core; it is there to be *synced*, not to run lessons.

**History — the three measured faults this layout closes (2026-09-25):** (1) the skill had **no core
copy**, so nothing synced it and `data/travel-apps.json` drifted on HQ alone until the drift gate went
red; (2) `edu_apps.py` and then `life-lesson-scenario.py` each read **a different file than this doc
names** — the doc/reader disagreement that hid the drift; (3) `life-lesson-{engine,audio,level}.py`
carried **`/root/.hermes/profiles/gentech` hardcoded into all four seats**, so every seat read HQ's state
and cache, and this doc's LEVEL LAYER section existed on HQ alone while the level *script* was on all
four seats. One canonical tree + a path-derived seat closes all three.

## Pitfalls

- **The plan changes; the engine must not.** Jordan: *"Lol sorry trip plans change a lot"* — so **which trip
  leads a lesson is PACK DATA** (`data/trip-priority.json`), never a dict in the script. Two rules ride with
  it: a place he has **NAMED** outranks a fare **WATCHER** (a watcher outlives the decision that created it —
  that is exactly how the engine drilled the DR for a Thailand trip), and a **missing or empty priority table
  makes the engine REFUSE** rather than pick whichever country happens to match first. Changing the plan is a
  one-file edit with the reason written beside the rank; nobody edits the engine for a calendar.
- **The trip source is a MOVABLE path, and when it moves the engine silently serves the WRONG LANGUAGE.**
  `TRIPS` resolves `VAULT/Travel/travel-jordan.json`. That directory was deleted on 2026-10-15 when travel
  consolidated into `00-HQ/01-Travel/` — and the consolidation believed it was an empty shell, because it
  inspected the *folder* and not the *readers*. With no trip record the engine degrades quietly to the
  `00-HQ/01-Travel/*/price-history.md` fare **watchers**, where a stale city tracker outranks the real trip
  (`NEXT_TRIP_RANK`: puerto plata=1, bangkok=2) — measured: it served **es-DO for a Thailand trip**. A missing
  trip file must be **loud**, not a silent fallback into fare history. Two rules follow: (1) when relocating
  trip data, `grep` the fleet for readers of the old path **first** — a folder that is empty to you may be the
  only input to a script; (2) never treat "a city has a fare tracker" as "he is going there" — a watcher
  outlives the plan it was created for.
- **A phrase bank keyed by dialect but not by LEARNER teaches the wrong person — FIXED 2026-10-17, keep it
  fixed.** Mastery used to live at `profiles/<seat>/state/life-lessons.json`, keyed by phrase: one record per
  **seat**, so two learners shared it and each one's misses sorted the other's drills. And a language bank is
  not learner-neutral: every particle in the `th-TH` bank is the **male** form (`ครับ`) — **`ค่ะ` is the female
  form**, so a female learner rehearsed the wrong politeness particle on every sentence. Jordan's fix, in his
  words: *"share progress but separate… Similar to tenant cron jobs."* The built shape, copied from the
  Treasury's tenant pattern because it was already proven:
  1. **The registry is PACK DATA** (`data/learners.json`) — adding a learner is a file edit. An **unknown
     learner is an ERROR, not a permission** (the `tenant_guard` rule; a warning gets scrolled past in a cron
     log). The script exits 1 and names the registry path.
  2. **Separate progress:** `profiles/<seat>/state/learners/<learner>.json`. Keep a read-only legacy fallback
     to the old single-record path so a structural change never loses history.
  3. **Forms are per learner, and the render SAYS which one it served** (*"served in the female form"*).
     Substitute the English gloss too — `Hello (male speaker)` standing beside `สวัสดีค่ะ` is a mislabel, and
     a mislabel is a wrong answer, not a cosmetic one.
  4. **Lessons per learner in the brain:** `EDU/lessons/<learner>/<date>-<dialect>.md`. Never one shared file.
  Selftests 10–12 plant exactly these failures: unknown learner must stop, two learners must differ in BOTH
  record and form, and every lesson must name who it was for.
- **The third element of a shape line is not always a textbook variant.** `render()` labels `lines[2]`
  `(textbook: …)`, which is right for `es-DO` (regional vs standard) but wrong for `th-TH`, where element 3
  is the **romanisation/reading** (`jàak krung-thêep…`). The label is per-dialect; do not read a Thai shape's
  output as a register contrast.
- **The level layer counts the WHOLE bank, not the dialect's.** Thailand reports `bank coverage: 0/28`
  (es-DO 19 + th-TH 9); for a Thai learner the denominator must be 9. Coverage is never the level, but a
  wrong denominator is still a wrong number — and this product exists to not print those.
- **The human record belongs in the vault `EDU/` folder, the data belongs in the CORE.** Lessons served,
  learner state and session notes go to `EDU/{packs,learners,lessons,sessions}/`; the phrase bank, shapes,
  venues and level targets go to `10-Labs/skills-distribution/edu/data/`. **A lesson written only into `EDU/`
  is a document, not a pack** — if the engine cannot serve it, say so rather than filing it and calling it
  built. `ROUTING.md` must name the folder the same session it is created, or the next agent routes past it.
- **Symlink-free, seat-by-seat sync when a full fleet sync would destroy work.** `fleet-skills-sync.py --sync`
  is CORE→seat and **refuses only seat-only skills** — it will happily overwrite a seat's *newer version of a
  skill that also exists in CORE*. Before syncing, run `--check` and `diff -rq` the CORE against each seat;
  measured 2026-10-17, a global `--sync` would have destroyed gentech-treasury's corrected
  `market-data-feed-selection`. Sync the one skill, verify the content digest per seat, and park `.bak` files
  OUTSIDE the skill dir so they do not ship to six seats.
- **Renaming a language key orphans stored mastery.** Splitting `es` → `es-DO` silently reset every learner
  record to "new", so the drill loop forgot what he got wrong. **A rename is not a reason to lose data** —
  keep a legacy-key fallback when you re-key. (Selftest caught this, not review.)
- **Filename vs place-name mismatch.** Vault dirs use hyphens (`puerto-plata/`), place keys use spaces
  (`puerto plata`) — a plain `in` test **never matched**, so a country silently dropped out of the ranking.
  Normalise both sides.
- **Iteration order is not priority.** Returning the first match meant the alphabet decided the language
  (`bangkok/` beat `puerto-plata/`), serving **Thai two months early**. Rank by **nearest trip**, and prove
  order-independence with a reversed-input check.
- **Never trust a grep over a file's behaviour.** A class sweep flagged a guard as missing that was present
  under a different name. Confirm by **running it**, and check the run was not suspiciously fast.
- **EDIT THE CORE, NEVER A SEAT COPY — the sync will clobber it and the digest is how you know.**
  Fell into this 2026-10-17 while fixing a defect the Sr audit found: patched
  `profiles/arthur/skills/edu/scripts/life-lesson-engine.py`, ran the sync, and the fix was **gone**.
  The tell was that the CORE digest **had not changed** — an edit that lands must move the digest, so an
  unchanged digest after an edit means the edit went somewhere the sync overwrites. Check
  `grep -c '<your new marker>' <CORE path>` after any edit; if that is 0, you fixed a build artifact.
- **A phrase bank written in ONE gendered form will key the other learner's mastery to the wrong
  phrase.** Measured 2026-10-17: the mastery key was computed from the bank phrase (male) and the
  politeness form was swapped *afterwards*, so the female learner's served `ฉันมาเที่ยวค่ะ` carried a
  status derived from `ผมมาเที่ยวครับ`. Her misses could never return as drills and she would see NEW
  forever, with **no error raised**. **Apply the learner's form FIRST, then compute the key from the
  phrase actually served** — and keep the bank-phrase key as a fallback so existing records survive.
  Selftest 16 plants exactly this: her miss must come back as a drill, keyed to the served phrase, and
  must not leak into the other learner.
- **A BRIDGE KEYED TO THE DIALECT IS NOT A BRIDGE — KEY IT TO THE LEARNER'S FIRST LANGUAGE.** Jordan,
  2026-10-17: *"I am American, so I speak English… Josephine, she's Filipino, so she speaks Tagalog…
  speak to her and her language whenever she is asking for pronunciation."* The first build had **ONE**
  global bridge voice (American), which served a Tagalog speaker an English-eye approximation. Now
  `bridge.by_lang` in `data/voices.json` is keyed by the learner's own `first_language.code` (from
  `learners.json`), and `resolve_bridge_voice(learner)` returns `None` for a language with no entry so
  the Thai is served **alone** and says so — never another language's approximation wearing the name
  "bridge". **AND THE SECOND LAYER, WHICH IS STILL OPEN: the READING TEXT itself.** The `rom` is an
  RTGS spelling built for an English eye (`phom ma thiao khrap`); Tagalog is phonetically regular and has
  no `ph`/`kh`, so her approximation needs re-spelling in Tagalog orthography. A Filipino voice reading
  an English spelling is *half* a bridge. Do not present it as whole.
- **"No key" and "quota exhausted" are different failures — measure which one you have.** Audio was
  reported blocked on this seat because `ELEVENLABS_API_KEY` had no `.env` entry. The key was on the host
  the whole time, in `profiles/*/secrets/elevenlabs_api_key` (600) — **the gate was the lookup, not the
  credential.** Fix the lookup first (env → secrets file → seat `.env`), and only then look at quota.
  With the key working, the real gate was `HTTP 401 … quota_exceeded` (Creator: 13 of 363,000 characters
  left) — and ElevenLabs returns that as **401**, which reads like "bad key". Read the body before
  concluding anything. A quota that resets is a *wait*, not a blocker: schedule the render for just after
  the reset and have the job refuse to fabricate audio if the gate is still shut. **Voice ADDS are free —
  they do not consume characters** — so add the voices immediately and let only synthesis wait.
- **The lane has a THIRD state between "no key" and "quota exhausted": PAST-DUE BILLING, and a 1-char
  probe cannot see it.** MEASURED 2026-10-17 19:06–19:19 UTC: `/v1/user/subscription` read
  `status=past_due` + `has_open_invoices=true` with one open invoice of **$23.72** (Creator; retry
  2026-10-24 22:01:15 UTC), while the character counter sat frozen at **362,997/363,000** with
  `next_character_count_reset_unix` **already in the past** — so no reset had happened, and none may be
  reported as one. `elevenlabs-credit-check.py --probe` printed **"LANE OPEN — 14,253 bytes of MPEG
  audio" TWICE** on real 1-character syntheses; the next minute **every** lesson clip was refused:
  `401 {"type":"payment_required","code":"payment_issue","message":"Your subscription has a failed or
  incomplete payment. Complete the latest invoice to continue usage."}` — Latin and Thai, 1 and 37
  characters, both voices, three models. **So a passing probe is NOT the gate: in past_due a small
  request can slip through while every real render is refused**, and the counter hides the whole state.
  Read `status` from the same payload that carries the counter and refuse on a **deny-list**
  (`past_due`, `unpaid`, `suspended`, `blocked`, `canceled`, `restricted`) *before* spending a
  character — an unknown status must never stop a paid, working account. Then report the invoice
  instead of rendering silence. (Guard shipped in Arthur's `scripts/elevenlabs-credit-check.py`; the
  gentech/pixel/gizmo copies are drifted versions and do not carry it.)

## References

- `travel-planning/references/language-learning-plan.md` — dialect phonology, verified slang, pricing tiers.
- `09-Green Room/gentech-edu/life-based-lessons.md` (vault) — the mechanism, the corrected framing, the
  Dominican feature table, and the Agent-Kit placement.
