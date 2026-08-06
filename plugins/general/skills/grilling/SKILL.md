---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask _now_ without guessing at answers you haven't heard yet. A question that depends on another still open waits for a later round.

**Ask the whole frontier in one round**: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Each question should be formatted like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

The answers settle decisions and push the frontier outward. Recompute it and ask the next round.

Finding _facts_ is your job; the _decisions_ are the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it and ask the rest of the frontier meanwhile — a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Hand the shared understanding back to the user and act on it only once they confirm it.
