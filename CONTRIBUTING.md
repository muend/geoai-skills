# Contributing

Contributions are welcome — new skills, fixes to existing ones, better evals,
and real-world failure reports all count.

## Ground rules

1. **One skill = one folder** under `skills/`, named in kebab-case, containing
   `SKILL.md` and optionally `scripts/`, `references/`, `assets/`, `evals/`.
2. **Frontmatter** must pass `python tools/validate_skills.py`:
   `name` (kebab-case, identical to the folder name, ≤ 64 chars, no
   "claude"/"anthropic"), `description` (what it does AND when to trigger,
   ≤ 1024 chars — aim for 400–700), plus `license` and `metadata.version`.
3. **Progressive disclosure.** Keep `SKILL.md` under ~200 lines. Long tables,
   reference material, and code > 15 lines belong in `references/` and
   `scripts/`, linked from the body. Unloaded files cost zero tokens.
4. **No duplication.** If a rule already has a canonical home (e.g. spatial
   cross-validation lives in
   `skills/ml-experiment-standards/references/spatial-cv-protocol.md`),
   link to it — do not restate it.
5. **Evals required.** Every new or changed skill ships `evals/evals.json`
   with ≥ 3 scenarios: a realistic prompt plus the expected behaviors.
6. **English, universal scope.** Locale-specific pitfalls are welcome as
   i18n notes, not as the skill's frame.
7. **Verification culture.** Every skill ends with a verification protocol
   and a pitfalls checklist. Spatial work fails silently; a stage without a
   check is not a stage.

## Workflow

```bash
git checkout -b feat/my-skill
# ... add skills/my-skill/...
python tools/validate_skills.py   # must pass with 0 errors
```

Open a PR describing: what the skill covers, why it is not overlap with an
existing skill, and one real task where it changed the outcome.

## Testing a skill for real

Use the two-session loop: in session A, write/edit the skill. In a fresh
session B, run one of its evals as a real task and note where the agent
stumbles. Feed that observation back into A. One loop minimum before a PR.

## Reporting a catch

If a skill caught a real bug (wrong CRS, leaked split, phantom change...),
add a privacy-safe, reproducible entry to `CASE_STUDIES.md`. Link the input or
a minimal synthetic reproducer, the before/after behavior, and the verification
result. Do not present illustrative or unverified examples as real catches.
