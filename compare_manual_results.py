#!/usr/bin/env python3
"""
Compare Original ProSpecPy anchor-point + spline Gaussian peak-fitting results against manually processed peak data.

Expected project layout
-----------------------
ProSpecPy/
├── compare_manual_results.py
├── manual_data/
│   └── Hyd2_pH6_manually processed data.xlsx
└── peak_fitting_results/
    └── erni_fitting_outputs/
        └── fitted_peaks.csv

Outputs
-------
manual_comparison_results/
├── all_manual_peaks_with_match_status.csv
├── matched_peaks_all.csv
├── matched_peaks_exact.csv
├── matched_peaks_within_25mV.csv
├── matched_peaks_within_50mV.csv
├── summary_statistics.csv
├── summary_exact.csv
├── summary_within_25mV.csv
├── summary_within_50mV.csv
├── sample_summary.csv
├── centre_comparison_exact.png
├── centre_comparison_within_25mV.png
├── centre_comparison_within_50mV.png
├── height_comparison_exact.png
├── height_comparison_within_25mV.png
└── height_comparison_within_50mV.png

Primary interpretation
----------------------
- Peak-centre accuracy may be summarized using matches within 50 mV.
- Peak-height accuracy should be interpreted primarily from exact-potential matches.
- Mean row-wise relative height error can be unstable for small manual heights.
  Therefore this script also reports a normalized aggregate height error:
      sum(abs(original_height - manual_height)) / sum(abs(manual_height))
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SAMPLE_POTENTIALS_MV = {
    "011a": 0,
    "011b": -50,
    "011c": -100,
    "011d": -1050,
    "011e": -200,
    "011f": -250,
    "011g": -275,
    "011h": -300,
    "011i": -325,
    "011k": -375,
    "011l": -400,
    "011m": -425,
    "011n": -450,
    "011o": -475,
    "011p": -500,
    "011q": -550,
    "011r": -600,
    "011s": -700,
    "011t": -800,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manual-xlsx",
        type=Path,
        default=Path("manual_data/Hyd2_pH6_manually processed data.xlsx"),
    )
    parser.add_argument(
        "--fitted-peaks",
        type=Path,
        default=Path("peak_fitting_results_original/erni_fitting_outputs/fitted_peaks.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("manual_comparison_results_original"),
    )
    parser.add_argument(
        "--centre-tolerance",
        type=float,
        default=2.0,
        help="Maximum centre difference in cm-1 for a valid peak match.",
    )
    return parser.parse_args()


def read_manual_data(path: Path) -> tuple[np.ndarray, dict[float, np.ndarray]]:
    if not path.exists():
        raise FileNotFoundError(f"Manual Excel file not found: {path}")

    raw = pd.read_excel(path, sheet_name=0, header=None)

    # Workbook structure:
    # - row 1, columns I onward: reference peak centres
    # - column H: mV vs Ag/AgCl
    # - rows 2 onward, columns I onward: manual maximum peak heights
    reference_centres = pd.to_numeric(
        raw.iloc[0, 8:], errors="coerce"
    ).to_numpy(dtype=float)

    manual_by_potential: dict[float, np.ndarray] = {}

    for row_index in range(1, len(raw)):
        potential = pd.to_numeric(raw.iloc[row_index, 7], errors="coerce")
        if pd.isna(potential):
            continue

        heights = pd.to_numeric(
            raw.iloc[row_index, 8 : 8 + len(reference_centres)],
            errors="coerce",
        ).to_numpy(dtype=float)

        manual_by_potential[float(potential)] = heights

    if not manual_by_potential:
        raise ValueError("No manual potentials were found in column H.")

    return reference_centres, manual_by_potential


def read_gaussian_fits(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Fitted-peaks CSV not found: {path}")

    fitted = pd.read_csv(path)

    required_columns = {
        "fit_attempt_id",
        "fitted_centre_cm1",
        "peak_height",
    }
    missing = required_columns - set(fitted.columns)
    if missing:
        raise ValueError(
            f"fitted_peaks.csv is missing columns: {sorted(missing)}"
        )

    gaussian = fitted[
        fitted["fit_attempt_id"]
        .astype(str)
        .str.contains("gaussian", case=False, na=False)
    ].copy()

    gaussian["sample_id"] = (
        gaussian["fit_attempt_id"]
        .astype(str)
        .str.extract(r"(011[a-z])", expand=False)
    )

    gaussian["fitted_centre_cm1"] = pd.to_numeric(
        gaussian["fitted_centre_cm1"], errors="coerce"
    )
    gaussian["peak_height"] = pd.to_numeric(
        gaussian["peak_height"], errors="coerce"
    )

    gaussian = gaussian.dropna(
        subset=["sample_id", "fitted_centre_cm1", "peak_height"]
    )

    if gaussian.empty:
        raise ValueError("No valid Gaussian fit rows were found.")

    return gaussian


def nearest_manual_potential(
    sample_potential: float,
    available_potentials: np.ndarray,
) -> float:
    differences = np.abs(available_potentials - sample_potential)
    minimum_difference = float(np.min(differences))
    tied = available_potentials[
        np.isclose(differences, minimum_difference)
    ]

    # In an exact tie, choose the more negative potential.
    # Example: -475 is equally close to -425 and -525, so choose -525.
    return float(np.min(tied))


def build_comparison(
    reference_centres: np.ndarray,
    manual_by_potential: dict[float, np.ndarray],
    gaussian: pd.DataFrame,
    centre_tolerance: float,
) -> pd.DataFrame:
    available_potentials = np.asarray(
        sorted(manual_by_potential), dtype=float
    )

    rows: list[dict[str, object]] = []

    for sample_id, sample_potential in SAMPLE_POTENTIALS_MV.items():
        manual_potential = nearest_manual_potential(
            float(sample_potential),
            available_potentials,
        )
        potential_gap = abs(
            float(sample_potential) - manual_potential
        )

        sample_fits = gaussian[
            gaussian["sample_id"] == sample_id
        ].copy()
        sample_fits = sample_fits.sort_values(
            "fitted_centre_cm1"
        )

        manual_heights = manual_by_potential[manual_potential]

        for reference_centre, manual_height in zip(
            reference_centres,
            manual_heights,
            strict=False,
        ):
            if not math.isfinite(reference_centre):
                continue
            if not math.isfinite(manual_height):
                continue

            row: dict[str, object] = {
                "baseline_method": "Original ProSpecPy",
                "sample_id": sample_id,
                "sample_potential_mV_vs_AgAgCl": float(
                    sample_potential
                ),
                "manual_potential_mV_vs_AgAgCl": manual_potential,
                "potential_gap_mV": potential_gap,
                "manual_centre_cm1": float(reference_centre),
                "manual_height": float(manual_height),
                "original_centre_cm1": np.nan,
                "original_height": np.nan,
                "centre_abs_error_cm1": np.nan,
                "height_abs_error": np.nan,
                "height_relative_error_percent": np.nan,
                "peak_match": False,
                "match_reason": "no_fitted_peaks_for_sample",
                "nearest_fitted_centre_cm1": np.nan,
                "nearest_centre_distance_cm1": np.nan,
            }

            if not sample_fits.empty:
                distances = (
                    sample_fits["fitted_centre_cm1"]
                    - float(reference_centre)
                ).abs()

                nearest_index = distances.idxmin()
                nearest = sample_fits.loc[nearest_index]

                fitted_centre = float(
                    nearest["fitted_centre_cm1"]
                )
                fitted_height = float(nearest["peak_height"])
                centre_error = abs(
                    fitted_centre - float(reference_centre)
                )

                row["nearest_fitted_centre_cm1"] = fitted_centre
                row["nearest_centre_distance_cm1"] = centre_error

                if centre_error <= centre_tolerance:
                    height_error = abs(
                        fitted_height - float(manual_height)
                    )

                    if manual_height != 0:
                        relative_error = (
                            height_error
                            / abs(float(manual_height))
                            * 100.0
                        )
                    else:
                        relative_error = np.nan

                    row.update(
                        {
                            "original_centre_cm1": fitted_centre,
                            "original_height": fitted_height,
                            "centre_abs_error_cm1": centre_error,
                            "height_abs_error": height_error,
                            "height_relative_error_percent": relative_error,
                            "peak_match": True,
                            "match_reason": (
                                "nearest_peak_within_tolerance"
                            ),
                        }
                    )
                else:
                    row["match_reason"] = (
                        "nearest_peak_outside_centre_tolerance"
                    )

            rows.append(row)

    result = pd.DataFrame(rows)

    # A single fitted peak should not be matched to multiple manual peaks
    # within the same sample. Keep the closest manual match only.
    matched = result[result["peak_match"]].copy()

    if not matched.empty:
        matched["_fitted_key"] = (
            matched["sample_id"].astype(str)
            + "|"
            + matched["original_centre_cm1"]
            .round(6)
            .astype(str)
        )

        duplicate_mask = matched.duplicated(
            "_fitted_key", keep="first"
        )
        duplicate_indices = matched.index[duplicate_mask]

        result.loc[duplicate_indices, "peak_match"] = False
        result.loc[
            duplicate_indices, "match_reason"
        ] = "fitted_peak_already_used_by_closer_manual_peak"

        for column in [
            "original_centre_cm1",
            "original_height",
            "centre_abs_error_cm1",
            "height_abs_error",
            "height_relative_error_percent",
        ]:
            result.loc[duplicate_indices, column] = np.nan

    return result


def safe_mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def safe_median(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.median()) if not values.empty else np.nan


def safe_max(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.max()) if not values.empty else np.nan


def normalized_height_error(rows: pd.DataFrame) -> float:
    if rows.empty:
        return np.nan

    manual = pd.to_numeric(
        rows["manual_height"], errors="coerce"
    )
    errors = pd.to_numeric(
        rows["height_abs_error"], errors="coerce"
    )

    valid = manual.notna() & errors.notna()
    manual = manual[valid]
    errors = errors[valid]

    denominator = float(np.abs(manual).sum())

    if denominator == 0:
        return np.nan

    return float(errors.sum() / denominator)


def summarize_subset(
    rows: pd.DataFrame,
    group_label: str,
    potential_rule: str,
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(
            [
                {
                    "group": group_label,
                    "metric": "matched_peak_count",
                    "value": 0,
                    "notes": (
                        f"No valid matches for {potential_rule}."
                    ),
                }
            ]
        )

    summary_rows = [
        {
            "group": group_label,
            "metric": "matched_peak_count",
            "value": len(rows),
            "notes": potential_rule,
        },
        {
            "group": group_label,
            "metric": "unique_sample_count",
            "value": rows["sample_id"].nunique(),
            "notes": potential_rule,
        },
        {
            "group": group_label,
            "metric": "centre_MAE_cm1",
            "value": safe_mean(
                rows["centre_abs_error_cm1"]
            ),
            "notes": "Mean absolute peak-centre error.",
        },
        {
            "group": group_label,
            "metric": "centre_median_absolute_error_cm1",
            "value": safe_median(
                rows["centre_abs_error_cm1"]
            ),
            "notes": "Median absolute peak-centre error.",
        },
        {
            "group": group_label,
            "metric": "centre_max_absolute_error_cm1",
            "value": safe_max(
                rows["centre_abs_error_cm1"]
            ),
            "notes": "Largest peak-centre error.",
        },
        {
            "group": group_label,
            "metric": "height_MAE",
            "value": safe_mean(
                rows["height_abs_error"]
            ),
            "notes": "Mean absolute peak-height error.",
        },
        {
            "group": group_label,
            "metric": "height_median_absolute_error",
            "value": safe_median(
                rows["height_abs_error"]
            ),
            "notes": "Median absolute peak-height error.",
        },
        {
            "group": group_label,
            "metric": "height_mean_relative_error_percent",
            "value": safe_mean(
                rows["height_relative_error_percent"]
            ),
            "notes": (
                "Mean row-wise relative height error; "
                "can be inflated by very small manual heights."
            ),
        },
        {
            "group": group_label,
            "metric": "height_normalized_aggregate_error",
            "value": normalized_height_error(rows),
            "notes": (
                "sum(abs(Original-manual)) / "
                "sum(abs(manual)); more stable than "
                "averaging row-wise percentages."
            ),
        },
    ]

    return pd.DataFrame(summary_rows)


def make_grouped_outputs(
    comparison: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    matched = comparison[comparison["peak_match"]].copy()

    exact = matched[
        matched["potential_gap_mV"] == 0
    ].copy()

    within_25 = matched[
        matched["potential_gap_mV"] <= 25
    ].copy()

    within_50 = matched[
        matched["potential_gap_mV"] <= 50
    ].copy()

    return matched, exact, within_25, within_50


def make_summary_tables(
    exact: pd.DataFrame,
    within_25: pd.DataFrame,
    within_50: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_exact = summarize_subset(
        exact,
        group_label="exact_potential",
        potential_rule="potential_gap_mV == 0",
    )

    summary_within_25 = summarize_subset(
        within_25,
        group_label="within_25mV",
        potential_rule="potential_gap_mV <= 25",
    )

    summary_within_50 = summarize_subset(
        within_50,
        group_label="within_50mV",
        potential_rule="potential_gap_mV <= 50",
    )

    combined = pd.concat(
        [
            summary_exact,
            summary_within_25,
            summary_within_50,
        ],
        ignore_index=True,
    )

    return (
        combined,
        summary_exact,
        summary_within_25,
        summary_within_50,
    )


def make_sample_summary(
    matched: pd.DataFrame,
) -> pd.DataFrame:
    if matched.empty:
        return pd.DataFrame(
            columns=[
                "baseline_method",
                "sample_id",
                "sample_potential_mV_vs_AgAgCl",
                "manual_potential_mV_vs_AgAgCl",
                "potential_gap_mV",
                "matched_peak_count",
                "centre_MAE_cm1",
                "height_MAE",
                "height_mean_relative_error_percent",
                "height_normalized_aggregate_error",
            ]
        )

    rows: list[dict[str, object]] = []

    grouping_columns = [
        "sample_id",
        "sample_potential_mV_vs_AgAgCl",
        "manual_potential_mV_vs_AgAgCl",
        "potential_gap_mV",
    ]

    for keys, group in matched.groupby(
        grouping_columns,
        dropna=False,
    ):
        (
            sample_id,
            sample_potential,
            manual_potential,
            potential_gap,
        ) = keys

        rows.append(
            {
                "baseline_method": "Original ProSpecPy",
                "sample_id": sample_id,
                "sample_potential_mV_vs_AgAgCl": sample_potential,
                "manual_potential_mV_vs_AgAgCl": manual_potential,
                "potential_gap_mV": potential_gap,
                "matched_peak_count": len(group),
                "centre_MAE_cm1": safe_mean(
                    group["centre_abs_error_cm1"]
                ),
                "height_MAE": safe_mean(
                    group["height_abs_error"]
                ),
                "height_mean_relative_error_percent": safe_mean(
                    group["height_relative_error_percent"]
                ),
                "height_normalized_aggregate_error": (
                    normalized_height_error(group)
                ),
            }
        )

    return pd.DataFrame(rows)


def add_identity_line(
    ax: plt.Axes,
    x: pd.Series,
    y: pd.Series,
) -> None:
    low = float(min(x.min(), y.min()))
    high = float(max(x.max(), y.max()))

    ax.plot(
        [low, high],
        [low, high],
        linestyle="--",
        label="y = x",
    )


def create_comparison_plots(
    rows: pd.DataFrame,
    output_dir: Path,
    suffix: str,
    title_suffix: str,
) -> None:
    if rows.empty:
        return

    centre_rows = rows.dropna(
        subset=[
            "manual_centre_cm1",
            "original_centre_cm1",
        ]
    )

    if not centre_rows.empty:
        fig, ax = plt.subplots(figsize=(7, 6))

        ax.scatter(
            centre_rows["manual_centre_cm1"],
            centre_rows["original_centre_cm1"],
        )

        add_identity_line(
            ax,
            centre_rows["manual_centre_cm1"],
            centre_rows["original_centre_cm1"],
        )

        ax.set_xlabel("Manual peak centre (cm$^{-1}$)")
        ax.set_ylabel("Original anchor+spline fitted peak centre (cm$^{-1}$)")
        ax.set_title(
            f"Manual vs Original anchor+spline peak centres — {title_suffix}"
        )
        ax.legend()

        fig.tight_layout()
        fig.savefig(
            output_dir / f"centre_comparison_{suffix}.png",
            dpi=300,
        )
        plt.close(fig)

    height_rows = rows.dropna(
        subset=["manual_height", "original_height"]
    )

    if not height_rows.empty:
        fig, ax = plt.subplots(figsize=(7, 6))

        ax.scatter(
            height_rows["manual_height"],
            height_rows["original_height"],
        )

        add_identity_line(
            ax,
            height_rows["manual_height"],
            height_rows["original_height"],
        )

        ax.set_xlabel("Manual peak height")
        ax.set_ylabel("Original anchor+spline fitted peak height")
        ax.set_title(
            f"Manual vs Original anchor+spline peak heights — {title_suffix}"
        )
        ax.legend()

        fig.tight_layout()
        fig.savefig(
            output_dir / f"height_comparison_{suffix}.png",
            dpi=300,
        )
        plt.close(fig)


def print_summary(
    summary: pd.DataFrame,
    heading: str,
) -> None:
    print()
    print(heading)
    print("-" * len(heading))

    for _, row in summary.iterrows():
        metric = row["metric"]
        value = row["value"]

        if pd.isna(value):
            formatted = "NaN"
        elif isinstance(value, (float, np.floating)):
            formatted = f"{float(value):.6g}"
        else:
            formatted = str(value)

        print(f"{metric}: {formatted}")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    reference_centres, manual_by_potential = (
        read_manual_data(args.manual_xlsx)
    )

    gaussian = read_gaussian_fits(args.fitted_peaks)

    comparison = build_comparison(
        reference_centres=reference_centres,
        manual_by_potential=manual_by_potential,
        gaussian=gaussian,
        centre_tolerance=args.centre_tolerance,
    )

    matched_all, exact, within_25, within_50 = (
        make_grouped_outputs(comparison)
    )

    (
        summary_all,
        summary_exact,
        summary_within_25,
        summary_within_50,
    ) = make_summary_tables(
        exact=exact,
        within_25=within_25,
        within_50=within_50,
    )

    sample_summary = make_sample_summary(matched_all)

    comparison.to_csv(
        args.output_dir
        / "all_manual_peaks_with_match_status.csv",
        index=False,
    )

    matched_all.to_csv(
        args.output_dir / "matched_peaks_all.csv",
        index=False,
    )

    exact.to_csv(
        args.output_dir / "matched_peaks_exact.csv",
        index=False,
    )

    within_25.to_csv(
        args.output_dir / "matched_peaks_within_25mV.csv",
        index=False,
    )

    within_50.to_csv(
        args.output_dir / "matched_peaks_within_50mV.csv",
        index=False,
    )

    summary_all.to_csv(
        args.output_dir / "summary_statistics.csv",
        index=False,
    )

    summary_exact.to_csv(
        args.output_dir / "summary_exact.csv",
        index=False,
    )

    summary_within_25.to_csv(
        args.output_dir / "summary_within_25mV.csv",
        index=False,
    )

    summary_within_50.to_csv(
        args.output_dir / "summary_within_50mV.csv",
        index=False,
    )

    sample_summary.to_csv(
        args.output_dir / "sample_summary.csv",
        index=False,
    )

    create_comparison_plots(
        exact,
        args.output_dir,
        suffix="exact",
        title_suffix="exact potentials",
    )

    create_comparison_plots(
        within_25,
        args.output_dir,
        suffix="within_25mV",
        title_suffix="potential gap ≤ 25 mV",
    )

    create_comparison_plots(
        within_50,
        args.output_dir,
        suffix="within_50mV",
        title_suffix="potential gap ≤ 50 mV",
    )

    print("=" * 72)
    print("Original anchor+spline manual comparison completed")
    print("=" * 72)
    print(f"Manual workbook: {args.manual_xlsx}")
    print(f"Fitted peaks:    {args.fitted_peaks}")
    print(f"Centre tolerance: ±{args.centre_tolerance:g} cm-1")
    print(f"All manual peak rows assessed: {len(comparison)}")
    print(f"All valid centre-matched peaks: {len(matched_all)}")

    print_summary(
        summary_exact,
        "Exact potential matches",
    )
    print_summary(
        summary_within_25,
        "Matches within 25 mV",
    )
    print_summary(
        summary_within_50,
        "Matches within 50 mV",
    )

    print()
    print(f"Outputs written to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()