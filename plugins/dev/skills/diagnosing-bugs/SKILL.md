---
name: diagnosing-bugs
description: Diagnosis loop for hard bugs and performance regressions. Use when the user asks to debug something, or reports it broken or slow.
---

# Diagnosing Bugs

Run the phases in order; state the justification before skipping one.

When exploring the codebase, read `CONTEXT.md` (if it exists) to get a clear mental model of the relevant modules, and check ADRs in the area you're touching.

## Phase 1 — Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug — one that goes **red** on _this_ bug — you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it.

Spend disproportionate effort here, and be **relentless**.

### Ways to construct one — try them in roughly this order

1. **Failing test** at whatever seam reaches the bug — unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) — drives the UI, asserts on DOM/console/network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL bash script.** Last resort. If a human must click, copy `${CLAUDE_PLUGIN_ROOT}/skills/diagnosing-bugs/scripts/hitl-loop.template.sh`, edit its steps to drive _them_, and parse the `KEY=VALUE` output it prints back.

### Non-deterministic bugs

Raise the **reproduction rate** until the bug is debuggable: loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to whatever environment reproduces it, (b) a captured artifact (HAR file, log dump, core dump, screen recording with timestamps), or (c) permission to add temporary production instrumentation.

### Completion criterion — a tight loop that goes red

Phase 1 is done when you can name **one command** — a script path, a test invocation, a curl — that you have **already run at least once** (paste the invocation and its output), and that is:

- [ ] **Red-capable** — it drives the actual bug code path and asserts the **user's exact symptom**, so it goes red on this bug and green once fixed. Sharpen the assertion until it catches _this_ bug rather than merely running clean.
- [ ] **Deterministic** — same verdict every run. Pin time, seed RNG, isolate the filesystem, freeze the network. (Flaky bugs: the raised reproduction rate, above.)
- [ ] **Fast** — seconds, not minutes. Cache setup, skip unrelated init, narrow the scope.
- [ ] **Agent-runnable** — you can run it unattended; a human in the loop only via `${CLAUDE_PLUGIN_ROOT}/skills/diagnosing-bugs/scripts/hitl-loop.template.sh`.

If you catch yourself reading code to build a theory before this command exists, go back to building the loop. No red-capable command, no Phase 2.

## Phase 2 — Reproduce + minimise

Run the loop and watch it go **red**. Confirm:

- [ ] The loop produces the failure mode the **user** described, rather than a different failure that happens to be nearby.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut.

Done when **every remaining element is load-bearing** — removing any one of them makes the loop go green.

## Phase 3 — Hypothesise

Generate **3–5 ranked hypotheses** before testing any of them.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe — discard or sharpen it.

**Show the ranked list to the user before testing.** They often re-rank it instantly ("we just deployed a change to #3") or name hypotheses they have already ruled out. Proceed with your own ranking if the user is AFK.

## Phase 4 — Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the env supports it.
2. **Targeted logs** at the boundaries that distinguish hypotheses.

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`, so Phase 6 cleanup is a single grep.

**Perf branch.** For performance regressions, measure before you change anything: establish a baseline (timing harness, `performance.now()`, profiler, query plan), then bisect.

Done when **every Phase 3 hypothesis is confirmed or eliminated** by a probe. If all of them are eliminated, return to Phase 3 with what the probes taught you.

## Phase 5 — Fix + regression test

Write the regression test **before the fix** — but only if there is a **correct seam** for it.

A correct seam is one where the test exercises the **real bug pattern** as it occurs at the call site. A seam that is too shallow (single-caller test when the bug needs multiple callers, unit test that can't replicate the chain that triggered the bug) gives false confidence.

**If no correct seam exists, that itself is the finding** — the architecture is preventing the bug from being locked down. Note it for Phase 6.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 loop against the original, un-minimised scenario.

## Phase 6 — Cleanup + post-mortem

Required before declaring done:

- [ ] The original repro goes **green**
- [ ] Regression test passes (or absence of a correct seam is documented)
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug location)
- [ ] The hypothesis that turned out correct is stated in the commit / PR message

**Then ask: what would have prevented this bug?** If the answer involves architectural change (no good test seam, tangled callers, hidden coupling), recommend the user run `/dev:improve-codebase-architecture`, and give them the specifics to paste in.
