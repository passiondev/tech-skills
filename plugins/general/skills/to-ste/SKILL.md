---
name: to-ste
description: De-slop prose into ASD-STE100 Simplified Technical English, then lint to prove the score dropped. Use when the user asks to de-slop a draft, and before another skill delivers technical writing with no byline: a ticket, spec, ADR, review, or report. STE strips voice on purpose, so a draft that carries a byline goes to /general:humanize instead.
---

# To STE

Slop is a problem of **form**, not of content. This skill fixes the form, and it cannot make a hollow paragraph true. STE strips voice on purpose, so it suits writing with no **byline**: the reader acts on the text and never asks who wrote it. A draft that a named person signs keeps its voice, and `/general:humanize` is the skill for that one.

## Process

### 1. Take the target and its exempt spans

- **From a calling skill.** A draft the caller holds in context, not yet written anywhere. The caller may name the mode and the spans to exempt: quoted hunks, snippets, a user-story frame.
- **From a person.** A file path, an issue reference, or text pasted into the conversation. Read the whole source.

Fenced code, inline code, identifiers, and command syntax are exempt on every run. Copy every exempt span through untouched.

### 2. Pick a mode

Route on what the reader does with the text.

- **strict.** The reader executes it: procedures, runbooks, acceptance criteria, error messages, safety text. Apply every rule and both length caps.
- **flavored.** The reader reads it: tickets, specs, ADRs, code reviews, research reports, READMEs, PR descriptions, release notes, comments. Apply the sentence, paragraph, active-voice, and phrasal-verb discipline, and keep richer vocabulary so the text reads naturally. The banned words still go.

A document that mixes the two takes strict on its executable parts and flavored on the rest. State the mode you picked. A mode named by the caller or the user wins.

### 3. Rewrite against the rules

WORDS

- One name for one thing, held across the whole document.
- One meaning per word: `fall` means to move down, not to decrease.
- The short common word: start, use, help, make sure, before, after, about, get, show, also.
- Adjectives that measure, not adjectives that sell.
- American spelling.

VERBS

- Active voice: `the parser reads the file`, not `the file is read by the parser`.
- A verb for an action: analyze the log, not `perform an analysis of the log`.
- One plain verb where a phrasal verb tempts: start, not `kick off`.
- State the claim in one clause: `this improves X`, not `it is important to note that this may help to improve X`.
- Simple tense for a main verb, in place of the `-ing` form.

SENTENCES

- One instruction per sentence. Max 20 words for an instruction, max 25 for a descriptive sentence.
- Full forms in place of contractions. Keep the articles: a, an, the, this, these.

PUNCTUATION

- A period where a semicolon would go.
- Remove em dashes and en dashes. STE allows them, but the em dash is the top slop marker.

STRUCTURE

- One topic per paragraph, max six sentences. For steps, a numbered vertical list, one action per item, imperative form. A condition comes before its command.

### 4. Lint to prove it

The linter sits in the `scripts/` folder beside this file. `${CLAUDE_PLUGIN_ROOT}` holds the plugin root at runtime, so the path below resolves from any working directory. Python 3 is all it needs. Piped stdin returns the per-category JSON. File paths as arguments return one summary line each.

```
python3 "${CLAUDE_PLUGIN_ROOT}/skills/to-ste/scripts/ste-lint.py" < original.md   # per-category JSON
python3 "${CLAUDE_PLUGIN_ROOT}/skills/to-ste/scripts/ste-lint.py" < rewrite.md
```

Lint the original and the rewrite. For a draft held in context, write each version to a scratch file and lint that. Counts are violations per 100 words, so the **delta** between original and rewrite is the signal.

- **strict.** Every category at 0, `em_dash` at 0, `longest_sentence_words` at 20 or less.
- **flavored.** Every category at 0 except `long_sentence(>20w)`, which may keep a few descriptive sentences of 21 to 25 words. `em_dash` at 0. No instruction runs over 20 words.

When a count holds above zero, `sample_banned` and `sample_marketing` name the offenders, and the category name says where to look. Fix and lint again. Done when the thresholds for the mode hold and the rewrite scores below the original on `total_per100w`.

### 5. Deliver

- **To a calling skill.** Return the converted text as the draft, plus before and after `total_per100w` on one line. The caller decides where it lands.
- **To a person.** Show the converted text with before and after `total_per100w` and `em_dash`. Write it back to the source file when the user asks for that.

## Credits

Distilled from **ASD-STE100 Simplified Technical English**, the free standard at https://asd-ste100.org. The standard carries a copyright, so quote fragments rather than the dictionary in full. Skill and linter adapted from woosal1337, "The cure for AI slop is a 1986 aircraft manual" (`blog/videos/ep01-the-cure-for-ai-slop`). The linter is a heuristic subset, not a certified STE checker.
