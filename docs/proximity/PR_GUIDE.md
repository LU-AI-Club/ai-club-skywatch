# Proximity team — PR guide

Two halves: how to write one, and how to review one. Nate asked us to be
**super critical** of each other's PRs, so the second half matters as much as
the first. Critical means specific and about the code, never about the person.

## Branching

```
main
 └── Proximity_Detector          ← our team branch, one per detector
      ├── proximity/erik/interpolate
      ├── proximity/manni/geometry
      ├── proximity/calebg/pairs
      ├── proximity/calebk/rules
      └── proximity/paul/wiring
```

Your PR targets **`Proximity_Detector`**, not `main`. Paul merges the team
branch into `main` once the detector works end to end.

```bash
git checkout Proximity_Detector && git pull
git checkout -b proximity/<yourname>/<thing>
# ... work ...
git push -u origin proximity/<yourname>/<thing>
```

## Every PR contains three things

1. **The code** — one function (or two closely related ones). Nothing else.
2. **The tests passing** — the ones already written for your function, with the
   `@todo("YourName")` line deleted from each test you made pass.
3. **A markdown file in `docs/proximity/`** — copy `_TEMPLATE.md`, name it after
   your function.

## Writing a good PR description

```markdown
## What
One sentence: which function, what it now does.

## How
The approach in 2-4 bullets. Name the formula or the rule you followed.

## Proof it works
Paste the pytest output showing your tests green:
    pytest tests/air/detectors/proximity/test_proximity_<file>.py -q

## Decisions I made
Anything a reviewer might disagree with, and why you chose it.

## What I'm unsure about
Say it here. This is not a weakness — it tells the reviewer where to look.
```

## Reviewing: be critical, be specific

Work through this list. Leave a comment for every "no".

**Correctness**
- [ ] Does it do what the docstring says — all of it, not most of it?
- [ ] Units right? Knots vs m/s, feet vs metres, nm vs metres, degrees vs radians.
- [ ] Signs right? Negative `t_cpa` means diverging. Separation is never negative.
- [ ] Boundaries: `<` vs `<=`. Our tiers are strict `<` — 0.5 nm is NOT HIGH.
- [ ] What happens with `None` inputs? Missing fields must abstain, not crash.
- [ ] Empty list, single element, two identical items — handled?

**Purity (the playbook rule)**
- [ ] Same input always gives the same output.
- [ ] No file reads, no network, no globals, no printing.
- [ ] Does not mutate its arguments.

**Tests**
- [ ] Is there a positive case AND a benign/negative case?
- [ ] Did they delete the `@todo` lines for tests they now pass?
- [ ] Did they change a test to make it pass? If so, ask why — that is either a
      real bug in the test or a red flag.

**Thresholds and config**
- [ ] No number typed into the code that belongs in `proximity.yaml`.

**Governance**
- [ ] Nothing in an explanation string says "dangerous", "unsafe", "violation",
      "threat" or "intent". We state distance, altitude gap and time.
- [ ] Nothing computes Trust — that is TCE/CAATS's job.

**Docs**
- [ ] `docs/proximity/<function>.md` present and actually readable.
- [ ] The "what it does NOT handle" section is filled in honestly.

**Before approving**
- [ ] `pytest -q` is green on the whole repo, not just their file.

## How to word a critical comment

Aim for: *what you saw → why it matters → what to do.*

- Good: "`velocity_xy(100, 90)` returns `vy = 6.1e-15`, not 0. Floating point,
  so the test should use `pytest.approx(0, abs=1e-6)` rather than `== 0`."
- Good: "This drops pairs where altitude is `None`, but the docstring says
  abstain — which is the same outcome here, so it's fine. Worth a comment
  saying so, because the next reader will wonder."
- Not useful: "this is wrong", "clean this up", "looks good to me".

Approving a PR means you believe it is correct. If you are not sure, say what
you are not sure about instead of approving.
