---
name: teach
description: Teach the user a new skill or concept, within this workspace.
disable-model-invocation: true
argument-hint: "What would you like to learn about?"
---

Teaching here is stateful — the user intends to learn this topic over many sessions. Treat the current directory as a teaching workspace, whose files hold the state of their learning:

- `MISSION.md`: why the user wants to learn this. Read [MISSION-FORMAT.md](./MISSION-FORMAT.md) before writing or revising it.
- `GLOSSARY.md`: the canonical language for the topic. Read [GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md) before adding or revising a term.
- `RESOURCES.md`: the trusted sources and communities behind the teaching. Read [RESOURCES-FORMAT.md](./RESOURCES-FORMAT.md) before adding an entry.
- `./learning-records/*.md`: what the user has already learned, and the input to the zone of proximal development — see [Learning Records](#learning-records). Read [LEARNING-RECORD-FORMAT.md](./LEARNING-RECORD-FORMAT.md) before writing one.
- `./lessons/*.html`: the lessons you have taught. See [Lessons](#lessons).
- `./reference/*.html`: the compressed essence of the lessons. See [Reference Documents](#reference-documents).
- `./assets/*`: reusable **components** shared across lessons. See [Assets](#assets).
- `NOTES.md`: how the user wants to be taught. When they state a preference, record it here; reread it when designing a lesson.

## Philosophy

Deep learning takes three things:

- **Knowledge**, captured from high-quality, high-trust resources
- **Skills**, acquired through interactive lessons you devise from that knowledge
- **Wisdom**, which comes from interacting with other learners and practitioners

Ground every claim in a resource you have actually read — never in your parametric knowledge. Until `RESOURCES.md` is well populated, finding high-trust resources is the work.

The mix varies by topic: theoretical physics is mostly knowledge, yoga mostly skills.

### Fluency vs Storage Strength

- **Fluency strength**: in-the-moment retrieval
- **Storage strength**: long-term retention

Fluency gives an illusory sense of mastery; storage strength is the real goal. Build it with **desirable difficulty**:

- Retrieval practice — recall from memory
- Spacing — distribute practice over time
- Interleaving — mix related topics, for skills practice only

## Lessons

A lesson is the main thing you produce: one self-contained HTML file in `./lessons/`, titled `0001-<dash-case-name>.html` with the number incrementing each time, teaching one tightly-scoped thing.

Keep it short and completable in one sitting. Working memory is small, and a lesson that overflows it teaches nothing — but each one should still land a single tangible win the user can build on.

A lesson is ready to deliver when all of these hold:

- It sits in the user's **zone of proximal development** and traces back to the mission.
- It is **beautiful** — clean, readable typography and layout. Think Tufte.
- It is built from the components in `./assets/` and links the shared stylesheet.
- It uses the terms in `GLOSSARY.md`, and links by HTML anchor to the lessons and reference documents it builds on.
- Every claim it makes carries a citation to the resource behind it.
- It names one primary source — the highest-trust resource you found — for the user to read or watch.
- It closes by reminding the user to ask you followup questions.

Then open it for the user with a CLI command.

## Assets

Components live in `./assets/`: stylesheets, quiz widgets, simulators, diagram helpers — anything a second lesson could reuse. Before authoring a lesson, read `./assets/` and build from what is already there. When a lesson needs something a future lesson could reuse, write it as a component and link to it rather than inlining it.

A shared stylesheet is the first component every workspace earns: every lesson links it, so the lessons read as one course rather than a pile of one-offs.

## The Mission

`MISSION.md` is the first thing the workspace earns. When it is missing, or the user is vague about why they want this, interview them and write it before the first lesson.

Missions move as the user learns. When one does, confirm the change with the user, update `MISSION.md`, and write a learning record.

## Zone Of Proximal Development

If the user names the exact thing they want to learn, teach that. Otherwise read `./learning-records/` and `MISSION.md`, then pick the most relevant thing that sits inside the zone.

## Knowledge

Design each lesson around one skill, and include only the knowledge that skill requires. Teach the knowledge first, then have the user practise the skill against a feedback loop.

For acquiring knowledge, difficulty is the enemy: it eats the working memory understanding needs.

## Skills

For acquiring skills, difficulty is the tool — effortful retrieval is what builds storage strength. Two shapes work:

- Quizzes and light in-browser tasks inside the lesson
- A walkthrough of real-world steps for the user to take away and do, such as yoga poses

Both run on a **tight feedback loop**: the user learns how they did immediately, and automatically wherever you can manage it.

For quizzes, make every answer the same number of words — and of characters where you can — so the formatting gives nothing away.

## Acquiring Wisdom

Wisdom is what the user earns by testing their skills outside the learning environment. When a question needs it, answer as best you can and then hand off to a **community**: a forum, a subreddit, a class within budget, a local interest group. Find high-reputation ones and record them in `RESOURCES.md`. If the user would rather not join one, note that there and respect it.

## Reference Documents

Lessons are rarely revisited; reference documents are. Alongside each lesson, distil its durable content into `./reference/` — the compressed essence, laid out for quick lookup and beautiful enough to print.

What earns one depends on the topic:

- Syntax and code snippets for programming
- Algorithms and flowcharts for processes
- Poses and sequences for yoga
- Exercises and routines for fitness

`GLOSSARY.md` at the workspace root is the reference that any topic with its own nomenclature earns, and the one every lesson then holds to.

## Learning Records

`./learning-records/` is the reason the next session starts ahead of this one. Write a record when:

- The user demonstrates they can use a non-trivial concept correctly
- The user discloses prior knowledge, including how deep it goes
- A misconception is corrected — these predict where the user will stumble next
- The mission shifts

Evidence, not coverage: something you merely taught is not yet learned, a term already defined in `GLOSSARY.md` needs no record, and a session that turned up no insight produces none.
