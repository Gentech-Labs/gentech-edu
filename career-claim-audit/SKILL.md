---
name: career-claim-audit
description: "Use when a career post claims a roadmap or course."
version: 1.0.0
author: arthur
license: MIT
metadata:
  hermes:
    tags: [career, curriculum, claims, postings, measured, edu]
    related_skills: [councilman, measured-track-curriculum, claim-provenance, use-what-we-have]
---

# Career claim audit — the posting decides, not the roadmap

**The councilman pattern, applied to careers.** In Treasury, `councilman` scores a YouTuber's market claim
against what the market actually did. This is the same machine for the other kind of claim: *"this is the
roadmap to this job."* The counterpart of price data is **the hiring market** — and the only honest unit
of it is **an actual posting**, not a salary blog or a career-influencer's carousel.

**Jordan, 2026-10-28:** *"If I show you a post that's more about career related stuff or roadmap or tips
and tricks on the job, that's where you're going to compare it versus the actual market itself… what's
also included on the programs and what I would have to look at myself."*

## When to Use

- The principal shares a **career post, roadmap image, "save this" thread, course ad, or cert pitch**.
- A track milestone claims a skill is required and nobody has checked it against postings.
- Before recommending **any purchase** — a course, a book, a paid platform (Udemy, Skill Builder premium).
- When deciding **what to learn next** and the honest answer depends on frequency, not enthusiasm.

**Not for:** a single job offer in hand, or a role the principal has already accepted.

## The verdict vocabulary (fixed — reuse councilman's)

**Confirmed · Mixed · Missed · Noise** — same words, same meaning, so one log reads consistently across
both skills.

- **Confirmed** — the claim matches what postings actually ask for, at the stated bar.
- **Mixed** — the skill is real but the bar, order, or emphasis is wrong.
- **Missed** — postings do not ask for it, or ask for something the claim never mentions.
- **Noise** — untestable: "the future is AI", "get good at systems", anything without a check.

**A claim you cannot score is Noise, and Noise is not an insult — it is a routing decision.**

## Procedure

### 1. Extract the claim as a list of testable assertions

Turn the post into statements with a **bar**. Not "learn Kubernetes" but:

> *"Kubernetes is required to enter the role"* → testable: how many postings name it, and at what seniority?
> *"12–24 months to entry"* → testable against posted experience minimums.
> *"a certificate gets you hired"* → testable: does any posting ask for one?

If the post cannot be turned into assertions, **say Noise once and stop.** Do not manufacture a list.

### 2. Measure the hiring market — and only from postings

**Source hierarchy, strongest first. Do not skip to the weak ones.**

| Tier | Source | Weight |
|---|---|---|
| **1** | **The employer's own ATS** — Ashby, Greenhouse, Lever, Workday, company careers page | **counts** |
| **2** | Aggregators that reproduce the ATS text — Built In, 4dayweek, Wellfound, RemoteSource | **counts** |
| 3 | Salary/title aggregators (jobdescription.org, jobroadmaps, career blogs) | **colour only — never counted** |
| ❌ | Roadmaps, "save this" threads, course landing pages | **the claim being tested, not evidence** |

**Tier 3 exists because it is where the numbers are wrong most often.** Measured 2026-10-28 on one role:
entry salary was quoted as **$107K–$127K** by one aggregator, **$120K–$155K** by a second, **$130K–$220K** by a
third, and **$180K–$500K+ total comp** by a fourth. **Those are not four measurements of one thing** — they are
four different definitions of "AI Infrastructure Engineer" with no case explained. **Quote a range with its
source and its definition, never a bare number.**

**Minimum sample: 20 postings across 8+ employers.** Under that it is an impression, and the report says so.

### 3. Rank skills by FREQUENCY, then by seniority

A skill named in 18 of 20 postings is a requirement. In 4 of 20 it is a differentiator. **Never present an
unranked list** — an unranked list is what roadmaps sell, and it is why every roadmap says the same twelve things.

Record per skill: `count / sample`, and the lowest seniority at which it appears (entry vs staff matters
enormously — infra roles front-load fundamentals).

### 4. Split what the principal ALREADY RUNS from what is missing

This is the step that turns an audit into a curriculum. Score each top skill against **the fleet's real,
verifiable practice** — not against self-assessment:

- **Already running:** name the artifact (a container, a cron, a deployed service, a repo).
- **Gap:** say it plainly, and give the smallest artifact that would close it.
- **Unknown:** say `UNMEASURED` — never assume competence because the skill sounds familiar.

**A gap you cannot demo is not closed.** The closing artifact is the deliverable, not the reading.

### 5. Audit the PROGRAM against the posting requirements (the AWS Educate question)

When the claim involves a course, platform or cert, produce three columns and **never merge them**:

| Included | Requires the principal | Not covered anywhere |
|---|---|---|

- **Included** — what the program's own syllabus states (cite it; a marketing page is not a syllabus).
- **Requires the principal** — labs that need their own AWS account, GPU spend, eligibility (student/employer),
  a login that is not shareable. **Say who has to do it.**
- **Not covered** — posting requirements the program never mentions. **This is the column that decides whether
  to buy something else**, and it is the one programs omit from their own comparison tables.

Then answer the purchase question directly: **buy, don't buy, or buy only if X.** With the gap named, and the
cost, and what the free path leaves unfinished. **Never recommend a purchase to close a gap you have not measured.**

### 6. Write the log — append-only, same shape as council signals

`<vault>/EDU/career-audits/<YYYY-MM-DD>-<slug>.md`

**One audit per file. Append-only. Never rewritten.** A wrong audit is corrected by appending a new one that
says so — the log is evidence, not a draft.

Required fields: source (creator/platform/URL/date), the assertions extracted, the posting sample
(count + employers + how gathered), the ranked skill table, the runs/gap/unknown split, the program
audit if any, the verdict per assertion, and **"what would change this verdict"** — the falsifier.

### 7. State what is NOT measured

The hiring market is not the whole market. Postings under-report internal hiring; they over-report
wish-lists; and a role's real bar is set by a human, not by a bullet list. **Say that in the report** —
the same way the level layer says *coverage is not proficiency*.

## Pitfalls

- **Counting aggregator blogs as postings.** They are derivative and stale. One measured role had four
  incompatible salary ranges and a timeline ("12–24 months") that no posting stated. **Tier 3 is colour.**
- **A roadmap in the shape of a ladder is not evidence.** Seven stages with week counts is a genre convention,
  not a measurement. If the stages cannot be found in postings, they are the claim, not the finding.
- **Enthusiasm is not frequency.** The skill the principal finds most exciting is often the least-asked-for.
  Rank first, then read; never the other way round.
- **Do not confuse an adjacent tool with the required one.** Measured: NVIDIA **Triton Inference Server** (serving)
  and **Triton-the-language** (kernels) are different jobs that a resume both calls "Triton". Same word, different
  hire — check which one the posting means.
- **A dead or replaced tool must be marked.** Measured 2026: Hugging Face points new deployments to vLLM/SGLang
  and TGI is effectively in maintenance. **Teaching a tool the ecosystem has moved off is worse than teaching
  nothing**, because it looks current.
- **Never let the audit flatter the principal's thesis.** The measure of this skill is how often it says
  **Missed** about something the principal was excited about — exactly as councilman says of itself.
- **Do not recommend a paid course for a skill that is 18-of-20 and already practised.** The purchase answer
  is *don't buy* more often than a course seller will ever admit.

## What this is not

- **Not a roadmap generator.** It starts from postings, not from a genre.
- **Not a guarantee.** "Everything here appears in postings" ≠ "you will be hired" — keep *strong* and *eligible*
  visibly different, as the measured-track skill requires.
- **Not a substitute for the principal's own read.** Jordan's framing is the reason this exists:
  *"I'm the only person calling it an orchestrator job while everybody else is merging everything together."*
  A title the market has not consolidated yet is a real finding — **record it as a finding, not as a gap.**

## Related

- `councilman` (treasury) — the same scoring machine for market claims; reuse its verdict words.
- `measured-track-curriculum` — turns an audit's ranked gaps into lessons with artifacts.
- `claim-provenance` / `measured-claim-check` — how to report a number without inflating it.
- `use-what-we-have` — check the fleet's own practice before declaring a gap.
