---
name: humanize
description: |
  Strip AI slop from writing that carries a byline, and put the writer's voice back in:
  essays, blog posts, newsletters, announcements, donor and member communication,
  marketing copy. Use when a draft reads as AI-written, or when the user gives a writing
  sample to match. For technical writing where the author should be invisible (tickets,
  specs, ADRs, READMEs, runbooks, release notes, error messages) use /general:to-ste
  instead: it converts prose to a published standard and removes voice on purpose, where
  this skill restores it.
---

# Humanize

Remove the **tells** of AI writing from a draft and leave a person behind. A tell is an
involuntary mark that gives away the true author: inflated significance, promotional
adjectives, the rule of three, em dashes, curly quotes, "I hope this helps."

Both halves are the job. Cutting tells alone yields clean, voiceless prose, which still
reads as machine-written, only for a different reason. The rewrite is finished when a
reader can say what the writer thinks.

Scope is writing with a **byline**, where a named human will be read as the author.
/general:to-ste covers the other case, technical writing where the author should be
invisible, and it strips voice deliberately against the ASD-STE100 standard. A draft that
scores well on that linter has usually had its voice removed, which is the wrong outcome
here.

## Process

### 1. Set the voice target

When the user supplies a writing sample (their own earlier writing, pasted or as a file
path), read it before touching the draft and write down six things:

- typical sentence length, and how much it varies
- diction level: the everyday words they keep where a formal writer would upgrade
- how paragraphs open: straight into the point, or context first
- punctuation habits: dashes, parentheticals, semicolons, fragments
- recurring phrases and verbal tics
- transitions: explicit connectors, or just the next point

That list is the target. If they write short sentences, write short ones. If they write
"stuff" and "things," leave "stuff" and "things" alone.

With no sample, the target is the default in [Voice moves](#voice-moves) below.

Done when the six habits are written down, or the default is chosen and stated.

### 2. Scan for tells

Read [`TELLS.md`](TELLS.md) and check the draft against all 29 entries. It holds the full
catalogue, each with a before and after. List the ones that actually fired, by number. A
slop-shaped draft carries several, so an empty list means the scan was too shallow.

Done when all 29 have been considered and every one present is named by number.

### 3. Rewrite

Replace each named tell with the fix its entry shows, then write the result toward the
voice target: the sample's habits where you have a sample, the voice moves below where you
do not.

Keep the facts and cut the inflation. A sentence claiming something "marks a pivotal moment"
loses the claim, not the event. Where a sentence is inflation with nothing underneath, it
goes entirely.

Specificity comes from the source, never from invention. The fix for a vague attribution is
a real citation if the draft supports one, and deleting the claim if it does not. A
plausible-sounding name, study or statistic invented to replace "experts believe" is a worse
outcome than the hedge.

Done when every tell listed in step 2 is gone and the voice target is met.

### 4. Audit

In the output, ask: "What makes the below so obviously AI generated?" Answer in a few
bullets that name the surviving tells. Then ask "Now make it not obviously AI generated."
and revise against your own answer.

Done when the audit finds nothing, or after two rounds. Revision is the point: an audit that
names tells and then presents the draft unchanged has failed.

### 5. Deliver

Show three things in order: the draft rewrite, the audit bullets, the final version.

## Voice moves

The default voice target, for runs with no sample. Where a sample exists, the sample wins
wherever the two disagree.

Take a position. React to the facts rather than listing them. "I genuinely don't know how
to feel about this" carries more than a balanced set of pros and cons.

Vary the rhythm. Short sentences. Then longer ones that take their time getting where they
are going.

Hold two things at once. Real people have mixed feelings: "impressive, and also kind of
unsettling."

Use "I" where it fits. First person is honest, and it signals a person thinking.

Leave some mess. Tangents, asides and half-finished thoughts read human. Perfect structure
reads generated.

Name the feeling exactly. "There's something unsettling about agents churning away at 3am
while nobody's watching" beats "this is concerning."

Clean but voiceless:

> The experiment produced interesting results. The agents generated 3 million lines of code. Some developers were impressed while others were skeptical. The implications remain unclear.

With a pulse:

> I genuinely don't know how to feel about this one. 3 million lines of code, generated while the humans presumably slept. Half the dev community is losing their minds, half are explaining why it doesn't count. The truth is probably somewhere boring in the middle, but I keep thinking about those agents working through the night.
