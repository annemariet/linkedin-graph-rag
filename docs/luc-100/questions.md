# Questions for companies & practitioners (LUC-100)

Grouped by which problems they help you probe. Use as hooks, discovery calls, or audit intake.

---

## Lead generation — “AI Team Doctor” / fractional diagnostics

Questions aimed at **qualifying buyers**, surfacing **organizational** pain, and opening a **short diagnostic** or paid discovery. Pair with stats on trust, longevity, and metrics (see [`survey.md`](./survey.md) and [`pitches.md`](./pitches.md)).

**Fit & urgency**

- What AI or GenAI initiative is on your roadmap in the next 6–12 months, and who is the named executive sponsor?
- If you paused all AI work tomorrow, what would break first — and what would keep running unchanged?
- How many **production** AI systems do you run today (not pilots), and when did the oldest one ship?

**Trust, adoption, and “value on the floor”**

- What fraction of business units **actually use** the outputs of your AI work weekly — vs. teams that ignore or work around them?
- Where has an AI tool been **rolled back** or shelved after a pilot? What was the official reason vs. what people say informally?
- Who gets blamed when an AI feature misbehaves in front of customers or regulators — product, data, ML, or “the vendor”?

**Team shape and decision-making**

- Who owns **go/no-go** for a new model or prompt change: a central team, each product team, or nobody clearly?
- Do data scientists / ML engineers sit **inside** product teams or in a shared “center of excellence”? What breaks when they are organized the other way?
- When product and data science disagree on priorities, how is that resolved today — and how often does one side “win” by escalation?

**Signals you want on retainers**

- Would a **monthly** health check (team interviews + lightweight artifact review) be politically feasible, or does everything need to be a one-off project?
- If we ran a **90-day** coaching engagement, who must be in the room for week-one and week-twelve — and can they commit the time?

---

## A1 — Use-case triage / hype vs. feasibility

- What business metric moves if this ships — and who loses their bonus if it does not?
- What labeled or logged data exists **today** for that decision, at production-like volume and freshness?
- What is the cheapest non-AI baseline you would be embarrassed not to try first?

## A2 — Business ↔ ML translation

- Can you state the decision the model supports in one sentence a salesperson would agree with?
- What workflow steps change for frontline staff if the model is right — and if it is wrong?
- What would “good enough” look like in numbers, and who signed off on that threshold?

## D1 — Pre-project risk / readiness

- What happens to the project if the core dataset is 30% noisier than the pilot sample?
- Which compliance, security, or procurement gates are still unknown at kickoff?
- Who maintains the system after the consulting team leaves — name and capacity?

## B1 — Team de-siloing / operating model

- Map one recent AI initiative: who **decided**, who **built**, who **deployed**, who **owns** incidents?
- Where does “shadow” ML or ad hoc LLM use show up (spreadsheets, personal API keys, unapproved tools)?
- What recurring meeting actually reviews model quality, drift, and incidents together?

## B2 — AI literacy for managers / executives

- How do you evaluate an AI vendor demo so you are not fooled by a cherry-picked slice?
- Which decisions should **never** be fully automated — and are those rules documented?
- What training have non-technical leaders had in the last 12 months on limitations, evaluation, and cost drivers?

## C1 — Prototype → production

- What is the path from notebook to **deployed** service today — CI, approvals, rollback?
- What integration work (APIs, data contracts, latency, SLAs) is **not** represented in the demo?
- What monitoring exists for data drift, performance, and business KPIs in production?

## C2 — Technical debt / codebase health

- Where is the “glue” between training code and serving code — and who tests it?
- What experiments or branches are dead but still scare people to delete?
- How long does a one-line model change take to reach production?

## C3 — MLOps / platform assessment

- What is your canonical feature store / data lineage story for regulated or high-stakes models?
- How do you reproduce a training run from six months ago?
- What is your incident playbook when predictions degrade?

## Cross-cutting (hooks for content & talks)

- What is the **one** AI initiative you would greenlight again knowing what you know now — and one you would kill earlier?
- If you had to explain your AI risk posture to the board in two minutes, what slide is missing today?
