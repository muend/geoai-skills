# Releasing GeoAI Skills

This runbook keeps a release candidate reproducible, installable, and separate
from the irreversible act of publishing it. It applies to the repository,
OpenAI and Claude plugin packages, individual skill ZIP files, Skills CLI, and
GitHub Copilot.

## Release invariants

- `pyproject.toml`, `.codex-plugin/plugin.json`,
  `.claude-plugin/plugin.json`, and `.claude-plugin/marketplace.json` must
  declare the same SemVer version.
- A version maps to one immutable source tree. Never rebuild different bytes
  under an existing tag or silently replace published assets.
- Generated archives stay under ignored `dist/`; they are never committed.
- Release packages contain runtime files and the MIT license, never evaluation
  runs, caches, credentials, development-only tools, or local planning files.
- Runtime source directories below `skills/` contain no `evals/` folders;
  repository installers recursively copy those directories into agent runtimes.
- A release remains blocked until automated validation and every applicable
  clean-install row below pass.

## 1. Local preflight

Run from a clean checkout of the candidate commit:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy tools/
python tools/validate_skills.py
python tools/validate_evals.py
python tools/check_links.py
python tools/build_split.py
python tools/check_regression_gates.py
python tools/build_openai_plugin_bundle.py
python tools/build_skill_archives.py --expected-version 0.4.0
```

Record the candidate commit, Python version, operating system, package version,
test totals, archive count, and `SHA256SUMS` result. A warning, skipped
installation path, or unexplained platform difference keeps the candidate
open.

## 2. Non-publishing GitHub runner check

Before creating a tag:

1. Open **Actions → release-skill-archives → Run workflow**.
2. Select the candidate branch and enter the exact manifest version.
3. Confirm that `verify-release-candidate` passes.
4. Download `geoai-skills-<version>-release-candidate`.
5. Verify that it contains 18 ZIP files plus `SHA256SUMS`, then run:

   ```bash
   sha256sum --check SHA256SUMS
   ```

   `sha256sum` is GNU coreutils and is absent from a stock Windows shell. On
   Windows, either call the copy Git for Windows ships:

   ```powershell
   & "$env:ProgramFiles\Git\usr\bin\sha256sum.exe" --check SHA256SUMS
   ```

   or verify with PowerShell alone:

   ```powershell
   Get-Content SHA256SUMS | ForEach-Object {
     $expected, $name = $_ -split '\s+', 2
     $name = $name.Trim()
     $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $name).Hash.ToLower()
     if ($actual -ne $expected) { "FAIL  $name  expected=$expected actual=$actual" }
   }
   ```

6. Compare the artifact's `SHA256SUMS` against the one produced locally in
   step 1. This is the step that has evidential value: an identical file means
   the maintainer's platform and the Ubuntu runner produced byte-identical
   archives from the same commit.

   ```bash
   diff dist/skills/SHA256SUMS <artifact-dir>/SHA256SUMS
   ```

   ```powershell
   Compare-Object (Get-Content dist\skills\SHA256SUMS) (Get-Content <artifact-dir>\SHA256SUMS)
   ```

   Empty output is the pass condition. Any difference is a platform dependency
   in packaging — the class of defect found and fixed before v0.3.0 — and keeps
   the candidate open until it is explained.

The manual workflow has read-only repository permission and retains its
run-scoped workflow artifact for seven days. It cannot create a tag, GitHub
Release, or release asset. Only the separate `release: published` job has
`contents: write`.

## 3. Clean-install matrix

Use a new temporary directory or a disposable user profile for every row.
Do not reuse an existing skill cache. For pre-release tests, replace
`<candidate-ref>` with the exact candidate commit SHA; after publication, use
`v0.4.0`.

Record the installed Skills CLI version and set `DISABLE_TELEMETRY=1` for
verification runs so the release check does not emit optional usage telemetry.

| Surface | Clean-install procedure | Required evidence |
| --- | --- | --- |
| Skills CLI discovery | `npx skills add muend/geoai-skills --list` | Exactly 18 public skills are listed. |
| Skills CLI full suite for Claude Code | `npx skills add muend/geoai-skills --skill '*' -a claude-code --copy -y` | Exactly 18 installed `SKILL.md` files; no evaluation or local-planning files. |
| Skills CLI full suite for Codex | `npx skills add muend/geoai-skills --skill '*' -a codex --copy -y` | Exactly 18 installed `SKILL.md` files under the detected Codex project path. |
| Skills CLI single skill | `npx skills add muend/geoai-skills --skill remote-sensing-analysis -a claude-code --copy -y` | One skill installs with its declared runtime resources. |
| Claude marketplace | `claude plugin marketplace add muend/geoai-skills`, then `claude plugin install geoai@geoai-skills` | Plugin is enabled at the expected version; the cached `skills/` directory holds exactly 18 skills; the cache contains no ignored or private material (`private-planning/`, `dist/`). See the note below on what the marketplace does cache. |
| Claude.ai / Claude desktop ZIP | Build archives, verify `SHA256SUMS`, and upload one representative ZIP through **Customize → Skills**. | The skill is accepted, displays its name and description, and activates for one positive prompt without activating for one negative prompt. |
| OpenAI plugin | `python tools/build_openai_plugin_bundle.py`, then inspect the ignored ZIP. Upload via the listing's **Upload draft** action, never **Create plugin**. | Manifest, policies, logo, and 18 runtime skills are present; evaluations, benchmarks, tests, tools, and local planning are absent. The directory version receives one positive and one negative smoke prompt. |

**The OpenAI portal may publish on submit.** In July 2026 a submission entered a
review queue and went live only after approval; in August 2026 the same flow
published immediately. Treat pressing *Confirm and submit* as the public act for
that channel, and do not upload until the release is otherwise ready — including
the tag. Do not rely on a review window to catch a mistake.
| GitHub repository validator | With GitHub CLI 2.90.0 or later, run `gh skill publish --dry-run` from the candidate checkout. | The Agent Skills specification and remote repository security checks pass without publishing. |
| GitHub Copilot via GitHub CLI | With GitHub CLI 2.90.0 or later, run `gh skill preview muend/geoai-skills remote-sensing-analysis`, then `gh skill install muend/geoai-skills remote-sensing-analysis@<candidate-ref>`. | Preview is reviewed before installation; the project receives one skill directory with provenance metadata and its resources. |
| GitHub Copilot via Skills CLI | `npx skills add muend/geoai-skills --skill remote-sensing-analysis -a github-copilot --copy -y` | One skill is installed to Copilot's detected project path and is discoverable by Copilot. |
| Generic Agent Skills runtime | Copy one complete directory from `skills/` into the runtime's documented skills directory. | `SKILL.md` and referenced runtime files remain together; positive and negative activation checks behave as expected. |

### What the Claude marketplace actually caches

The marketplace clones the repository. `.claude-plugin/plugin.json` declares
`"skills": "./skills/"`, which selects what the plugin *exposes* to the agent —
not what gets downloaded. So the cache under
`~/.claude/plugins/cache/geoai-skills/geoai/<version>/` also holds `evals/`,
`tests/`, `tools/`, `benchmarks/`, `.github/` and `assets/`.

This is the marketplace's design, not a packaging defect, and it cannot be
filtered from this side. It differs from the ZIP archives, which contain runtime
files only and are enforced by `tests/test_skill_archives.py`.

It is acceptable because everything cached is already public in the repository.
The material that must never reach a user's disk — `private-planning/` — lives
*outside* the repository directory and is therefore unreachable by any clone.
Ignored build output (`dist/`) is likewise absent. Verify both rather than
assuming: a future reorganisation that moves private material inside the repo
would silently start shipping it.

Real `arcgis-pro-automation` execution is a separate exact-environment
integration check. It requires Windows, licensed ArcGIS Pro, and a configured
local `arcgis-mcp-bridge`; a text-only smoke response is not execution evidence.

## 4. Evidence record

For each row, record:

- candidate commit or published tag;
- installer and runtime version;
- operating system and clean directory/profile used;
- installed skill count and expected version;
- command exit status or portal acceptance;
- one positive and one negative activation result;
- artifact names and SHA-256 values;
- limitation, skip reason, or failure trace.

Do not include API keys, access tokens, private benchmark prompts, ignored
evaluation traces, or personal filesystem paths in public evidence.

## 5. Publication gate

Publishing requires explicit maintainer approval after all applicable rows pass.
Immediately before approval, confirm:

1. the candidate commit is the intended `main` commit;
2. `v0.4.0` does not already exist;
3. release notes match `CHANGELOG.md`;
4. the repository tree and generated archives contain no secrets or private
   development material;
5. the GitHub Actions release job will build from the exact tag;
6. marketplace metadata and public policy URLs are current.

Publishing the GitHub Release triggers deterministic archive generation and
attaches the 18 ZIP files plus `SHA256SUMS`. Do not upload locally rebuilt
replacements to the same release.

## 6. Failure and rollback

- **Before publication:** keep or delete the draft; do not create the tag.
- **Manual RC workflow fails:** preserve the run logs, fix on a new commit, and
  rerun from that exact commit.
- **Clean installation fails:** preserve the installer/runtime versions and
  failure output; do not waive the row without an explicit documented reason.
- **After publication:** do not move the tag or overwrite assets. Publish a
  patch release that identifies the superseded version and explains the fix.
- **Marketplace-specific defect:** pause or unpublish that marketplace version
  when supported, keep the GitHub evidence intact, and issue a patch version.

## Authoritative installation references

- [GitHub Copilot agent skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)
- [Skills CLI](https://github.com/vercel-labs/skills)
- [Agent Skills specification](https://agentskills.io)
