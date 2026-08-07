# Implementation Plan: ProSpecPy Codebase Improvements

---
**Date:** 2026-08-07
**Author:** AI Assistant
**Status:** Draft
**Related Documents:**
- `plan-prospecpy-blockers-and-infrastructure.md` — packaging, environment, documentation.
  **Its Phase 2 supersedes this plan's Phase 4.**
- `plan-arpls-and-fit-qc-integration.md` — merges the arPLS baseline and QC peak fitting from
  the `arPLS-baseline` branch. **It supersedes this plan's Phase 5.**
- *(No prior research doc — findings synthesised from direct codebase analysis)*

---

## Overview

ProSpecPy is an FTIR spectroscopy data processing package for Bruker instruments. It implements a
seven-stage pipeline: load → range cut / water-vapour subtraction → second derivative → peak
finding → anchor points → baseline correction → Gaussian / Lorentzian peak fitting.

This plan addresses thirteen issues identified through static analysis: one debug artefact, four
correctness bugs, one O(n²) hot loop, two portability gaps, two usability blockers, two code-
quality issues, and one ambiguous ownership problem. The changes are grouped into five independent
phases ordered by risk (lowest first) so each phase can be merged and validated before the next
begins.

> **Scope boundary.** A companion plan,
> `plan-prospecpy-blockers-and-infrastructure.md`, covers packaging, environment, and documentation
> defects — including two that make the package unusable outside GitHub Codespaces. Two points of
> contact matter here: **that plan's Phase 2 supersedes this plan's Phase 4**, and its Phase 1
> (declaring the undeclared `ipywidgets`/`IPython` dependencies) should land before this plan's
> Phase 1 adds package-root exports. Neither plan changes any numerical output.

> **⚠️ Phase 5 of this plan is superseded by `plan-arpls-and-fit-qc-integration.md`.**
> That plan merges two student contributions from the `arPLS-baseline` branch: an automatic
> arPLS baseline that **replaces** the anchor-point/GUI method, and a QC-instrumented peak
> fitter. Phase 5 below optimises `baseline_correction`, `baseline_spline`, and
> `subtract_baseline` — all three of which that plan's Phase 4 **deletes**. Do not implement
> Phase 5; see "Phase 5" below for the full notice. Phase 3's failure-isolation and
> transposed-argument fixes are **not** superseded and are still needed.

**Goal:** A ProSpecPy package where new users can `from prospecpy import ProSpecPy`, re-run
notebooks without hitting `FileExistsError`, and receive explicit feedback when processing fails —
without any change to numerical pipeline outputs.

**Motivation:** The package is in active scientific use. Correctness bugs (silent exception
swallowing, unreachable `save_plot` branch) mask failures; the O(n²) loop limits scalability; the
absent `__init__` exports force users to know internal module names; hardcoded path separators
break on Windows.

---

## Current State Analysis

**Existing Implementation:**

- `src/prospecpy/__init__.py:1-3` — exports only `VERSION`; all other public symbols are inaccessible at the package level
- `src/prospecpy/prospecpy.py:28-34` — `__init__` raises `FileExistsError` unconditionally if output folder exists
- `src/prospecpy/prospecpy.py:71-87` — `save_plot`: `os.path.exists(self.output_folder)` checked before `self.output_folder == None`; `os.path.exists(None)` raises `TypeError` (`"stat: path should be string, bytes, os.PathLike or integer, not NoneType"`), so the `None` branch is unreachable
- `src/prospecpy/prospecpy.py:262-353` — `subtract_baseline`: `raw_spline(self.get_subtracted_spectra_wavenumber(), self.get_subtracted_spectra_absorbance())` called **seven** times with identical arguments (verified via `grep -n "raw_spline(" src/prospecpy/prospecpy.py`: lines 267, 271, 278, 282, 290, 305, 324 are all inside `subtract_baseline`; two more calls at lines 362 and 417 belong to `gaussian_fit_baseline`/`lorentzian_fit_baseline` respectively and are out of scope for this fix)
- `src/prospecpy/prospecpy.py:356-406` — `gaussian_fit_baseline`: `except Exception as e: print(...)` swallows the error silently
- `src/prospecpy/prospecpy.py:408-455` — `lorentzian_fit_baseline`: same bare-except pattern
- `src/prospecpy/io.py:44` — `raw_data[i.name] = read_file(i)` reads the file
- `src/prospecpy/io.py:54` — `new_prospecpy_obj.set_raw_data(read_file(i), ...)` reads the same file again
- `src/prospecpy/io.py:81` — `re.search("opus_files\s*(.*)", filepath)` requires the literal string `opus_files` in the path
- `src/prospecpy/io.py:90` — `batch_id_file_name_path.split("/")` hardcodes POSIX separator
- `src/prospecpy/baseline.py:79-94` — `baseline_correction`: per-point `diff_array.idxmin()` over 1000-element DataFrame = O(n²)
- `src/prospecpy/baseline.py:113-123` — `get_baseline_peak_index`: `if range_val > 1000: break` exits silently without warning
- `src/prospecpy/remove_wv.py:36` — `print(raw_spectra["Sample"]["SNM"][0:4])` debug statement
- `src/prospecpy/peak_fit.py:80,89` and `src/prospecpy/peak_fit.py:92,101` — **`save` and `showplot`
  are transposed.** Both batch wrappers declare `(objects, show_plots=False, save=True, verbose=True)`
  and call the method positionally as `gaussian_fit_baseline(show_plots, save, verbose)`, but the
  method signature is `gaussian_fit_baseline(self, save=True, showplot=True, verbose=True)`
  (`src/prospecpy/prospecpy.py:356` and `:408`). So `show_plots` lands in `save` and `save` lands in
  `showplot`. `src/prospecpy/second_deriv.py:130` and `src/prospecpy/baseline.py:175` pass the
  correct order, which is what makes this a slip rather than a convention.

**Current Limitations:**
- `from prospecpy import ProSpecPy` raises `ImportError`; users must use `from prospecpy.prospecpy import ProSpecPy`
- Re-running a notebook cell that calls `ProSpecPy(path)` always raises `FileExistsError`
- A failed Gaussian or Lorentzian fit prints one line and continues silently; the output CSVs are never written
- `batch_id_sample_name` returns `(None, None)` on any path that does not contain the literal string `opus_files`, and fails on Windows. **Measured consequence:** on the project's own `Hyd2_pH6_data/examples for you to try/` tree (no `opus_files` component), every sample resolves to the same `<output>/None/None` folder and the pipeline dies with `FileExistsError` on the second sample — so ProSpecPy currently cannot run on its own data. Fixed in `plan-prospecpy-blockers-and-infrastructure.md` Phase 2, not here.
- `baseline_correction` is O(n²) in spectrum length. The originally estimated "~1 second per spectrum at 1000 points" was not measured; the **measured** cost on real data is **82 ms per sample** at the 157-point length produced by the 2150–1850 cm⁻¹ range used in `docs/workflow_demo.ipynb`. The quadratic growth is real and worth fixing, but it is not currently a bottleneck — see the revised Phase 5 priority.
- `subtract_baseline` computes `UnivariateSpline` seven times over the same data
- Gaussian and Lorentzian fits fail on **8 of the 19** real samples in `Hyd2_pH6_data/examples for you to try/` (`maxfev` exhaustion), all silently swallowed today. This is the measured basis for the revised Phase 3 risk assessment.

---

## Desired End State

**New Behavior:**
- `from prospecpy import ProSpecPy, import_run_data` works out of the box
- `ProSpecPy(path, exist_ok=True)` reuses an existing folder; default behaviour (fail on existing) is preserved
- `save_plot` is safe when `output_folder` is `None`
- A failed peak fit raises the exception after printing context; the caller knows the fit failed
- `batch_id_sample_name` uses `pathlib.Path.parts` and works on Windows and on paths that do not contain `opus_files`
- `baseline_correction` runs in O(n log n) using `np.interp`; output is numerically equivalent to the
  original within a small, derived tolerance for all tested spectra (exact agreement when baseline
  and raw wavenumber grids coincide; a slope-dependent bound otherwise — see Key Architectural
  Decision 1)
- `subtract_baseline` calls `raw_spline` once and reuses the result
- `get_baseline_peak_index` emits a `warnings.warn` when the peak search exhausts its range
- `remove_wv.py` has a module docstring explaining its legacy status and relationship to `cut_range.py`; the debug print is gone

**Success Looks Like:**
- `pytest tests/` passes with all tests green
- `python -c "from prospecpy import ProSpecPy, import_run_data"` exits 0
- Running a notebook cell that creates `ProSpecPy("output/run1", exist_ok=True)` twice does not raise
- A deliberate `curve_fit` failure (e.g. mismatched initial guess) propagates as an exception rather than printing silently

---

## What We're NOT Doing

- [ ] Rewriting the FTIR pipeline algorithm (water vapour subtraction, spline baseline, peak shapes)
- [ ] Adding new pipeline stages or analysis features
- [ ] Migrating from `print` to the `logging` module throughout the codebase (only fixing the silent-swallow pattern)
- [ ] Removing `remove_wv.py` (documenting it is safer until its usage is confirmed absent)
- [ ] Adding type annotations beyond what the fixes require
- [ ] Changing CSV output format or plot appearance
- [ ] Modifying `vaporfit.py`, `anchor_points.py`, `cut_range.py`, or `second_deriv.py` (none require changes)
- [ ] Modifying the numerical content of `peak_fit.py` — the `gaussian`, `lorentzian`, and `peak_fit`
      functions are untouched. **Phase 3 does now edit the two batch wrappers**
      (`gaussian_fit_prospecpy_objects`, `lorentzian_fit_prospecpy_objects`) to fix the transposed
      `save`/`showplot` arguments and add per-sample failure isolation. No fitted value changes.
- [ ] Packaging, environment, and documentation defects — see
      `plan-prospecpy-blockers-and-infrastructure.md`

**Rationale:** Scope is limited to the thirteen identified issues. Pipeline *numerics* are
scientifically validated; touching them without domain-expert review would be irresponsible. The
`logging` migration is a separate refactor that would touch every file.

---

## Implementation Approach

**Technical Strategy:**
Each fix is made in isolation within its file, touching only the lines that contain the defect.
Per CLAUDE.md, every changed line must trace directly to one of the thirteen issues. No adjacent
cleanup.

Tests are written first using synthetic data (small NumPy arrays) so they run without Bruker
instrument files. The `baseline_correction` fix is verified for numerical equivalence against the
original implementation before the original is removed.

**Key Architectural Decisions:**

1. **Decision:** Use `np.interp` (not `np.searchsorted`) for `baseline_correction`
   - **Rationale:** `np.interp` is a one-liner that handles interpolation, boundary clamping, and
     is well-known to the scientific Python audience. `np.searchsorted` requires manual index
     clamping and is less readable.
   - **Trade-offs:** `np.interp` interpolates between baseline points; the original used nearest-
     neighbour. For a 1000-point baseline over a ~3500 cm⁻¹ range, grid spacing is ~3.5 cm⁻¹, so the
     two methods can differ by roughly `slope * spacing / 2` at any given point — sub-noise for
     typical gentle baseline slopes, but not literally zero. One test verifies exact agreement on a
     same-grid synthetic case (interp lands exactly on a knot, so both methods agree to machine
     precision there); a second test verifies agreement to a derived, slope-dependent tolerance on
     mismatched grids resembling real pipeline usage (baseline over the anchor-point range, raw data
     over the full cut-range). Both tests are needed — the same-grid case alone doesn't exercise the
     interpolation-vs-nearest-neighbour difference at all.
   - **Alternatives considered:** `np.searchsorted` (more code, same result), `pd.merge_asof`
     (pandas, slower, less obvious).

2. **Decision:** Keep `exist_ok=False` as the default in `ProSpecPy.__init__`
   - **Rationale:** The current default (fail on existing folder) protects against silent
     overwrites of prior results, which matters in scientific workflows. Changing the default would
     be a behaviour-breaking change.
   - **Trade-offs:** Users running notebooks interactively must pass `exist_ok=True`; this is one
     extra kwarg but is self-documenting.

3. **Decision:** Re-raise after printing in `gaussian_fit_baseline` / `lorentzian_fit_baseline`
   - **Rationale:** The existing `print` provides human-readable context; removing it would lose
     that. Adding `raise` after the print ensures the caller receives the exception. Full `logging`
     migration is out of scope.
   - **Trade-offs:** The exception will now propagate to the batch loop
     (`gaussian_fit_prospecpy_objects`), which will halt on the first failure. This is correct —
     the current behaviour silently produces empty CSVs.

4. **Decision:** Replace `batch_id_sample_name` regex + split with `pathlib.Path.parts`
   - **Rationale:** `pathlib` is already imported in `io.py`. The existing regex requires `opus_files`
     in the path name, which is an undocumented, fragile contract. `Path.parts` works on any path.
   - **Trade-offs:** The proposed implementation preserves the original `(None, None)` contract for
     paths without `opus_files` (it looks up `"opus_files"` in `Path(filepath).parts` and returns
     `(None, None)` on `ValueError` if absent) — it does *not* extract the last two path components
     unconditionally. This is a genuine behavioral no-op for that case, and
     `test_returns_none_none_when_opus_files_absent` in Phase 4 explicitly covers it. The only real
     behavior change is *how* paths containing `opus_files` are parsed (pathlib parts vs. regex+split),
     which the docstring update documents.

**Patterns to Follow:**
- Docstring style: existing docstrings in `io.py`/`baseline.py` use a `Parameters:` / `- name: type` bullet list (see `io.py:12-29`) rather than strict numpydoc formatting (`Parameters\n----------\nname : type`). The docstrings proposed below for `ProSpecPy.__init__`, `save_plot`, and `baseline_correction` use full numpydoc-style formatting, which is a minor style improvement over — not an exact match of — the current convention. This is intentional and low-risk, but flagging it so reviewers don't expect byte-for-byte consistency with existing docstrings.
- `pathlib.Path` already used in `io.py:5` — extend, don't add a new import

---

## Implementation Phases

### Phase 1: Public API — `__init__.py` exports and `exist_ok` parameter

**Objective:** New users can import from the package root, and notebooks can re-run without
`FileExistsError`.

> **`plan-arpls-and-fit-qc-integration.md` changes this export list.** Its Phase 4 removes
> `interact` and the anchor-point baseline functions; its Phase 2 adds `fit_report` symbols.
> Do this phase first anyway — it is a prerequisite for that plan, and establishing the
> `__all__` convention is what makes the later edit a one-line change. Just expect to revisit
> the list, and do not treat the removal of `interact` as a regression.

**Tasks:**

- [ ] **Write the failing test** for `__init__` exports
  - File: `tests/test_public_api.py` (new)

  ```python
  def test_prospecpy_importable_from_package():
      from prospecpy import ProSpecPy
      assert ProSpecPy is not None

  def test_import_run_data_importable_from_package():
      from prospecpy import import_run_data
      assert import_run_data is not None

  def test_batch_functions_importable_from_package():
      from prospecpy import (
          cut_range_subtract_prospecpy_objects,
          second_deriv_prospecpy_objects,
          baseline_correction_prospecpy_objects,
          gaussian_fit_prospecpy_objects,
          lorentzian_fit_prospecpy_objects,
      )
      assert all(
          fn is not None
          for fn in [
              cut_range_subtract_prospecpy_objects,
              second_deriv_prospecpy_objects,
              baseline_correction_prospecpy_objects,
              gaussian_fit_prospecpy_objects,
              lorentzian_fit_prospecpy_objects,
          ]
      )
  ```

- [ ] **Run it, watch it fail:** `pytest tests/test_public_api.py -v`
  → expect `ImportError: cannot import name 'ProSpecPy' from 'prospecpy'`

- [ ] **Implement:** update `src/prospecpy/__init__.py:1-3`

  ```python
  from __future__ import annotations

  from .version import version as VERSION  # noqa

  __version__ = VERSION

  from .prospecpy import ProSpecPy
  from .io import import_run_data
  from .cut_range import cut_range_subtract_prospecpy_objects
  from .second_deriv import second_deriv_prospecpy_objects
  from .baseline import baseline_correction_prospecpy_objects
  from .peak_fit import gaussian_fit_prospecpy_objects, lorentzian_fit_prospecpy_objects

  __all__ = [
      "ProSpecPy",
      "import_run_data",
      "cut_range_subtract_prospecpy_objects",
      "second_deriv_prospecpy_objects",
      "baseline_correction_prospecpy_objects",
      "gaussian_fit_prospecpy_objects",
      "lorentzian_fit_prospecpy_objects",
  ]
  ```

- [ ] **Run it, watch it pass:** `pytest tests/test_public_api.py -v`
  → expect 3 PASSED

- [ ] **Write the failing test** for `exist_ok`
  - File: `tests/test_public_api.py` (append)

  ```python
  import os
  import tempfile

  def test_prospecpy_raises_on_existing_folder_by_default():
      with tempfile.TemporaryDirectory() as tmp:
          existing = os.path.join(tmp, "run1")
          os.makedirs(existing)
          import pytest
          with pytest.raises(FileExistsError):
              ProSpecPy(existing)

  def test_prospecpy_exist_ok_does_not_raise():
      with tempfile.TemporaryDirectory() as tmp:
          existing = os.path.join(tmp, "run1")
          os.makedirs(existing)
          obj = ProSpecPy(existing, exist_ok=True)
          assert obj.output_folder == existing
  ```

- [ ] **Run it, watch it fail:** `pytest tests/test_public_api.py::test_prospecpy_exist_ok_does_not_raise -v`
  → expect `TypeError: __init__() got an unexpected keyword argument 'exist_ok'`

- [ ] **Implement:** update `src/prospecpy/prospecpy.py:28-34`

  ```python
  def __init__(self, output_folder_path=None, exist_ok: bool = False) -> None:
      """
      Initialize a ProSpecPy analysis session.

      Parameters
      ----------
      output_folder_path : str or None
          Directory where CSVs and plots will be saved. If None, results
          are not saved and a notice is printed.
      exist_ok : bool, optional
          If False (default), raises ``FileExistsError`` when the output
          folder already exists — prevents accidentally overwriting a prior
          run. Set True to reuse an existing folder (useful when re-running
          notebook cells).
      """
      self.output_folder = output_folder_path
      if self.output_folder is not None:
          if os.path.exists(self.output_folder) and not exist_ok:
              raise FileExistsError(f"The folder '{self.output_folder}' already exists.")
          os.makedirs(self.output_folder, exist_ok=exist_ok)
      else:
          print("No output folder specified! Results from analysis will not be saved")
      # ... rest of attribute initialisation unchanged (self.raw_data = None, etc.)
  ```

  *Note: only lines 28–34 change. Lines 37–59 (`self.raw_data = None` through `self.baseline_corrected_abs = None`) are untouched.*

- [ ] **Run it, watch it pass:** `pytest tests/test_public_api.py -v`
  → expect 5 PASSED

- [ ] **Commit:** `git commit -m "feat: export public API from __init__ and add exist_ok to ProSpecPy"`

**Dependencies:** None

**Verification:**
- [ ] `python -c "from prospecpy import ProSpecPy, import_run_data; print('OK')"` prints `OK`
- [ ] `pytest tests/test_public_api.py -v` shows 5 PASSED

---

### Phase 2: Bugs and Debug Artefacts

**Objective:** Fix the `save_plot` `None`-check order, eliminate the double file read in `io.py`,
and remove the debug `print` left in `remove_wv.py`.

**Tasks:**

- [ ] **Write the failing test** for `save_plot` with `output_folder=None`
  - File: `tests/test_save_plot.py` (new)

  ```python
  import matplotlib.pyplot as plt
  from prospecpy import ProSpecPy

  def test_save_plot_with_none_folder_does_not_raise():
      """save_plot must not raise TypeError when output_folder is None."""
      obj = ProSpecPy(output_folder_path=None)
      fig, _ = plt.subplots()
      # Before fix: os.path.exists(None) raises TypeError
      obj.save_plot(fig, "test.png")
      plt.close(fig)
  ```

- [ ] **Run it, watch it fail:** `pytest tests/test_save_plot.py -v`
  → expect `TypeError: stat: path should be string, bytes, os.PathLike or integer, not NoneType`

- [ ] **Implement:** update `src/prospecpy/prospecpy.py:71-87`

  ```python
  def save_plot(self, fig, filename, verbose=True):
      """
      Save the given figure to the output folder.

      Checks ``output_folder is None`` first so that ``os.path.exists`` is
      never called with ``None`` (which raises ``TypeError``).

      Parameters
      ----------
      fig : matplotlib.figure.Figure
          The figure to save.
      filename : str
          Filename (without directory) for the saved figure.
      verbose : bool, optional
          If True, print the saved path. Defaults to True.
      """
      if self.output_folder is None:
          print("No output folder given")
          return
      if not os.path.exists(self.output_folder):
          print("No such folder exists! please create a valid output folder")
          return
      full_path = os.path.join(self.output_folder, filename)
      fig.savefig(full_path)
      if verbose:
          print(f"Plot saved to {full_path}")
  ```

- [ ] **Run it, watch it pass:** `pytest tests/test_save_plot.py -v` → expect PASSED

- [ ] **Write the failing test** for double file read
  - File: `tests/test_io.py` (new)

  ```python
  from pathlib import Path
  from unittest.mock import call, patch, MagicMock

  def test_import_run_data_reads_each_file_once(tmp_path):
      """Each OPUS file must be read exactly once; the stored result is reused."""
      fake_file = tmp_path / "opus_files" / "batch1" / "sample1.0"
      fake_file.parent.mkdir(parents=True)
      fake_file.write_bytes(b"")

      mock_opus = MagicMock()
      mock_opus.__getitem__ = MagicMock(return_value=MagicMock())

      with patch("prospecpy.io.read_file", return_value=mock_opus) as mock_read:
          from prospecpy import import_run_data
          import_run_data(tmp_path / "opus_files" / "batch1", input_type="raw spectra",
                          output_folder=str(tmp_path / "out"))

      # read_file must be called exactly once per file
      assert mock_read.call_count == 1
  ```

- [ ] **Run it, watch it fail:** `pytest tests/test_io.py::test_import_run_data_reads_each_file_once -v`
  → expect `AssertionError: assert 2 == 1`

- [ ] **Implement:** update `src/prospecpy/io.py:39-56` (the whole `for i in raw_files:` loop body)

  ```python
  for i in raw_files:
      if not i.name.startswith(".DS_Store"):
          batch_id, sample_name = batch_id_sample_name(str(i))
          # Read the file once and reuse the result below.
          # Previously read_file(i) was called twice per file (lines 44 and 54),
          # doubling disk I/O for every spectrum.
          file_data = read_file(i)
          raw_data[f"{i.name}"] = file_data
          output_folder_for_sample = None

          if input_type == "raw spectra":
              if output_folder is not None:
                  output_folder_for_sample = f"{output_folder}/{batch_id}/{sample_name}"
              new_prospecpy_obj = ProSpecPy(output_folder_for_sample)
              new_prospecpy_obj.set_raw_data(file_data, sample_name, batch_id)
              raw_data_objects.append(new_prospecpy_obj)
  ```

- [ ] **Run it, watch it pass:** `pytest tests/test_io.py -v` → expect PASSED

- [ ] **Remove the debug print** in `src/prospecpy/remove_wv.py:36`
  - Delete the line: `print(raw_spectra["Sample"]["SNM"][0:4])`
  - No test needed: `ruff check src/prospecpy/remove_wv.py` would flag `T20` (print statement) if the file were not excluded; the deletion is trivially verifiable by inspection.

- [ ] **Commit:** `git commit -m "fix: save_plot None-check order, single file read per spectrum, remove debug print"`

**Dependencies:** Phase 1 (the test imports `from prospecpy import ProSpecPy`)

**Verification:**
- [ ] `pytest tests/test_save_plot.py tests/test_io.py -v` shows all PASSED
- [ ] `grep -n 'print(raw_spectra' src/prospecpy/remove_wv.py` returns no output

---

### Phase 3: Code Quality — Error Propagation and Documentation

**Objective:** Failed peak fits raise instead of printing silently; `get_baseline_peak_index`
warns when the peak search fails; `remove_wv.py` documents its legacy status so contributors
understand when to use it vs. `cut_range.py`.

**Tasks:**

- [ ] **Write the failing test** for exception propagation in `gaussian_fit_baseline`
  - File: `tests/test_peak_fit_errors.py` (new)

  ```python
  import pytest
  import numpy as np
  from unittest.mock import patch, MagicMock
  from prospecpy import ProSpecPy

  def test_gaussian_fit_baseline_propagates_exception():
      """A failed curve_fit must propagate, not be swallowed by bare except."""
      obj = ProSpecPy.__new__(ProSpecPy)
      obj.output_folder = None
      obj.sample_name = "test"
      obj.batch_id = None
      obj.baseline_corrected_abs = np.array([0.1, 0.2, 0.1])
      obj.baseline_corrected_peak_dict = {"peak_index": np.array([1])}
      # gaussian_fit_baseline calls self.get_subtracted_spectra_wavenumber()/
      # ...absorbance() as *arguments* to raw_spline(); these are evaluated
      # before raw_spline() runs, so cut_atmfitparams_obj must be set even
      # though raw_spline itself is mocked below — otherwise this raises
      # AttributeError instead of exercising the code path under test.
      obj.cut_atmfitparams_obj = [
          MagicMock(sub_spectrum=np.array([0.1, 0.2, 0.1]), wavenb=np.array([1.0, 2.0, 3.0]))
      ]

      with patch("prospecpy.prospecpy.raw_spline", return_value=[np.array([1.0, 2.0, 3.0]), np.array([0.1, 0.2, 0.1])]):
          with patch("prospecpy.prospecpy.peak_fit", side_effect=RuntimeError("curve_fit failed")):
              with pytest.raises(RuntimeError, match="curve_fit failed"):
                  obj.gaussian_fit_baseline(save=False, showplot=False, verbose=False)
  ```

- [ ] **Run it, watch it fail:** `pytest tests/test_peak_fit_errors.py -v`
  → expect test to fail because the exception is swallowed (no `RuntimeError` raised)

- [ ] **Implement:** update `src/prospecpy/prospecpy.py:405-406` (gaussian) and `src/prospecpy/prospecpy.py:454-455` (lorentzian)

  For `gaussian_fit_baseline`, replace:
  ```python
          except Exception as e:
              print(f"An error occurred: {e}")
  ```
  with:
  ```python
          except Exception as e:
              # Print context before re-raising so the sample name is visible in
              # the traceback even when called from a batch loop.
              print(f"Gaussian fitting failed for {self.sample_name!r}: {e}")
              raise
  ```

  For `lorentzian_fit_baseline`, replace:
  ```python
          except Exception as e:
              print(f"An error occurred: {e}")
  ```
  with:
  ```python
          except Exception as e:
              print(f"Lorentzian fitting failed for {self.sample_name!r}: {e}")
              raise
  ```

- [ ] **Write the failing test** for per-sample failure isolation and the transposed arguments
  - Append to `tests/test_peak_fit_errors.py`

  > **This task is not optional and must ship in the same commit as the re-raise above.** 8 of the
  > 19 real samples in `Hyd2_pH6_data/examples for you to try/` fail `curve_fit` today. Re-raising
  > without isolating means the notebook dies on roughly the third sample with no output at all —
  > worse than the current silent failure. See Risk Assessment item 2.

  ```python
  from unittest.mock import MagicMock

  from prospecpy.peak_fit import gaussian_fit_prospecpy_objects


  def test_batch_gaussian_fit_isolates_per_sample_failures():
      """One failing sample must not abort the rest of the batch."""
      ok_first, bad, ok_last = MagicMock(), MagicMock(), MagicMock()
      bad.sample_name = "bad_sample"
      bad.gaussian_fit_baseline.side_effect = RuntimeError("maxfev exceeded")

      failures = gaussian_fit_prospecpy_objects([ok_first, bad, ok_last], verbose=False)

      assert ok_last.gaussian_fit_baseline.called, "batch aborted early on the failing sample"
      assert set(failures) == {"bad_sample"}


  def test_batch_gaussian_fit_passes_save_and_showplot_in_the_right_order():
      """Regression guard: the wrapper used to pass (show_plots, save, verbose)
      positionally into a (save, showplot, verbose) signature, transposing the
      first two arguments."""
      obj = MagicMock()
      gaussian_fit_prospecpy_objects([obj], show_plots=False, save=True, verbose=False)

      obj.gaussian_fit_baseline.assert_called_once_with(
          save=True, showplot=False, verbose=False
      )
  ```

- [ ] **Run them, watch them fail:** `pytest tests/test_peak_fit_errors.py -v`
  → expect the isolation test to fail with `RuntimeError` propagating out of the batch call, and the
  ordering test to fail on the positional-vs-keyword mismatch

- [ ] **Implement:** rewrite both batch wrappers at `src/prospecpy/peak_fit.py:80-89` and
  `src/prospecpy/peak_fit.py:92-101`. This fixes the transposition and adds isolation together,
  since both edit the same call site:

  ```python
  def gaussian_fit_prospecpy_objects(
      list_of_prospecpy_object, show_plots=False, save=True, verbose=True
  ):
      """
      Fit a Gaussian to each object's baseline-corrected spectrum.

      A sample whose fit fails is recorded and skipped rather than aborting the
      batch — ``curve_fit`` non-convergence is common on real spectra and one bad
      sample should not discard the rest of a run.

      Returns
      -------
      dict[str, Exception]
          Sample names that failed, mapped to the raised exception. Empty on
          full success.
      """
      failures = {}
      for prospecpy_obj in list_of_prospecpy_object:
          try:
              # Keyword arguments: passing positionally transposed save/showplot.
              prospecpy_obj.gaussian_fit_baseline(
                  save=save, showplot=show_plots, verbose=verbose
              )
          except Exception as exc:
              failures[prospecpy_obj.sample_name] = exc
      if failures and verbose:
          print(
              f"Gaussian fit failed for {len(failures)} of "
              f"{len(list_of_prospecpy_object)} samples:"
          )
          for name, exc in failures.items():
              print(f"  {name}: {exc}")
      return failures
  ```

  Apply the same shape to `lorentzian_fit_prospecpy_objects`.

  *Note `src/prospecpy/second_deriv.py:130` and `src/prospecpy/baseline.py:175` already pass their
  arguments in the correct order and must not be changed.*

- [ ] **Run them, watch them pass:** `pytest tests/test_peak_fit_errors.py -v` → expect all PASSED

- [ ] **Write the failing test** for `get_baseline_peak_index` warning
  - Append to `tests/test_peak_fit_errors.py`

  ```python
  import warnings
  import numpy as np
  from prospecpy.baseline import get_baseline_peak_index

  def test_get_baseline_peak_index_warns_when_peaks_not_all_found():
      """When range_val exceeds 1000 without finding all peaks, a warning is emitted."""
      # baseline data: a single peak at index 5
      baseline_abs = [0.0] * 10
      baseline_abs[5] = 1.0
      raw_wv = list(range(10))
      # Ask for a peak at wavenumber 500 — far from any peak in baseline_abs
      raw_data_peak_wv = [500.0]

      with warnings.catch_warnings(record=True) as caught:
          warnings.simplefilter("always")
          get_baseline_peak_index(baseline_abs, raw_wv, raw_data_peak_wv)

      assert any("get_baseline_peak_index" in str(w.message) for w in caught), \
          "Expected a warning when not all peaks are found"
  ```

- [ ] **Run it, watch it fail:** `pytest tests/test_peak_fit_errors.py::test_get_baseline_peak_index_warns_when_peaks_not_all_found -v`
  → expect `AssertionError` (no warning was emitted)

- [ ] **Implement:** update `src/prospecpy/baseline.py:117-118`

  ```python
  import warnings  # add to imports at top of baseline.py

  # Inside get_baseline_peak_index, replace:
  #   if range_val > 1000:
  #       break
  # with:
          if range_val > 1000:
              warnings.warn(
                  f"get_baseline_peak_index: found {len(peak_wv_baseline)} of "
                  f"{len(raw_data_peak_wv)} expected peaks after range_val reached 1000. "
                  "Check the threshold passed to peak_finder() or the adjustment_factor "
                  "in anchor_point_fit().",
                  stacklevel=2,
              )
              break
  ```

- [ ] **Run it, watch it pass:** `pytest tests/test_peak_fit_errors.py -v` → expect all PASSED

- [ ] **Document `remove_wv.py`** — add module docstring at `src/prospecpy/remove_wv.py:1` (before existing imports)

  ```python
  """
  Legacy standalone water-vapour subtraction.

  This module was written before the ``cut_range`` module and uses
  ``brukeropusreader``'s built-in ``interpolate()`` to resample data to a
  100-point grid prior to subtraction.

  **It is not used by the main ProSpecPy pipeline.** The pipeline uses
  :func:`prospecpy.cut_range.cut_range_subtraction` (or its
  ``_multiple_wv`` variant), which operates on the full-resolution data
  and integrates wavenumber range cutting.

  Preserve this module for reference or standalone experiments. If you need
  water-vapour subtraction integrated with range cutting, use
  :mod:`prospecpy.cut_range` instead.
  """
  ```

- [ ] **Commit:** `git commit -m "fix: re-raise peak fit exceptions, warn on incomplete peak search, document remove_wv legacy status"`

**Dependencies:** Phase 1

**Verification:**
- [ ] `pytest tests/test_peak_fit_errors.py -v` shows all PASSED
- [ ] `python -c "import prospecpy.remove_wv; print(prospecpy.remove_wv.__doc__[:40])"` prints the first 40 chars of the docstring

---

### Phase 4: Portability — Path Handling in `batch_id_sample_name`

> **⚠️ SUPERSEDED by `plan-prospecpy-blockers-and-infrastructure.md` Phase 2. Do not implement this
> phase as written.**
>
> This phase's implementation deliberately preserves the `(None, None)` return for paths lacking an
> `opus_files` component — see Architectural Decision 4 and the
> `test_returns_none_none_when_opus_files_absent` test below. That behaviour is the direct cause of a
> live blocker: on the project's own `Hyd2_pH6_data/examples for you to try/` tree, every sample
> resolves to `<output>/None/None` and the pipeline raises `FileExistsError` on the second sample.
> **Fixing the Windows portability gap without also fixing the fallback leaves ProSpecPy unable to
> run on its own data.**
>
> The superseding phase is a strict superset: it keeps the `pathlib` rewrite and the Windows fix,
> adds a `Path(...).name` fallback so each sample gets a distinct output folder, and removes the
> `\s` escape-sequence defect at `io.py:81` as a side effect. Implement that version, then mark this
> phase complete. The material below is retained for context on the portability rationale.

**Objective:** `batch_id_sample_name` works on Windows (no hardcoded `/`) and on paths that do not
contain the literal string `opus_files`.

**Tasks:**

- [ ] **Write the failing tests**
  - File: `tests/test_batch_id_sample_name.py` (new)

  ```python
  from prospecpy.io import batch_id_sample_name

  def test_extracts_batch_and_sample_from_opus_files_path():
      path = "/data/opus_files/batch001/sample_A.0"
      batch_id, sample_name = batch_id_sample_name(path)
      assert batch_id == "batch001"
      assert sample_name == "sample_A.0"

  def test_extracts_sample_only_when_no_batch():
      path = "/data/opus_files/sample_A.0"
      batch_id, sample_name = batch_id_sample_name(path)
      assert batch_id is None
      assert sample_name == "sample_A.0"

  def test_returns_none_none_when_opus_files_absent():
      # Paths without 'opus_files' return (None, None) — consistent with
      # original behaviour for unrecognised directory structures.
      path = "/data/spectra/batch001/sample_A.0"
      batch_id, sample_name = batch_id_sample_name(path)
      assert batch_id is None
      assert sample_name is None

  @pytest.mark.skipif(
      sys.platform != "win32",
      reason=(
          "pathlib.Path resolves to PosixPath on POSIX systems, which does NOT "
          "treat '\\\\' as a separator — Path('C:\\\\data\\\\...').parts returns a "
          "single opaque component, not split parts, so this assertion can only "
          "pass where Path resolves to WindowsPath. Verified empirically: on "
          "macOS/Linux, Path(str(PureWindowsPath(...))).parts is a 1-tuple "
          "containing the whole backslash-separated string. The CI matrix in "
          ".github/workflows/ci.yml runs on ubuntu-latest, macos-14, AND "
          "windows-latest, so without this skip the test would fail on 2 of 3 "
          "platforms even with the pathlib-based fix correctly implemented."
      ),
  )
  def test_handles_windows_style_path():
      # This exercises real Windows-path handling only when actually running on
      # Windows (where pathlib.Path is WindowsPath and understands '\\').
      from pathlib import PureWindowsPath
      path = str(PureWindowsPath(r"C:\data\opus_files\batch001\sample_A.0"))
      batch_id, sample_name = batch_id_sample_name(path)
      assert sample_name == "sample_A.0"
  ```

  *Requires `import sys` and `import pytest` at the top of `tests/test_batch_id_sample_name.py`.*

- [ ] **Run them, watch them fail:** `pytest tests/test_batch_id_sample_name.py -v`
  → `test_returns_none_none_when_opus_files_absent` passes even before the fix (current regex-based code already returns `(None, None)` correctly for this case); `test_handles_windows_style_path` fails on the CI runner it actually executes on (`windows-latest`, per the skip condition above) with `AssertionError: assert None == 'sample_A.0'`, because the old code's `.split("/")` hardcodes the POSIX separator and never matches on a backslash-separated Windows path, regardless of OS

- [ ] **Implement:** replace `src/prospecpy/io.py:66-98` with:

  ```python
  def batch_id_sample_name(filepath: str) -> tuple[str | None, str | None]:
      """
      Extract batch_id and sample_name from a file path.

      Expects one of these directory structures under an ``opus_files`` folder:

      - ``…/opus_files/<batch_id>/<sample_name>``  →  ``(batch_id, sample_name)``
      - ``…/opus_files/<sample_name>``              →  ``(None, sample_name)``
      - any other structure                          →  ``(None, None)``

      Uses :mod:`pathlib` for portable path parsing (works on Windows and POSIX).
      The original implementation used a regex requiring the literal string
      ``opus_files`` in the path and split on ``"/"`` which failed on Windows.

      Parameters
      ----------
      filepath : str
          The file path to parse.

      Returns
      -------
      batch_id : str or None
      sample_name : str or None
      """
      parts = Path(filepath).parts
      try:
          opus_idx = parts.index("opus_files")
      except ValueError:
          return None, None
      after = parts[opus_idx + 1 :]
      if len(after) >= 2:
          return after[0], after[1]
      if len(after) == 1:
          return None, after[0]
      return None, None
  ```

  *The `re` import at `io.py:4` becomes unused — remove it.*

- [ ] **Run them, watch them pass:** `pytest tests/test_batch_id_sample_name.py -v` → expect all PASSED

- [ ] **Commit:** `git commit -m "fix: replace regex+split path parsing with pathlib in batch_id_sample_name"`

**Dependencies:** Phase 1 (by convention, for consistent sequential ordering — not a hard technical
requirement: `tests/test_batch_id_sample_name.py` imports `from prospecpy.io import batch_id_sample_name`
directly and does not need the package-level exports added in Phase 1)

**Verification:**
- [ ] `pytest tests/test_batch_id_sample_name.py -v` shows all PASSED
- [ ] `grep -n "^import re" src/prospecpy/io.py` returns no output (unused import removed)

---

### Phase 5: Performance — O(n²) Baseline and Redundant Spline Calls

> **⚠️ SUPERSEDED by `plan-arpls-and-fit-qc-integration.md`. Do not implement this phase.**
>
> This phase optimises `baseline_correction` (`baseline.py:66-94`) and caches the seven
> redundant `raw_spline` calls in `subtract_baseline` (`prospecpy.py:262-353`). The arPLS
> integration plan **replaces the entire anchor-point baseline path** with an automatic
> algorithm, and its Phase 4 deletes `baseline_correction`, `baseline_spline`,
> `subtract_baseline`, and `anchor_points.py`. Optimising code that is scheduled for deletion
> is wasted effort, and this phase was already the only one carrying an unresolved
> numerical-equivalence question (see Open Questions).
>
> **The `raw_spline` caching lesson still holds** — the replacement method
> `subtract_baseline_arpls` already calls `raw_spline` exactly once, so the defect does not
> recur.
>
> **If Phase 3 of the arPLS plan produces an unfavourable comparison** and the anchor-point
> path is retained alongside arPLS rather than deleted, this phase becomes live again.
> The material below is retained for that case.
>
> **Priority revised down — do this last.** The plan originally justified this phase with an
> estimated "~1 second per spectrum at 1000 points". That figure was never measured. A profiled run
> over the 19 real samples in `Hyd2_pH6_data/examples for you to try/` puts baseline correction at
> **82 ms per sample**, and the **entire seven-stage pipeline at 5.0 seconds end to end**. There is
> no bottleneck here today.
>
> The change is still correct and still worth making — it protects against higher instrument
> resolution or a wider wavenumber range than the narrow 2150–1850 cm⁻¹ window the demo notebook
> uses — but it is the only phase in this plan carrying an unresolved numerical-equivalence question
> (see Open Questions), and it is optimising something that costs 1.6% of a five-second run.
> Sequence it after every other phase, and do not let it block them.

**Objective:** `baseline_correction` runs in O(n log n) using `np.interp`; `subtract_baseline`
calls `raw_spline` once. Both changes are verified to produce numerically equivalent output.

**Tasks:**

- [ ] **Write the failing test** for `baseline_correction` numerical equivalence
  - File: `tests/test_baseline_performance.py` (new)

  ```python
  import numpy as np
  import pandas as pd
  import pytest

  def _original_baseline_correction(baseline_points, raw_wavenumber, raw_absorbance):
      """Reference implementation (original O(n²) algorithm) kept here for comparison."""
      baseline_corrected_abs = []
      for idx, wv_num in enumerate(raw_wavenumber):
          diff_array = abs(baseline_points["wavenumber"] - wv_num)
          closest_wv_num = diff_array.idxmin()
          raw_minus_baseline = raw_absorbance[idx] - baseline_points.loc[closest_wv_num, "absorbance"]
          if raw_minus_baseline < 0:
              baseline_corrected_abs.append(0)
          else:
              baseline_corrected_abs.append(raw_minus_baseline)
      return baseline_corrected_abs

  def test_baseline_correction_matches_original_on_linear_baseline():
      """np.interp result must agree with the original nearest-neighbour within 1e-6."""
      wv = np.linspace(500, 4000, 100)
      # linear baseline: y = 0.001 * x
      baseline = pd.DataFrame({"wavenumber": wv, "absorbance": 0.001 * wv})
      raw_abs = 0.001 * wv + 0.05  # signal is baseline + constant offset

      from prospecpy.baseline import baseline_correction
      result_new = np.array(baseline_correction(baseline, wv, raw_abs))
      result_ref = np.array(_original_baseline_correction(baseline, wv, raw_abs))

      np.testing.assert_allclose(result_new, result_ref, atol=1e-6)

  def test_baseline_correction_close_to_original_on_mismatched_grids():
      """On non-identical grids — as in real pipeline usage, where baseline_spline()
      evaluates over the (narrower) anchor-point range and raw_spline() evaluates
      over the full cut-range spectrum range — np.interp and the original
      nearest-neighbour lookup are NOT identical; they diverge by roughly
      slope * (grid_spacing / 2). The test above uses identical grids for both
      arguments, so interp lands exactly on a baseline knot and both methods
      agree to machine precision regardless of slope — it does not exercise this
      divergence at all. This test uses deliberately different grids and a
      gentle, realistic baseline slope to make the (small but nonzero) bound
      explicit, rather than asserting an unjustified blanket 1e-6.
      """
      baseline_wv = np.linspace(800, 3600, 1000)  # narrower anchor-point range
      raw_wv = np.linspace(499, 3997, 1000)  # full cut-range spectrum range
      slope = 2e-5  # absorbance units per cm^-1 — gentle, realistic baseline slope
      baseline = pd.DataFrame({"wavenumber": baseline_wv, "absorbance": slope * baseline_wv})
      raw_abs = slope * np.clip(raw_wv, 800, 3600) + 0.05

      from prospecpy.baseline import baseline_correction
      result_new = np.array(baseline_correction(baseline, raw_wv, raw_abs))
      result_ref = np.array(_original_baseline_correction(baseline, raw_wv, raw_abs))

      grid_spacing = baseline_wv[1] - baseline_wv[0]
      # Empirically verified bound (see Review History): max diff ~2.8e-5 for
      # this slope/spacing; slope * grid_spacing gives a safe, derived margin
      # rather than a magic number.
      np.testing.assert_allclose(result_new, result_ref, atol=slope * grid_spacing)

  def test_baseline_correction_clips_negative_values():
      """Values where baseline > raw absorbance must be clipped to 0, not negative."""
      wv = np.array([1.0, 2.0, 3.0])
      baseline = pd.DataFrame({"wavenumber": wv, "absorbance": np.array([0.5, 0.5, 0.5])})
      raw_abs = np.array([0.3, 0.6, 0.3])  # index 0 and 2 below baseline

      from prospecpy.baseline import baseline_correction
      result = baseline_correction(baseline, wv, raw_abs)
      assert result[0] == 0, "negative difference must be clipped to 0"
      assert result[2] == 0, "negative difference must be clipped to 0"
      assert result[1] > 0
  ```

- [ ] **Run them, watch them fail** (the clipping test may pass with the original implementation too,
  since it isn't specific to the O(n²) vs O(n log n) change; the two equivalence tests confirm agreement
  on same-grid and mismatched-grid cases respectively):
  `pytest tests/test_baseline_performance.py -v`

- [ ] **Implement:** replace `src/prospecpy/baseline.py:66-94` with:

  ```python
  def baseline_correction(baseline_points, raw_wavenumber, raw_absorbance):
      """
      Subtract the baseline from raw absorbance at each wavenumber.

      Uses ``np.interp`` to evaluate the baseline at every raw wavenumber in
      O(n log n) time. The original implementation used a per-point
      ``DataFrame.idxmin()`` scan which was O(n²) — noticeable at 1000 points
      and prohibitive at higher resolutions.

      Values where the baseline exceeds the raw absorbance are clipped to zero
      (physically, absorbance cannot be negative).

      Parameters
      ----------
      baseline_points : pd.DataFrame
          DataFrame with ``"wavenumber"`` and ``"absorbance"`` columns,
          sorted in ascending wavenumber order (as produced by
          :func:`baseline_spline`).
      raw_wavenumber : array-like
          Wavenumber values from the raw (spline-smoothed) spectrum.
      raw_absorbance : array-like
          Absorbance values from the raw (spline-smoothed) spectrum.

      Returns
      -------
      list of float
          Baseline-corrected absorbance, same length as ``raw_wavenumber``.
      """
      baseline_abs_interp = np.interp(
          raw_wavenumber,
          baseline_points["wavenumber"],
          baseline_points["absorbance"],
      )
      corrected = np.maximum(np.asarray(raw_absorbance) - baseline_abs_interp, 0.0)
      return list(corrected)
  ```

- [ ] **Run them, watch them pass:** `pytest tests/test_baseline_performance.py -v` → expect 3 PASSED

- [ ] **Write the failing test** for `raw_spline` call count in `subtract_baseline`
  - Append to `tests/test_baseline_performance.py`

  ```python
  from unittest.mock import patch, MagicMock
  from prospecpy import ProSpecPy

  def test_subtract_baseline_calls_raw_spline_once():
      """raw_spline must be called exactly once per subtract_baseline invocation."""
      obj = ProSpecPy.__new__(ProSpecPy)
      obj.output_folder = None
      obj.sample_name = "test"
      obj.batch_id = None
      obj.second_deriv_peak_dict = {"peak_wavenumber": np.array([1500.0])}
      obj.baseline_corrected_peak_dict = {}
      obj.peak_width_half_height = None

      fake_wv = np.linspace(500, 4000, 1000)
      fake_abs = np.ones(1000) * 0.5
      fake_baseline = pd.DataFrame({"wavenumber": fake_wv, "absorbance": fake_abs * 0.1})

      obj.baseline_curve = fake_baseline
      obj.cut_atmfitparams_obj = [MagicMock(sub_spectrum=fake_abs, wavenb=fake_wv)]

      spline_result = [fake_wv, fake_abs]

      with patch("prospecpy.prospecpy.raw_spline", return_value=spline_result) as mock_spline:
          with patch("prospecpy.prospecpy.baseline_correction", return_value=list(fake_abs * 0.4)):
              with patch("prospecpy.prospecpy.get_peaks_absorbance", return_value=([], [])):
                  with patch("prospecpy.prospecpy.get_baseline_peak_index", return_value=([], [], [])):
                      with patch("prospecpy.prospecpy.get_peak_wid_at_half_height", return_value=[]):
                          with patch("prospecpy.prospecpy.plot_baseline_corrected_data", return_value=MagicMock()):
                              obj.subtract_baseline(save=False, showplot=False, verbose=False)

      assert mock_spline.call_count == 1, (
          f"raw_spline called {mock_spline.call_count} times; expected 1"
      )
  ```

- [ ] **Run it, watch it fail:** `pytest tests/test_baseline_performance.py::test_subtract_baseline_calls_raw_spline_once -v`
  → expect `AssertionError: raw_spline called 7 times; expected 1`

- [ ] **Implement:** update `src/prospecpy/prospecpy.py:262-353` (the entire `subtract_baseline` method,
  including the `if save:` CSV-writing block, which also references `raw_spline`).
  Add a single `raw_spline` call at the top of the `if self.baseline_curve is not None:` block,
  assign to `raw_wv, raw_abs`, and replace all **seven** occurrences of
  `raw_spline(self.get_subtracted_spectra_wavenumber(), self.get_subtracted_spectra_absorbance())[0]`
  and `...[1]` with `raw_wv` and `raw_abs` respectively. Note that `raw_spline` is also called once
  each in `gaussian_fit_baseline` (line 362) and `lorentzian_fit_baseline` (line 417) — those calls
  are outside `subtract_baseline` and are **not** touched by this fix:

  ```python
  def subtract_baseline(self, save=True, showplot=True, verbose=True):
      if self.baseline_curve is not None:
          # Compute the smoothed spline representation once.
          # Previously raw_spline(...) was called seven times in this method with
          # identical arguments; each call recomputes the UnivariateSpline from scratch.
          raw_wv, raw_abs = raw_spline(
              self.get_subtracted_spectra_wavenumber(),
              self.get_subtracted_spectra_absorbance(),
          )
          self.baseline_corrected_abs = baseline_correction(
              self.get_baseline_curve(), raw_wv, raw_abs
          )
          peak_wv, peak_abs = get_peaks_absorbance(
              self.second_deriv_peak_dict["peak_wavenumber"], raw_wv, raw_abs
          )
          peak_wv_index, peak_wv_baseline, peak_baseline_abs = get_baseline_peak_index(
              self.baseline_corrected_abs, raw_wv, peak_wv
          )
          self.peak_width_half_height = get_peak_wid_at_half_height(
              self.baseline_corrected_abs, peak_wv_index
          )
          self.baseline_corrected_peak_dict["peak_index"] = peak_wv_index
          self.baseline_corrected_peak_dict["wavenumber"] = peak_wv_baseline
          self.baseline_corrected_peak_dict["absorbance"] = peak_baseline_abs
          baseline_corrected_fig = plot_baseline_corrected_data(
              raw_wv, self.baseline_corrected_abs, peak_wv_baseline,
              peak_baseline_abs, self.sample_name, self.batch_id, showplot,
          )
          if save:
              filename = "baseline_subtracted_spectra"
              self.save_plot(baseline_corrected_fig, filename, verbose=verbose)
              data_df = pd.DataFrame(
                  {"wavenumber": raw_wv, "absorbance": self.baseline_corrected_abs}
              )
              csv_filename = "baseline_corrected_data.csv"
              data_df.to_csv(os.path.join(self.output_folder, csv_filename), index=False)
              if verbose:
                  print(f"Baseline corrected csv data saved to {os.path.join(self.output_folder, csv_filename)}")
              baseline_peak_filename = os.path.join(
                  self.output_folder, "baseline_corrected_peak_info.csv"
              )
              keys = self.baseline_corrected_peak_dict.keys()
              values = zip(*self.baseline_corrected_peak_dict.values(), strict=False)
              with open(baseline_peak_filename, "w", newline="") as csvfile:
                  writer = csv.writer(csvfile)
                  writer.writerow(keys)
                  writer.writerows(values)
              if verbose:
                  print(f"Baseline corrected peak info saved to {baseline_peak_filename}")
      else:
          print("Please set and save the thresholds and adjustment factor for baseline spline!")
  ```

- [ ] **Run it, watch it pass:** `pytest tests/test_baseline_performance.py -v` → expect all PASSED

- [ ] **Commit:** `git commit -m "perf: O(n²) → O(n log n) baseline_correction via np.interp, cache raw_spline in subtract_baseline"`

**Dependencies:** Phases 1–4 complete

**Verification:**
- [ ] `pytest tests/test_baseline_performance.py -v` shows all PASSED
- [ ] `grep -c "raw_spline(" src/prospecpy/prospecpy.py` returns `3` — one cached call in `subtract_baseline`
  (down from seven), plus the one call each in `gaussian_fit_baseline` and `lorentzian_fit_baseline`,
  which are unchanged by this phase

---

## Success Criteria

### Automated Verification

- [ ] `pytest tests/ -v` — all tests pass (existing `test_import.py` + all new tests)
- [ ] `python -c "from prospecpy import ProSpecPy, import_run_data, cut_range_subtract_prospecpy_objects, second_deriv_prospecpy_objects, baseline_correction_prospecpy_objects, gaussian_fit_prospecpy_objects, lorentzian_fit_prospecpy_objects; print('OK')"` exits 0
- [ ] `grep -n "raw_spline(" src/prospecpy/prospecpy.py` returns exactly 3 matches (one cached call in
  `subtract_baseline`, and one each — unchanged — in `gaussian_fit_baseline` and `lorentzian_fit_baseline`)
- [ ] `grep -rn "print(raw_spectra" src/prospecpy/remove_wv.py` returns no output
- [ ] `grep -n "^import re" src/prospecpy/io.py` returns no output
- [ ] `grep -n "== None" src/prospecpy/prospecpy.py` returns no output

### Manual Verification

- [ ] In a notebook: `from prospecpy import ProSpecPy` works without error on a fresh kernel
- [ ] In a notebook: creating `ProSpecPy("output/run1")`, then re-running the cell with `ProSpecPy("output/run1", exist_ok=True)` does not raise
- [ ] On a real OPUS file: `import_run_data(path, input_type="raw spectra")` produces objects with correct `batch_id` and `sample_name` attributes
- [ ] When `curve_fit` fails (e.g. too few data points), the exception message includes the sample name and propagates to the caller rather than printing silently

---

## Testing Strategy

**Unit Test Coverage (written in-phase above):**
- `tests/test_public_api.py` — package-level imports, `exist_ok` parameter
- `tests/test_save_plot.py` — `save_plot` with `None` folder
- `tests/test_io.py` — single file read per spectrum
- `tests/test_batch_id_sample_name.py` — path parsing (with batch, without batch, no `opus_files`, Windows-style)
- `tests/test_peak_fit_errors.py` — exception propagation, incomplete peak search warning
- `tests/test_baseline_performance.py` — `baseline_correction` numerical equivalence + clipping, `raw_spline` call count

**Integration Tests:**
- No new integration tests are added; a full pipeline run against a real OPUS file remains a manual verification step (instrument files are not committed to the repo)

**Manual Testing:**
- Full notebook run with `workflow_demo.ipynb` after all phases to verify end-to-end pipeline output is unchanged

**Test Data Requirements:**
- All unit tests use synthetic NumPy arrays — no OPUS files required
- `test_io.py` uses `tmp_path` (pytest fixture) with empty stub files and `unittest.mock.patch` on `read_file`

---

## Migration Strategy

**Backward Compatibility:**
- `ProSpecPy(path)` with a non-existing folder: unchanged behaviour
- `ProSpecPy(path)` with an existing folder: still raises `FileExistsError` (default `exist_ok=False`)
- `from prospecpy.prospecpy import ProSpecPy`: still works (no removal of internal module)
- `baseline_correction` output: numerically equivalent to original (exact on matching grids, verified
  by test to 1e-6; within a derived slope-dependent tolerance on mismatched grids resembling real
  pipeline usage — see Key Architectural Decision 1 and Phase 5 tests)
- `batch_id_sample_name` on paths containing `opus_files`: same output as before
- `batch_id_sample_name` on paths without `opus_files`: was `(None, None)` before, remains `(None, None)` — no regression

**Rollback Plan:**
Each phase is a separate commit. Any phase can be reverted with `git revert <sha>` without
affecting other phases.

---

## Risk Assessment

1. **Risk:** `np.interp` uses linear interpolation between baseline knots; original used nearest-neighbour
   - **Likelihood:** Low (knot spacing ~3.5 cm⁻¹, spectral noise is larger); note the 1e-6 tolerance
     only holds exactly when baseline and raw wavenumber grids coincide (as tested), not in general —
     see the mismatched-grid test in Phase 5 for the realistic bound
   - **Impact:** Low for typical gentle baseline slopes (sub-noise difference), but this has not been
     validated against a real OPUS spectrum with real anchor points — **flagged as needing a
     domain-expert / real-data check before merging Phase 5** (see Open Questions)
   - **Mitigation:** Numerical equivalence tests confirm exact agreement on matching grids (atol=1e-6)
     and a derived, slope-dependent tolerance on mismatched grids resembling real usage

2. **Risk:** Re-raising in `gaussian_fit_baseline` halts batch runs that previously continued past a failed sample
   - **Likelihood:** **Certain, not speculative.** This was previously rated "Medium (failures may
     exist in wild data)". A measured run of the full pipeline over the 19 real samples in
     `Hyd2_pH6_data/examples for you to try/` found **8 of 19 samples fail `curve_fit`** with
     `Optimal parameters not found: Number of calls to function has reached maxfev`. Every one is
     currently swallowed by the bare `except`.
   - **Impact:** **High.** After this phase ships, `gaussian_fit_prospecpy_objects` raises on roughly
     the third sample and the notebook dies with eleven samples unprocessed and no output. Today's
     behaviour is wrong but at least completes; naive re-raising makes the scientist's experience
     strictly worse.
   - **Mitigation:** **Do not ship the re-raise alone.** Land it together with per-sample failure
     isolation in the batch wrappers, so one failing sample does not abort the other eighteen:

     ```python
     def gaussian_fit_prospecpy_objects(list_of_prospecpy_object, show_plots=False, save=True, verbose=True):
         failures = {}
         for prospecpy_obj in list_of_prospecpy_object:
             try:
                 prospecpy_obj.gaussian_fit_baseline(save, show_plots, verbose)
             except Exception as exc:
                 failures[prospecpy_obj.sample_name] = exc
         if failures and verbose:
             print(f"Gaussian fit failed for {len(failures)} of {len(list_of_prospecpy_object)} samples:")
             for name, exc in failures.items():
                 print(f"  {name}: {exc}")
         return failures
     ```

     Note this changes the batch wrappers from returning `None` to returning a failures dict, which
     is additive and safe for existing callers.
   - **Root cause, out of scope here:** `maxfev` exhaustion at 2000–3200 calls points at poor initial
     guesses derived from `peak_widths`, not a code defect. This is
     [issue #12](https://github.com/ProSpecPy/ProSpecPy/issues/12) (restoring user-supplied peak
     guesses), and fixing it is worth more to users than anything in this plan.

3. **Risk:** `batch_id_sample_name` contract change — paths without `opus_files` now return `(None, None)` where before they would have returned `(None, None)` too (same) but paths WITH `opus_files` use pathlib parts instead of regex
   - **Likelihood:** Low
   - **Impact:** Low (four targeted tests verify all cases)
   - **Mitigation:** Tests cover the known path shapes
   - **Superseded:** See the Phase 4 notice above. Preserving `(None, None)` is itself the defect;
     `plan-prospecpy-blockers-and-infrastructure.md` Phase 2 replaces this behaviour.

4. **Risk:** `save` and `showplot` are transposed in the peak-fit batch wrappers (pre-existing bug,
   newly discovered)
   - **Likelihood:** Certain — verified by inspection, see the Current State Analysis entry
   - **Impact:** Medium. Anyone relying on the documented defaults silently gets `save=False,
     showplot=True` — the opposite of what the signature promises, so no CSVs are written.
     `docs/workflow_demo.ipynb` masks it by passing both as `True`.
   - **Mitigation:** Fix in Phase 3 alongside the failure-isolation change, since both edit the same
     two functions. Use keyword arguments at the call site so the bug cannot recur.

---

## Edge Cases and Error Handling

1. **Case:** `ProSpecPy(None)` — no output folder
   - **Expected Behavior:** `save_plot` prints "No output folder given" and returns; no exception
   - **Implementation:** Phase 2, `save_plot` `None` check first

2. **Case:** `batch_id_sample_name` called on a path with `opus_files` as the last component (no children)
   - **Expected Behavior:** `(None, None)` — `after` is empty
   - **Implementation:** Phase 4 — neither the `len(after) >= 2` nor `len(after) == 1` branch matches
     when `after` is empty, so execution falls through to the final `return None, None` (there is no
     separate explicit `if len(after) == 0:` line in the proposed code)

3. **Case:** `baseline_correction` called with `raw_wavenumber` outside the range of `baseline_points["wavenumber"]`
   - **Expected Behavior:** `np.interp` clamps to the nearest boundary value (documented behaviour of `np.interp`)
   - **Implementation:** No extra handling needed; behaviour is well-defined and better than the original (which would return the nearest point, same effect)

---

## Performance Considerations

- `baseline_correction`: 1000 × 1000 = 1M scalar comparisons → `np.interp` on 1000 points runs in microseconds
- `subtract_baseline`: 7 `UnivariateSpline` constructions → 1 construction; the other six accesses become array lookups

**Measured baseline, for calibration.** The estimates above are asymptotic, not empirical. Profiling
the full seven-stage pipeline over the 19 real samples in `Hyd2_pH6_data/examples for you to try/`
gives **5.0 seconds end to end**, broken down per sample as:

| Stage | Per sample |
|---|---|
| Load OPUS | 3 ms |
| Range cut + water-vapour subtraction | 53 ms |
| Second derivative | 69 ms |
| Peak find + anchor points | 1 ms |
| Baseline correction | 82 ms |
| Gaussian fit | 28 ms |
| Lorentzian fit | 26 ms |

Two conclusions follow. First, Phase 5 optimises the 82 ms line item — real, but 1.6% of a
five-second run, which is why its priority is revised down. Second, this measurement is the basis for
rejecting workflow-orchestration frameworks in the companion plan: any orchestrator whose own fixed
overhead is measured in seconds would cost more than the science it manages.

*Caveat: single machine, warm cache, and the narrow 2150–1850 cm⁻¹ range used in
`docs/workflow_demo.ipynb`, which yields 157-point spectra. A full 3997–499 cm⁻¹ range would grow the
baseline-correction figure quadratically and could change this picture — which is exactly why Phase 5
is still worth doing, just last.*

---

## Documentation Updates

- [ ] `src/prospecpy/__init__.py` — `__all__` list serves as the primary API index
- [ ] `src/prospecpy/prospecpy.py` — `ProSpecPy.__init__` docstring updated with `exist_ok` parameter
- [ ] `src/prospecpy/prospecpy.py` — `save_plot` docstring updated
- [ ] `src/prospecpy/baseline.py` — `baseline_correction` docstring explains `np.interp` and the O(n²) → O(n log n) change
- [ ] `src/prospecpy/io.py` — `batch_id_sample_name` docstring updated with new contract and pathlib rationale
- [ ] `src/prospecpy/remove_wv.py` — module docstring added explaining legacy status

---

## Open Questions

1. **`baseline_correction` numerical equivalence on real data:** The synthetic tests in Phase 5 verify
   `np.interp` vs. the original nearest-neighbour lookup agree exactly on matching grids and within a
   derived, slope-dependent tolerance on synthetic mismatched grids. Neither test runs the actual
   pipeline (`baseline_spline()` → `raw_spline()` → `baseline_correction()`) on a real OPUS spectrum,
   where the true anchor-point range, baseline slope, and noise level are known. **Recommendation:**
   before merging Phase 5, a domain expert should run the before/after implementations on at least one
   real sample and confirm the difference is negligible relative to instrument noise, or explicitly
   accept the documented bound. This is noted as a manual/domain-expert verification step rather than
   an automated one because it requires real instrument data not committed to the repo.

---

## References

**Files Analysed:**
- `src/prospecpy/__init__.py`
- `src/prospecpy/prospecpy.py`
- `src/prospecpy/io.py`
- `src/prospecpy/baseline.py`
- `src/prospecpy/anchor_points.py`
- `src/prospecpy/second_deriv.py`
- `src/prospecpy/vaporfit.py`
- `src/prospecpy/peak_fit.py`
- `src/prospecpy/cut_range.py`
- `src/prospecpy/remove_wv.py`
- `tests/test_import.py`
- `pyproject.toml`

**External Documentation:**
- [`numpy.interp`](https://numpy.org/doc/stable/reference/generated/numpy.interp.html)
- [`pathlib.Path.parts`](https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.parts)
- [`warnings.warn`](https://docs.python.org/3/library/warnings.html#warnings.warn)

---

## Review History

### Version 1.0 — 2026-07-01
- Initial plan created from direct codebase analysis

### Version 1.1 — 2026-08-07
Reviewed against the current state of `src/prospecpy/` and `tests/` (no source or test files were
modified — only this plan document). Findings and fixes:

**Stale/incorrect line numbers:**
- `prospecpy.py:262-335` for `subtract_baseline` → corrected to `262-353` (the method, including the
  `if save:` CSV block, actually runs to line 353); used in both the Current State Analysis and the
  Phase 5 implementation task.
- `prospecpy.py:358-406` for `gaussian_fit_baseline` → corrected to `356-406` (the `def` line is 356,
  not 358; `lorentzian_fit_baseline`'s `408-455` citation was already correct).
- `io.py:43-54` for the Phase 2 double-read fix → corrected to `io.py:39-56` (the actual `for i in
  raw_files:` loop body that the proposed replacement code covers).
- Phase 1's "lines 37–60 untouched" note → corrected to `37–59` (line 60 is a blank line; line 59 is
  the last attribute assignment).

**Numeric/factual errors (verified via `grep -n "raw_spline(" src/prospecpy/prospecpy.py`, which
returns 9 matches: 7 inside `subtract_baseline`, 1 each inside `gaussian_fit_baseline` and
`lorentzian_fit_baseline`):**
- "`raw_spline` called five times" → corrected to seven, in the Current State Analysis, the Phase 5
  task description, the in-code comment, and the "watch it fail" step.
- The Phase 5 and Success Criteria verification steps claimed `grep -c "raw_spline(" ...` would return
  `1` after the fix — corrected to `3`, since `gaussian_fit_baseline` and `lorentzian_fit_baseline`
  each retain their own (untouched) `raw_spline` call.
- Performance Considerations "5 UnivariateSpline constructions → 1" corrected to "7 → 1".
- `save_plot`'s expected `TypeError` message text corrected to match the actual CPython message
  (`"stat: path should be string, bytes, os.PathLike or integer, not NoneType"`), verified empirically.

**Test-correctness bugs (would have caused failing/incorrect tests if implemented as originally written):**
- Phase 3's `test_gaussian_fit_baseline_propagates_exception` didn't set `obj.cut_atmfitparams_obj`.
  Since `gaussian_fit_baseline` evaluates `self.get_subtracted_spectra_wavenumber()`/`...absorbance()`
  as *arguments* to the mocked `raw_spline` (arguments are evaluated before the mock is invoked), the
  test would raise `AttributeError` before ever reaching the mocked `peak_fit`/`raw_spline` calls,
  never actually exercising the exception-propagation path it claims to test. Fixed by adding a
  `MagicMock`-based `cut_atmfitparams_obj`, mirroring the (correct) pattern already used in the Phase 5
  `test_subtract_baseline_calls_raw_spline_once` test.
- Phase 4's `test_handles_windows_style_path` claimed "pathlib normalises Windows separators so this
  works cross-platform" — verified empirically **false**: on POSIX, `pathlib.Path` resolves to
  `PosixPath`, which does not treat `\` as a separator, so `Path(str(PureWindowsPath(...))).parts`
  returns a single opaque component rather than split parts. Since `.github/workflows/ci.yml` runs the
  test matrix on `ubuntu-latest`, `macos-14`, and `windows-latest`, this test would fail on 2 of 3 CI
  platforms even with the pathlib-based fix correctly implemented. Fixed by adding a
  `skipif(sys.platform != "win32", ...)` guard and correcting the "watch it fail" expectation.
- Mock patch targets (`prospecpy.prospecpy.raw_spline`, `prospecpy.prospecpy.peak_fit`,
  `prospecpy.baseline.get_baseline_peak_index`, and the five patch targets in the Phase 5
  `subtract_baseline` test) were all checked against the actual `import` statements in
  `prospecpy/prospecpy.py` and found **correct** — every patched name is bound into the
  `prospecpy.prospecpy` module namespace via a top-level `from ... import ...`, matching where
  `unittest.mock.patch` needs to intercept it. No changes made here.

**Numerical-equivalence claim for `baseline_correction` (Key Architectural Decision 1):**
- The original `test_baseline_correction_matches_original_on_linear_baseline` uses the *same* array
  for both `raw_wavenumber` and `baseline_points["wavenumber"]`. On matching grids, `np.interp` always
  lands exactly on a baseline knot, so it agrees with the original nearest-neighbour lookup to machine
  precision *regardless of baseline slope* — the test never actually exercises the
  interpolation-vs-nearest-neighbour difference that Decision 1's Trade-offs discuss. Verified
  empirically (see calculation below) that on realistic *mismatched* grids (baseline over a narrower
  anchor-point range, as `baseline_spline()` produces, vs. raw data over the full cut-range, as
  `raw_spline()` produces — which is the actual production relationship between these two grids) the
  two methods diverge by roughly `slope * grid_spacing`, e.g. ~2.8e-5 for a gentle slope of 2e-5 and
  ~2.8 cm⁻¹ spacing — three orders of magnitude larger than the claimed `atol=1e-6`, and ~1.4e-3 for
  the plan's own example slope of 0.001. Added a second test
  (`test_baseline_correction_close_to_original_on_mismatched_grids`) using deliberately different
  grids and a derived (not magic-number) tolerance, softened the "numerically identical" language in
  the Desired End State, Migration Strategy, and Risk Assessment sections to reflect the two-tier
  claim (exact on matching grids, bounded-but-nonzero otherwise), and added an Open Question
  recommending a real-data check by a domain expert before merging Phase 5.

**Internal-consistency / minor items:**
- Key Architectural Decision 4's "Trade-offs" bullet described the new `batch_id_sample_name` as
  "extracting the last two parts regardless" of whether `opus_files` is present, and claimed "the
  existing tests do not cover this case" — both statements contradicted the actual Phase 4
  implementation (which returns `(None, None)` via `except ValueError` when `opus_files` is absent,
  identical to the original) and the actual Phase 4 test suite (`test_returns_none_none_when_opus_files_absent`
  explicitly covers it). Corrected to accurately describe the implementation as a behavioral no-op for
  that case.
- "Patterns to Follow" claimed the existing `io.py`/`baseline.py` docstrings are "NumPy-style"; they
  actually use a `Parameters:` / `- name: type` bullet format, not strict numpydoc
  (`Parameters\n----------\nname : type`) — which the plan's own proposed new docstrings for
  `ProSpecPy.__init__`/`save_plot` do use. Added a clarifying note rather than rewriting the
  illustrative code snippets.
- Phase 4's "Dependencies: Phase 1" note was checked against the pattern from Phase 2 (whose test
  literally does `from prospecpy import ProSpecPy`, so the dependency is real). Phase 4's test imports
  `from prospecpy.io import batch_id_sample_name` directly and has no such requirement. Clarified that
  the dependency reflects sequential-merge convention, not a hard technical requirement.
- The Edge Cases entry for "opus_files as the last path component" referenced a non-existent
  `if len(after) == 0: return None, None` line; corrected to describe the actual fallthrough behavior
  of the proposed implementation.

**Confirmed correct (no changes needed):** the twelve-issues-across-five-phases accounting in the
Overview (verified all thirteen Current State Analysis bullets map to twelve distinct issues, since
the double-file-read issue spans two line citations); the "What We're NOT Doing" file list
(`vaporfit.py`, `anchor_points.py`, `cut_range.py`, `second_deriv.py`, `peak_fit.py` are indeed
untouched by every phase's tasks); all `__init__.py` export names against their actual source
locations; the `batch_id_sample_name` pathlib rewrite's behavioral equivalence to the original regex
approach for the non-Windows cases; Phase 2's and Phase 3's stated dependency on Phase 1 (both test
files literally do `from prospecpy import ProSpecPy`); and `tests/test_import.py`'s continued
existence and content.

### Version 1.2 — 2026-08-07

Revised following three parallel audits (an orchestration-framework evaluation, a packaging/pixi
audit, and a documentation/accessibility audit). Those audits ran the pipeline against real data
rather than reading it, which replaced several of this plan's estimates with measurements. A
companion plan, `plan-prospecpy-blockers-and-infrastructure.md`, was created to hold the packaging,
environment, and documentation findings; this entry records only what changed *here*.

**One new issue added (count is now thirteen, was twelve):**
- `save` and `showplot` are **transposed** in both peak-fit batch wrappers
  (`src/prospecpy/peak_fit.py:80,89` and `:92,101`). The wrappers declare
  `(objects, show_plots, save, verbose)` and call positionally into a `(save, showplot, verbose)`
  signature. `docs/workflow_demo.ipynb` masks this by passing both flags as `True`; anyone using the
  documented defaults silently gets `save=False`, so no CSVs are written. Verified by inspection
  against `prospecpy.py:356` and `:408`. A fix task and a regression test were added to Phase 3, and
  "What We're NOT Doing" was narrowed accordingly — `peak_fit.py`'s numerical functions remain
  untouched, but its two batch wrappers are now in scope.

**Three estimates replaced with measurements:**
- **Phase 3's risk is now known-certain, and the mitigation is now mandatory.** Risk item 2 rated
  batch-halting as "Likelihood: Medium (failures may exist in wild data)". Measurement:
  **8 of 19** real samples in `Hyd2_pH6_data/examples for you to try/` fail `curve_fit` with
  `maxfev` exhaustion today, all silently swallowed. Shipping the re-raise alone would kill the
  notebook around sample 3 with no output — strictly worse than current behaviour. The
  "can be wrapped in try/except if needed" mitigation was promoted from an optional suggestion to a
  required Phase 3 task with tests.
- **Phase 5 priority revised down.** The plan justified it with an unmeasured "~1 second per
  spectrum at 1000 points". Measured: **82 ms per sample**, within a **5.0 second** end-to-end
  pipeline over 19 samples. Still correct and still worth doing — it protects against higher
  resolution or a wider wavenumber range — but it is now explicitly sequenced last and must not
  block other phases. A per-stage timing table was added to Performance Considerations.
- **Phase 4 superseded.** Its implementation deliberately preserves `(None, None)` for paths lacking
  `opus_files`. Measurement: on the project's own `Hyd2_pH6_data/` tree that behaviour routes every
  sample to `<output>/None/None` and raises `FileExistsError` on sample 2 — **ProSpecPy cannot
  currently run on its own data**. A superseding notice now heads the phase, pointing at
  `plan-prospecpy-blockers-and-infrastructure.md` Phase 2, which keeps the pathlib/Windows fix, adds
  a filename fallback, and removes the `io.py:81` `\s` escape defect as a side effect. Risk item 3
  was annotated to match.

**Also recorded:**
- A scope-boundary note in the Overview describing the companion plan and the two ordering
  constraints between them (that plan's Phase 2 supersedes this plan's Phase 4; its Phase 1 should
  precede this plan's Phase 1, because adding package-root exports while `ipywidgets` is undeclared
  would break `cd.yml`'s release-time import smoke test).
- Orchestration frameworks (Prefect, Dask, Snakemake, Airflow, Luigi, Pydra, Nextflow) were
  evaluated and rejected on measured grounds; the rationale lives in the companion plan's "What
  We're NOT Doing" so the question is not reopened without new information.
