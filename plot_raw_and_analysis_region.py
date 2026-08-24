from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from brukeropusreader import read_file


# =========================================================
# 1. Project paths
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent

RAW_FILE_NAME = "011h as iso Hyd2 dark titration -300mV.0006"

RAW_FILE = (
    PROJECT_ROOT
    / "data"
    / "opus_files"
    / "pH6"
    / RAW_FILE_NAME
)

OUTPUT_FOLDER = PROJECT_ROOT / "paper_figures"
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

OUTPUT_PNG = OUTPUT_FOLDER / "figure_3_1_raw_and_analysis_region.png"
OUTPUT_PDF = OUTPUT_FOLDER / "figure_3_1_raw_and_analysis_region.pdf"


# =========================================================
# 2. Plot settings
# =========================================================
MAIN_DISPLAY_REGION = (4000.0, 1500.0)
ANALYSIS_REGION = (2150.0, 1850.0)

FIGURE_SIZE = (8.2, 7.2)
MAIN_LINE_WIDTH = 1.0
DETAIL_LINE_WIDTH = 1.35
OUTPUT_DPI = 600


# =========================================================
# 3. Load raw OPUS spectrum
# =========================================================
if not RAW_FILE.exists():
    raise FileNotFoundError(
        f"Raw OPUS file was not found:\n{RAW_FILE}\n\n"
        "Check the file name and raw-data folder."
    )

opus_data = read_file(RAW_FILE)

if "AB" not in opus_data:
    raise KeyError(
        "The OPUS file does not contain an 'AB' absorbance data block.\n"
        f"Available keys: {list(opus_data.keys())}"
    )

wavenumber = np.asarray(
    opus_data.get_range("AB"),
    dtype=float,
)

absorbance = np.asarray(
    opus_data["AB"][: len(wavenumber)],
    dtype=float,
)

valid_mask = np.isfinite(wavenumber) & np.isfinite(absorbance)

wavenumber = wavenumber[valid_mask]
absorbance = absorbance[valid_mask]

if wavenumber.size == 0:
    raise ValueError("No valid absorbance data were found in the OPUS file.")

sort_order = np.argsort(wavenumber)[::-1]
wavenumber = wavenumber[sort_order]
absorbance = absorbance[sort_order]


# =========================================================
# 4. Select displayed regions
# =========================================================
main_high = max(MAIN_DISPLAY_REGION)
main_low = min(MAIN_DISPLAY_REGION)

main_mask = (
    (wavenumber <= main_high)
    & (wavenumber >= main_low)
)

main_x = wavenumber[main_mask]
main_y = absorbance[main_mask]

if main_x.size == 0:
    raise ValueError("No data were found within the main display region.")


analysis_high = max(ANALYSIS_REGION)
analysis_low = min(ANALYSIS_REGION)

analysis_mask = (
    (wavenumber <= analysis_high)
    & (wavenumber >= analysis_low)
)

analysis_x = wavenumber[analysis_mask]
analysis_y = absorbance[analysis_mask]

if analysis_x.size == 0:
    raise ValueError("No data were found within the analysis region.")


# =========================================================
# 5. Create two-panel figure
# =========================================================
fig, axes = plt.subplots(
    nrows=2,
    ncols=1,
    figsize=FIGURE_SIZE,
    gridspec_kw={
        "height_ratios": [1.0, 1.05],
        "hspace": 0.22,
    },
    constrained_layout=True,
)

ax_raw, ax_detail = axes


# =========================================================
# 6. Panel (a): raw FTIR spectrum
# =========================================================
ax_raw.plot(
    main_x,
    main_y,
    linewidth=MAIN_LINE_WIDTH,
)

# FTIR convention: higher wavenumbers are shown on the left.
ax_raw.set_xlim(
    main_high,
    main_low,
)

ax_raw.set_ylabel(
    "Absorbance",
    fontsize=11,
)

ax_raw.tick_params(
    axis="both",
    labelsize=10,
)

ax_raw.spines["top"].set_visible(False)
ax_raw.spines["right"].set_visible(False)

ax_raw.text(
    0.015,
    0.96,
    "(a) Raw FTIR spectrum",
    transform=ax_raw.transAxes,
    ha="left",
    va="top",
    fontsize=10.5,
)


# =========================================================
# 7. Highlight the region analysed in this study
# =========================================================
analysis_y_min_main = float(analysis_y.min())
analysis_y_max_main = float(analysis_y.max())
analysis_y_range_main = (
    analysis_y_max_main - analysis_y_min_main
)

if analysis_y_range_main == 0:
    analysis_y_range_main = 1.0

box_bottom = (
    analysis_y_min_main
    - 0.10 * analysis_y_range_main
)

box_top = (
    analysis_y_max_main
    + 0.10 * analysis_y_range_main
)

ax_raw.plot(
    [analysis_high, analysis_low],
    [box_bottom, box_bottom],
    linestyle="--",
    linewidth=0.9,
)

ax_raw.plot(
    [analysis_high, analysis_low],
    [box_top, box_top],
    linestyle="--",
    linewidth=0.9,
)

ax_raw.plot(
    [analysis_high, analysis_high],
    [box_bottom, box_top],
    linestyle="--",
    linewidth=0.9,
)

ax_raw.plot(
    [analysis_low, analysis_low],
    [box_bottom, box_top],
    linestyle="--",
    linewidth=0.9,
)

ax_raw.text(
    (analysis_high + analysis_low) / 2,
    box_top + 0.08 * analysis_y_range_main,
    "Region analysed in this study",
    ha="center",
    va="bottom",
    fontsize=9,
)


# =========================================================
# 8. Panel (b): enlarged hydrogenase analysis region
# =========================================================
ax_detail.plot(
    analysis_x,
    analysis_y,
    linewidth=DETAIL_LINE_WIDTH,
)

ax_detail.set_xlim(
    analysis_high,
    analysis_low,
)

detail_y_min = float(analysis_y.min())
detail_y_max = float(analysis_y.max())
detail_y_range = detail_y_max - detail_y_min

if detail_y_range == 0:
    detail_y_range = 1.0

# Extra space is added above the spectrum for annotations.
ax_detail.set_ylim(
    detail_y_min - 0.04 * detail_y_range,
    detail_y_max + 0.18 * detail_y_range,
)

ax_detail.set_xlabel(
    r"Wavenumber (cm$^{-1}$)",
    fontsize=11,
)

ax_detail.set_ylabel(
    "Absorbance",
    fontsize=11,
)

ax_detail.tick_params(
    axis="both",
    labelsize=10,
)

ax_detail.spines["top"].set_visible(False)
ax_detail.spines["right"].set_visible(False)

ax_detail.text(
    0.0,
    1.03,
    "(b) Hydrogenase FTIR analysis region",
    transform=ax_detail.transAxes,
    ha="left",
    va="bottom",
    fontsize=10.5,
    clip_on=False,
)


# =========================================================
# 9. Add CN and CO annotations
# =========================================================
cn_label_y = detail_y_max + 0.12 * detail_y_range
co_label_y = detail_y_max + 0.06 * detail_y_range

ax_detail.text(
    2075,
    cn_label_y,
    "CN stretching",
    ha="center",
    va="top",
    fontsize=9.5,
)

ax_detail.text(
    1940,
    co_label_y,
    "CO stretching",
    ha="center",
    va="top",
    fontsize=9.5,
)


# =========================================================
# 10. Save the figure
# =========================================================
fig.savefig(
    OUTPUT_PNG,
    dpi=OUTPUT_DPI,
    bbox_inches="tight",
)

fig.savefig(
    OUTPUT_PDF,
    bbox_inches="tight",
)

plt.show()

print(f"Saved PNG: {OUTPUT_PNG}")
print(f"Saved PDF: {OUTPUT_PDF}")