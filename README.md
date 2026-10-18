# GenTech EDU — the learning engine and its packs

**Jordan, 2026-09-23:** *"why don't we rename it to EDU? So I'll say, hey, Jintek, activate EDU and then
I'll describe what I want."*

**Jordan, 2026-10-18:** *"there should also be a repo for the Gintech EDU… can you create that repo for us?
Talk to GinTech about which repo to actually put that on."*

---

## What this is

EDU is the engine under every "learn something from your own material" scenario. Language was the first
pack, not the product.

> *"the idea for the GenTech EDU was if you want to learn something you can just give us info and we'll
> create scenarios that help you learn and you get engaged because it's something that you care about."*

## The two lanes

| Lane | What it does |
|---|---|
| **Lane 1 — engineered teaching** | The engine, the packs, the sessions. Sequenced scenarios built from the learner's own corpus (an itinerary, a menu, a portfolio). |
| **Lane 2 — the fleet's own incidents as case studies** | `data/scenario-shapes.json` + the `gentech-watch` pack: our own failures become the teaching material. |

## Where the truth lives — READ THIS BEFORE EDITING

**This repository is a published MIRROR, not the source of truth.**

- **Source of truth (CORE):** `10-Labs/skills-distribution/edu/` inside the GenTech vault.
- **Direction:** one-way out. CORE → repo. Seats sync from the CORE, never from here.
- **Why the direction is declared:** a second copy with no declared direction is exactly how `skills/edu/`
  inside `genTech-agent-skills` went **two days stale** and stayed there — silently teaching a wrong voice.
  Never fix a bug here first; fix it in the CORE and re-publish.

### Publish (run from a CORE checkout)

```bash
rsync -a --delete --exclude learners.json --exclude __pycache__ \
  "/opt/data/.obsidian-vault/10-Labs/skills-distribution/edu/" <this-repo>/
# then commit + push
```

## What is deliberately NOT published here

| Excluded | Why |
|---|---|
| `data/learners.json` | The learner registry — **names real people** (Jordan; Josephine B, his partner) with relationship and first-language notes. Personal data. |
| `EDU/learners/*.md`, `EDU/lessons/<learner>/` | Per-learner progress and lesson records. Shared engine, **separate progress** — a public repo plus personal records is a privacy call, and it was made: keep them out. |

The engine is generic: a learner is an entry in a pack file, not a branch in the code. So excluding the
registry loses nothing that belongs in public.

## Layout

```
SKILL.md              the engine contract — activation, the engine/pack boundary, the honesty rules
scripts/
  life-lesson-engine.py   the engine (sequencing, mastery, honesty checks)
  life-lesson-level.py    level + dialect resolution
  life-lesson-scenario.py scenario construction
  life-lesson-audio.py    voice rendering (per-form native voices; never one voice for all)
  fde-lesson.py           the FDE track
  edu_apps.py             travel-app pack reader
  make-pronunciation.py   pronunciation bridge (generated, never hand-typed)
data/                 the PACK data — a subject is a file here, not a code change
  voices.json             which native voice speaks which dialect, per learner FORM
  level-targets.json      the level caps (a survival set is capped on purpose)
  trip-priority.json      which trip is being taught
  scenario-shapes.json    the scenario templates
  fde-track.json          forward-deployed-engineer track (measured against real postings)
  travel-apps.json travel-venues.json  the corpus for the Thailand pack
  pronunciation-th.json   generated Thai romanization
```

## Honesty rules (they are the product, not decoration)

- **UNMEASURED is not 0%.** A number nobody measured is reported as unmeasured.
- **Coverage is not proficiency.** Completions are counted, mastery is earned.
- **A native voice per form, never Roger.** A multilingual voice that *can* pronounce Thai is still an
  English speaker pronouncing Thai — the learner copies the accent and unlearns it at cost.
- **An unknown learner is an error, not a permission** — a hard stop, never a warning, because a warning
  gets scrolled past at 3am in a cron log.

## Provenance

- Published from the CORE at `10-Labs/skills-distribution/edu/` (engine 776 lines at publish time).
- Supersedes the stale `skills/edu/` copy that was buried inside `genTech-agent-skills`
  (engine 426 lines, and carrying the American voice wired to `th-TH`). That copy is retired.
- Owned by **Arthur** (the GenTech EDU seat).
