# Implementation Plan: ProSpecPy Release Blockers, Packaging, and Documentation

---
**Date:** 2026-08-07
**Version:** 1.4
**Author:** AI Assistant
**Status:** Draft — all Open Questions resolved; ready for review
**Related Documents:**
- `plan-prospecpy-improvements.md` — the parallel plan covering correctness/performance bugs inside
  the pipeline. **Phase 2 of this plan supersedes Phase 4 of that plan.** See "Relationship to the
  improvements plan" below.
- `plan-arpls-and-fit-qc-integration.md` — merges the arPLS baseline and QC-instrumented peak
  fitting from the `arPLS-baseline` branch. **Phases 1 and 2 of this plan are hard
  prerequisites for it**, and it narrows the rationale behind Decision 1 below.

---

## Overview

Two defects currently make ProSpecPy unusable outside the GitHub Codespaces environment, and a third
group of packaging/documentation issues prevents the project from being installable, discoverable,
or publishable in the way its metadata claims.

This plan covers three distinct classes of work, ordered by urgency:

1. **Blockers** (Phases 1–2) — `pip install prospecpy` produces a package whose interactive stage
   cannot be imported, and the pipeline crashes on the project's own real data layout.
2. **Packaging and environment correctness** (Phases 3–5) — deprecated license metadata, unpinned
   dependencies, a three-way Python version split, four overlapping environment definitions, and a
   committed `pixi.lock` that CI never exercises.
3. **Documentation and data handling** (Phases 6–8) — a failing Read the Docs build publishing a
   stale page that contains an import traceback and zero plots, no API reference at all, four
   mutually inconsistent answers to "where does the data live", and accessibility defects in the
   matplotlib output that is this package's primary scientific artifact.

**Goal:** A ProSpecPy that a bench scientist can `pip install` and use outside Codespaces, whose
published documentation renders its own spectra, whose packaging metadata is accurate enough to
publish and cite, and which never carries instrument data in git.

**A constraint that shapes several phases:** no instrument data is committed to the repository, by
project policy. This is why the documentation ships pre-executed notebook outputs rather than
building them (Phase 6), why the data location is resolved at runtime through one convention rather
than relative paths (Phase 6a), and why the end-to-end pipeline check cannot be promoted to CI. See
Architectural Decisions 5 and 7.

**Motivation:** The package is in active scientific use and is advertised via a Zenodo DOI and a
Read the Docs site. Both of those front doors are currently broken. Every finding in this plan was
verified against the working tree rather than inferred.

---

## Current State Analysis

### Blockers

- `src/prospecpy/interact.py:6` — `import ipywidgets as widgets`
- `src/prospecpy/interact.py:9` — `from IPython.display import display`
- `pyproject.toml:22-30` — `[project.dependencies]` declares neither `ipywidgets` nor `ipython`.
  Verified: they appear in `pixi.lock` only inside other packages' `extra == '...'` marker strings,
  never as installed packages in any of the four environments.
- `.devcontainer/environment.yml:6` — the only place in the repo that names `ipywidgets`, which is
  why the defect is invisible to anyone developing in Codespaces (the `quay.io/pangeo/base-image`
  also supplies it).
- `src/prospecpy/io.py:66-98` — `batch_id_sample_name` returns `(None, None)` for any path that does
  not contain the literal string `opus_files`. The project's own `Hyd2_pH6_data/examples for you to
  try/` directory has no such component, so every sample resolves to the same
  `<output>/None/None` folder and `ProSpecPy.__init__` raises `FileExistsError` on the second
  sample. **The pipeline cannot run on the repository's own data.**
- `src/prospecpy/io.py:81` — `re.search("opus_files\s*(.*)", filepath)` is a non-raw string
  containing `\s`. Verified: `python -W error::SyntaxWarning` reports
  `SyntaxError: invalid escape sequence '\s'`. This is a `SyntaxWarning` on Python 3.12+ and becomes
  a hard `SyntaxError` in Python 3.14.

### Packaging and environments

- `pyproject.toml:28` — `openpyxl` is declared but has zero references in `src/`, `tests/`, or
  `docs/`. (`tabulate` *is* genuinely used, at `src/prospecpy/interact.py:10` and `:148`.)
- `pyproject.toml:22-30` — all seven runtime dependencies are bare names with no lower bounds.
- `pyproject.toml:51-52` — legacy `[project.license] file = "LICENSE"` table form, deprecated by
  PEP 639. `[build-system] requires` (`pyproject.toml:2`) does not pin hatchling, so every build
  pulls a current backend.
- `pyproject.toml:14` — `"License :: OSI Approved :: BSD License"` classifier. Once the SPDX string
  form is adopted, build backends **error** if this classifier is also present; the two must change
  together.
- `pyproject.toml:12` — `"Intended Audience :: Developers"` and `pyproject.toml:19` —
  `"Topic :: Software Development :: Build Tools"`. Both are cookiecutter residue and inaccurate for
  a bench-science package.
- `pyproject.toml:55-57` and `docs/_config.yml:24` and `README.md:49` — point at `uw-ssec/ProSpecPy`
  / `uw-ssec/prospecpy`. **The canonical org is `ProSpecPy/ProSpecPy`** (confirmed by the project
  owner and matching `git remote origin` and `CITATION.cff:20`). PyPI Trusted Publishing is
  configured per repository owner/name, so a mismatch surfaces as an opaque OIDC rejection at
  release time.
- `pixi.lock` — resolves `python-3.13.3` in every environment, because there is no
  `[tool.pixi.dependencies]` section to constrain it. Meanwhile `.github/workflows/ci.yml:27` tests
  only 3.11 and 3.12, and `pyproject.toml:16-17` claims only 3.11 and 3.12. Three sources, three
  answers.
- `pixi.lock` — `numpy`, `scipy`, `pandas`, and `matplotlib` all resolve to **PyPI wheels**, not
  conda-forge builds (verified: they appear as `pypi:` URLs). Only `python`, `openssl`, `libgcc` and
  similar come from conda. This forfeits the primary reason to adopt pixi for scientific work.
- `pyproject.toml:122` — pixi platforms are `["osx-arm64", "osx-64", "linux-64"]`, but
  `.github/workflows/ci.yml:28` tests `windows-latest`. A Windows scientist cannot `pixi install`
  at all; the project simultaneously asserts that Windows is and is not supported.
- `requirements.txt`, `docs/requirements.txt`, `.devcontainer/environment.yml` — three environment
  definitions, all drifted, and **none of them referenced by anything**. Verified: a repo-wide grep
  for `requirements.txt` returns zero hits outside the files themselves; `.readthedocs.yml:26-31`
  uses `python.install` with `extra_requirements: [docs]` and never reads a requirements file; and
  `.devcontainer/devcontainer.json` uses a prebuilt image plus `postBuild.sh`, never the conda file.
- `.devcontainer/postBuild.sh:6` — `mkdir -p "/workspaces/hydrogenase-ftir/data"` uses the
  project's **former name**, so in a Codespace for this repo it silently creates a stray directory
  and the `data` folder the README tells users to expect never appears.
- `.devcontainer/postBuild.sh:4` — hand-installs `matplotlib brukeropusreader openpyxl tabulate`,
  duplicating `[project.dependencies]` and omitting `[dev]`, so a Codespaces contributor cannot run
  the tests or pre-commit.
- `pyproject.toml:75` — `filterwarnings = ["error"]`. Harmless today only because `tests/` contains
  one trivial test. The first test that does `import prospecpy.io` will fail CI on Python 3.12+ via
  the `\s` SyntaxWarning above.
- `pyproject.toml:135` — the pixi `test` task passes `--disable-warnings`, which suppresses only the
  warnings *summary section*, not errors raised by the `error` filter. It is misleading.
- `.github/workflows/ci.yml:41,45` — installs non-editable (`pip install ".[dev]"`) then runs
  `--cov=prospecpy`, so coverage records `site-packages` paths that Codecov cannot map to the source
  tree. `.coveragerc` sets neither `relative_files` nor a `[paths]` mapping.
- `.github/workflows/ci.yml` — never runs `pixi install`. The committed `pixi.lock` can rot silently
  and reaches developers before it reaches CI.
- `.github/workflows/cd.yml:39-41` — `test-built-dist` has no event guard, so every push to `main`
  uploads a new `.devN` release to TestPyPI.
- `.github/workflows/cd.yml:32-37` — artifact upload happens *before* `twine check`.
- `.github/workflows/cd.yml` — sdist contents are never listed.
- `pyproject.toml:68-69` — `[tool.hatch.build.targets.sdist] exclude = ["/tests"]`.
- `pyproject.toml:35` — `nox` is a dev dependency; there is no `noxfile.py`. `pyproject.toml:118`
  even carries a `per-file-ignores` entry for it.
- `pyproject.toml:80` — ruff `exclude = ["tests/**", "testing.py"]` makes the `"tests/**"` entry in
  `per-file-ignores` (`pyproject.toml:117`) dead config, and `testing.py` does not exist.
  `pyproject.toml:113-114` still contains a literal `{{ cookiecutter.__project_slug }}` comment.
- `.github/dependabot.yml:4` — covers `github-actions` only, not `pip`.
- `CITATION.cff` — has authors and ORCIDs, but no `version`, `date-released`, `doi`, `type`,
  `license`, `abstract`, or `keywords`. `README.md:4` badges a Zenodo DOI that the CFF does not
  carry, so GitHub's "Cite this repository" widget emits a citation with no persistent identifier.

### Documentation

- **The last six Read the Docs builds have failed** (2026-07-21, 07-27, 08-03, via the RTD public
  build API). The published site is a stale successful build.
- **The published `workflow_demo` page is a `ModuleNotFoundError` traceback.** Execution dies on
  `import ipywidgets`, so every subsequent cell renders as bare source. The live documentation for a
  plot-centric spectroscopy package contains **zero plots**.
- `pyproject.toml:44` — `sphinx-panels` was last released 2021-06-03 and requires `sphinx>=2,<5`,
  while `jupyter-book` 1.0.4 (the version in `pixi.lock`) requires `sphinx>=5,<8`. The ranges are
  disjoint; the `docs` extra cannot resolve to a coherent environment. This is the leading candidate
  for the build failures.
- `pyproject.toml:42-45` — `sphinx_rtd_theme`, `sphinx-automodapi`, and `sphinxcontrib-mermaid` are
  declared and referenced nowhere. `sphinx-automodapi` in particular signals an intent to build API
  docs that was never completed.
- `docs/_toc.yml` — the entire table of contents is two pages (`intro` + `workflow_demo`). There is
  **no API reference, no tutorials section, no how-to guides, and no explanation section.**
- `docs/_config.yml:11` — `execute_notebooks: force` on a notebook whose data (`../../data/opus_files/...`)
  is not in the repo. Note that `auto` would **not** fix this: `workflow_demo.ipynb` has no stored
  outputs, so `auto` behaves identically to `force`.
- `.readthedocs.yml:19-20` — `fail_on_warning` is not set. MyST-NB defaults
  `nb_execution_raise_on_error` to `False`, which is why a notebook that dies mid-execution still
  ships a green build.
- `docs/workflow_demo.ipynb` — cell 0 is `sys.path.append("PATH TO src folder")` (literal
  placeholder text); `FILL_IN` placeholders throughout; `FIIL_IN_raw_data` (typo, `NameError`) in
  cell 20; `path_to_output_plots_` defined in cell 4 and never used while cell 6 hardcodes a
  different path.
- `docs/references.bib` — unmodified cookiecutter boilerplate (four neuroscience papers and *The
  Ruby Programming Language*). Nothing cites anything. The project's actual scientific provenance
  sits as loose PDFs in `reference/`, cited from nowhere.
- `src/prospecpy/vaporfit.py` — third-party code by Piotr Bruździak whose module header asks to be
  cited but **names no paper**. This is an attribution obligation, not a nicety. The paper has since
  been identified (Open Question 2): Bruździak 2019,
  [doi:10.1016/j.saa.2019.117373](https://doi.org/10.1016/j.saa.2019.117373). The header also
  misspells the author as "Bruzdziak" without the ź, which makes the attribution hard to search for.
- No module in `src/prospecpy/` uses NumPy-style docstrings. Verified: zero matches for the
  numpydoc underline form (`Parameters` followed by `----------`). What exists is two competing
  non-numpydoc styles — `Parameters:` with bullets in four files and Google-style `Args:` in four
  files, with `baseline.py` using both. Ruff has no `D`/pydocstyle rules enabled, so nothing
  enforces or even implies a standard.

### Plot accessibility (the package's primary artifact)

- `src/prospecpy/interact.py:130-133` — red peaks (`"ro"`), blue anchor points (`"bx"`), green
  baseline (`"g--"`) on one axes. Red `#FF0000` (L=0.213) against green `#008000` (L=0.154) is a
  **1.28:1 luminance contrast ratio** — indistinguishable in grayscale and on the most common
  colour-vision-deficiency axis. This is the plot where the scientist makes the one irreversible
  judgement in the entire workflow.
- `src/prospecpy/baseline.py:149-150` — default `C0` blue (`#1f77b4`, L=0.168) with red `"ro"`
  markers: **1.21:1**, rescued only by marker shape.
- `src/prospecpy/vaporfit.py:155-156` — pure red on white is **4.00:1**, below the 4.5:1 floor, and
  both series are drawn at `linewidth=0.5` against a 1.5pt guideline minimum. This is the first
  figure a scientist sees and the one they must read to judge whether subtraction worked.
- `src/prospecpy/second_deriv.py:95,112` — x-axis labelled `"wavenumber"` with **no units**;
  `src/prospecpy/second_deriv.py:113` — y-axis labelled `"d2ydx2"`, a Python identifier where a
  physical quantity belongs. `src/prospecpy/interact.py:135-136` has the same missing-units problem.
  (Note `src/prospecpy/interact.py:109-110`, `baseline.py:157-158`, `peak_fit.py:69-70`, and
  `vaporfit.py:162` *do* label units correctly — the defect is inconsistency, not universal absence.)
- **No plotting function anywhere calls `ax.invert_xaxis()`** (verified by grep across `src/`).
  Matplotlib autoscales to `(min, max)` regardless of input order, so **every spectrum renders with
  wavenumber increasing left-to-right**, backwards from universal FTIR convention. Every bench
  spectroscopist will read these plots in reverse.
- `src/prospecpy/prospecpy.py:85` — `fig.savefig(full_path)` with no `dpi` and no `bbox_inches`, so
  100 dpi and clipped labels. Callers also pass filenames with no extension.
- `src/prospecpy/interact.py:94` — `plt.figure(figsize=(18, 6))`; scaled down in a notebook, default
  10pt annotations become unreadable.
- `src/prospecpy/peak_fit.py:62` and 18 `plt.*` global calls in `interact.py` use pyplot's global
  state, which is not thread-safe. This forecloses any threaded per-sample parallelism later.

---

## Relationship to the other plans

Three plans now exist. `plan-prospecpy-improvements.md` covers correctness and performance defects
*inside* the pipeline. `plan-arpls-and-fit-qc-integration.md` merges the two student contributions
from the `arPLS-baseline` branch. This plan covers defects in the package's *packaging,
environment, and documentation*.

### To the arPLS integration plan

1. **Phases 1 and 2 of this plan are hard prerequisites.** Phase 2 in particular: without the
   `batch_id_sample_name` fix, the pipeline cannot run on the repository's own data at all, so
   none of that plan's real-data validation work is possible.
2. **Decision 1 below is narrowed, but not reversed.** That plan's Phase 4 retires the
   `interact()` GUI, which weakens the "interact() is stage 5 of 7" rationale for making
   `ipywidgets` a core dependency. It does not eliminate it — the package remains notebook-first
   and the demo notebook still renders widgets. Revisit only after that plan's Phase 4 lands.
3. **Decision 5's no-data-in-git policy applies to that branch too.** The `arPLS-baseline` branch
   commits ~21,000 lines of derived outputs under `output_plots/` and `peak_fitting_results/`.
   Its Phase 4 purges them and extends `.gitignore` accordingly.

### To the improvements plan

They are mostly independent, with three deliberate points of contact:

1. **Phase 2 of this plan supersedes Phase 4 of the improvements plan.** Both rewrite
   `batch_id_sample_name`. The improvements-plan version preserves the `(None, None)` return for
   paths lacking `opus_files`, which is exactly the behaviour that makes the pipeline unrunnable on
   real data. Implement the version in this plan and mark the other phase done. Doing so also
   deletes the `\s` escape-sequence defect as a side effect.
2. **Phase 1 of this plan should land before Phase 1 of the improvements plan.** The improvements
   plan adds package-root exports to `__init__.py`. If `interact` is ever added to those exports
   while `ipywidgets` is undeclared, `.github/workflows/cd.yml:72`'s
   `python -c "import prospecpy"` smoke test starts failing at release time. Declaring the
   dependencies first removes that trap.
3. **Nothing here touches the numerical pipeline.** No change in this plan alters any computed
   value.

---

## Desired End State

**New Behavior:**
- `pip install prospecpy` in a clean environment yields a package where `from prospecpy.interact
  import interact` succeeds
- `import_run_data` works on any directory layout, including `Hyd2_pH6_data/examples for you to try/`,
  with distinct output folders per sample
- `pixi install` succeeds on Windows; the resolved Python matches what CI tests and what the
  classifiers claim; numpy/scipy/pandas/matplotlib come from conda-forge
- Opening the repo in GitHub Codespaces yields a container where the documented workflow runs
  end to end — the `data` directory exists at the expected path, `interact()` imports, and the demo
  notebook executes — and CI proves it stays that way
- Exactly one environment definition exists (`pyproject.toml` + `pixi.lock`)
- The Read the Docs build succeeds, renders real spectra from committed notebook outputs, and fails
  loudly when it cannot
- The docs contain an API reference and a Diátaxis-structured table of contents
- Every plot is legible in grayscale, distinguishable under colour-vision deficiency, labelled with
  units, and oriented to FTIR convention
- All GitHub URLs point at `ProSpecPy/ProSpecPy`
- **No instrument data is present in the repository, and it is not possible to add any by accident.**
  `src/`, the notebook, and the devcontainer all resolve the data location through the single
  `get_data_dir()` convention, so a user with data anywhere on disk can point ProSpecPy at it with
  one environment variable
- `CITATION.cff` carries the concept DOI and a version that cannot silently drift from the git tag

**Success Looks Like:**
- `pip install .` into a clean venv, then `python -c "from prospecpy.interact import interact"` exits 0
- `import_run_data("Hyd2_pH6_data/examples for you to try", input_type="raw spectra", output_folder=tmp)`
  processes all 19 samples into 19 distinct folders
- `pixi run -e docs docs-build` completes locally with zero warnings
- The published `workflow_demo` page shows rendered spectra rather than a traceback

---

## What We're NOT Doing

- [ ] Adopting Prefect, Dask, Snakemake, or any workflow-orchestration framework. Evaluated
      separately and rejected: the full 19-sample pipeline runs in **5.0 seconds**, while Prefect's
      fixed overhead alone is ~4 s for the first flow plus ~1 s per subsequent run, for 57
      dependencies and 232 MB. Prefect additionally cannot host the `interact()` step
      (`suspend_flow_run` requires a deployment a notebook does not have; `pause_flow_run` blocks
      the kernel so ipywidgets callbacks never fire).
- [ ] The `PipelineConfig` / `SpectraRun` facade refactor proposed as the Prefect alternative. It is
      a good idea and deliberately deferred to its own plan; it is not a blocker.
- [ ] Rewriting the FTIR pipeline algorithm or changing any numerical output.
- [ ] Adding `py.typed`. Verified: across 64 function definitions in `src/prospecpy/`, exactly one
      has a return annotation and zero have annotated parameters. The `from __future__ import
      annotations` lines are mechanically inserted by ruff's `isort.required-imports`, not evidence
      of typing. Shipping `py.typed` would make downstream mypy silently infer `Any` everywhere
      instead of correctly reporting the package as untyped.
- [ ] Migrating `dev` to PEP 735 `[dependency-groups]`. Real churn, modest benefit, and `docs` must
      stay an extra regardless because `.readthedocs.yml:30-31` uses `extra_requirements`, which has
      no dependency-group equivalent.
- [ ] Adding `SECURITY.md`. This is an offline data-processing library with no network surface and
      no untrusted-input threat model beyond parsing instrument files.
- [ ] Exact version pinning in `[project.dependencies]`. That pattern suits a one-shot analysis
      backing a paper; for a redistributable library it would make ProSpecPy uninstallable alongside
      anything else. `pixi.lock` already provides developer-side reproducibility.

---

## Implementation Approach

**Technical Strategy:**
Phases 1 and 2 are blockers and should be merged first, independently, and fast. Phases 3–5 are
configuration-only and carry no runtime risk. Phases 6–8 are the largest body of work and can
proceed in parallel with each other once Phase 1 lands.

Tests are written first where a test is meaningful. Several findings here are configuration changes
where the honest verification is a command rather than a pytest assertion; those are listed under
each phase's Verification rather than dressed up as unit tests.

**Key Architectural Decisions:**

1. **Decision:** Make `ipywidgets` and `ipython` core runtime dependencies rather than an
   `interactive` extra
   - **Rationale:** `interact()` is stage 5 of a 7-stage pipeline, not an optional add-on. The
     audience arrives via a notebook. A bare `pip install prospecpy` that cannot run the documented
     workflow is a worse failure than a slightly heavier install.
   - **Trade-offs:** ~30 MB of Jupyter machinery for a user who only wants headless batch
     processing.
   - **Alternatives considered:** An `interactive` extra — rejected because `docs` would then have
     to include it anyway or Read the Docs stays broken, which defeats the isolation.
   - **Narrowed by `plan-arpls-and-fit-qc-integration.md`:** that plan's Phase 4 retires
     `interact()`, so the "stage 5 of a 7-stage pipeline" argument no longer applies. The decision
     stands regardless — the package is notebook-first and the demo notebook still renders
     widgets — but the *reason* is now weaker. Revisit after that Phase 4 lands, and treat it as a
     separate question rather than reverting silently.

2. **Decision:** `batch_id_sample_name` falls back to `Path.stem` instead of returning `(None, None)`
   - **Rationale:** Returning `(None, None)` collapses every sample into one output directory, which
     is a guaranteed `FileExistsError` rather than a graceful degradation. A filename-derived sample
     name is always available and always unique within a directory.
   - **Trade-offs:** Changes the documented contract. No caller depends on the `(None, None)` case
     today, because that case crashes.

3. **Decision:** Stay on Jupyter Book v1; do not migrate to bare Sphinx or Jupyter Book v2
   - **Rationale:** Jupyter Book v1 *is* Sphinx — `_config.yml` compiles to a `conf.py`, which
     `.readthedocs.yml:14-16` already does explicitly. Everything missing is reachable through
     `sphinx.extra_extensions`. Migration to bare Sphinx costs 1–2 days for zero capability gain and
     loses the toc-as-data model that keeps `_toc.yml` legible to chemist maintainers. Jupyter Book
     v2 / MyST-MD is a different engine with no autodoc story, so it would *cost* the API reference.
   - **Trade-offs:** Jupyter Book forces `html_theme = sphinx_book_theme`, so the `sphinx_rtd_theme`
     dependency is dead weight either way.

4. **Decision:** Use `autodoc` + `autosummary` with a hand-written `reference/api.md` rather than
   `sphinx-autoapi` or the already-declared `sphinx-automodapi`
   - **Rationale:** A committed `reference/api.md` satisfies `_toc.yml` directly, avoiding
     `sphinx-autoapi`'s `builder-inited` ordering conflict with `sphinx-external-toc`. More
     importantly it lets us *curate*: `ProSpecPy` has ~26 undocumented members, and an exhaustive
     dump would publish a wall of empty signatures and make the package look abandoned.
   - **Alternatives considered:** `sphinx-autoapi` (attractive because static parsing avoids
     imports, but dumps everything); `sphinx-automodapi` (Astropy-oriented, expects a curated
     `__all__`).

5. **Decision:** **No instrument data is committed to the repository, ever.** Notebooks are shipped
   with pre-saved outputs and are not executed during the docs build; the data location is resolved
   at runtime through a single documented convention *(directed by the project owner, 2026-08-07)*
   - **Rationale:** The project owner's instruction is that no data should be pushed to GitHub. This
     supersedes the earlier draft of this decision, which proposed committing ≈370 KB of real
     spectra. Size was never the constraint; the policy is.
   - **Consequences, which reach further than they first appear:**
     - `execute_notebooks` must be **`off`**, not `cache`. Every other setting (`force`, `auto`,
       `cache`) executes a notebook with no stored outputs, and without data that is a guaranteed
       docs-build failure. This is the *only* setting compatible with the policy.
     - Because notebook outputs are therefore committed artifacts rather than build products, they
       can silently go stale — the documentation can show results that the current code no longer
       produces. This is a real and permanent cost of the policy, and it needs an active mitigation
       (see Phase 6's staleness guard) rather than being accepted quietly.
     - `fail_on_warning: true` becomes safe to enable immediately, since nothing executes.
     - The docs build no longer needs the scientific stack to *run*, only to import for autodoc.
   - **Trade-offs:** Committed outputs decouple the documentation from the code. Mitigated, not
     eliminated, by a CI check that the notebook's recorded `prospecpy` version matches the current
     one.
   - **Alternatives considered:** Committing real data — **excluded by policy**. Synthetic data —
     rejected on scientific grounds even setting policy aside: stages 2 and 3 exist specifically to
     cope with real rovibrational water-vapour lines and real instrument noise, so a synthetic sum
     of Gaussians would show the algorithms succeeding against a signal with none of the pathology
     they exist to handle. `pooch` fetching from a data repository — viable *later* if the group ever
     publishes a citable dataset (Zenodo, PANGAEA), and the cleanest long-term answer since it keeps
     data out of git while still allowing executable docs; out of scope now because no such deposit
     exists.

6. **Decision:** The devcontainer is a first-class supported entry point and must be repaired, not
   retired *(resolved by the project owner, 2026-08-07)*
   - **Rationale:** The stated goal is that users can take advantage of GitHub Codespaces for
     development, contribution, **and usage** of ProSpecPy. That third audience is the load-bearing
     one: it means the devcontainer is not merely a contributor convenience but a supported way for
     a bench scientist to *run* the package, so it carries the same correctness bar as a `pip
     install`.
   - **Consequences, which run wider than the devcontainer files themselves:**
     - It reinforces Decision 1. If `ipywidgets`/`ipython` were relegated to an optional extra, a
       Codespaces user would get a container in which the documented workflow cannot run. Core
       dependencies are the only choice consistent with this decision.
     - `.devcontainer/postBuild.sh:6`'s wrong workspace path stops being cosmetic. The README tells
       users to create a `data` folder; the container currently creates it under the project's
       former name, so end users land in a container where the documented first step has silently
       already failed somewhere they will not look.
     - A supported entry point needs CI coverage, or it will rot again exactly as it has. Added to
       Phase 5.
     - `image: quay.io/pangeo/base-image:latest` (`devcontainer.json:3`) is unpinned, so the
       environment every Codespaces user receives changes without warning. Acceptable for a
       scratch dev box, not for a supported usage path.
   - **Trade-offs:** Ongoing maintenance of a third environment surface alongside pip and pixi. This
     is accepted deliberately; the alternative considered and rejected was retiring it in favour of
     `pixi install`, which would remove the zero-install browser-based path that makes the package
     accessible to scientists who do not want to manage a local Python environment at all.

7. **Decision:** **`<repo root>/data/` is the canonical data location** — the gitignored folder that
   `.devcontainer/postBuild.sh` already creates. Everything else is made consistent with it
   *(directed by the project owner, 2026-08-07)*
   - **Rationale:** Two of the four conventions currently in the repo already agree on this:
     `.gitignore:142` ignores `data/` at the repo root, and `.devcontainer/postBuild.sh:6` creates a
     `data` folder for Codespaces users. That is the convention with existing momentum, it is already
     what the README tells users to make, and it needs no new concepts. The other two are simply
     wrong and get corrected to match:
     - `docs/workflow_demo.ipynb` cell 4 reads `../../data/opus_files/...`, which from `docs/`
       resolves to `<repo_parent>/data` — **outside the repository entirely**.
     - Cell 6 writes to `../../output_plots/`, a fourth location, while the `path_to_output_plots_`
       variable defined in cell 4 is never used at all.
   - **`postBuild.sh:6` is itself broken and must be fixed for this decision to mean anything.** It
     hardcodes `/workspaces/hydrogenase-ftir/data` — the project's *former* name — so in a current
     Codespace it creates a stray directory beside the workspace and the intended `data/` folder
     never appears. The canonical location is therefore not merely under-documented today; in the
     one environment that is supposed to create it automatically, it does not exist. Fixed in Phase
     4.
   - **How it is resolved in code:** `get_data_dir()` walks up from the current working directory to
     find `data/`. This is deliberately *not* a new location — it is the mechanism that makes the
     single location reachable identically from the repository root, from `docs/`, and from a
     subdirectory, which bare relative paths demonstrably are not.
   - **Trade-offs:** One small module instead of a literal path string. Accepted because the literal
     path is exactly what produced the current inconsistency: `../../data` is correct from *some*
     working directory and wrong from the one the notebook actually runs in.
   - **The `PROSPECPY_DATA_DIR` override is retained but demoted** to a documented escape hatch, not
     the primary mechanism. It covers the case the in-repo convention genuinely cannot: a user who
     `pip install`s ProSpecPy outside a checkout has no repository root to walk up to, and a user
     whose spectra live on an external drive or lab network share should not have to copy tens of
     gigabytes into the repo to satisfy a convention. Documented as the exception; `<repo
     root>/data/` is the answer given everywhere by default.
   - **Alternatives considered:** A config file (`prospecpy.toml`) — more ceremony than one path
     needs. An absolute path — breaks across local, Codespaces, and Windows. Keeping bare relative
     paths — this is the status quo and it is what is being fixed.

**Patterns to Follow:**
- Docstring style: NumPy/numpydoc, to be adopted going forward (nothing currently conforms)
- `pathlib.Path` already used in `io.py:5`

---

## Implementation Phases

### Phase 1: Blocker — declare the missing runtime dependencies

**Objective:** `pip install prospecpy` produces a package whose interactive stage imports.

**Tasks:**

- [ ] **Write the failing test**
  - File: `tests/test_dependencies.py` (new)

  ```python
  from __future__ import annotations


  def test_interact_module_is_importable():
      """interact() is pipeline stage 5; its dependencies must be declared."""
      from prospecpy.interact import interact

      assert interact is not None
  ```

- [ ] **Run it, watch it fail** in a clean venv built from `pip install .`
  → expect `ModuleNotFoundError: No module named 'ipywidgets'`
  *(It will pass in Codespaces and in the current pixi env, both of which supply ipywidgets by
  accident. Verify in a clean venv, not in your working environment — this is the whole point.)*

- [ ] **Implement:** update `pyproject.toml:22-30`

  ```toml
  dependencies = [
      "brukeropusreader",
      "ipython",              # IPython.display, used in interact.py:9
      "ipywidgets>=8",        # widgets, used in interact.py:6
      "matplotlib",
      "numpy",
      "pandas",
      "scipy",
      "tabulate",
      # openpyxl removed: zero references in src/, tests/, or docs/
  ]
  ```

- [ ] **Run it, watch it pass** in a fresh clean venv

- [ ] **Commit:** `git commit -m "fix: declare ipywidgets and IPython runtime deps, drop unused openpyxl"`

**Dependencies:** None. This is the first thing that should merge.

**Verification:**
- [ ] `python -m venv /tmp/v && /tmp/v/bin/pip install . && /tmp/v/bin/python -c "from prospecpy.interact import interact"` exits 0
- [ ] `rg -n "openpyxl" src/ tests/ docs/` returns no output
- [ ] The next Read the Docs build succeeds and `workflow_demo` renders plots rather than a traceback

---

### Phase 2: Blocker — make the pipeline runnable on real data layouts

**Objective:** `import_run_data` works on directory layouts that do not contain an `opus_files`
component, giving each sample a distinct output folder.

> **Supersedes Phase 4 of `plan-prospecpy-improvements.md`.** That phase's implementation preserves
> the `(None, None)` return that causes this crash. Implement this version instead and mark the
> other phase complete. This also removes the `\s` escape-sequence defect at `io.py:81`.

**Tasks:**

- [ ] **Write the failing tests**
  - File: `tests/test_batch_id_sample_name.py` (new)

  ```python
  from __future__ import annotations

  import sys

  import pytest

  from prospecpy.io import batch_id_sample_name


  def test_extracts_batch_and_sample_under_opus_files():
      batch_id, sample_name = batch_id_sample_name("/data/opus_files/batch001/sample_A.0")
      assert batch_id == "batch001"
      assert sample_name == "sample_A.0"


  def test_extracts_sample_only_when_no_batch_dir():
      batch_id, sample_name = batch_id_sample_name("/data/opus_files/sample_A.0")
      assert batch_id is None
      assert sample_name == "sample_A.0"


  def test_falls_back_to_filename_when_opus_files_absent():
      """The real Hyd2 layout has no 'opus_files' component. Returning
      (None, None) here collapses every sample into one output folder and
      raises FileExistsError on the second sample."""
      batch_id, sample_name = batch_id_sample_name(
          "Hyd2_pH6_data/examples for you to try/011a as iso Hyd2 dark titration 0 mV.0022"
      )
      assert batch_id is None
      assert sample_name == "011a as iso Hyd2 dark titration 0 mV.0022"


  def test_distinct_samples_get_distinct_names_without_opus_files():
      """Regression guard for the FileExistsError collapse."""
      _, first = batch_id_sample_name("/data/run/sample_A.0")
      _, second = batch_id_sample_name("/data/run/sample_B.0")
      assert first != second


  @pytest.mark.skipif(sys.platform != "win32", reason="pathlib only splits '\\' on Windows")
  def test_handles_windows_separators():
      batch_id, sample_name = batch_id_sample_name(r"C:\data\opus_files\batch001\sample_A.0")
      assert batch_id == "batch001"
      assert sample_name == "sample_A.0"
  ```

- [ ] **Run them, watch them fail:** `pytest tests/test_batch_id_sample_name.py -v`
  → expect `test_falls_back_to_filename_when_opus_files_absent` and
  `test_distinct_samples_get_distinct_names_without_opus_files` to fail with `assert None == '...'`

- [ ] **Implement:** replace `src/prospecpy/io.py:66-98`

  ```python
  def batch_id_sample_name(filepath: str) -> tuple[str | None, str | None]:
      """
      Extract ``batch_id`` and ``sample_name`` from a file path.

      When the path contains an ``opus_files`` component, the one or two
      components following it are used::

          …/opus_files/<batch_id>/<sample_name>  ->  (batch_id, sample_name)
          …/opus_files/<sample_name>             ->  (None, sample_name)

      Otherwise the file's own name is used as the sample name::

          …/<any>/<sample_name>                  ->  (None, sample_name)

      The fallback matters: the previous implementation returned
      ``(None, None)`` for any path lacking the literal string ``opus_files``,
      which routed every sample in a run to the same output directory and
      raised ``FileExistsError`` on the second sample.

      Uses :mod:`pathlib` for portable parsing; the original used a regex and
      split on ``"/"``, which failed on Windows.

      Parameters
      ----------
      filepath : str
          Path to an OPUS file.

      Returns
      -------
      batch_id : str or None
          The batch directory name, or None if the layout has no batch level.
      sample_name : str or None
          The sample name. None only when `filepath` has no filename component.
      """
      path = Path(filepath)
      parts = path.parts

      if "opus_files" in parts:
          after = parts[parts.index("opus_files") + 1 :]
          if len(after) >= 2:
              return after[0], after[1]
          if len(after) == 1:
              return None, after[0]

      return None, path.name or None
  ```

  *Remove the now-unused `re` import at `src/prospecpy/io.py:4`. This deletes the `\s`
  SyntaxWarning along with it.*

- [ ] **Run them, watch them pass:** `pytest tests/test_batch_id_sample_name.py -v` → expect all PASSED
      (the Windows test skips on POSIX)

- [ ] **Verify end-to-end on the real data**

  ```bash
  python -c "
  import tempfile
  from prospecpy.io import import_run_data
  with tempfile.TemporaryDirectory() as tmp:
      objs = import_run_data('Hyd2_pH6_data/examples for you to try',
                             input_type='raw spectra', output_folder=tmp)
      names = {o.sample_name for o in objs}
      print(len(objs), 'samples,', len(names), 'distinct names')
      assert len(objs) == len(names), 'sample names collided'
  "
  ```

- [ ] **Commit:** `git commit -m "fix: derive sample name from filename when opus_files is absent"`

**Dependencies:** None technically, but merge after Phase 1 so the end-to-end check can run.

**Verification:**
- [ ] `pytest tests/test_batch_id_sample_name.py -v` all PASSED
- [ ] The end-to-end snippet above prints `19 samples, 19 distinct names`
- [ ] `rg -n "^import re" src/prospecpy/io.py` returns no output
- [ ] `python -W error::SyntaxWarning -c "import py_compile; py_compile.compile('src/prospecpy/io.py', doraise=True)"` exits 0

---

### Phase 3: Packaging metadata correctness

**Objective:** License metadata is PEP 639-compliant, dependencies have floors, URLs point at the
canonical org, and `CITATION.cff` is usable.

> **One addition from `plan-arpls-and-fit-qc-integration.md` Phase 2:** that plan adds a
> console script, and it belongs in this file rather than being bolted on separately.
>
> ```toml
> [project.scripts]
> prospecpy = "prospecpy.cli:main"
> ```
>
> If this phase runs first, leave the stanza out and let Phase 2 add it. If it runs after,
> include it here. Either way it should appear in `pyproject.toml` exactly once.

**Tasks:**

- [ ] **Pin the build backend and adopt SPDX licensing.** These must change together — build
      backends error if a `License ::` classifier coexists with the SPDX string form.

  ```toml
  [build-system]
  requires = ["hatchling>=1.27", "hatch-vcs"]
  build-backend = "hatchling.build"

  [project]
  license = "BSD-3-Clause"
  license-files = ["LICENSE"]
  classifiers = [
      "Development Status :: 3 - Alpha",
      "Intended Audience :: Science/Research",
      "Operating System :: OS Independent",
      "Programming Language :: Python :: 3.11",
      "Programming Language :: Python :: 3.12",
      "Programming Language :: Python :: 3.13",
      "Topic :: Scientific/Engineering",
  ]
  ```

  *Delete the `[project.license]` table at `pyproject.toml:51-52`, the
  `"License :: OSI Approved :: BSD License"` classifier, `"Intended Audience :: Developers"`, and
  `"Topic :: Software Development :: Build Tools"`.*

- [ ] **Add dependency floors.** The code is NumPy-2 clean — verified no `np.float_`, `np.NaN`,
      `np.in1d`, `np.trapz`, or `np.product`, no SciPy 1.14 removals (`simps`, `cumtrapz`,
      `interp2d`), and no pandas 2.0 removals. **No upper caps are warranted.** The floors below
      exist so that every *allowed combination* is NumPy-2-safe, which is the real hazard: without
      them a user can land numpy 2 alongside scipy 1.11 and get a binary-incompatibility crash that
      looks like a ProSpecPy bug.

  ```toml
  dependencies = [
      "brukeropusreader>=1.3.4",
      "ipython>=8.18",
      "ipywidgets>=8.1",
      "matplotlib>=3.9",
      "numpy>=1.26",
      "pandas>=2.2.2",   # first NumPy-2-compatible pandas
      "scipy>=1.13",     # first SciPy supporting both NumPy 1.22+ and 2.0 ABIs
      "tabulate>=0.9",
  ]
  ```

- [ ] **Correct the GitHub org** to `ProSpecPy/ProSpecPy` (canonical, per project owner) in three
      places: `pyproject.toml:55-57`, `docs/_config.yml:24`, and `README.md:49`.
      `CITATION.cff:20` is already correct.

      `README.md:49` is the highest-priority of the three: it is the
      `https://codespaces.new/uw-ssec/ProSpecPy?quickstart=1` badge, and per Architectural Decision 6
      Codespaces is a supported way for end users to *run* ProSpecPy. A wrong org there means the
      primary advertised entry point sends users to the wrong repository. The
      `pyproject.toml` URLs matter for a different reason — PyPI Trusted Publishing is configured per
      repository owner/name, so a mismatch surfaces as an opaque OIDC rejection at release time.

- [ ] **Complete `CITATION.cff`** — add `type: software`, `version`, `date-released`, `doi`,
      `license: BSD-3-Clause`, `abstract`, and `keywords`. Without a `doi`, GitHub's citation widget
      emits no persistent identifier at all.

      The badge at `README.md:4` resolves through `zenodo.org/badge/latestdoi/836894886` to
      **record 15330896**, whose metadata was retrieved on 2026-08-07 and gives both identifiers:

      | Identifier | DOI | Resolves to |
      |---|---|---|
      | **Concept DOI** | `10.5281/zenodo.15330895` | always the newest release |
      | Version DOI (v0.1.0) | `10.5281/zenodo.15330896` | v0.1.0 forever, released 2025-05-03 |

      **Decided by the project owner (2026-08-07): use the concept DOI.** It goes in the top-level
      `doi:` field, with the version DOI retained under `identifiers:` so that a reader reproducing a
      specific result can still reach the frozen release. Recording only the version DOI — the easy
      mistake, since that is what the badge link resolves to — would permanently pin every citation
      to v0.1.0:

  ```yaml
  cff-version: 1.2.0
  message: "If you use this software, please cite it as below."
  title: "ProSpecPy: FTIR Spectroscopy Data Processing Library"
  type: software
  doi: 10.5281/zenodo.15330895   # concept DOI — always resolves to the latest release
  identifiers:
    - type: doi
      value: 10.5281/zenodo.15330895
      description: Concept DOI for all versions
    - type: doi
      value: 10.5281/zenodo.15330896
      description: Version DOI for v0.1.0
  version: 0.1.0
  date-released: 2025-05-03
  license: BSD-3-Clause
  ```

- [ ] **Auto-sync `version` and `date-released` in `cd.yml`** *(decided by the project owner,
      2026-08-07)*. These two fields are the only place in the repository where a version number is
      written by hand — everywhere else hatch-vcs derives it from git tags — so tagging `v0.2.0`
      updates the package while `CITATION.cff` silently keeps claiming 0.1.0. The failure is
      invisible to maintainers and visible only to people citing the work, which is why it needs
      automating rather than remembering. Add to `.github/workflows/cd.yml`:

  ```yaml
    sync-citation:
      needs: [publish]
      if: github.event_name == 'release'
      runs-on: ubuntu-latest
      permissions:
        contents: write        # the default GITHUB_TOKEN suffices; no PAT needed
      steps:
        - uses: actions/checkout@v4
          with:
            ref: main          # not the tag: the tag is detached and cannot be pushed to

        - name: Sync CITATION.cff to the release
          env:
            TAG: ${{ github.event.release.tag_name }}
            RELEASED: ${{ github.event.release.published_at }}
          run: |
            python - <<'EOF'
            import os, pathlib, re
            version = os.environ["TAG"].lstrip("v")
            released = os.environ["RELEASED"][:10]   # ISO timestamp -> YYYY-MM-DD
            p = pathlib.Path("CITATION.cff")
            s = p.read_text()
            s, n1 = re.subn(r"^version:.*$", f"version: {version}", s, flags=re.M)
            s, n2 = re.subn(r"^date-released:.*$", f"date-released: {released}", s, flags=re.M)
            if not (n1 and n2):
                raise SystemExit("CITATION.cff is missing version or date-released")
            p.write_text(s)
            EOF

        - name: Validate
          run: pipx run cffconvert --validate

        - name: Commit
          run: |
            git config user.name  "github-actions[bot]"
            git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
            git add CITATION.cff
            git diff --staged --quiet || git commit -m "chore: sync CITATION.cff to ${{ github.event.release.tag_name }}"
            git push
  ```

      Three details that are easy to get wrong and cause a silent no-op:
      - **Check out `main`, not the tag.** A tag checkout is detached, so the push fails or goes
        nowhere. This is the most common way this pattern is broken in the wild.
      - **Use `github.event.release.published_at`, not `date.today()`.** They differ whenever a
        release is drafted before publishing, and `date-released` should record the release.
      - **`re.subn`, not `re.sub`.** A plain substitution that matches nothing succeeds silently,
        which would reintroduce exactly the drift this job exists to prevent. Failing loudly on a
        zero-match is the whole safety property.

      **One known limitation, worth stating rather than discovering later:** this job runs *after*
      the release is published, so the commit lands on `main` one commit ahead of the tag. The
      source archive Zenodo captures at the tag therefore still contains the previous
      `CITATION.cff`. This does not affect the DOI or the version Zenodo records (both come from the
      GitHub release itself), only the file inside the archive. Accepted as the cost of a fully
      automatic approach; the alternative — bumping `CITATION.cff` in a release-prep PR *before*
      tagging — orders it correctly but reintroduces a manual step, which is what this decision set
      out to remove.

- [ ] **Remove the sdist test exclusion** at `pyproject.toml:68-69`. conda-forge and Debian
      packagers build from the sdist and run the suite as packaging QA; excluding tests makes that
      impossible. The size argument does not apply (two small files, no fixture data).

- [ ] **Commit:** `git commit -m "fix: PEP 639 license metadata, dependency floors, canonical org URLs, complete CITATION.cff"`

**Dependencies:** Phase 1 (shares the `dependencies` list).

**Verification:**
- [ ] `pipx run build` succeeds with no deprecation warnings
- [ ] `pipx run twine check dist/*` passes
- [ ] `rg -n "uw-ssec" --glob '!pixi.lock' --glob '!docs/rse/**' .` returns no output
- [ ] `pipx run cffconvert --validate` passes
- [ ] `tar -tzf dist/*.tar.gz | rg "tests/"` shows the test files included

---

### Phase 4: Environment consolidation

**Objective:** One environment definition. Pixi resolves a Python that CI actually tests, on every
platform CI actually tests, using conda-forge builds of the scientific stack.

**Tasks:**

- [ ] **Delete the three dead environment files.** Verified unreferenced:
  - `requirements.txt` — no repo-wide references; also already drifted (missing `openpyxl`/`tabulate`)
  - `docs/requirements.txt` — `.readthedocs.yml:26-31` uses `extra_requirements: [docs]` and never
    reads a requirements file
  - `.devcontainer/environment.yml` — `devcontainer.json` uses `image:` plus `postBuild.sh`; the
    conda file is referenced nowhere

- [ ] **Repair the devcontainer.** Per Architectural Decision 6 this is a supported path for
      development, contribution, *and end-user usage*, so it carries the same correctness bar as a
      `pip install`. Four defects:

  **(a) `postBuild.sh` creates the `data` directory under the project's former name**
  (`postBuild.sh:6`, `/workspaces/hydrogenase-ftir/data`), so the folder the README tells users to
  expect never appears where they look. Under Architectural Decision 7 this directory is the
  project's canonical data location, which promotes the bug from a stale-path annoyance to a break
  in the one convention everything else now depends on. It also hand-installs four packages
  (`postBuild.sh:4`), duplicating `[project.dependencies]` and omitting `[dev]`, so a contributor
  cannot run the tests.

  **(b) The script is invoked with `sh`, not `bash`** (`devcontainer.json:16`:
  `"postCreateCommand": "sh .devcontainer/postBuild.sh"`). A `#!/usr/bin/env bash` shebang is
  ignored under that invocation, and `set -o pipefail` is not POSIX, so a strict-mode script would
  fail on a `sh` that lacks it. Fix both halves together:

  ```jsonc
  // devcontainer.json
  "postCreateCommand": "bash .devcontainer/postBuild.sh",
  ```

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  python3 -m pip install -e ".[dev,docs]"

  # Canonical data location (Architectural Decision 7): <repo root>/data, gitignored.
  # postCreateCommand runs with the workspace folder as cwd, so a bare relative path
  # is correct here and cannot go stale if the repository is renamed again — which is
  # exactly how the previous hardcoded /workspaces/hydrogenase-ftir/data broke.
  mkdir -p data
  ```

  *Deliberately **not** `${containerWorkspaceFolder}/data`: that is a devcontainer.json substitution
  variable, not a shell environment variable, so it does not expand inside `postBuild.sh` and would
  silently create a directory named `${containerWorkspaceFolder}`.*

  **(c) The base image is unpinned** — `devcontainer.json:3` uses
  `quay.io/pangeo/base-image:latest`, so the environment every Codespaces user receives changes
  without warning and without a lockfile entry. Pin to a dated tag and bump deliberately:

  ```jsonc
  "image": "quay.io/pangeo/base-image:2025.05.19",  // pin; bump deliberately, not implicitly
  ```

  *This also removes the accident that has been masking the undeclared-`ipywidgets` bug: the pangeo
  image happens to supply `ipywidgets`, which is why the defect was invisible in Codespaces. Phase 1
  makes that explicit rather than incidental.*

  **(d) Drop the `black` and `pylint` features** (`devcontainer.json:18-19`) — the project
  standardised on ruff, so these install two linters that disagree with the configured one.

- [ ] **Constrain Python and source the scientific stack from conda-forge**

  ```toml
  [tool.pixi.dependencies]
  python = ">=3.11,<3.14"
  numpy = ">=1.26"
  scipy = ">=1.13"
  pandas = ">=2.2.2"
  matplotlib-base = ">=3.9"
  ipywidgets = ">=8.1"
  ```

  *Note this pixi-level Python cap does **not** contradict the "never cap `requires-python`" rule.
  `requires-python` is published metadata constraining users; `[tool.pixi.dependencies] python`
  pins only the development environment.*

- [ ] **Add `win-64` to pixi platforms** at `pyproject.toml:122`, matching the CI matrix:

  ```toml
  [tool.pixi.workspace]
  channels = ["conda-forge"]
  platforms = ["linux-64", "osx-64", "osx-arm64", "win-64"]
  ```

- [ ] **Expand pixi tasks.** Note the existing two live under `[tool.pixi.feature.dev.tasks]`, so
      `pixi run test` fails in the default environment and requires `pixi run -e dev test` — a
      papercut for new contributors.

  ```toml
  [tool.pixi.feature.dev.tasks]
  lint     = "pre-commit run --all-files"
  test     = "pytest"
  test-cov = "pytest --cov=prospecpy --cov-report=term-missing --cov-report=xml"
  check    = { depends-on = ["lint", "test-cov"] }

  [tool.pixi.feature.docs.tasks]
  docs-build = "jupyter-book build docs --warningiserror"
  docs-clean = "jupyter-book clean docs"
  ```

  *Drop `--disable-warnings` from the `test` task — it suppresses only the summary section, never
  the errors raised by `filterwarnings = ["error"]`, so it misleads without helping.*

- [ ] **Relock:** `pixi install` and commit the updated `pixi.lock`

- [ ] **Commit:** `git commit -m "chore: consolidate to a single environment definition, pin pixi python, add win-64"`

**Dependencies:** Phase 3 (shares `pyproject.toml` edits; sequence to avoid conflicts).

**Verification:**
- [ ] `ls requirements.txt docs/requirements.txt .devcontainer/environment.yml` reports all three missing
- [ ] `rg -o 'python-3\.[0-9]+\.[0-9]+' pixi.lock | sort -u` shows only 3.11/3.12/3.13 within the cap
- [ ] `rg -c 'conda:.*numpy' pixi.lock` is non-zero (numpy now comes from conda-forge, not PyPI)
- [ ] `pixi info` lists `win-64` among the platforms
- [ ] `rg -n "hydrogenase-ftir" .devcontainer/` returns no output
- [ ] `rg -n "base-image:latest" .devcontainer/devcontainer.json` returns no output (image is pinned)
- [ ] **Launch a real Codespace from the branch** and confirm, as an end user would: the `data`
      directory exists at the workspace root, `from prospecpy.interact import interact` succeeds,
      and `docs/workflow_demo.ipynb` opens with a working kernel and renders widgets. Automated in
      Phase 5, but worth doing by hand once, since this is the path most users will take.

---

### Phase 5: CI/CD hardening

**Objective:** CI exercises the lockfile and the Python developers actually use; coverage maps to
source; CD stops publishing to TestPyPI on every merge.

> **`plan-arpls-and-fit-qc-integration.md` adds test assets this phase must account for:**
> `tests/test_arpls.py`, `tests/test_fit_report.py`, and a `tests/data/` directory holding
> small golden-file CSVs. Two consequences: coverage config must not exclude the new
> `fit_report`/`cli` modules, and if `tests/` ships in the sdist then `tests/data/` needs a
> `MANIFEST.in`/`force-include` entry or the golden-file tests fail on an installed copy.
> Keep those fixtures small — they are checked-in data, and Architectural Decision 5 says
> data does not live in git; a few kilobytes of derived CSV used as a test oracle is the
> deliberate exception, not a precedent for committing spectra.

**Tasks:**

- [ ] **Add Python 3.13 to the CI matrix** at `.github/workflows/ci.yml:27` so CI covers what pixi
      resolves and what the classifiers now claim.

- [ ] **Fix coverage path mapping.** CI installs non-editable, so coverage records `site-packages`
      paths Codecov cannot map. Move config into `pyproject.toml` and delete `.coveragerc`:

  ```toml
  [tool.coverage.run]
  source = ["src/prospecpy"]
  relative_files = true
  omit = ["*/version.py"]

  [tool.coverage.paths]
  source = ["src/prospecpy", "*/site-packages/prospecpy"]

  [tool.coverage.report]
  exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:", "raise NotImplementedError"]
  ```

- [ ] **Add a pixi lockfile validation job.** One job, not a matrix — the point is validating the
      lock, which is the same lock everywhere. `locked: true` turns drift into a CI failure instead
      of a surprise for the next developer.

  ```yaml
    pixi:
      name: Validate pixi lockfile
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
          with:
            fetch-depth: 0
        - uses: prefix-dev/setup-pixi@v0.8.1
          with:
            environments: dev
            locked: true
            cache: true
        - run: pixi run -e dev test
  ```

- [ ] **Add a docs build job** so a broken docs build is caught in CI rather than discovered on Read
      the Docs weeks later. This would have caught the current failure months ago.

- [ ] **Add a devcontainer build job.** Per Architectural Decision 6 the devcontainer is a supported
      entry point for end users, not just contributors — and it silently rotted to the point of
      creating its data directory under the project's *former name*. Nothing would have caught that,
      because nothing builds it. The `devcontainers/ci` action builds the image, runs
      `postCreateCommand`, and then runs a command inside the container:

  ```yaml
    devcontainer:
      name: Validate devcontainer
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: devcontainers/ci@v0.3
          with:
            push: never
            runCmd: |
              set -euo pipefail
              # The documented user workflow must actually work in the container.
              python -c "from prospecpy.interact import interact; print('interact OK')"
              # runCmd starts in the workspace folder, so a relative path is correct
              # here for the same reason it is in postBuild.sh.
              test -d data || { echo "canonical data/ directory missing"; exit 1; }
              python -c "from prospecpy import get_data_dir; print(get_data_dir())"
              pytest -q
  ```

  The `test -d data` assertion is the specific regression guard for the wrong-workspace-path bug
  fixed in Phase 4, and the `get_data_dir()` call proves the canonical convention resolves inside the
  container with no environment variable set — together they cover both halves of Architectural
  Decision 7. The `interact` import guards the Phase 1 dependency bug, checked in the one environment
  where the pangeo base image would otherwise mask it.

  *Note this job is slower than the others (it builds a container image). If PR latency becomes a
  problem, restrict it to `paths: ['.devcontainer/**', 'pyproject.toml']` rather than dropping it.*

- [ ] **Guard `test-built-dist`** at `.github/workflows/cd.yml:39-41`. With hatch-vcs and
      `local_scheme = "no-local-version"`, every merge to `main` currently uploads a new `.devN`
      release to TestPyPI:

  ```yaml
    test-built-dist:
      needs: [dist]
      if: github.event_name == 'release' || github.event_name == 'workflow_dispatch'
  ```

- [ ] **Reorder `twine check` before artifact upload** (`.github/workflows/cd.yml:32-37`) and add an
      sdist content listing, giving the artifact an explicit name rather than relying on the
      implicit `artifact` default that `cd.yml:52` hardcodes:

  ```yaml
        - name: Build sdist and wheel
          run: pipx run build
        - name: Check products
          run: pipx run twine check dist/*
        - name: Inspect sdist contents
          run: tar -tvf dist/*.tar.gz
        - uses: actions/upload-artifact@v4
          with:
            name: dist
            path: dist
  ```

- [ ] **Add a `pip` ecosystem entry to `.github/dependabot.yml`.** Note there is no dependabot
      ecosystem for pixi; keeping `pixi.lock` fresh needs a scheduled `pixi update` job.

- [ ] **Scope `filterwarnings` escape hatches.** Keep `error` as the default — it is valuable — but
      add narrow, dated exemptions as third-party deprecations appear:

  ```toml
  [tool.pytest.ini_options]
  filterwarnings = [
      "error",
      # Narrowly scope each third-party deprecation and delete it when the
      # upstream fix lands. Do not broaden to a bare "ignore::DeprecationWarning".
      "ignore::DeprecationWarning:brukeropusreader.*",
  ]
  ```

- [ ] **Commit:** `git commit -m "ci: validate pixi lock, build docs, fix coverage paths, guard TestPyPI uploads"`

**Dependencies:** Phase 4 (the pixi job needs the corrected platform list).

**Verification:**
- [ ] A PR shows a green `Validate pixi lockfile` job
- [ ] Codecov annotates lines on a PR diff (proves path mapping works)
- [ ] Merging to `main` produces no new TestPyPI release

---

### Phase 6: Documentation — unbreak the Read the Docs build

**Objective:** The docs build succeeds, renders real spectra, and fails loudly when it cannot.

**Tasks:**

- [ ] **Fix the `docs` extra.** `sphinx-panels` requires `sphinx<5` while `jupyter-book` 1.0.4
      requires `sphinx>=5` — disjoint ranges. Jupyter Book 1.x already bundles `sphinx-design`,
      sphinx-panels' successor, so nothing needs adding:

  ```toml
  docs = [
      "jupyter-book>=1.0,<2",
      "numpydoc>=1.6",
  ]
  ```

  *Drops `sphinx-panels` (dead since 2021, blocks resolution), `sphinx_rtd_theme` (Jupyter Book
  forces `sphinx_book_theme` and wins), `sphinx-automodapi` (unused; superseded by the Phase 7
  approach), and `sphinxcontrib-mermaid` (unused).*

- [ ] **Set `execute_notebooks: off`** in `docs/_config.yml`. Per Architectural Decision 5 no data
      is committed, so this is the only viable setting — `force`, `auto`, and `cache` all execute a
      notebook that has no stored outputs, which without data fails every time. `auto` is the
      specific trap, because it sounds safe: it executes notebooks that lack stored outputs, and
      `workflow_demo.ipynb` lacks them.

- [ ] **Commit the notebook with its outputs saved.** This is the change that actually fixes the
      published page. Run the notebook locally against real data, save it *with* outputs (figures
      included), and commit that. The rendered spectra then come from the committed artifact rather
      than from a build-time execution.

      Note this collides with `nbstripout`-style hygiene if it is ever added, and with the
      `check-added-large-files` pre-commit hook if the figures are large — keep figures at a
      reasonable DPI (Phase 8 sets `savefig.dpi`) and check the resulting notebook size before
      committing.

- [ ] **Add a staleness guard.** Committed outputs are the known cost of Decision 5: the docs can
      show results the current code no longer produces, and nothing would notice. Record the
      generating version in the notebook and assert it in CI:

  ```python
  # final cell of workflow_demo.ipynb
  import prospecpy
  print(f"Outputs generated with prospecpy {prospecpy.__version__}")
  ```

  ```yaml
  # in the docs CI job
  - name: Warn if notebook outputs are stale
    run: |
      recorded=$(python - <<'EOF'
      import json, re
      nb = json.load(open("docs/workflow_demo.ipynb"))
      texts = ["".join(o.get("text", "")) for c in nb["cells"] for o in c.get("outputs", [])]
      m = [re.search(r"prospecpy (\S+)", t) for t in texts]
      print(next((x.group(1) for x in m if x), "UNKNOWN"))
      EOF
      )
      current=$(python -c "import prospecpy; print(prospecpy.__version__)")
      [ "$recorded" = "$current" ] || echo "::warning::notebook outputs generated with $recorded, package is $current — consider re-running the notebook"
  ```

  A warning rather than a hard failure, deliberately: outputs will legitimately lag by a patch
  release, and a blocking check would train people to bypass it.

- [ ] **Enable `fail_on_warning`** in `.readthedocs.yml`, and rename to the non-deprecated
      `.readthedocs.yaml`. Safe to do immediately under Decision 5, since nothing executes during the
      build and the MyST-NB execution warnings that would have made this risky cannot occur.

- [ ] **Clean up `docs/workflow_demo.ipynb`** — delete the `sys.path.append("PATH TO src folder")`
      cell entirely (unnecessary once the package is pip-installed), replace the `FILL_IN`
      placeholders using the `get_data_dir()` helper from Phase 6a below, fix `FIIL_IN_raw_data`,
      remove the unused `path_to_output_plots_`, and fix the user-visible typos "cruve fit" and
      "lorentizian".

  > **Coordinate with `plan-arpls-and-fit-qc-integration.md` Phase 4, which rewrites this
  > same notebook** to drop the `interact()` GUI stage and call `subtract_baseline_arpls()`.
  > **Do that plan's Phase 4 first**, then do this cleanup and commit outputs — otherwise
  > this phase commits executed outputs for a workflow that is about to be deleted, and the
  > notebook must be re-run anyway. The two edits are complementary, not conflicting: that
  > plan changes *which cells exist*, this one fixes *paths and typos* in them. The branch's
  > notebook hardcodes `../output_plots/`; it must adopt `get_data_dir()` from Phase 6a
  > rather than introducing a fourth path convention.

- [ ] **Replace `docs/references.bib`** — it is cookiecutter boilerplate (four neuroscience papers
      and *The Ruby Programming Language*), and nothing cites anything. The Bruździak paper is now
      identified (Open Question 2) and should be cited from both the `vaporfit` module docstring and
      the water-vapour explanation page:

  ```bibtex
  @article{bruzdziak2019vapor,
    author  = {Bru{\'z}dziak, Piotr},
    title   = {Vapor correction of {FTIR} spectra --- A simple automatic least squares approach},
    journal = {Spectrochimica Acta Part A: Molecular and Biomolecular Spectroscopy},
    volume  = {223},
    pages   = {117373},
    year    = {2019},
    doi     = {10.1016/j.saa.2019.117373},
  }
  ```

  Add entries for `reference/Baek et al., 2015.pdf` and `reference/Quéméré, 2024.pdf` alongside it.

- [ ] **Commit:** `git commit -m "docs: unblock the RTD build, ship notebook outputs, fail on warnings"`

**Dependencies:** Phase 1 (the notebook cannot be *run locally* to generate outputs without
`ipywidgets` declared), and Phase 6a (the notebook uses `get_data_dir()`).

**Verification:**
- [ ] `pixi run -e docs docs-build` completes locally with zero warnings
- [ ] The built `workflow_demo` page contains rendered `<img>` spectra
- [ ] The Read the Docs build for the PR is green
- [ ] `rg -n "execute_notebooks" docs/_config.yml` shows `off`
- [ ] `git check-ignore -v Hyd2_pH6_data/` confirms no instrument data can be committed accidentally

---

### Phase 6a: Data location — standardise on the gitignored `<repo root>/data/`

**Objective:** `<repo root>/data/` is the one place ProSpecPy looks for instrument data, it is
impossible to commit that data by accident, and `src/`, the notebook, and the devcontainer all agree.

> Per Architectural Decision 7. Today there are **four** different answers to "where is the data".
> Two of them — `.gitignore:142` and `postBuild.sh:6` — already point at `<repo root>/data/`, so this
> phase is mostly making the other two agree rather than inventing a convention.
>
> **Expected layout**, matching what the README and `workflow_demo.ipynb` already describe:
>
> ```text
> <repo root>/
> └── data/                     # gitignored; created by postBuild.sh in Codespaces
>     ├── opus_files/
>     │   ├── water_vapor/      # water-vapour reference spectra
>     │   └── <run name>/       # one folder per experiment
>     └── output_plots/         # written by the pipeline
> ```

**Tasks:**

- [ ] **Extend `.gitignore`.** `data/` is already ignored (`.gitignore:142`), but the real spectra
      currently sitting untracked in the working tree are not covered and are one `git add -A` away
      from being published:

  ```gitignore
  # Local Files for Analysis — instrument data is NEVER committed (see docs/rse/specs)
  data/
  Hyd2_pH6_data/
  *_data/
  # Bruker OPUS files are numbered extensions: sample.0, sample.0022, ...
  *.[0-9]
  *.[0-9][0-9]
  *.[0-9][0-9][0-9]
  *.[0-9][0-9][0-9][0-9]
  # Working notes / Word drafts — not source of truth (PDFs in reference/ are kept)
  reference/Changes.docx
  reference/~$*.docx
  ```

  *Resolved by the project owner (2026-08-07): ignore `reference/Changes.docx` (and Word lock
  files `reference/~$*.docx`); leave `reference/Baek et al., 2015.pdf` and
  `reference/Quéméré, 2024.pdf` unignored so they can be committed. Do **not** ignore the whole
  `reference/` directory.*

  **These patterns were verified against the working tree on 2026-08-07** rather than assumed, since
  an over-broad `*.[0-9]` glob could silently stop tracking source files. With the owner's answer
  applied: **0 of 39 tracked files** match (nothing currently committed would be dropped);
  instrument data and `Changes.docx` / `~$hanges.docx` are ignored; the Baek and Quéméré PDFs are
  **not** ignored and remain available to commit. Re-run the check before merging:

  ```bash
  git ls-files | git -c core.excludesFile=.gitignore check-ignore --no-index --stdin -v
  # must print nothing — any output means the patterns would untrack a real file
  git check-ignore -v "reference/Changes.docx" "reference/~\$hanges.docx"
  # must both match
  git check-ignore -v "reference/Baek et al., 2015.pdf" "reference/Quéméré, 2024.pdf"
  # must print nothing — those PDFs stay commit-able
  ```

- [ ] **Write the failing test**
  - File: `tests/test_paths.py` (new)

  ```python
  from __future__ import annotations

  from pathlib import Path

  import pytest

  from prospecpy.paths import DataDirectoryNotFound, get_data_dir


  def test_env_var_takes_precedence(tmp_path, monkeypatch):
      monkeypatch.setenv("PROSPECPY_DATA_DIR", str(tmp_path))
      assert get_data_dir() == tmp_path


  def test_finds_data_dir_by_walking_up(tmp_path, monkeypatch):
      """A notebook in docs/ must find <repo>/data without relative-path guessing."""
      monkeypatch.delenv("PROSPECPY_DATA_DIR", raising=False)
      (tmp_path / "data").mkdir()
      nested = tmp_path / "docs" / "nested"
      nested.mkdir(parents=True)
      monkeypatch.chdir(nested)
      # .resolve() is required, not incidental: on macOS pytest's tmp_path is
      # under /var, which is a symlink to /private/var, while get_data_dir
      # resolves. Comparing against a bare tmp_path fails on macOS only.
      assert get_data_dir() == tmp_path.resolve() / "data"


  def test_raises_actionable_error_when_absent(tmp_path, monkeypatch):
      monkeypatch.delenv("PROSPECPY_DATA_DIR", raising=False)
      monkeypatch.chdir(tmp_path)
      with pytest.raises(DataDirectoryNotFound, match="PROSPECPY_DATA_DIR"):
          get_data_dir()
  ```

  *All three tests were executed against the implementation below before being recorded here. The
  `.resolve()` in the second test is the result: without it the test passes on Linux CI and fails on
  every macOS developer machine, which is the worst way for a test to be wrong.*

- [ ] **Implement** `src/prospecpy/paths.py`

  ```python
  from __future__ import annotations

  import os
  from pathlib import Path

  DATA_DIR_ENV_VAR = "PROSPECPY_DATA_DIR"
  _MAX_PARENTS = 4


  class DataDirectoryNotFound(RuntimeError):
      """Raised when the ProSpecPy data directory cannot be located."""


  def get_data_dir(start: Path | None = None) -> Path:
      """
      Locate the directory holding OPUS instrument data.

      The canonical location is ``data/`` at the repository root — the
      gitignored folder that ``.devcontainer/postBuild.sh`` creates. Instrument
      data is never committed, so the folder exists only on the user's machine
      and must be located at runtime rather than assumed.

      Resolution order:

      1. ``$PROSPECPY_DATA_DIR`` if set. Checked first because an explicit
         override that a nearby ``data/`` folder could silently defeat would
         not be an override at all. Intended for the cases the convention
         cannot cover: ProSpecPy installed outside a checkout (no repository
         root to walk up to), or spectra kept on an external drive or lab
         share too large to sit inside the repo.
      2. Otherwise — the normal case — the nearest ``data/`` directory found
         by walking up from `start` (or the current working directory), at
         most four levels. The upward walk is what lets a notebook in
         ``docs/`` and a script at the repository root reach the same folder
         without either hardcoding a relative path.

      Parameters
      ----------
      start : Path, optional
          Directory to begin the upward search from. Defaults to the current
          working directory.

      Returns
      -------
      Path
          The resolved data directory.

      Raises
      ------
      DataDirectoryNotFound
          If no directory is found. The message names the environment
          variable so the fix is obvious from the traceback alone.
      """
      configured = os.environ.get(DATA_DIR_ENV_VAR)
      if configured:
          path = Path(configured).expanduser()
          if not path.is_dir():
              msg = f"{DATA_DIR_ENV_VAR} is set to {path!s}, which is not a directory."
              raise DataDirectoryNotFound(msg)
          return path

      here = (start or Path.cwd()).resolve()
      for candidate in [here, *here.parents][:_MAX_PARENTS + 1]:
          if (candidate / "data").is_dir():
              return candidate / "data"

      msg = (
          f"No 'data' directory found at or above {here!s}. Create one at your "
          f"repository root, or set {DATA_DIR_ENV_VAR} to the folder holding your "
          "OPUS files. Instrument data is deliberately not distributed with "
          "ProSpecPy."
      )
      raise DataDirectoryNotFound(msg)
  ```

- [ ] **Export it** from `__init__.py` alongside the other public names.

- [ ] **Update the notebook** to use it, replacing the three inconsistent relative paths — including
      `output_folder`, which cell 6 currently hardcodes to a path that is neither of the other two:

  ```python
  from prospecpy import get_data_dir

  data_dir = get_data_dir()
  path_to_water_vapor_data = data_dir / "opus_files" / "water_vapor"
  path_to_run_data = data_dir / "opus_files" / "hyd2_ph6"
  output_folder = data_dir / "output_plots"
  ```

- [ ] **Document the layout** in the README, replacing the current bare instruction to create a
      `data` folder with the concrete tree shown at the top of this phase. State plainly that `data/`
      lives at the repository root, is gitignored, and is never committed. Add the
      `PROSPECPY_DATA_DIR` override as a clearly-marked exception for out-of-tree data rather than
      as an equal alternative, so the documented happy path stays single.

- [ ] **Make the devcontainer consistent.** `postBuild.sh` already creates the folder once Phase 4
      fixes its path, and `get_data_dir()` finds it by walking up, so **no `remoteEnv` entry is
      needed** — adding one would introduce a second source of truth for a location the convention
      already determines. Verify by opening a Codespace and confirming `get_data_dir()` returns
      `/workspaces/ProSpecPy/data` with no environment variable set.

- [ ] **Commit:** `git commit -m "feat: standardise on gitignored <repo>/data; never commit instrument data"`

**Dependencies:** Phase 1. Phase 4 fixes `postBuild.sh` so the canonical folder actually gets created
in Codespaces; the two should land together or Codespaces users hit `DataDirectoryNotFound`.

**Verification:**
- [ ] `pytest tests/test_paths.py -v` all PASSED
- [ ] `git check-ignore -v Hyd2_pH6_data/` reports a match
- [ ] `git status --short` shows no instrument data as untracked-and-addable
- [ ] `rg -n '\.\./\.\./data' docs/` returns no output

---

### Phase 7: Documentation — API reference and Diátaxis structure

**Objective:** The docs have an API reference and a structure a new user can navigate.

**Tasks:**

- [ ] **Enable autodoc in `docs/_config.yml`.** Jupyter Book does **not** enable
      `sphinx.ext.napoleon` by default, so without it the existing `Parameters:` bullet lists render
      as preformatted blobs:

  ```yaml
  sphinx:
    extra_extensions:
      - sphinx.ext.autodoc
      - sphinx.ext.autosummary
      - sphinx.ext.napoleon
      - sphinx.ext.viewcode
      - sphinx.ext.intersphinx
    config:
      autosummary_generate: true
      autodoc_typehints: description
      autodoc_member_order: bysource
      autoclass_content: both
      autodoc_default_options:
        members: true
        show-inheritance: true
        # deliberately NOT undoc-members: ProSpecPy has ~26 undocumented
        # members and publishing bare signatures looks worse than omitting them
      napoleon_google_docstring: true   # temporary: Args: blocks still exist
      napoleon_numpy_docstring: true
      intersphinx_mapping:
        python: ["https://docs.python.org/3", null]
        numpy: ["https://numpy.org/doc/stable/", null]
        scipy: ["https://docs.scipy.org/doc/scipy/", null]
        pandas: ["https://pandas.pydata.org/docs/", null]
        matplotlib: ["https://matplotlib.org/stable/", null]
    only_build_toc_files: true          # keeps docs/rse/ out of the published site
  ```

  *Set `napoleon_google_docstring: false` once the docstring standardisation below is complete.*

> **Sequence this phase after `plan-arpls-and-fit-qc-integration.md` Phase 4.** That plan
> changes the public surface this phase documents: it **adds** `fit_report` and `cli`, and
> **deletes** `interact.py`, `anchor_point_fit`, `baseline_fit`, `subtract_baseline`,
> `baseline_spline`, and `baseline_correction`. Writing the API reference first means
> documenting six functions that are about to disappear.

- [ ] **Write `docs/reference/api.md`** curating the seven pipeline entry points a scientist
      actually calls, plus the `ProSpecPy` class, rather than dumping all ~60 symbols.
      **Note:** "seven" counts the pre-arPLS pipeline. After that plan's Phase 4 the set
      changes — `subtract_baseline` is replaced by `subtract_baseline_arpls`, and the
      fit-report entry point joins it. Enumerate from the post-merge `__init__.py`, not from
      this list.

- [ ] **Restructure `docs/_toc.yml` along Diátaxis.** The four highest-value pages, which take the
      docs from "one broken notebook" to genuinely usable:
  - `tutorials/first-run` — end-to-end walkthrough. Since no data ships with the package
    (Architectural Decision 5), this must open by telling the reader to put their OPUS files in
    `data/opus_files/<run name>/` at the repository root, per the layout in Phase 6a, then show
    expected output at each stage as static committed figures. Mention `PROSPECPY_DATA_DIR` only as
    an aside for data that cannot live in the repo — a tutorial that opens with an environment
    variable teaches the exception as if it were the rule. Write it against the same run used to
    generate the notebook outputs so the two agree.
  - `howto/choose-threshold-and-adjustment-factor` — **rewrite this page's scope.**
    `adj_factor` is an `interact()` parameter, deleted by
    `plan-arpls-and-fit-qc-integration.md` Phase 4. After that, the tunable parameters are
    the second-derivative `threshold` (which survives, still hand-picked at `0.35`) and the
    arPLS `lam` smoothness parameter. Retitle to `howto/choose-threshold-and-lambda` and
    document those two, using the λ sweep (1e5/1e6/1e7) already in the demo notebook. The
    underlying point stands — this is the workflow's one irreversible judgement and it is
    undocumented — but it is now a judgement about different knobs.
  - `explanation/why-second-derivative` — how d²A/dν̃² resolves overlapping bands invisible in raw
    absorbance, the noise-amplification tradeoff, and why splining before differentiating. The page
    a new grad student needs.
  - `reference/api` — the above
  Further pages (water-vapour rationale, output-file spec, glossary, Gaussian vs Lorentzian
  guidance, citation/reproduction) follow as capacity allows.

- [ ] **Standardise docstrings on numpydoc.** Nothing currently conforms, so this is adoption rather
      than migration. Highest-value targets in order: the `ProSpecPy` class and `__init__`
      (`prospecpy.py:27`, ~26 undocumented members, and the object's whole design is
      "attributes get filled in as stages run" with nothing saying so); `peak_fit.gaussian` /
      `lorentzian` / `peak_fit` (no docstrings; need the functional forms in a `Notes` block plus
      `References`); `vaporfit.AtmFitParams`; the `plot_*` functions.

- [ ] **Discharge the `vaporfit.py` attribution obligation.** The module header asks to be cited and
      names no paper, which is the one docstring defect that is a licence matter rather than a
      quality one. Name the paper, and fix the missing ź in the author's surname:

  ```python
  """
  Automatic least-squares correction of water-vapour contributions to FTIR spectra.

  This module is third-party code contributed by Piotr Bruździak. If you use it,
  please cite the paper describing the algorithm.

  References
  ----------
  .. [1] P. Bruździak, "Vapor correction of FTIR spectra - A simple automatic
         least squares approach," Spectrochimica Acta Part A: Molecular and
         Biomolecular Spectroscopy, vol. 223, p. 117373, 2019.
         :doi:`10.1016/j.saa.2019.117373`
  """
  ```

      Cross-reference it from `remove_wv.py`, which is where users actually invoke the algorithm and
      so where they are most likely to look for what to cite.

- [ ] **Enforce it going forward**, scoped to avoid a 200-error day one:

  ```toml
  [tool.ruff.lint]
  extend-select = [..., "D"]

  [tool.ruff.lint.pydocstyle]
  convention = "numpy"
  ```

- [ ] **Commit:** `git commit -m "docs: add API reference, restructure along Diataxis, adopt numpydoc"`

**Dependencies:** Phase 6.

**Verification:**
- [ ] The built site has a populated API reference page with rendered parameter tables
- [ ] `pixi run -e docs docs-build` still passes with `--warningiserror`

---

### Phase 8: Plot accessibility and FTIR conventions

**Objective:** Every plot is legible in grayscale, distinguishable under colour-vision deficiency,
labelled with units, and oriented to FTIR convention.

> **Scope reduced by `plan-arpls-and-fit-qc-integration.md`. Re-scope before starting.**
>
> Three changes, all verified against the `arPLS-baseline` branch:
>
> 1. **The fitting plots are already done.** Jiarui's `make_plots` already calls
>    `invert_xaxis()`, labels units, and sets `dpi=220`. That plan's Phase 2 moves the code
>    into `peak_fit.py`, so those plots arrive compliant. Audit them, don't rewrite them.
> 2. **`interact.py:130-133` disappears.** That plan's Phase 4 deletes `interact.py`
>    entirely. Do not spend effort on its 1.28:1 red-on-green palette — **verify the file is
>    gone first.** If Phase 4 has not landed, fix it; if it has, strike the task.
> 3. **`invert_xaxis()` on `plot_baseline_corrected_data` is already done**, pulled forward
>    into that plan's Phase 1 Task 7 because after Phase 4 it is the package's only baseline
>    plot and should not ship mirrored. **The `dpi`/rcParams work is deliberately left
>    here** — it is a global decision and splitting it invites conflicting defaults.
>
> Net: this phase keeps the rcParams module, the `vaporfit.py` linewidth/contrast fix, and
> the colour-plus-linestyle redundancy work on surviving plots. Sequence it **after** that
> plan's Phase 4.

**Tasks:**

- [ ] **Add a shared plotting module** `src/prospecpy/_plotting.py` setting rcParams once, fixing
      the DPI/figsize/font class of issues globally:

  ```python
  SPECTRUM_RC = {
      "figure.figsize": (8, 4.5),
      "figure.dpi": 150,
      "savefig.dpi": 300,
      "savefig.bbox": "tight",
      "font.size": 12,
      "lines.linewidth": 1.5,
      "axes.prop_cycle": plt.cycler(
          color=["#0077BB", "#EE7733", "#009988", "#CC3311", "#33BBEE"]
      ),
  }
  ```

- [ ] **Fix the colour and redundancy problem** at `interact.py:130-133` (1.28:1 red-on-green) and
      `baseline.py:149-150` (1.21:1). A palette swap alone does **not** fix grayscale — even the
      recommended `#0077BB`/`#EE7733` pair is 1.68:1 — so colour must be paired with linestyle and
      marker redundancy:

  ```python
  ax.plot(wavenumber, absorbance, color="#0077BB", linestyle="-", linewidth=1.5,
          label="baseline-subtracted")
  ax.plot(peak_wv, peak_abs, color="#CC3311", linestyle="none", marker="o",
          markersize=6, label="peaks")
  ax.plot(anchor_wv, anchor_abs, color="#EE7733", linestyle="none", marker="x",
          markersize=7, label="anchor points")
  ax.plot(base_wv, base_abs, color="#009988", linestyle="--", linewidth=1.5,
          label="baseline fit")
  ```

- [ ] **Raise `vaporfit.py:155-156` from `linewidth=0.5`** to the 1.5pt minimum and move off pure
      red (4.00:1, below the 4.5:1 floor). This is the first figure a scientist sees and the one
      they read to judge whether water-vapour subtraction worked.

- [ ] **Invert the x-axis on every spectrum plot.** No plotting function calls `ax.invert_xaxis()`,
      so matplotlib autoscales to `(min, max)` and **every spectrum currently renders backwards**
      from universal FTIR convention. Cheap fix, large credibility payoff with the target audience.

- [ ] **Fix axis labels** at `second_deriv.py:95` and `:112` (bare `"wavenumber"`, no units),
      `second_deriv.py:113` (`"d2ydx2"` → `d²A/dν̃² (a.u.)`), and `interact.py:135-136` (no units).
      `interact.py:109-110`, `baseline.py:157-158`, `peak_fit.py:69-70`, and `vaporfit.py:162`
      already label correctly and should be left alone — the defect is inconsistency.

- [ ] **Give `save_plot` a real extension and DPI.** `prospecpy.py:85` calls `fig.savefig(full_path)`
      with no `dpi` or `bbox_inches`, and callers pass extension-less filenames that matplotlib
      silently saves as PNG.

- [ ] **Fix the `batch_d` typo** in plot titles at `peak_fit.py:66`, `baseline.py:154`, and
      `second_deriv.py:92`/`:110` (should be `batch_id`; `vaporfit.py:158` already gets it right).
      This one is user-visible in the primary artifact.

- [ ] **Commit:** `git commit -m "fix: accessible plot colours, FTIR axis orientation, unit labels, output DPI"`

**Dependencies:** None technically; sequence after Phase 7 so the docs rebuild picks up the new
figures.

**Verification:**
- [ ] Every saved figure remains interpretable when converted to grayscale
- [ ] All plot colour pairs meet 4.5:1 against the background and are distinguished by marker or
      linestyle as well as hue
- [ ] `rg -n "invert_xaxis" src/prospecpy/` shows a call in every spectrum-plotting function
- [ ] `rg -n "batch_d\b" src/prospecpy/` returns no output

---

## Success Criteria

### Automated Verification

- [ ] `python -m venv /tmp/v && /tmp/v/bin/pip install . && /tmp/v/bin/python -c "from prospecpy.interact import interact"` exits 0
- [ ] `pytest tests/ -v` — all tests pass
- [ ] The 19-sample end-to-end snippet in Phase 2 prints `19 samples, 19 distinct names`
- [ ] `rg -n "uw-ssec" --glob '!pixi.lock' --glob '!docs/rse/**' .` returns no output
- [ ] `rg -n "openpyxl" src/ tests/ docs/` returns no output
- [ ] `rg -n "^import re" src/prospecpy/io.py` returns no output
- [ ] `ls requirements.txt docs/requirements.txt .devcontainer/environment.yml` reports all missing
- [ ] `pixi run -e docs docs-build` completes with zero warnings
- [ ] `pipx run build && pipx run twine check dist/*` passes with no deprecation warnings
- [ ] `rg -n "batch_d\b" src/prospecpy/` returns no output
- [ ] `git ls-files | git check-ignore --no-index --stdin -v` returns no output — proves the data
      patterns do not untrack any real file
- [ ] `git check-ignore -v Hyd2_pH6_data/` reports a match — proves instrument data cannot be
      committed by accident
- [ ] `rg -n '\.\./\.\./data' docs/ src/` returns no output — the broken relative paths are gone
- [ ] `pipx run cffconvert --validate` passes
- [ ] `python -c "import yaml; d=yaml.safe_load(open('CITATION.cff')); assert d['doi']=='10.5281/zenodo.15330895'"` exits 0

### Manual Verification

- [ ] A scientist on Windows can `pixi install` and run the demo notebook
- [ ] A scientist who clicks the Codespaces badge in the README lands in a working container: `data`
      directory present, `interact()` importable, demo notebook runs with live widgets
- [ ] The published Read the Docs `workflow_demo` page shows rendered spectra, not a traceback
- [ ] Every published figure is interpretable printed in grayscale
- [ ] Spectra render with wavenumber decreasing left-to-right
- [ ] GitHub's "Cite this repository" widget produces a citation containing the concept DOI
      `10.5281/zenodo.15330895`, not the v0.1.0 version DOI
- [ ] A user whose data lives outside the repo (external drive, network mount) can run the pipeline
      by setting `PROSPECPY_DATA_DIR` alone, with no code edits

---

## Testing Strategy

**Unit Test Coverage (written in-phase above):**
- `tests/test_dependencies.py` — the interactive stage imports from a clean install
- `tests/test_batch_id_sample_name.py` — all four path layouts plus a Windows-guarded case and an
  explicit collision regression guard

**Integration Tests:**
- The 19-sample end-to-end check in Phase 2 runs against the real `Hyd2_pH6_data` tree. Under
  Architectural Decision 5 this data is never committed, so **this check stays a locally-run manual
  gate and cannot be promoted to CI.** That is a genuine and permanent coverage gap: the full
  pipeline is never exercised end-to-end by an automated run. Two partial compensations, neither a
  substitute:
  - Mark it `@pytest.mark.integration`, skipped unless `PROSPECPY_DATA_DIR` is set, so it is at
    least a single command for a maintainer with data rather than a manual procedure.
  - Keep unit coverage of the path logic (`test_batch_id_sample_name.py`) and the fitting failure
    isolation high, since those are where the Phase 2 check actually found bugs.

  If the group later deposits a citable dataset on Zenodo, fetching it with `pooch` in a scheduled
  (not per-PR) CI job would close this gap without violating the policy.

**Test Data Requirements:**
- Phases 1–5, 6a, 7, and 8 need no instrument data. Phase 6a's tests use `tmp_path` fixtures with
  fabricated directory trees, which is sufficient because it tests *path resolution*, not file
  parsing.
- Phase 2's end-to-end verification uses the existing untracked `Hyd2_pH6_data/`, supplied locally
  by the maintainer via `PROSPECPY_DATA_DIR`
- Phase 6 needs real data **once**, locally, to generate the notebook outputs that are then
  committed. This is a one-time manual step by someone who already holds the data, repeated only when
  the outputs are refreshed.
- **No phase requires data to be present in CI**, which is what makes the policy in Architectural
  Decision 5 implementable rather than merely aspirational.

---

## Migration Strategy

**Backward Compatibility:**
- Adding `ipywidgets`/`ipython`: additive; no existing install breaks
- Removing `openpyxl`: it is unused, so nothing can depend on it through this package
- `batch_id_sample_name` on paths containing `opus_files`: **unchanged output**
- `batch_id_sample_name` on paths without `opus_files`: was `(None, None)`, now `(None, <filename>)`.
  This is the intended fix. No caller can depend on the old behaviour because it crashed.
- Deleting `requirements.txt` / `docs/requirements.txt` / `.devcontainer/environment.yml`: verified
  unreferenced
- Plot appearance **does** change in Phase 8 (colours, axis orientation). This is deliberate and
  user-visible; announce it in the changelog. No numerical output changes.

**Rollback Plan:**
Each phase is a separate commit and can be reverted with `git revert <sha>` independently, with the
sequencing exceptions noted under each phase's Dependencies.

---

## Risk Assessment

1. **Risk:** Phase 8 changes every published figure's appearance, invalidating figures in
   in-progress manuscripts
   - **Likelihood:** Medium — the package is in active scientific use
   - **Impact:** Medium — cosmetic, but a scientist mid-write-up will notice
   - **Mitigation:** Announce in the changelog; the underlying numerical outputs and CSVs are
     untouched, so figures can be regenerated identically apart from styling

2. **Risk:** Adding `win-64` to pixi surfaces a dependency that has no Windows conda-forge build
   - **Likelihood:** Low — the stack is numpy/scipy/pandas/matplotlib/ipywidgets, all of which build
     on Windows; `brukeropusreader` is pure Python
   - **Impact:** Medium — would block the relock
   - **Mitigation:** `brukeropusreader` stays a PyPI dependency; if a conda package is missing,
     move it to `[tool.pixi.pypi-dependencies]`

3. **Risk:** `fail_on_warning: true` blocks the docs build on benign MyST-NB warnings
   - **Likelihood:** **Low, reduced from Medium.** The warnings this risk anticipated — missing
     kernel metadata, cached-output mismatches — are all *execution* warnings, and Architectural
     Decision 5 sets `execute_notebooks: off`, so they cannot arise.
   - **Impact:** Low — blocks a docs build, not a release
   - **Mitigation:** No longer needs sequencing after sample data (which is never committed);
     `fail_on_warning` can be enabled in the same commit as the rest of Phase 6.

4. **Risk:** The `python = ">=3.11,<3.14"` pixi cap needs bumping every Python release
   - **Likelihood:** High (annually)
   - **Impact:** Low
   - **Mitigation:** Accepted deliberately. An unconstrained float is how developers ended up on
     3.13 while CI tested 3.11/3.12; an annual one-line bump is the cheaper failure mode.

5. **Risk:** Phase 2 conflicts with Phase 4 of the improvements plan if both are implemented
   - **Likelihood:** Medium — two plans, possibly two people
   - **Impact:** Medium — merge conflict in `io.py`, or the weaker version silently wins
   - **Mitigation:** Stated explicitly at the top of Phase 2 and in the improvements plan's Phase 4.
     Whoever implements first should mark the other phase complete.

6. **Risk:** Committed notebook outputs drift from the code, so the published documentation shows
   results the current version no longer produces
   - **Likelihood:** **High over time.** This is the direct and unavoidable cost of Architectural
     Decision 5 — outputs are now a hand-maintained artifact, and nothing forces anyone to refresh
     them. Documentation staleness is also the failure mode least likely to be noticed by
     maintainers, because it is invisible from inside the repository and only visible to readers.
   - **Impact:** Medium — erodes trust in the docs, and can mislead a scientist into expecting output
     the pipeline does not produce
   - **Mitigation:** The Phase 6 staleness guard records the generating `prospecpy` version in the
     notebook and warns in CI when it diverges. Deliberately a warning, not a hard failure, since
     outputs will legitimately lag a patch release and a blocking check trains people to bypass it.
     Add re-running the notebook to the release checklist so the refresh has an owner and a moment.

---

## Edge Cases and Error Handling

1. **Case:** `batch_id_sample_name` called on a path that is a bare filename with no directory
   - **Expected Behavior:** `(None, "<filename>")` — `Path("x.0").name` is `"x.0"`
   - **Implementation:** Phase 2, the `return None, path.name or None` fallback

2. **Case:** `batch_id_sample_name` called on a path ending in a separator (no filename component)
   - **Expected Behavior:** `(None, None)` — `Path("a/b/").name` is `""`, and `"" or None` is `None`
   - **Implementation:** Phase 2, the `or None` guard

3. **Case:** `opus_files` is the final path component with nothing after it
   - **Expected Behavior:** Falls through to the filename fallback rather than returning
     `(None, None)`, because `after` is empty and the `if` block does not return
   - **Implementation:** Phase 2, control flow falls past both `if len(after)` branches

4. **Case:** Two samples in different batch directories share a filename
   - **Expected Behavior:** Distinct output folders, because `batch_id` differs
   - **Implementation:** Unchanged from current behaviour for `opus_files` layouts. **Note:** two
     samples in *the same* directory with the same filename is impossible on any filesystem, so the
     fallback cannot collide within a single run.

---

## Performance Considerations

No phase in this plan changes pipeline runtime. For calibration, the full 7-stage pipeline over 19
real samples measures **5.0 seconds end to end**, with per-stage costs of roughly 53 ms (water
vapour), 69 ms (second derivative), 82 ms (baseline correction), and 28/26 ms (Gaussian/Lorentzian)
per sample. This is the measurement that rules out orchestration frameworks, and it is also why the
performance phase of the improvements plan is lower priority than that document originally assumed.

---

## Documentation Updates

- [ ] `README.md` — add `pip install prospecpy`, a PyPI badge, and a link to the Read the Docs site
      (currently the only documented install path is Codespaces, and the docs site is not linked
      from the front door at all)
- [ ] `README.md` — replace the bare "create a data folder" instruction with the concrete
      `<repo root>/data/` tree from Phase 6a, stating that it is gitignored and never committed.
      This is now the project's canonical data convention, so the README is where it has to be
      unambiguous
- [ ] `CONTRIBUTING.md` — new; `README.md:53-56` solicits contributions and `CODE_OF_CONDUCT.md`
      implies a process, but nothing documents `pixi install`, running tests, or pre-commit
- [ ] `CHANGELOG.md` — lower priority than usual: `.github/release.yml` already configures
      GitHub's auto-generated release notes, which covers most of the need at this stage
- [ ] `docs/_toc.yml` — surface `CODE_OF_CONDUCT.md`, `LICENSE`, and `CONTRIBUTING.md`, none of
      which currently appear on the site
- [ ] `docs/intro.md:21` — "Check out the workflow_demo.ipynb notebook and our README" is plain
      text with no links

---

## Open Questions

**All six questions are now resolved.** They are retained below with their answers, because each
one changed the plan and the reasoning is worth preserving.

1. ~~**May the `Hyd2_pH6_data/` spectra be committed under BSD-3?**~~ **Resolved 2026-08-07 — no.**
   The project owner's direction is that no data is pushed to GitHub at all. This is broader than the
   question asked: it is not that consent was unavailable for these particular spectra, but that
   committed instrument data is out of scope as a matter of policy. Phase 6 was rewritten around
   committed notebook outputs with `execute_notebooks: off`, and Phase 6a was added to give `src/`,
   the notebook, and the devcontainer one shared answer for where data lives. Recorded as
   Architectural Decisions 5 and 7.

   **Follow-up resolved 2026-08-07:** the canonical location is **`<repo root>/data/`** — the
   gitignored folder `.devcontainer/postBuild.sh` already creates. Everything else is made consistent
   with it, rather than a new location being introduced. Recorded as Architectural Decision 7.

2. ~~**What Bruzdziak paper does `vaporfit.py` want cited?**~~ **Resolved 2026-08-07.** Bruździak, P.
   (2019), "Vapor correction of FTIR spectra — A simple automatic least squares approach,"
   *Spectrochimica Acta Part A: Molecular and Biomolecular Spectroscopy* **223**, 117373,
   [doi:10.1016/j.saa.2019.117373](https://doi.org/10.1016/j.saa.2019.117373). Metadata confirmed via
   CrossRef. Note the author's name is **Bruździak** (with ź); the `vaporfit.py` header spells it
   "Bruzdziak", which should be corrected so the attribution is searchable. The paper's subject —
   automatic least-squares vapour correction — confirms it is the source algorithm for `vaporfit`,
   not merely a related reference. Cited from `docs/references.bib` in Phase 6 and from the module
   docstring in Phase 7.

3. ~~**What is the concept DOI behind the Zenodo badge?**~~ **Resolved 2026-08-07 —
   `10.5281/zenodo.15330895`, and the owner has chosen to use it** as the top-level `doi:` in
   `CITATION.cff`. Retrieved from the Zenodo API by following the badge's `latestdoi/836894886`
   redirect to record 15330896 and reading its `conceptdoi` field. The version DOI for v0.1.0
   (released 2025-05-03) is `10.5281/zenodo.15330896` and is retained under `identifiers:` for
   version-specific reproducibility. Both are recorded in the Phase 3 `CITATION.cff` task.

4. ~~**Should the released `version` in `CITATION.cff` track git tags?**~~ **Resolved 2026-08-07 —
   yes, synced automatically in `cd.yml`,** which the owner selected over the manual
   fail-the-release alternative. `version` and `date-released` are the only hand-written version
   numbers left once hatch-vcs derives everything else from tags, so they will drift, and the drift
   is invisible to maintainers while visible to everyone citing the work. Phase 3 specifies the job,
   including the three details that make this pattern silently no-op in practice (checking out `main`
   rather than the detached tag, using the release's `published_at` rather than today's date, and
   failing on a zero-match substitution) and the one accepted limitation: the sync commit lands one
   commit after the tag, so the archive Zenodo captures still contains the previous file. The DOI and
   the version Zenodo records are unaffected.

5. ~~**Does the devcontainer remain supported?**~~ **Resolved 2026-08-07 — yes**, for development,
   contribution, and end-user usage via GitHub Codespaces. Recorded as Architectural Decision 6.

6. ~~**Should `reference/` be git-ignored as well?**~~ **Resolved 2026-08-07 — no for the PDFs;
   yes for `Changes.docx`.** The owner directed: leave `reference/Baek et al., 2015.pdf` and
   `reference/Quéméré, 2024.pdf` available to commit; ignore `reference/Changes.docx` (and Word
   lock files `reference/~$*.docx`). Do not ignore the whole `reference/` directory. Phase 6a's
   `.gitignore` task records this.

---

## References

**Files Analysed:**
- `pyproject.toml`, `pixi.lock`, `requirements.txt`, `docs/requirements.txt`
- `.devcontainer/{devcontainer.json,environment.yml,postBuild.sh}`
- `.github/workflows/{ci.yml,cd.yml}`, `.github/dependabot.yml`
- `.readthedocs.yml`, `.pre-commit-config.yaml`, `.coveragerc`, `.gitattributes`
- `CITATION.cff`, `README.md`, `LICENSE`, `CODE_OF_CONDUCT.md`
- `docs/{_config.yml,_toc.yml,intro.md,references.bib,workflow_demo.ipynb}`
- `src/prospecpy/{__init__,io,interact,prospecpy,baseline,peak_fit,second_deriv,vaporfit,cut_range}.py`
- `tests/test_import.py`

**External Documentation:**
- [PEP 639 — Improving License Clarity](https://peps.python.org/pep-0639/)
- [Scientific Python Development Guide](https://learn.scientific-python.org/development/)
- [Diátaxis](https://diataxis.fr/)
- [pixi documentation](https://pixi.sh/latest/)
- [`prefix-dev/setup-pixi`](https://github.com/prefix-dev/setup-pixi)
- [Jupyter Book: Sphinx configuration](https://jupyterbook.org/en/stable/advanced/sphinx.html)
- [WCAG 2.1 contrast minimum](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)
- [Paul Tol, colour schemes for accessible figures](https://personal.sron.nl/~pault/)
- [Citation File Format 1.2.0 schema guide](https://github.com/citation-file-format/citation-file-format/blob/main/schema-guide.md)
- [Zenodo: versioning and concept DOIs](https://help.zenodo.org/docs/deposit/describe-records/versioning/)

**Scientific References:**
- Bruździak, P. (2019). "Vapor correction of FTIR spectra — A simple automatic least squares
  approach." *Spectrochimica Acta Part A: Molecular and Biomolecular Spectroscopy*, **223**, 117373.
  [doi:10.1016/j.saa.2019.117373](https://doi.org/10.1016/j.saa.2019.117373) — the algorithm
  implemented in `src/prospecpy/vaporfit.py`, and the citation its module header requests.

**Persistent Identifiers for this software:**
- Concept DOI (all versions): [10.5281/zenodo.15330895](https://doi.org/10.5281/zenodo.15330895)
- Version DOI (v0.1.0, 2025-05-03): [10.5281/zenodo.15330896](https://doi.org/10.5281/zenodo.15330896)

---

## Review History

### Version 1.0 — 2026-08-07
- Initial plan created from three parallel audits: a Prefect/orchestration evaluation, a
  packaging + pixi audit against the Scientific Python guides, and a documentation + accessibility
  audit.
- All line-number citations, dependency claims, contrast ratios, and the `\s` SyntaxWarning were
  independently re-verified against the working tree before being recorded here.
- Orchestration frameworks were evaluated and rejected on measured evidence (5.0 s pipeline vs ~4 s
  Prefect fixed overhead; `interact()` incompatible with both `pause_flow_run` and
  `suspend_flow_run`). Recorded under "What We're NOT Doing" so the question is not reopened without
  new information.

### Version 1.1 — 2026-08-07

**Open Question 5 resolved by the project owner:** the devcontainer is a supported entry point, with
the stated goal that users can take advantage of GitHub Codespaces for development, contribution,
and **usage** of ProSpecPy. Recorded as Architectural Decision 6 and removed from Open Questions.

The "usage" half of that goal is what changed the plan, because it means the devcontainer is a
supported way for a bench scientist to *run* the package rather than only a contributor
convenience, so it now carries the same correctness bar as a `pip install`. Consequences worked
through and folded in:

- **Reinforces Decision 1** (ipywidgets/IPython as core dependencies rather than an optional
  extra). Under an extra, a Codespaces user would receive a container in which the documented
  workflow cannot run.
- **Re-graded the `postBuild.sh` workspace-path bug** from cosmetic to user-facing: end users are
  told by the README to use a `data` folder that the container creates under the project's former
  name, so the documented first step has already silently failed somewhere they will not look.
- **Two further defects found** while re-reading `devcontainer.json` for this decision, both now
  Phase 4 tasks: `postCreateCommand` invokes the script with `sh` (`devcontainer.json:16`), which
  ignores a bash shebang and would break the strict-mode script the plan proposes; and the base
  image is unpinned at `quay.io/pangeo/base-image:latest` (`devcontainer.json:3`), so every
  Codespaces user's environment changes without warning — tolerable for a scratch dev box, not for
  a supported usage path. Pinning it also removes the accident that has been masking the
  undeclared-`ipywidgets` bug, since the pangeo image happens to supply it.
- **Added a devcontainer CI job** to Phase 5. A supported entry point that nothing builds is how
  this rotted to the point of referencing a former project name; the job asserts both the `data`
  directory and the `interact` import, which are the specific Phase 4 and Phase 1 regressions.
- **Re-prioritised the `README.md:49` org fix** within Phase 3. It is the Codespaces badge, so under
  this decision it is the primary advertised entry point and currently points at the wrong
  repository.
- Added a Codespaces line to Desired End State, a manual Codespaces check to Success Criteria, and
  three verification items to Phase 4.

### Version 1.2 — 2026-08-07

**The four remaining Open Questions were answered, closing all five.** Two were resolved by the
project owner and two by lookup rather than by asking, since both had a factual answer available.

**Open Question 1 — data release: resolved "no", and more broadly than asked.** The owner's
direction is that no data is pushed to GitHub as a matter of policy, not that consent happened to be
unavailable for these particular spectra. This reversed Architectural Decision 5, which had proposed
committing ≈370 KB of real spectra, and rewrote Phase 6 around committed notebook outputs. The
consequences ran further than the one phase:

- `execute_notebooks` must be **`off`** — it is now the only setting compatible with the policy,
  since `force`, `auto`, and `cache` all execute a notebook that has no stored outputs.
- `fail_on_warning` became *safer*, not riskier, and no longer needs sequencing behind sample data.
  Risk 3 was downgraded from Medium to Low accordingly, because the warnings it anticipated were all
  execution warnings that can no longer occur.
- **A new permanent cost was accepted and recorded rather than glossed:** committed outputs can go
  stale silently, showing readers results the code no longer produces. Added as Risk 6 with a CI
  staleness guard that warns (not fails) when the notebook's recorded version diverges.
- **A coverage gap was acknowledged:** the 19-sample end-to-end check can never run in CI, so the
  full pipeline is never exercised by an automated run. Recorded honestly in Testing Strategy with
  two partial compensations, neither described as a substitute.

**Phase 6a added — one data-location convention.** Investigating "where should things look for the
data" turned up **four mutually inconsistent answers** in the repo, of which at most one can be
right: `.gitignore:142` ignores `data/` at the repo root, `postBuild.sh:6` creates `<workspace>/data`
at the repo root, but `workflow_demo.ipynb` cell 4 reads `../../data/...` — which from `docs/`
resolves **outside the repository** — and cell 6 writes to a fourth path while the
`path_to_output_plots_` variable defined in cell 4 is never used. With data now permanently external,
this had to become explicit, so Phase 6a adds a `get_data_dir()` helper (env var, then upward search)
used by `src/`, the notebook, and the devcontainer alike. Recorded as Architectural Decision 7.

The proposed `.gitignore` patterns were **verified against the working tree rather than assumed**,
because an over-broad OPUS glob like `*.[0-9]` could silently untrack source files. Result: 0 of 39
tracked files matched, 26 of 27 untracked entries matched, and the single miss is `docs/rse/specs/`,
which should be committed. A re-check command is included in the task.

**Open Question 2 — Bruździak citation: resolved** to
[doi:10.1016/j.saa.2019.117373](https://doi.org/10.1016/j.saa.2019.117373), supplied by the owner and
confirmed against CrossRef. The paper's subject, automatic least-squares vapour correction, confirms
it is the source algorithm rather than a related reference. Added a Phase 7 task to discharge the
attribution obligation in the `vaporfit.py` header, a BibTeX entry to Phase 6, and a correction
throughout: the surname is **Bruździak**, which the module header misspells without the ź.

**Open Questions 3 and 4 — DOIs and CFF versioning: resolved by lookup.** Following the README badge
redirect to Zenodo record 15330896 and reading its metadata gave both identifiers: concept DOI
`10.5281/zenodo.15330895`, version DOI `10.5281/zenodo.15330896` (v0.1.0, 2025-05-03). The Phase 3
task now specifies which goes where and why, since recording only the version DOI — the easy mistake,
as it is what the badge link resolves to — would pin every citation to v0.1.0 forever. On versioning:
`version` and `date-released` are the only hand-written version numbers left once hatch-vcs derives
the rest from tags, so they will drift silently; Phase 3 adds a release-time sync with a
fail-the-release assertion as the lighter alternative.

**One new question raised (6):** whether `reference/` should be ignored too. Resolved in v1.4.

### Version 1.3 — 2026-08-07

Three owner decisions, all of which narrowed the plan rather than expanding it.

**Data location: standardise on the gitignored `<repo root>/data/` created by `postBuild.sh`.**
Architectural Decision 7 was rewritten around this. The practical effect is that v1.2 was solving a
slightly wrong problem: it framed the four inconsistent conventions as needing a *new* answer, when
two of the four — `.gitignore:142` and `postBuild.sh:6` — already agreed on `<repo root>/data/` and
simply needed the other two corrected to match. `get_data_dir()` is retained, but reframed as the
mechanism that makes one location reachable from any working directory rather than as a location
policy of its own, and `PROSPECPY_DATA_DIR` is demoted from co-equal mechanism to documented escape
hatch for out-of-tree data.

Consequences worked through while making this consistent:

- **`postBuild.sh:6` was re-graded again**, and this is the one that matters. It hardcodes
  `/workspaces/hydrogenase-ftir/data` — the project's former name — so the canonical folder is *not
  actually created* in Codespaces today; a stray directory appears beside the workspace instead. Once
  this folder is the convention everything else depends on, that bug stops being cosmetic drift and
  becomes the thing that breaks Codespaces users on first run. Phases 4 and 6a must land together.
- **Corrected a defect in the plan's own proposed fix.** Phase 4 had proposed
  `mkdir -p "${CONTAINER_WORKSPACE_FOLDER:-/workspaces/ProSpecPy}/data"`. That is wrong:
  `containerWorkspaceFolder` is a `devcontainer.json` substitution variable, not a shell environment
  variable, so it never expands inside the script. Replaced with a bare `mkdir -p data`, which is
  correct because `postCreateCommand` runs with the workspace folder as cwd, and which additionally
  cannot go stale if the repository is renamed again — the exact failure mode being fixed.
- **Dropped the proposed `remoteEnv` entry.** With `postBuild.sh` creating the folder and
  `get_data_dir()` finding it, setting `PROSPECPY_DATA_DIR` in the devcontainer would add a second
  source of truth for a location the convention already determines.
- **Fixed a contradiction introduced while editing:** the `get_data_dir` docstring briefly described
  the upward walk as taking precedence over the environment variable, while the implementation
  checked the variable first. The implementation is right — an override a nearby `data/` folder could
  silently defeat is not an override — and the docstring now says so explicitly.
- Added the expected directory tree to Phase 6a and to the README task, since "create a data folder"
  is what the README says today and it is not specific enough to be the canonical convention.

**Citation: use the concept DOI** (`10.5281/zenodo.15330895`) as the top-level `doi:`, with the
v0.1.0 version DOI retained under `identifiers:`. Phase 3 updated from recommendation to decision.

**Citation versioning: auto-sync in `cd.yml`,** chosen over the manual fail-the-release alternative.
Phase 3 now specifies the full job rather than a sketch, because the sketch would not have worked:
it checked out the release tag, which is detached and cannot be pushed to. Also corrected to use
`github.event.release.published_at` instead of `date.today()` (these differ for drafted releases,
and `date-released` should record the release), and to use `re.subn` with a zero-match failure
instead of `re.sub`, since a substitution that matches nothing succeeds silently and would
reintroduce precisely the drift the job exists to prevent. One limitation is now stated rather than
left to be discovered: the sync commit lands one commit after the tag, so the source archive Zenodo
captures still holds the previous `CITATION.cff`. The DOI and recorded version are unaffected, as
both come from the GitHub release itself.

### Version 1.4 — 2026-08-07

**Open Question 6 resolved by the project owner:** ignore `reference/Changes.docx` (and Word lock
files `reference/~$*.docx`); leave the Baek 2015 and Quéméré 2024 PDFs unignored so they can be
committed. Phase 6a's `.gitignore` task no longer proposes ignoring the whole `reference/`
directory — that was the wrong default once the owner distinguished working notes from the papers
the docs already cite by filename.
