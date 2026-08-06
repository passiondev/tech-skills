---
name: onboard
description: Name the two or three skills that fit someone's actual job. Use when a person is new to the Passion tech skills, asks what is available, or asks which skill to use for something.
argument-hint: "What do you do day-to-day?"
---

Leave them with two or three skills they will actually type this week.

The failure mode here is enthusiasm. The full roster is not an introduction — it
is a reason to close the picker. Three skills tied to work they described this
morning will stick.

## Step 1 — Ask, then stop

Ask these three, **one message, numbered**, and wait for all three answers:

1. What's your role, and which team — Global Engineering, Local Engineering, Ops, Analytics, or Service and Support?
2. What did you spend the most time on last week?
3. Is there a part of it you'd hand off if you could?

Hold every recommendation until answer 3 lands, even when answer 2 obviously
matches a skill. Answer 3 is the one they have to think about, and it is what
makes the recommendation land.

A brief answer ("engineer, tickets, meetings") is enough — work with it. If they
skip the questions and want the list instead, give them the two **everyone**
skills below, then answer at plugin level — one line per plugin — and point at
[the README](https://github.com/passiondev/tech-skills/blob/main/README.md),
which lists every skill under the plugin it comes from.

## Step 2 — Confirm what they have

```bash
claude plugin list
```

If nothing Passion-shaped is listed, they are not set up — send them to
[`ONBOARDING.md`](https://github.com/passiondev/tech-skills/blob/main/ONBOARDING.md)
and stop. Otherwise carry the installed plugin names into step 3.

## Step 3 — Name two or three, then stop

Rank by what they said in step 1; filter to what step 2 listed as installed. A
Local Engineer who spends their week in Rock should hear about `/rock:find`
before `/dev:tdd`.

**Everyone, regardless of role** — lead with whichever of these two fits:

| Skill | When it earns its place |
| --- | --- |
| `/jira:sprint` | They opened Jira to check their own queue |
| `/jira:ticket` | They pasted a ticket key to someone, or worked from one |

**Then one or two more, matched to the answer:**

| They said | Offer | Why it fits |
| --- | --- | --- |
| "I write code" | `/dev:tdd`, `/dev:code-review` | The two that change daily habit rather than adding a step |
| "I debug things" | `/dev:diagnosing-bugs` | Follows the evidence instead of guessing at a fix |
| "I look people up in Rock" | `/rock:find`, `/rock:inspect` | Search, then the full record |
| "Rock workflows break" | `/rock:status`, `/rock-build:audit` | Check the connection, then find what is broken |
| "I pull reports and numbers" | `/rock:data` | Dataviews, reports, attendance |
| "I write the spec / the ticket" | `/plan:to-spec`, `/plan:to-tickets` | Turns a conversation into something someone can pick up |
| "I get vague requests" | `/plan:triage` | Verifies the claim before anyone builds |
| "I have to decide something" | `/general:grill-me` | Questions them until the decision is actually made |
| "I write the docs / the release notes" | `/general:to-ste` | Rewrites it as Simplified Technical English, then lints to show the score dropped |
| "I write things people read" | `/general:humanize` | Strips the AI cadence out of a draft and keeps their voice |
| "I'm learning X" | `/general:teach` | A workspace that persists across sessions |

Give **one sentence and the exact thing to type** for each. Describe a skill
from its `SKILL.md`, reading it first whenever you are less than certain what it
does. If they lit up at question 3, tie the skill to that answer explicitly:
"you said you'd hand off writing the tickets — that's `/plan:to-tickets`."

## Step 4 — Two facts, then get out of the way

- Skills fire on their own when they fit. Typing `/<plugin>:<skill>` forces one.
- Everything updates itself — nothing to pull, and a skill can change under them.

Then offer to run one **right now** on something real they mentioned. A skill
used once in the conversation that introduced it is worth more than the whole
roster described perfectly.
