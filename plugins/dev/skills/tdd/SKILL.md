---
name: tdd
description: Test-driven development. Use when the user wants to build features or fix bugs test-first, or wants integration tests.
---

# Test-Driven Development

TDD is the red → green loop.

Read `CONTEXT.md` if the project has one, so test names and interface vocabulary match its domain language, and respect the ADRs covering the area you're touching.

## What a good test is

A good test reads like a specification: its name states a capability — "user can checkout with valid cart" — and its body exercises exactly that capability.

## Seams — where tests go

A **seam** is where a module's interface lives: the place you observe behavior without reaching inside.

**Test only at pre-agreed seams.** Before writing any test, list the seams under test — the critical paths and the complex logic — and confirm them with the user: "What's the public interface, and which seams should we test?"

When the shape of that interface is itself in question — how deep the module is, where the seam belongs, what the interface should expose — read `/dev:codebase-design` for the vocabulary, then come back to the loop.

## Anti-patterns

- **Implementation-coupled** — mocks an internal collaborator, tests a private method, asserts on call counts or call order, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed. Before mocking anything, read [mocking.md](mocking.md).
- **Tautological** — the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction. Take expected values from an independent source of truth — a known-good literal, a worked example, the spec.
- **Horizontal slicing** — all the tests written before any of the implementation, so they verify _imagined_ behavior. The tell: more than one failing test at a time.

When you are unsure whether a test you have written is one of these, check it against the pairs in [tests.md](tests.md).

## Rules of the loop

- **Red before green.** Write the test, run it, and watch it fail for the reason you expect. Then write only enough code to pass it.
- **One vertical slice per cycle.** One seam, one test, one minimal implementation — each test a **tracer bullet** aimed by what the last cycle taught you.
- **Refactoring is review work.** Take it to `/dev:code-review` after the loop.

A cycle is done when the new test is green, everything that was green still is, and none of the anti-patterns above fits the test you just wrote.
