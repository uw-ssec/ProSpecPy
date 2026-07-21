#!/usr/bin/env python3
"""

Minimum input:
    A directory containing ProSpecPy outputs with files named
    arpls_baseline_corrected_data.csv and, optionally,
    arpls_baseline_corrected_peak_info.csv.

Main output:
    erni_inputs/baseline_metadata.csv
    erni_fitting_outputs/fit_attempts.csv
    erni_fitting_outputs/fitted_peaks.csv
    erni_fitting_outputs/rule_events.csv
    report_plots/*.png
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import sys
import warnings
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

try:
    import numpy as np
    from scipy.optimize import OptimizeWarning, curve_fit
    from scipy.signal import find_peaks, peak_widths
except ImportError as exc:  # pragma: no cover - user environment guard.
    raise SystemExit(
        "Missing required Python packages. Install with:\n"
        "  python -m pip install numpy scipy matplotlib pandas brukeropusreader\n"
        f"Original import error: {exc}"
    ) from exc


ATTEMPT_HEADER = [
    "fit_attempt_id",
    "processing_run_id",
    "sample_id",
    "raw_file",
    "run_timestamp_utc",
    "software_version",
    "processing_mode",
    "fit_attempt_status",
    "fit_model",
    "solver",
    "bound_profile_id",
    "wavenumber_min_cm1",
    "wavenumber_max_cm1",
    "threshold",
    "adjustment_factor",
    "atmospheric_correction_method",
    "baseline_method",
    "baseline_config_json",
    "detected_peak_count",
    "fitted_peak_count",
    "fit_converged",
    "solver_status",
    "solver_message",
    "nfev",
    "rmse",
    "residual_mean",
    "residual_max_abs",
    "input_qc_pass",
    "input_qc_reason",
    "baseline_qc_pass",
    "baseline_qc_reason",
    "baseline_over_fraction",
    "baseline_max_overshoot",
    "baseline_oversubtraction_area",
    "zero_clipping_fraction",
    "fit_valid",
    "fit_valid_reason",
    "needs_manual_review",
    "manual_review_reason",
    "overall_qc",
    "overall_qc_reason",
    "triggered_rule_count",
    "notes",
]

PEAK_HEADER = [
    "peak_result_id",
    "fit_attempt_id",
    "peak_index",
    "peak_identity",
    "peak_assignment_status",
    "reference_evidence_ids",
    "matched_reference_centre_cm1",
    "initial_centre_cm1",
    "initial_model_amplitude",
    "initial_fwhm_cm1",
    "fitted_centre_cm1",
    "centre_deviation_cm1",
    "raw_model_amplitude",
    "raw_width_parameter",
    "raw_width_parameter_name",
    "peak_height",
    "peak_area",
    "fwhm_cm1",
    "position_stderr",
    "height_stderr",
    "area_stderr",
    "fwhm_stderr",
    "peak_valid",
    "peak_valid_reason",
    "needs_manual_review",
    "manual_review_reason",
    "notes",
]

EVENT_HEADER = [
    "rule_event_id",
    "fit_attempt_id",
    "peak_result_id",
    "rule_namespace",
    "rule_id",
    "bound_profile_id",
    "event_scope",
    "severity",
    "parameter",
    "observed_value",
    "lower_bound_used",
    "upper_bound_used",
    "units",
    "violation_action",
    "affects_fit_valid",
    "affects_overall_qc",
    "message",
    "evidence_source_ids",
    "created_at_utc",
]

MODELS = ("Gaussian", "Lorentzian")
ANALYSIS_MIN_CM1 = 1800.0
ANALYSIS_MAX_CM1 = 2150.0
WRAPPER_VERSION = "week6_standalone_peak_fitting_wrapper_v0.1"

METRIC_MEANINGS = {
    "completed_attempts": "Fit attempts that completed and produced interpretable solver output",
    "converged_attempts": "Fit attempts where the optimizer converged",
    "fit_valid_attempts": "Attempts passing fitting-level physical bounds and safety checks",
    "fitted_peaks": "Total fitted peak rows exported",
    "valid_peaks": "Fitted peaks passing hard safety checks",
    "overall_qc_pass_attempts": "Attempts where input, baseline, and fitting QC all passed",
    "manual_review_events": "WARN or REVIEW rule events requiring human inspection",
    "failed_fit_events": "FAIL events that affect fit_valid",
    "mean_rmse": "Mean fit-level RMSE across attempts with numeric RMSE",
    "median_rmse": "Median fit-level RMSE across attempts with numeric RMSE",
    "mean_residual_max_abs": "Mean maximum absolute residual across attempts with numeric values",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_argument_group("input")
    input_group.add_argument(
        "--erni-output-root",
        type=Path,
        help=(
            "Directory containing Erni native arPLS outputs to scan recursively. "
            "Not needed if --erni-metadata is provided."
        ),
    )
    input_group.add_argument(
        "--erni-metadata",
        type=Path,
        help=(
            "Already standardized baseline_metadata.csv. If provided, the "
            "Erni input preparation step is skipped."
        ),
    )
    input_group.add_argument(
        "--control-metadata",
        type=Path,
        help=(
            "Optional control baseline_metadata.csv in the same contract. "
            "Use this for initial anchor+spline vs Erni arPLS comparison."
        ),
    )
    input_group.add_argument(
        "--run-native-arpls",
        action="store_true",
        help="Optionally run Erni's ProSpecPy arPLS workflow from raw pD6 data first.",
    )
    input_group.add_argument(
        "--workflow-root",
        type=Path,
        default=Path("/Users/lili/Desktop/IC irp/ProSpecPy-irp-initial-exploration"),
        help="Root containing data/opus_files/pD6 and data/opus_files/water_vapor.",
    )
    input_group.add_argument(
        "--source-repo",
        type=Path,
        default=Path("/Users/lili/Documents/GitHub/ProSpecPy"),
        help="ProSpecPy repo containing src/prospecpy.",
    )

    output_group = parser.add_argument_group("output")
    output_group.add_argument(
        "--output-dir",
        type=Path,
        default=Path("week6_standalone_outputs"),
        help="Directory for all generated outputs.",
    )
    output_group.add_argument("--overwrite", action="store_true")
    output_group.add_argument("--skip-plots", action="store_true")

    fitting_group = parser.add_argument_group("fitting")
    fitting_group.add_argument("--analysis-min-cm1", type=float, default=ANALYSIS_MIN_CM1)
    fitting_group.add_argument("--analysis-max-cm1", type=float, default=ANALYSIS_MAX_CM1)
    fitting_group.add_argument("--bound-profile-id", default="pD6_bounds_v0.1")
    fitting_group.add_argument("--peak-prominence-fraction", type=float, default=0.08)
    fitting_group.add_argument("--min-peak-distance-cm1", type=float, default=8.0)
    fitting_group.add_argument("--max-peaks", type=int, default=8)
    fitting_group.add_argument("--maxfev", type=int, default=20000)

    arpls_group = parser.add_argument_group("Erni arPLS metadata defaults")
    arpls_group.add_argument("--baseline-family", default="arPLS")
    arpls_group.add_argument("--baseline-method", default="peak_guided_arPLS")
    arpls_group.add_argument("--baseline-implementation", default="Erni_ProSpecPy_week6")
    arpls_group.add_argument("--config-source", default="Erni workflow_demo.ipynb Week 6 default")
    arpls_group.add_argument("--lam", type=float, default=1e5)
    arpls_group.add_argument("--ratio", type=float, default=1e-6)
    arpls_group.add_argument("--max-iter", type=int, default=50)
    arpls_group.add_argument("--peak-threshold", type=float, default=0.35)
    arpls_group.add_argument("--peak-window", type=int, default=35)
    arpls_group.add_argument("--peak-weight", type=float, default=0.3)
    arpls_group.add_argument("--alpha", type=float, default=0.8)
    arpls_group.add_argument("--range-start", type=int, default=2150)
    arpls_group.add_argument("--range-end", type=int, default=1850)
    return parser.parse_args()


def prepare_dir(path: Path, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"{path} already exists; use --overwrite")
        shutil.rmtree(path)
    path.mkdir(parents=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in header})


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bool_text(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def parse_bool(value: str | None, *, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().upper()
    if normalized in {"TRUE", "PASS", "YES", "1"}:
        return True
    if normalized in {"FALSE", "FAIL", "NO", "0"}:
        return False
    raise ValueError(f"Unrecognised boolean value: {value!r}")


def clean_number(value: float | int | str | None) -> str:
    if value is None or value == "":
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(numeric):
        return ""
    return repr(float(numeric))


def clean_observed(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
    return str(value)


def slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return text or "unknown"


def resolve_relative(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else base_dir / path


def finite_numbers(values: list[str]) -> list[float]:
    numbers: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numbers.append(number)
    return numbers


def baseline_config(args: argparse.Namespace) -> str:
    config = {
        "baseline_family": args.baseline_family,
        "baseline_method": args.baseline_method,
        "baseline_implementation": args.baseline_implementation,
        "config_source": args.config_source,
        "lam": args.lam,
        "ratio": args.ratio,
        "max_iter": args.max_iter,
        "peak_threshold": args.peak_threshold,
        "peak_window": args.peak_window,
        "peak_weight": args.peak_weight,
        "alpha": args.alpha,
    }
    return json.dumps(config, separators=(",", ":"), sort_keys=True)


def sample_id_from_output_folder(path: Path) -> str:
    sample_name = path.parent.name
    first_token = sample_name.split()[0] if sample_name.split() else sample_name
    return first_token or slug(sample_name)


def spectrum_qc(rows: list[dict[str, str]]) -> tuple[str, str, str]:
    if not rows:
        return "FALSE", "empty_corrected_spectrum", ""
    header = set(rows[0])
    if {"wavenumber_cm1", "absorbance_corrected"}.issubset(header):
        y_col = "absorbance_corrected"
    elif {"wavenumber", "absorbance"}.issubset(header):
        y_col = "absorbance"
    else:
        return "FALSE", "missing_corrected_spectrum_columns", ""

    y = finite_numbers([row.get(y_col, "") for row in rows])
    if len(y) != len(rows):
        return "FALSE", "nonfinite_corrected_spectrum_values", ""
    if max(abs(value) for value in y) == 0:
        return "FALSE", "all_zero_corrected_spectrum", "1"
    zero_fraction = sum(value <= 0 for value in y) / len(y)
    return "TRUE", "provisional_numeric_qc_pass", f"{zero_fraction:.6g}"


def write_standard_spectrum(source: Path, dest: Path) -> tuple[str, str, str]:
    rows = read_csv(source)
    qc_pass, qc_reason, zero_fraction = spectrum_qc(rows)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        dest.write_text("wavenumber_cm1,absorbance_corrected\n", encoding="utf-8")
        return qc_pass, qc_reason, zero_fraction

    header = set(rows[0])
    if {"wavenumber_cm1", "absorbance_corrected"}.issubset(header):
        x_col = "wavenumber_cm1"
        y_col = "absorbance_corrected"
    elif {"wavenumber", "absorbance"}.issubset(header):
        x_col = "wavenumber"
        y_col = "absorbance"
    else:
        raise ValueError(f"Cannot standardize spectrum columns in {source}")

    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["wavenumber_cm1", "absorbance_corrected"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "wavenumber_cm1": row[x_col],
                    "absorbance_corrected": row[y_col],
                }
            )
    return qc_pass, qc_reason, zero_fraction


def write_candidate_peaks(source: Path, dest: Path) -> None:
    rows = read_csv(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["peak_index", "wavenumber_cm1", "absorbance_corrected"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "peak_index": row.get("peak_index", ""),
                    "wavenumber_cm1": row.get("wavenumber_cm1") or row.get("wavenumber", ""),
                    "absorbance_corrected": row.get("absorbance_corrected")
                    or row.get("absorbance", ""),
                }
            )


def run_native_arpls(args: argparse.Namespace, native_output: Path) -> None:
    source = args.source_repo / "src"
    sample_dir = args.workflow_root / "data" / "opus_files" / "pD6"
    water_dir = args.workflow_root / "data" / "opus_files" / "water_vapor"
    for required in (source, sample_dir, water_dir):
        if not required.exists():
            raise FileNotFoundError(required)
    prepare_dir(native_output, args.overwrite)
    sys.path.insert(0, str(source))

    from prospecpy.cut_range import cut_range_subtract_prospecpy_objects
    from prospecpy.io import import_run_data
    from prospecpy.second_deriv import second_deriv_prospecpy_objects

    spectra = import_run_data(
        sample_dir,
        input_type="raw spectra",
        output_folder=str(native_output),
    )
    water = import_run_data(water_dir)
    cut_range_subtract_prospecpy_objects(
        spectra,
        water,
        range_start=args.range_start,
        range_end=args.range_end,
        showplots=False,
        save=True,
        verbose=False,
    )
    second_deriv_prospecpy_objects(
        spectra,
        show_plots=False,
        save=True,
        verbose=False,
    )
    for obj in spectra:
        obj.peak_finder(args.peak_threshold)
        obj.subtract_baseline_arpls(
            lam=args.lam,
            ratio=args.ratio,
            max_iter=args.max_iter,
            peak_window=args.peak_window,
            peak_weight=args.peak_weight,
            alpha=args.alpha,
            save=True,
            showplot=False,
            verbose=False,
        )

    metadata = {
        "generated_at_utc": utc_now(),
        "source_repo": str(args.source_repo),
        "workflow_root": str(args.workflow_root),
        "baseline_family": args.baseline_family,
        "baseline_method": args.baseline_method,
        "baseline_implementation": args.baseline_implementation,
        "config_source": args.config_source,
        "lam": args.lam,
        "ratio": args.ratio,
        "max_iter": args.max_iter,
        "peak_threshold": args.peak_threshold,
        "peak_window": args.peak_window,
        "peak_weight": args.peak_weight,
        "alpha": args.alpha,
        "sample_count": len(spectra),
    }
    (native_output / "erni_arpls_run_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def prepare_erni_inputs(args: argparse.Namespace, erni_root: Path, output_dir: Path) -> Path:
    prepare_dir(output_dir, args.overwrite)
    (output_dir / "corrected_spectra").mkdir(exist_ok=True)
    (output_dir / "candidate_peaks").mkdir(exist_ok=True)

    source_files = sorted(erni_root.rglob("arpls_baseline_corrected_data.csv"))
    if not source_files:
        raise FileNotFoundError(
            f"No arpls_baseline_corrected_data.csv files found under {erni_root}"
        )

    seen_run_ids: set[str] = set()
    metadata_rows: list[dict[str, str]] = []
    for source in source_files:
        sample_id = sample_id_from_output_folder(source)
        base_run_id = f"erni-arpls-{slug(sample_id)}"
        run_id = base_run_id
        suffix = 2
        while run_id in seen_run_ids:
            run_id = f"{base_run_id}-{suffix}"
            suffix += 1
        seen_run_ids.add(run_id)

        spectrum_dest_name = f"{run_id}.csv"
        qc_pass, qc_reason, zero_fraction = write_standard_spectrum(
            source, output_dir / "corrected_spectra" / spectrum_dest_name
        )

        candidate_peak_file = ""
        peak_source = source.with_name("arpls_baseline_corrected_peak_info.csv")
        if peak_source.exists():
            peak_dest_name = f"{run_id}_candidate_peaks.csv"
            write_candidate_peaks(peak_source, output_dir / "candidate_peaks" / peak_dest_name)
            candidate_peak_file = f"candidate_peaks/{peak_dest_name}"

        metadata_rows.append(
            {
                "processing_run_id": run_id,
                "sample_id": sample_id,
                "raw_file": source.parent.name,
                "baseline_family": args.baseline_family,
                "baseline_method": args.baseline_method,
                "baseline_implementation": args.baseline_implementation,
                "baseline_config_json": baseline_config(args),
                "corrected_spectrum_file": f"corrected_spectra/{spectrum_dest_name}",
                "baseline_qc_pass": qc_pass,
                "baseline_qc_reason": qc_reason,
                "input_qc_pass": "TRUE",
                "input_qc_reason": "",
                "baseline_over_fraction": "",
                "baseline_max_overshoot": "",
                "baseline_oversubtraction_area": "",
                "zero_clipping_fraction": zero_fraction,
                "candidate_peak_file": candidate_peak_file,
                "notes": (
                    "Prepared from Erni Week 6 arPLS output; baseline QC is "
                    "provisional numeric availability QC, not a validated "
                    "baseline-quality threshold."
                ),
            }
        )

    metadata_path = output_dir / "baseline_metadata.csv"
    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metadata_rows[0]))
        writer.writeheader()
        writer.writerows(metadata_rows)
    return metadata_path


def validate_metadata(rows: list[dict[str, str]]) -> None:
    required = {
        "processing_run_id",
        "sample_id",
        "raw_file",
        "baseline_method",
        "baseline_config_json",
        "corrected_spectrum_file",
        "baseline_qc_pass",
        "baseline_qc_reason",
    }
    if not rows:
        raise ValueError("baseline_metadata.csv is empty")
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"baseline_metadata.csv missing required columns: {missing}")
    for row in rows:
        json.loads(row["baseline_config_json"] or "{}")


def gaussian(x: np.ndarray, *params: float) -> np.ndarray:
    y = np.zeros_like(x, dtype=float)
    for offset in range(0, len(params), 3):
        amplitude = params[offset]
        centre = params[offset + 1]
        sigma = params[offset + 2]
        y += (
            amplitude
            * (1.0 / (sigma * np.sqrt(2.0 * np.pi)))
            * np.exp(-0.5 * ((x - centre) / sigma) ** 2)
        )
    return y


def lorentzian(x: np.ndarray, *params: float) -> np.ndarray:
    y = np.zeros_like(x, dtype=float)
    for offset in range(0, len(params), 3):
        amplitude = params[offset]
        centre = params[offset + 1]
        sigma = params[offset + 2]
        y += amplitude * sigma**2 / ((x - centre) ** 2 + sigma**2)
    return y


def objective_for_model(model: str):
    if model == "Gaussian":
        return gaussian
    if model == "Lorentzian":
        return lorentzian
    raise ValueError(model)


def load_spectrum(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"{path} is empty")
    header = set(rows[0])
    if {"wavenumber_cm1", "absorbance_corrected"}.issubset(header):
        x_col = "wavenumber_cm1"
        y_col = "absorbance_corrected"
    elif {"wavenumber", "absorbance"}.issubset(header):
        x_col = "wavenumber"
        y_col = "absorbance"
    else:
        raise ValueError(
            f"{path} must contain wavenumber_cm1/absorbance_corrected "
            "or legacy wavenumber/absorbance columns"
        )
    x = np.asarray([float(row[x_col]) for row in rows], dtype=float)
    y = np.asarray([float(row[y_col]) for row in rows], dtype=float)
    return x, y


def window_spectrum(
    x: np.ndarray, y: np.ndarray, lower: float, upper: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lo = min(lower, upper)
    hi = max(lower, upper)
    mask = np.isfinite(x) & np.isfinite(y) & (x >= lo) & (x <= hi)
    if np.count_nonzero(mask) < 5:
        raise ValueError("Fewer than 5 finite points in fitting window")
    return x[mask], y[mask], np.flatnonzero(mask)


def median_step_cm1(x: np.ndarray) -> float:
    diffs = np.diff(np.sort(x))
    finite = diffs[np.isfinite(diffs) & (diffs > 0)]
    if len(finite) == 0:
        return 1.0
    return float(np.median(finite))


def load_candidate_indices(
    candidate_path: Path, full_x: np.ndarray, window_full_indices: np.ndarray
) -> np.ndarray:
    rows = read_csv(candidate_path)
    if not rows:
        return np.asarray([], dtype=int)

    full_to_window = {int(full_idx): idx for idx, full_idx in enumerate(window_full_indices)}
    window_x = full_x[window_full_indices]
    local_indices: list[int] = []
    for row in rows:
        if row.get("peak_index", "").strip() != "":
            full_idx = int(float(row["peak_index"]))
            if full_idx in full_to_window:
                local_indices.append(full_to_window[full_idx])
                continue
        wavenumber = row.get("wavenumber_cm1") or row.get("wavenumber")
        if wavenumber:
            nearest = int(np.argmin(np.abs(window_x - float(wavenumber))))
            local_indices.append(nearest)

    unique = sorted(set(local_indices))
    return np.asarray(unique, dtype=int)


def detect_peak_indices(
    x: np.ndarray,
    y: np.ndarray,
    *,
    prominence_fraction: float,
    min_distance_cm1: float,
    max_peaks: int,
) -> np.ndarray:
    y_for_detection = np.asarray(y, dtype=float)
    y_range = float(np.max(y_for_detection) - np.min(y_for_detection))
    if y_range <= 0:
        return np.asarray([], dtype=int)

    prominence = max(y_range * prominence_fraction, float(np.std(y_for_detection)) * 0.5)
    distance = max(1, int(round(min_distance_cm1 / median_step_cm1(x))))
    peaks, properties = find_peaks(
        y_for_detection,
        prominence=prominence,
        distance=distance,
    )
    if len(peaks) > max_peaks:
        prominences = properties.get("prominences", np.zeros_like(peaks, dtype=float))
        selected = np.argsort(prominences)[-max_peaks:]
        peaks = peaks[selected]
    return np.asarray(sorted(set(int(idx) for idx in peaks)), dtype=int)


def initial_guess(
    model: str, x: np.ndarray, y: np.ndarray, peak_indices: np.ndarray
) -> list[float]:
    step = median_step_cm1(x)
    widths = peak_widths(y, peak_indices, rel_height=0.5)[0] if len(peak_indices) else []
    y_max = float(np.max(y)) if len(y) else 0.0
    guess: list[float] = []
    for order, idx in enumerate(peak_indices):
        centre = float(x[idx])
        height = float(y[idx])
        if not math.isfinite(height) or height <= 0:
            height = max(y_max * 0.25, 1e-6)
        width_points = float(widths[order]) if order < len(widths) else 0.0
        fwhm = max(width_points * step, step * 4.0)
        if model == "Gaussian":
            sigma = fwhm / (2.0 * math.sqrt(2.0 * math.log(2.0)))
            amplitude = height * sigma * math.sqrt(2.0 * math.pi)
        else:
            sigma = fwhm / 2.0
            amplitude = height
        guess.extend([amplitude, centre, sigma])
    return guess


def fit_model(
    model: str,
    x: np.ndarray,
    y: np.ndarray,
    peak_indices: np.ndarray,
    maxfev: int,
) -> tuple[np.ndarray | None, dict[str, object], list[str]]:
    if len(peak_indices) == 0:
        return None, {"status": "not_run", "message": "No candidate peaks detected."}, []

    p0 = initial_guess(model, x, y, peak_indices)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", OptimizeWarning)
            params, _ = curve_fit(objective_for_model(model), x, y, p0=p0, maxfev=maxfev)
        predicted = objective_for_model(model)(x, *params)
        residual = y - predicted
        metrics = {
            "status": "completed",
            "message": "",
            "rmse": float(np.sqrt(np.mean(residual**2))),
            "residual_mean": float(np.mean(residual)),
            "residual_max_abs": float(np.max(np.abs(residual))),
        }
        return np.asarray(params, dtype=float), metrics, [str(item.message) for item in caught]
    except RuntimeError as exc:
        return None, {"status": "nonconverged", "message": f"RuntimeError: {exc}"}, []
    except Exception as exc:  # pragma: no cover - retained for robust batch runs.
        return None, {"status": "error", "message": f"{type(exc).__name__}: {exc}"}, []


def derived_peak_values(model: str, amplitude: float, sigma: float) -> dict[str, float | str]:
    if model == "Gaussian":
        height = amplitude / (sigma * math.sqrt(2.0 * math.pi))
        area = amplitude
        fwhm = 2.0 * math.sqrt(2.0 * math.log(2.0)) * abs(sigma)
        width_name = "sigma"
    else:
        height = amplitude
        area = math.pi * amplitude * abs(sigma)
        fwhm = 2.0 * abs(sigma)
        width_name = "gamma"
    return {
        "height": float(height),
        "area": float(area),
        "fwhm": float(fwhm),
        "width_name": width_name,
    }


def safety_checks(
    *,
    centre: float,
    amplitude: float,
    sigma: float,
    height: float,
    area: float,
    fwhm: float,
    lower: float,
    upper: float,
) -> list[dict[str, str]]:
    window_width = abs(upper - lower)
    checks: list[dict[str, str]] = []

    def add(
        reason: str,
        rule_id: str,
        parameter: str,
        observed: object,
        lo: str = "",
        hi: str = "",
        units: str = "",
    ) -> None:
        checks.append(
            {
                "reason": reason,
                "rule_id": rule_id,
                "parameter": parameter,
                "observed": clean_observed(observed),
                "lower": lo,
                "upper": hi,
                "units": units,
            }
        )

    finite_values = {
        "fitted_centre_cm1": centre,
        "raw_model_amplitude": amplitude,
        "raw_width_parameter": sigma,
        "peak_height": height,
        "peak_area": area,
        "fwhm_cm1": fwhm,
    }
    for parameter, value in finite_values.items():
        if not math.isfinite(value):
            add(f"{parameter}_nonfinite", "SAFETY_FINITE_PARAMETER", parameter, value)
    if checks:
        return checks

    if not (min(lower, upper) <= centre <= max(lower, upper)):
        add(
            "centre_outside_analysis_window",
            "SAFETY_CENTRE_WINDOW",
            "fitted_centre_cm1",
            centre,
            clean_number(min(lower, upper)),
            clean_number(max(lower, upper)),
            "cm-1",
        )
    if amplitude <= 0:
        add(
            "nonpositive_model_amplitude",
            "SAFETY_MODEL_AMPLITUDE_POSITIVE",
            "raw_model_amplitude",
            amplitude,
            "0",
            "",
            "model_specific",
        )
    if sigma <= 0:
        add(
            "nonpositive_raw_width",
            "SAFETY_RAW_WIDTH_POSITIVE",
            "raw_width_parameter",
            sigma,
            "0",
            "",
            "model_specific",
        )
    if height <= 0:
        add(
            "nonpositive_peak_height",
            "SAFETY_HEIGHT_POSITIVE",
            "peak_height",
            height,
            "0",
            "",
            "absorbance",
        )
    if area <= 0:
        add(
            "nonpositive_peak_area",
            "SAFETY_AREA_POSITIVE",
            "peak_area",
            area,
            "0",
            "",
            "absorbance*cm-1",
        )
    if fwhm <= 0 or fwhm >= window_width:
        add(
            "invalid_fwhm",
            "SAFETY_FWHM_RANGE",
            "fwhm_cm1",
            fwhm,
            "0",
            "fitting_window_width_cm1",
            "cm-1",
        )
    return checks


def add_event(
    events: list[dict[str, object]],
    counters: Counter[str],
    attempt_id: str,
    *,
    peak_id: str = "",
    namespace: str,
    rule_id: str,
    bound_profile_id: str = "",
    scope: str,
    severity: str,
    parameter: str = "",
    observed: str = "",
    lower: str = "",
    upper: str = "",
    units: str = "",
    action: str,
    affects_fit: bool,
    affects_overall: bool,
    message: str,
    created_at: str,
) -> None:
    counters[attempt_id] += 1
    events.append(
        {
            "rule_event_id": f"{attempt_id}-e{counters[attempt_id]:03d}",
            "fit_attempt_id": attempt_id,
            "peak_result_id": peak_id,
            "rule_namespace": namespace,
            "rule_id": rule_id,
            "bound_profile_id": bound_profile_id,
            "event_scope": scope,
            "severity": severity,
            "parameter": parameter,
            "observed_value": observed,
            "lower_bound_used": lower,
            "upper_bound_used": upper,
            "units": units,
            "violation_action": action,
            "affects_fit_valid": bool_text(affects_fit),
            "affects_overall_qc": bool_text(affects_overall),
            "message": message,
            "evidence_source_ids": "",
            "created_at_utc": created_at,
        }
    )


def attempt_status_from_fit_status(status: str) -> str:
    if status == "completed":
        return "completed"
    if status == "nonconverged":
        return "nonconverged"
    if status == "not_run":
        return "not_run"
    return "error"


def run_fitting(
    baseline_metadata: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> None:
    prepare_dir(output_dir, args.overwrite)
    metadata_rows = read_csv(baseline_metadata)
    validate_metadata(metadata_rows)
    metadata_dir = baseline_metadata.resolve().parent
    generated_at = utc_now()

    attempts: list[dict[str, object]] = []
    peaks: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    event_counters: Counter[str] = Counter()

    for meta in metadata_rows:
        processing_run_id = meta["processing_run_id"]
        spectrum_path = resolve_relative(meta["corrected_spectrum_file"], metadata_dir)
        full_x, full_y = load_spectrum(spectrum_path)
        fit_x, fit_y, window_full_indices = window_spectrum(
            full_x, full_y, args.analysis_min_cm1, args.analysis_max_cm1
        )

        candidate_source = "internal_find_peaks"
        candidate_file = meta.get("candidate_peak_file", "").strip()
        if candidate_file:
            candidate_path = resolve_relative(candidate_file, metadata_dir)
            peak_indices = load_candidate_indices(candidate_path, full_x, window_full_indices)
            candidate_source = str(candidate_path)
        else:
            peak_indices = detect_peak_indices(
                fit_x,
                fit_y,
                prominence_fraction=args.peak_prominence_fraction,
                min_distance_cm1=args.min_peak_distance_cm1,
                max_peaks=args.max_peaks,
            )

        input_qc_pass = parse_bool(meta.get("input_qc_pass"), default=True)
        baseline_qc_pass = parse_bool(meta.get("baseline_qc_pass"), default=True)
        baseline_reason = meta.get("baseline_qc_reason", "")
        input_reason = meta.get("input_qc_reason", "")
        threshold_value = (
            clean_number(args.peak_prominence_fraction)
            if candidate_source == "internal_find_peaks"
            else ""
        )

        for model in MODELS:
            attempt_id = f"{processing_run_id}-{model.lower()}"
            params, fit_metrics, caught_warnings = fit_model(
                model, fit_x, fit_y, peak_indices, args.maxfev
            )
            fit_status = str(fit_metrics["status"])
            fit_converged = fit_status == "completed"
            attempt_peak_rows: list[dict[str, object]] = []
            peak_valid_values: list[bool] = []

            if not input_qc_pass:
                add_event(
                    events,
                    event_counters,
                    attempt_id,
                    namespace="input_qc",
                    rule_id="INPUT_QC_FAILURE",
                    scope="run",
                    severity="FAIL",
                    parameter="input_qc_pass",
                    observed="FALSE",
                    action="set_overall_qc_false_only",
                    affects_fit=False,
                    affects_overall=True,
                    message=input_reason or "Input QC failed upstream.",
                    created_at=generated_at,
                )

            if not baseline_qc_pass:
                add_event(
                    events,
                    event_counters,
                    attempt_id,
                    namespace="baseline_qc",
                    rule_id="BASELINE_QC_FAILURE",
                    scope="run",
                    severity="FAIL",
                    parameter="baseline_qc_pass",
                    observed="FALSE",
                    action="set_overall_qc_false_only",
                    affects_fit=False,
                    affects_overall=True,
                    message=baseline_reason or "Baseline QC failed upstream.",
                    created_at=generated_at,
                )

            if fit_status == "not_run":
                add_event(
                    events,
                    event_counters,
                    attempt_id,
                    namespace="fit_qc",
                    rule_id="NO_CANDIDATE_PEAKS",
                    scope="fit",
                    severity="FAIL",
                    parameter="detected_peak_count",
                    observed="0",
                    action="set_fit_valid_false",
                    affects_fit=True,
                    affects_overall=True,
                    message="No candidate peaks were detected for fitting.",
                    created_at=generated_at,
                )
            elif fit_status != "completed":
                add_event(
                    events,
                    event_counters,
                    attempt_id,
                    namespace="fit_qc",
                    rule_id="FIT_NONCONVERGENCE" if fit_status == "nonconverged" else "FIT_ERROR",
                    scope="fit",
                    severity="FAIL",
                    parameter="fit_converged",
                    observed="FALSE",
                    action="set_fit_valid_false",
                    affects_fit=True,
                    affects_overall=True,
                    message=str(fit_metrics.get("message", "Fitting failed.")),
                    created_at=generated_at,
                )

            for warning_message in caught_warnings:
                add_event(
                    events,
                    event_counters,
                    attempt_id,
                    namespace="fit_qc",
                    rule_id="SCIPY_OPTIMIZE_WARNING",
                    scope="fit",
                    severity="WARN",
                    parameter="parameter_covariance",
                    action="flag_manual_review_only",
                    affects_fit=False,
                    affects_overall=False,
                    message=warning_message,
                    created_at=generated_at,
                )

            if params is not None:
                for peak_index, offset in enumerate(range(0, len(params), 3), start=1):
                    peak_id = f"{attempt_id}-p{peak_index:03d}"
                    amplitude = float(params[offset])
                    centre = float(params[offset + 1])
                    sigma = float(params[offset + 2])
                    derived = derived_peak_values(model, amplitude, sigma)
                    violations = safety_checks(
                        centre=centre,
                        amplitude=amplitude,
                        sigma=sigma,
                        height=float(derived["height"]),
                        area=float(derived["area"]),
                        fwhm=float(derived["fwhm"]),
                        lower=args.analysis_min_cm1,
                        upper=args.analysis_max_cm1,
                    )
                    peak_valid = len(violations) == 0
                    peak_valid_values.append(peak_valid)
                    reasons = "; ".join(item["reason"] for item in violations)

                    peak_row = {
                        "peak_result_id": peak_id,
                        "fit_attempt_id": attempt_id,
                        "peak_index": peak_index,
                        "peak_identity": "",
                        "peak_assignment_status": "unassigned",
                        "reference_evidence_ids": "",
                        "matched_reference_centre_cm1": "",
                        "initial_centre_cm1": clean_number(fit_x[peak_indices[peak_index - 1]])
                        if peak_index - 1 < len(peak_indices)
                        else "",
                        "initial_model_amplitude": "",
                        "initial_fwhm_cm1": "",
                        "fitted_centre_cm1": clean_number(centre),
                        "centre_deviation_cm1": "",
                        "raw_model_amplitude": clean_number(amplitude),
                        "raw_width_parameter": clean_number(sigma),
                        "raw_width_parameter_name": derived["width_name"],
                        "peak_height": clean_number(float(derived["height"])),
                        "peak_area": clean_number(float(derived["area"])),
                        "fwhm_cm1": clean_number(float(derived["fwhm"])),
                        "position_stderr": "",
                        "height_stderr": "",
                        "area_stderr": "",
                        "fwhm_stderr": "",
                        "peak_valid": bool_text(peak_valid),
                        "peak_valid_reason": reasons,
                        "needs_manual_review": "FALSE",
                        "manual_review_reason": "",
                        "notes": "No automatic peak identity assignment was applied.",
                    }
                    attempt_peak_rows.append(peak_row)

                    for violation in violations:
                        add_event(
                            events,
                            event_counters,
                            attempt_id,
                            peak_id=peak_id,
                            namespace="bounds_profile",
                            rule_id=violation["rule_id"],
                            bound_profile_id=args.bound_profile_id,
                            scope="peak",
                            severity="FAIL",
                            parameter=violation["parameter"],
                            observed=violation["observed"],
                            lower=violation["lower"],
                            upper=violation["upper"],
                            units=violation["units"],
                            action="set_fit_valid_false",
                            affects_fit=True,
                            affects_overall=True,
                            message=f"Safety check failed: {violation['reason']}.",
                            created_at=generated_at,
                        )

            peaks.extend(attempt_peak_rows)

            fit_valid = (
                fit_status == "completed"
                and fit_converged
                and len(attempt_peak_rows) > 0
                and all(peak_valid_values)
            )
            fit_valid_reason = "" if fit_valid else "fit_safety_checks_failed"
            if fit_status == "not_run":
                fit_valid_reason = "no candidate peaks detected"
            elif fit_status == "nonconverged":
                fit_valid_reason = "optimizer did not converge"
            elif fit_status == "error":
                fit_valid_reason = "fitting error"

            attempt_events = [event for event in events if event["fit_attempt_id"] == attempt_id]
            review_events = [
                event for event in attempt_events if event["severity"] in {"WARN", "REVIEW"}
            ]
            needs_manual_review = bool(review_events)
            overall_qc = input_qc_pass and baseline_qc_pass and fit_valid
            overall_reasons = []
            if not input_qc_pass:
                overall_reasons.append("input_qc_failed")
            if not baseline_qc_pass:
                overall_reasons.append("baseline_qc_failed")
            if not fit_valid:
                overall_reasons.append("fit_invalid")

            attempts.append(
                {
                    "fit_attempt_id": attempt_id,
                    "processing_run_id": processing_run_id,
                    "sample_id": meta["sample_id"],
                    "raw_file": meta["raw_file"],
                    "run_timestamp_utc": generated_at,
                    "software_version": WRAPPER_VERSION,
                    "processing_mode": "automated",
                    "fit_attempt_status": attempt_status_from_fit_status(fit_status),
                    "fit_model": model,
                    "solver": "scipy.optimize.curve_fit",
                    "bound_profile_id": args.bound_profile_id,
                    "wavenumber_min_cm1": clean_number(min(fit_x)),
                    "wavenumber_max_cm1": clean_number(max(fit_x)),
                    "threshold": threshold_value,
                    "adjustment_factor": "",
                    "atmospheric_correction_method": meta.get("atmospheric_correction_method", ""),
                    "baseline_method": meta["baseline_method"],
                    "baseline_config_json": meta["baseline_config_json"],
                    "detected_peak_count": len(peak_indices),
                    "fitted_peak_count": len(attempt_peak_rows),
                    "fit_converged": bool_text(fit_converged),
                    "solver_status": fit_status.upper(),
                    "solver_message": fit_metrics.get("message", ""),
                    "nfev": "",
                    "rmse": clean_number(fit_metrics.get("rmse")),
                    "residual_mean": clean_number(fit_metrics.get("residual_mean")),
                    "residual_max_abs": clean_number(fit_metrics.get("residual_max_abs")),
                    "input_qc_pass": bool_text(input_qc_pass),
                    "input_qc_reason": input_reason if not input_qc_pass else "",
                    "baseline_qc_pass": bool_text(baseline_qc_pass),
                    "baseline_qc_reason": baseline_reason if not baseline_qc_pass else "",
                    "baseline_over_fraction": meta.get("baseline_over_fraction", ""),
                    "baseline_max_overshoot": meta.get("baseline_max_overshoot", ""),
                    "baseline_oversubtraction_area": meta.get("baseline_oversubtraction_area", ""),
                    "zero_clipping_fraction": meta.get("zero_clipping_fraction", ""),
                    "fit_valid": bool_text(fit_valid),
                    "fit_valid_reason": fit_valid_reason,
                    "needs_manual_review": bool_text(needs_manual_review),
                    "manual_review_reason": "; ".join(
                        str(event["message"]) for event in review_events
                    ),
                    "overall_qc": bool_text(overall_qc),
                    "overall_qc_reason": "; ".join(overall_reasons),
                    "triggered_rule_count": len(attempt_events),
                    "notes": (
                        f"candidate_peak_source={candidate_source}; "
                        f"metadata_notes={meta.get('notes', '')}"
                    ),
                }
            )

    write_csv(output_dir / "fit_attempts.csv", ATTEMPT_HEADER, attempts)
    write_csv(output_dir / "fitted_peaks.csv", PEAK_HEADER, peaks)
    write_csv(output_dir / "rule_events.csv", EVENT_HEADER, events)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_unique(rows: list[dict[str, str]], field: str) -> None:
    values = [row[field] for row in rows]
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    require(not duplicates, f"{field} contains duplicate IDs: {duplicates[:5]}")
    require(all(values), f"{field} contains empty IDs")


def validate_three_tables(output_dir: Path) -> None:
    attempts = read_csv(output_dir / "fit_attempts.csv")
    peaks = read_csv(output_dir / "fitted_peaks.csv")
    events = read_csv(output_dir / "rule_events.csv")
    require(attempts, "fit_attempts.csv has no rows")
    require(list(attempts[0]) == ATTEMPT_HEADER, "fit_attempts.csv header mismatch")
    if peaks:
        require(list(peaks[0]) == PEAK_HEADER, "fitted_peaks.csv header mismatch")
    if events:
        require(list(events[0]) == EVENT_HEADER, "rule_events.csv header mismatch")

    assert_unique(attempts, "fit_attempt_id")
    if peaks:
        assert_unique(peaks, "peak_result_id")
    if events:
        assert_unique(events, "rule_event_id")

    attempt_ids = {row["fit_attempt_id"] for row in attempts}
    peak_ids = {row["peak_result_id"] for row in peaks}
    require(
        all(row["fit_attempt_id"] in attempt_ids for row in peaks),
        "fitted_peaks contains fit_attempt_id values missing from fit_attempts",
    )
    require(
        all(row["fit_attempt_id"] in attempt_ids for row in events),
        "rule_events contains fit_attempt_id values missing from fit_attempts",
    )
    require(
        all(row["peak_result_id"] == "" or row["peak_result_id"] in peak_ids for row in events),
        "rule_events contains peak_result_id values missing from fitted_peaks",
    )

    models_by_run: dict[str, set[str]] = defaultdict(set)
    for row in attempts:
        models_by_run[row["processing_run_id"]].add(row["fit_model"])
    missing_model_runs = {
        run_id: sorted(set(MODELS) - models)
        for run_id, models in models_by_run.items()
        if models != set(MODELS)
    }
    require(
        not missing_model_runs,
        f"Each processing_run_id must have Gaussian and Lorentzian attempts: {missing_model_runs}",
    )

    event_counts = Counter(row["fit_attempt_id"] for row in events)
    for row in attempts:
        require(
            int(row["triggered_rule_count"]) == event_counts[row["fit_attempt_id"]],
            f"triggered_rule_count mismatch for {row['fit_attempt_id']}",
        )

    for event in events:
        if event["rule_namespace"] == "baseline_qc":
            require(
                event["affects_fit_valid"] == "FALSE",
                "baseline_qc events must not directly affect fit_valid",
            )
            require(
                event["affects_overall_qc"] == "TRUE",
                "baseline_qc events must affect overall_qc",
            )
    print(f"validated {len(attempts)} attempts, {len(peaks)} peaks, {len(events)} rule events")


def bool_value(value: str) -> bool:
    return str(value).strip().upper() == "TRUE"


def numeric_values(rows: list[dict[str, str]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(field, "")
        if value == "":
            continue
        try:
            numeric = float(value)
        except ValueError:
            continue
        if math.isfinite(numeric):
            values.append(numeric)
    return values


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.8g}"


def summarize(directory: Path) -> dict[str, float | int | None]:
    attempts = read_csv(directory / "fit_attempts.csv")
    peaks = read_csv(directory / "fitted_peaks.csv")
    events = read_csv(directory / "rule_events.csv")
    rmse = numeric_values(attempts, "rmse")
    residual_max_abs = numeric_values(attempts, "residual_max_abs")
    return {
        "completed_attempts": sum(row.get("fit_attempt_status") == "completed" for row in attempts),
        "converged_attempts": sum(bool_value(row.get("fit_converged", "")) for row in attempts),
        "fit_valid_attempts": sum(bool_value(row.get("fit_valid", "")) for row in attempts),
        "fitted_peaks": len(peaks),
        "valid_peaks": sum(bool_value(row.get("peak_valid", "")) for row in peaks),
        "overall_qc_pass_attempts": sum(bool_value(row.get("overall_qc", "")) for row in attempts),
        "manual_review_events": sum(row.get("severity") in {"WARN", "REVIEW"} for row in events),
        "failed_fit_events": sum(
            row.get("severity") == "FAIL" and bool_value(row.get("affects_fit_valid", ""))
            for row in events
        ),
        "mean_rmse": mean(rmse),
        "median_rmse": median(rmse),
        "mean_residual_max_abs": mean(residual_max_abs),
    }


def write_comparison(
    output: Path,
    dir_a: Path,
    dir_b: Path,
    *,
    label_a: str,
    label_b: str,
) -> None:
    summary_a = summarize(dir_a)
    summary_b = summarize(dir_b)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["metric", label_a, label_b, "delta_b_minus_a", "meaning"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for metric, meaning in METRIC_MEANINGS.items():
            value_a = summary_a[metric]
            value_b = summary_b[metric]
            delta = None if value_a is None or value_b is None else float(value_b) - float(value_a)
            writer.writerow(
                {
                    "metric": metric,
                    label_a: fmt(value_a),
                    label_b: fmt(value_b),
                    "delta_b_minus_a": fmt(delta),
                    "meaning": meaning,
                }
            )


def read_xy(
    path: Path, x_col: str = "wavenumber_cm1", y_col: str = "absorbance_corrected"
) -> tuple[np.ndarray, np.ndarray]:
    rows = read_csv(path)
    x = np.asarray([float(row[x_col]) for row in rows], dtype=float)
    y = np.asarray([float(row[y_col]) for row in rows], dtype=float)
    order = np.argsort(x)
    return x[order], y[order]


def gaussian_component(x: np.ndarray, amplitude: float, centre: float, sigma: float) -> np.ndarray:
    return (
        amplitude
        * (1.0 / (sigma * np.sqrt(2.0 * np.pi)))
        * np.exp(-0.5 * ((x - centre) / sigma) ** 2)
    )


def gaussian_fit_from_peak_rows(x: np.ndarray, peak_rows: list[dict[str, str]]) -> np.ndarray:
    y = np.zeros_like(x, dtype=float)
    for row in peak_rows:
        try:
            amplitude = float(row["raw_model_amplitude"])
            centre = float(row["fitted_centre_cm1"])
            sigma = float(row["raw_width_parameter"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(amplitude) and math.isfinite(centre) and math.isfinite(sigma):
            y += gaussian_component(x, amplitude, centre, sigma)
    return y


def choose_attempts(fit_dir: Path) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    gaussian_attempts = [
        row
        for row in read_csv(fit_dir / "fit_attempts.csv")
        if row["fit_model"] == "Gaussian" and row["fit_attempt_status"] == "completed"
    ]
    numeric = []
    for row in gaussian_attempts:
        try:
            rmse = float(row["rmse"])
            residual = float(row["residual_max_abs"])
        except ValueError:
            continue
        if math.isfinite(rmse) and math.isfinite(residual):
            numeric.append((rmse, residual, row))
    if not numeric:
        return None, None
    good = sorted(numeric, key=lambda item: (item[0], item[1]))[0][2]
    review = sorted(numeric, key=lambda item: item[1], reverse=True)[0][2]
    return good, review


def style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color="#e6e6e6", linewidth=0.7)


def make_plots(
    erni_metadata: Path,
    erni_fit_dir: Path,
    plot_dir: Path,
    *,
    control_metadata: Path | None = None,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for plots. Install it or rerun with --skip-plots."
        ) from exc

    prepare_dir(plot_dir, True)
    erni_rows = read_csv(erni_metadata)
    erni_by_run = {row["processing_run_id"]: row for row in erni_rows}
    erni_meta_dir = erni_metadata.resolve().parent
    peaks = read_csv(erni_fit_dir / "fitted_peaks.csv")
    peaks_by_attempt: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in peaks:
        peaks_by_attempt[row["fit_attempt_id"]].append(row)
    for rows in peaks_by_attempt.values():
        rows.sort(key=lambda row: int(row["peak_index"]))

    manifest: list[str] = []

    good, review = choose_attempts(erni_fit_dir)
    for label, attempt in (("best_fit", good), ("review_residual", review)):
        if attempt is None:
            continue
        meta = erni_by_run[attempt["processing_run_id"]]
        spectrum = resolve_relative(meta["corrected_spectrum_file"], erni_meta_dir)
        x, y = read_xy(spectrum)
        fit_y = gaussian_fit_from_peak_rows(x, peaks_by_attempt[attempt["fit_attempt_id"]])
        residual = y - fit_y
        fig, axes = plt.subplots(
            2,
            1,
            figsize=(9.5, 6.5),
            sharex=True,
            gridspec_kw={"height_ratios": [3, 1]},
        )
        axes[0].plot(x, y, color="#222222", linewidth=1.4, label="arPLS corrected spectrum")
        axes[0].plot(x, fit_y, color="#D55E00", linewidth=1.3, label="Gaussian total fit")
        centres = [
            float(row["fitted_centre_cm1"])
            for row in peaks_by_attempt[attempt["fit_attempt_id"]]
            if row["fitted_centre_cm1"]
        ]
        heights = [
            float(row["peak_height"])
            for row in peaks_by_attempt[attempt["fit_attempt_id"]]
            if row["peak_height"]
        ]
        axes[0].scatter(
            centres, heights, s=26, color="#0072B2", zorder=3, label="fitted peak centres"
        )
        for centre in centres:
            axes[0].axvline(centre, color="#0072B2", alpha=0.18, linewidth=0.8)
        axes[0].set_ylabel("Corrected absorbance")
        axes[0].set_title(
            f"Sample {attempt['sample_id']}: arPLS Gaussian {label.replace('_', ' ')}"
        )
        axes[0].legend(loc="best", fontsize=8)
        style_axes(axes[0])

        axes[1].axhline(0, color="#666666", linewidth=0.8)
        axes[1].plot(x, residual, color="#009E73", linewidth=1.1, label="residual")
        axes[1].fill_between(x, residual, 0, color="#009E73", alpha=0.18)
        axes[1].set_xlabel("Wavenumber (cm$^{-1}$)")
        axes[1].set_ylabel("Residual")
        axes[1].text(
            0.01,
            0.88,
            (
                f"RMSE={float(attempt['rmse']):.4g}; "
                f"max |residual|={float(attempt['residual_max_abs']):.4g}; "
                f"fit_valid={attempt['fit_valid']}"
            ),
            transform=axes[1].transAxes,
            fontsize=8,
            va="top",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#bbbbbb"},
        )
        style_axes(axes[1])
        axes[1].invert_xaxis()
        fig.tight_layout()
        path = plot_dir / f"sample_{attempt['sample_id']}_arpls_gaussian_{label}.png"
        fig.savefig(path, dpi=220)
        plt.close(fig)
        manifest.append(str(path))

    if control_metadata is not None and good is not None:
        control_rows = read_csv(control_metadata)
        control_match = next(
            (row for row in control_rows if row["sample_id"] == good["sample_id"]), None
        )
        erni_match = erni_by_run[good["processing_run_id"]]
        if control_match is not None:
            control_dir = control_metadata.resolve().parent
            control_path = resolve_relative(control_match["corrected_spectrum_file"], control_dir)
            erni_path = resolve_relative(erni_match["corrected_spectrum_file"], erni_meta_dir)
            cx, cy = read_xy(control_path)
            ex, ey = read_xy(erni_path)
            fig, ax = plt.subplots(1, 1, figsize=(9.5, 4.8))
            ax.plot(cx, cy, color="#0072B2", linewidth=1.4, label="control corrected spectrum")
            ax.plot(ex, ey, color="#D55E00", linewidth=1.4, label="Erni arPLS corrected spectrum")
            ax.set_title(f"Sample {good['sample_id']}: control vs Erni arPLS corrected spectra")
            ax.set_xlabel("Wavenumber (cm$^{-1}$)")
            ax.set_ylabel("Corrected absorbance")
            ax.legend(loc="best", fontsize=8)
            style_axes(ax)
            ax.invert_xaxis()
            fig.tight_layout()
            path = plot_dir / f"sample_{good['sample_id']}_control_vs_arpls_input.png"
            fig.savefig(path, dpi=220)
            plt.close(fig)
            manifest.insert(0, str(path))

    (plot_dir / "plot_manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    captions = [
        "The downstream wrapper can consume Erni arPLS-corrected spectra and export valid peak parameters.",
        "Residual plots are included to separate rule-level validity from residual-pattern review.",
    ]
    if control_metadata is not None:
        captions.insert(
            0,
            "Control and Erni arPLS corrected spectra are plotted for matched samples when available.",
        )
    (plot_dir / "figure_captions.txt").write_text("\n".join(captions) + "\n", encoding="utf-8")


def print_counts(label: str, output_dir: Path) -> None:
    attempts = read_csv(output_dir / "fit_attempts.csv")
    peaks = read_csv(output_dir / "fitted_peaks.csv")
    events = read_csv(output_dir / "rule_events.csv")
    print(f"{label}: {len(attempts)} attempts, {len(peaks)} peaks, {len(events)} rule events")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    native_output = args.output_dir / "erni_arpls_native_outputs"
    erni_input_dir = args.output_dir / "erni_inputs"
    erni_fit_dir = args.output_dir / "erni_fitting_outputs"
    control_fit_dir = args.output_dir / "control_fitting_outputs"
    comparison_output = args.output_dir / "control_vs_erni_arpls_comparison_summary.csv"
    plot_dir = args.output_dir / "report_plots"

    if args.run_native_arpls:
        print("Running Erni native arPLS workflow...")
        run_native_arpls(args, native_output)
        erni_metadata = prepare_erni_inputs(args, native_output, erni_input_dir)
    elif args.erni_metadata is not None:
        erni_metadata = args.erni_metadata
    else:
        if args.erni_output_root is None:
            raise SystemExit("Provide --erni-output-root, --erni-metadata, or --run-native-arpls.")
        erni_metadata = prepare_erni_inputs(args, args.erni_output_root, erni_input_dir)

    print("Running downstream fitting/QC on Erni arPLS spectra...")
    run_fitting(erni_metadata, erni_fit_dir, args)
    validate_three_tables(erni_fit_dir)
    print_counts("Erni arPLS", erni_fit_dir)

    if args.control_metadata is not None:
        print("Running downstream fitting/QC on control spectra...")
        run_fitting(args.control_metadata, control_fit_dir, args)
        validate_three_tables(control_fit_dir)
        print_counts("Control", control_fit_dir)
        write_comparison(
            comparison_output,
            control_fit_dir,
            erni_fit_dir,
            label_a="control",
            label_b="erni_arpls",
        )
        print(f"Comparison summary: {comparison_output}")

    if not args.skip_plots:
        print("Generating report plots...")
        make_plots(
            erni_metadata,
            erni_fit_dir,
            plot_dir,
            control_metadata=args.control_metadata,
        )
        print(f"Report plots: {plot_dir}")

    print("\nDone.")
    print(f"Erni metadata used: {erni_metadata}")
    print(f"Erni fitting outputs: {erni_fit_dir}")
    if args.control_metadata is not None:
        print(f"Control fitting outputs: {control_fit_dir}")


if __name__ == "__main__":
    main()
