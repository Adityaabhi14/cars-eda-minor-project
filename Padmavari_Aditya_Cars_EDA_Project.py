"""Cars EDA minor project: load, audit, clean, analyse, plot, and write a PDF.

Run: python Padmavari_Aditya_Cars_EDA_Project.py
Check cleaning behaviour: python Padmavari_Aditya_Cars_EDA_Project.py --self-test
Source: UCI Automobile, https://doi.org/10.24432/C5B01C (CC BY 4.0).
All analysis and report generation live in this one submission code file.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import unittest
import urllib.error
import urllib.request
from xml.sax.saxutils import escape
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

# An explicit backend makes chart generation work without a desktop display.
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / "tmp" / "matplotlib"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from pypdf import PdfReader
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


# 1. Source, schema, and research questions
ROOT = Path(__file__).resolve().parent
SOURCE_PAGE = "https://archive.ics.uci.edu/dataset/10/automobile"
SOURCE_DOI = "https://doi.org/10.24432/C5B01C"
SOURCE_ZIP = "https://archive.ics.uci.edu/static/public/10/automobile.zip"
SOURCE_SHA256 = "125db8bd36a84801f7223faf54071d15f85f26c13a9a7aee63375ac46098fb7f"
COLUMNS = [
    "symboling", "normalized-losses", "make", "fuel-type", "aspiration",
    "num-of-doors", "body-style", "drive-wheels", "engine-location", "wheel-base",
    "length", "width", "height", "curb-weight", "engine-type", "num-of-cylinders",
    "engine-size", "fuel-system", "bore", "stroke", "compression-ratio",
    "horsepower", "peak-rpm", "city-mpg", "highway-mpg", "price",
]
CATEGORICAL = [
    "make", "fuel-type", "aspiration", "body-style", "drive-wheels",
    "engine-location", "engine-type", "fuel-system",
]
NUMERICAL = [column for column in COLUMNS if column not in CATEGORICAL]
COUNT_COLUMNS = ["symboling", "num-of-doors", "num-of-cylinders"]
NUMBER_WORDS = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
                "eight": "8", "twelve": "12"}
LABEL_CORRECTIONS = {"alfa-romero": "alfa-romeo", "peugot": "peugeot"}
MISSING_TOKENS = {"?", "", "na", "n/a", "null", "none", "nan"}
DESCRIPTIONS = [
    "Insurance risk rating; ordinal, not a measured quantity",
    "Normalized relative insurance loss payment",
    "Vehicle manufacturer", "Gas or diesel", "Standard or turbo aspiration",
    "Door count; word labels converted to counts", "Vehicle body category",
    "Drive arrangement: fwd, rwd, or 4wd", "Front or rear engine",
    "Wheel base (source units)", "Length (source units)", "Width (source units)",
    "Height (source units)", "Curb weight (source units)", "Engine construction",
    "Cylinder count; word labels converted to counts", "Engine size (source units)",
    "Fuel delivery system", "Bore (source units)", "Stroke (source units)",
    "Compression ratio", "Reported horsepower", "Engine speed in RPM",
    "City fuel economy in MPG", "Highway fuel economy in MPG", "Listed price (source units)",
]
QUESTIONS = [
    "How are prices distributed, and where are the unusual values?",
    "Which manufacturers, fuel types, and body styles are represented?",
    "How do engine size, horsepower, weight, and fuel economy relate to price?",
    "How do prices differ between body styles and sufficiently represented makes?",
]
NAVY, TEAL, ORANGE, GRAY = "#17324D", "#087F8C", "#DC7F37", "#536273"


def native(value):
    """Convert pandas/numpy values into strict JSON without NaN or Infinity."""
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [native(v) for v in value]
    if value is pd.NA or value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


# 2. Data loading and explicit data-quality checks
def download_dataset(destination: Path) -> None:
    """Fetch the documented source when the standalone submission has no data."""
    request = urllib.request.Request(SOURCE_ZIP, headers={"User-Agent": "Cars-EDA-Student-Project/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        archive_bytes = response.read()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        matches = [name for name in archive.namelist() if name.endswith("/imports-85.data")]
        if len(matches) != 1:
            raise ValueError("The UCI archive does not contain the expected data file.")
        contents = archive.read(matches[0])
    if hashlib.sha256(contents).hexdigest() != SOURCE_SHA256:
        raise ValueError("Source checksum changed. Review the upstream dataset before using it.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(contents)
    temporary.replace(destination)


def load_data(path: Path) -> pd.DataFrame:
    # Read strings first so '?' values and type corrections remain auditable.
    frame = pd.read_csv(path, header=None, dtype="string", keep_default_na=False)
    if frame.shape[1] != len(COLUMNS) or frame.empty:
        raise ValueError(f"Expected a nonempty, headerless UCI file with 26 columns; got {frame.shape}.")
    frame.columns = COLUMNS
    return frame


def clean_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if list(raw.columns) != COLUMNS or raw.empty:
        raise ValueError("Input must contain the 26 UCI columns in source order and at least one row.")
    clean = raw.copy(deep=True)
    missing_before, normalization_changes, conversion_errors, domain_errors = {}, {}, {}, {}
    for column in COLUMNS:
        original = raw[column].astype("string")
        normalized = original.str.strip().str.lower()
        missing = normalized.isna() | normalized.isin(MISSING_TOKENS)
        missing_before[column] = int(missing.sum())
        normalization_changes[column] = int(((original != normalized) & ~missing).fillna(False).sum())
        clean[column] = normalized.mask(missing)

    corrections = {label: int((clean["make"] == label).sum()) for label in LABEL_CORRECTIONS}
    clean["make"] = clean["make"].replace(LABEL_CORRECTIONS)
    for column in ["num-of-doors", "num-of-cylinders"]:
        clean[column] = clean[column].replace(NUMBER_WORDS)
    for column in NUMERICAL:
        values = pd.to_numeric(clean[column], errors="coerce").astype("float64")
        conversion_errors[column] = int((clean[column].notna() & values.isna()).sum())
        invalid = values.notna() & ~np.isfinite(values)
        if column == "symboling":
            invalid |= values.notna() & (~values.between(-3, 3) | (values % 1 != 0))
        else:
            invalid |= values.notna() & (values <= 0)
        if column == "num-of-doors":
            invalid |= values.notna() & ~values.isin([2, 4])
        if column == "num-of-cylinders":
            invalid |= values.notna() & ~values.isin([2, 3, 4, 5, 6, 8, 12])
        domain_errors[column] = int(invalid.sum())
        values = values.mask(invalid)
        clean[column] = values.astype("Int64") if column in COUNT_COLUMNS else values
    for column in CATEGORICAL:
        clean[column] = clean[column].fillna("unknown").astype("string")

    # No values are invented for missing measurements. Each analysis uses its
    # own complete pairs so rows with unknown price still inform category counts.
    duplicates = int(clean.duplicated().sum())
    clean = clean.drop_duplicates().copy()
    clean.index = clean.index + 1
    clean.index.name = "source_record"
    audit = {
        "raw_shape": list(raw.shape), "clean_shape": list(clean.shape),
        "raw_exact_duplicates": int(raw.duplicated().sum()),
        "duplicates_after_normalization": duplicates,
        "missing_before": missing_before,
        "missing_after": clean.isna().sum().astype(int).to_dict(),
        "normalization_changes": normalization_changes,
        "make_label_corrections": corrections,
        "numeric_conversion_errors": conversion_errors,
        "invalid_domain_values": domain_errors,
        "unknown_category_counts": {c: int(clean[c].eq("unknown").sum()) for c in CATEGORICAL},
        "price_analysis_rows": int(clean["price"].notna().sum()),
        "decisions": [
            "Interpret '?' and blank/null-like tokens as missing, rather than as categories or zero.",
            "Strip surrounding whitespace and normalize category case before checking duplicates.",
            "Correct make labels alfa-romero -> alfa-romeo and peugot -> peugeot; preserve the raw source.",
            "Parse 18 numerical columns, including word-encoded door/cylinder counts; symboling remains ordinal.",
            "Set nonnumeric, nonfinite, or impossible values to missing and record their counts.",
            "Remove only exact duplicates across all 26 normalized fields; retain differing variants.",
            "Keep missing numerical values, without imputation; use complete observations for each question.",
            "Keep plausible IQR outliers: an unusual luxury or performance car is not automatically a data error.",
        ],
    }
    return clean, native(audit)


# 3. Descriptive statistics, group comparisons, and outliers
def analyse(clean: pd.DataFrame, audit: dict) -> dict:
    priced = clean.dropna(subset=["price"])
    if len(priced) < 10 or clean["make"].nunique() < 2:
        raise ValueError("Too few usable records or makes for meaningful analysis.")
    numerical = clean[NUMERICAL].describe().T
    numerical["missing"] = clean[NUMERICAL].isna().sum()
    numerical["skew"] = clean[NUMERICAL].skew()
    category_records = []
    for column in CATEGORICAL:
        counts = clean[column].value_counts()
        category_records.append({"column": column, "unique": len(counts), "mode": counts.index[0],
                                 "mode_count": int(counts.iloc[0]),
                                 "mode_share_percent": 100 * counts.iloc[0] / len(clean)})
    categorical = pd.DataFrame(category_records).set_index("column")
    outlier_records, flagged_records = [], []
    for column in NUMERICAL:
        values = clean[column].dropna().astype(float)
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        flags = (values < low) | (values > high)
        outlier_records.append({"column": column, "n": len(values), "q1": q1, "q3": q3,
                                "iqr": iqr, "lower_fence": low, "upper_fence": high,
                                "flagged": int(flags.sum()), "flagged_percent": 100 * flags.mean()})
        for row_id, value in values[flags].items():
            flagged_records.append({"source_record": row_id, "make": clean.loc[row_id, "make"],
                                    "column": column, "value": value, "lower_fence": low,
                                    "upper_fence": high})
    outliers = pd.DataFrame(outlier_records).set_index("column")
    features = ["price", "engine-size", "horsepower", "curb-weight", "city-mpg", "highway-mpg"]
    correlations = clean[features].corr(method="pearson", min_periods=3)
    available = clean[features].notna().astype(int)
    pair_counts = available.T.dot(available)
    brand_prices = priced.groupby("make")["price"].agg(["count", "mean", "median"]).sort_values("mean", ascending=False)
    body_prices = priced.groupby("body-style")["price"].agg(["count", "mean", "median"]).sort_values("median", ascending=False)
    fuel_summary = clean.groupby("fuel-type").agg(
        records=("fuel-type", "size"), priced_records=("price", "count"),
        mean_price=("price", "mean"), median_price=("price", "median"),
        mean_highway_mpg=("highway-mpg", "mean"),
    )
    return {"numerical": numerical, "categorical": categorical, "outliers": outliers,
            "flagged_records": pd.DataFrame(flagged_records, columns=[
                "source_record", "make", "column", "value", "lower_fence", "upper_fence"]),
            "correlations": correlations, "pair_counts": pair_counts,
            "brand_prices": brand_prices, "body_prices": body_prices,
            "fuel_summary": fuel_summary, "audit": audit}


# 4. Eight meaningful charts using five chart types
def create_charts(clean: pd.DataFrame, results: dict, directory: Path) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 13,
                         "axes.titleweight": "bold", "axes.titlecolor": NAVY,
                         "axes.labelcolor": NAVY, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "white",
                         "savefig.facecolor": "white"})
    charts = []
    priced = clean.dropna(subset=["price"])
    thousands = FuncFormatter(lambda value, _: f"{value:,.0f}")

    def save(number, name, kind, title, observation, fig):
        fig.tight_layout(pad=1.0)
        path = directory / f"{number:02d}_{name}.png"
        fig.savefig(path, dpi=180)
        plt.close(fig)
        charts.append({"number": number, "path": str(path), "file": path.name,
                       "type": kind, "title": title, "observation": observation})

    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    ax.hist(priced["price"], bins=18, color=TEAL, edgecolor="white")
    median = priced["price"].median()
    ax.axvline(median, color=ORANGE, linewidth=2, label=f"Median: {median:,.0f}")
    ax.set(title=f"Price distribution (n={len(priced)})", xlabel="Listed price (source units)", ylabel="Number of cars")
    ax.xaxis.set_major_formatter(thousands)
    ax.legend(frameon=False)
    save(1, "price_distribution", "histogram", "Price distribution",
         f"The mean price is {priced['price'].mean():,.0f}, compared with a median of {median:,.0f}; "
         f"sample skewness is {priced['price'].skew():.2f}. The higher mean and long upper tail indicate right skew.", fig)

    counts = clean["make"].value_counts().head(10).sort_values()
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    bars = ax.barh(counts.index, counts.values, color=TEAL)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set(xlim=(0, counts.max() * 1.15), xlabel="Number of records", ylabel="Make",
           title=f"Ten most represented makes (all {len(clean)} records)")
    top = clean["make"].value_counts()
    save(2, "make_counts", "bar", "Most represented makes",
         f"{top.index[0].title()} contributes {top.iloc[0]} of {len(clean)} records "
         f"({100 * top.iloc[0] / len(clean):.1f}%). The dataset contains {len(top)} makes; "
         "these counts describe dataset composition, not market share.", fig)

    fuel = clean["fuel-type"].value_counts()
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    bars = ax.bar(fuel.index, fuel.values, color=[TEAL, ORANGE, NAVY][:len(fuel)], width=0.55)
    ax.bar_label(bars, labels=[f"{n} ({100*n/len(clean):.1f}%)" for n in fuel.values], padding=5)
    ax.set(ylim=(0, fuel.max() * 1.22), xlabel="Fuel type", ylabel="Number of cars",
           title=f"Fuel-type representation (n={len(clean)})")
    save(3, "fuel_counts", "bar", "Fuel-type representation",
         "; ".join(f"{name}: {int(n)} records ({100*n/len(clean):.1f}%)" for name, n in fuel.items())
         + ". The imbalance limits comparisons between fuel groups.", fig)

    bodies = sorted(priced["body-style"].unique())
    body_values = [priced.loc[priced["body-style"] == body, "price"].to_numpy() for body in bodies]
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    boxes = ax.boxplot(body_values, patch_artist=True, widths=0.55)
    for box in boxes["boxes"]:
        box.set_facecolor("#D6ECEE")
    for line in boxes["medians"]:
        line.set(color=ORANGE, linewidth=2)
    ax.set_xticks(range(1, len(bodies) + 1), [f"{b}\n(n={len(v)})" for b, v in zip(bodies, body_values)])
    ax.set(title="Price varies across body styles", xlabel="Body style (priced records only)", ylabel="Listed price (source units)")
    ax.yaxis.set_major_formatter(thousands)
    best = results["body_prices"].iloc[0]
    best_body = results["body_prices"].index[0]
    save(4, "price_by_body_style", "box", "Price by body style",
         f"{best_body.title()} cars have the highest group median ({best['median']:,.0f}; n={int(best['count'])}). "
         "Group sizes differ; the boxes show spread, and isolated points are IQR flags rather than proven errors.", fig)

    engine_pairs = clean.dropna(subset=["engine-size", "price"])
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    for fuel_type, color in [("gas", TEAL), ("diesel", ORANGE)]:
        group = engine_pairs[engine_pairs["fuel-type"] == fuel_type]
        ax.scatter(group["engine-size"], group["price"], s=30, alpha=0.75, color=color,
                   label=f"{fuel_type} (n={len(group)})", edgecolor="white", linewidth=0.3)
    ax.set(title=f"Engine size and price, by fuel type (n={len(engine_pairs)})",
           xlabel="Engine size (source units)", ylabel="Listed price (source units)")
    ax.yaxis.set_major_formatter(thousands)
    ax.legend(frameon=False, loc="upper left")
    r = engine_pairs["engine-size"].corr(engine_pairs["price"])
    save(5, "engine_size_price", "scatter", "Engine size, price, and fuel type",
         f"Engine size and price have Pearson r={r:.3f} across {len(engine_pairs)} complete pairs. "
         "Fuel colour adds a third variable; the pooled association does not isolate an engine-size effect or establish causation.", fig)

    hp_pairs = clean.dropna(subset=["horsepower", "highway-mpg"])
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    for fuel_type, color in [("gas", TEAL), ("diesel", ORANGE)]:
        group = hp_pairs[hp_pairs["fuel-type"] == fuel_type]
        ax.scatter(group["horsepower"], group["highway-mpg"], color=color, s=30, alpha=0.75,
                   label=f"{fuel_type} (n={len(group)})", edgecolor="white", linewidth=0.3)
    ax.set(title=f"Horsepower and highway fuel economy (n={len(hp_pairs)})",
           xlabel="Reported horsepower", ylabel="Highway fuel economy (MPG)")
    ax.legend(frameon=False)
    r_hp = hp_pairs["horsepower"].corr(hp_pairs["highway-mpg"])
    save(6, "horsepower_highway_mpg", "scatter", "Horsepower and fuel economy",
         f"Horsepower and highway MPG have Pearson r={r_hp:.3f} (n={len(hp_pairs)}). "
         "Higher-power cars tend to have lower fuel economy in this sample; MPG measures efficiency, not distance driven.", fig)

    corr = results["correlations"]
    names = ["Price", "Engine size", "Horsepower", "Curb weight", "City MPG", "Highway MPG"]
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    heat = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(names)), names, rotation=20, ha="right", fontsize=9)
    ax.set_yticks(range(len(names)), names, fontsize=9)
    for row in range(len(names)):
        for column in range(len(names)):
            value = corr.iloc[row, column]
            ax.text(column, row, f"{value:.2f}", ha="center", va="center", fontsize=9,
                    color="white" if abs(value) > 0.6 else NAVY)
    fig.colorbar(heat, ax=ax, fraction=0.03, pad=0.03, label="Pearson r")
    ax.set(title="Relationships among six numerical features", xlabel="Feature", ylabel="Feature")
    ns = results["pair_counts"].to_numpy()
    save(7, "correlation_heatmap", "heatmap", "Numerical feature relationships",
         f"City and highway MPG are closely related (r={corr.loc['city-mpg', 'highway-mpg']:.3f}). "
         f"Cell sample sizes range from {ns.min()} to {ns.max()} because missing values are excluded pair by pair. "
         "Correlations involving similar measurements can be redundant.", fig)

    eligible = results["brand_prices"].query("count >= 5").head(8).sort_values("mean")
    if eligible.empty:
        raise ValueError("No makes have at least five priced records for the make comparison.")
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    bars = ax.barh([f"{brand} (n={int(row['count'])})" for brand, row in eligible.iterrows()],
                   eligible["mean"], color=TEAL)
    ax.bar_label(bars, labels=[f"{v:,.0f}" for v in eligible["mean"]], padding=3, fontsize=9)
    ax.set(xlim=(0, eligible["mean"].max() * 1.22), title="Highest mean prices among makes with n >= 5",
           xlabel="Mean listed price (source units)", ylabel="Make (priced records)")
    ax.xaxis.set_major_formatter(thousands)
    leader = eligible.iloc[-1]
    save(8, "mean_price_by_make", "bar", "Mean prices by make",
         f"Among makes with at least five priced records, {eligible.index[-1]} has the highest mean price "
         f"({leader['mean']:,.0f}; n={int(leader['count'])}). Only the top eight eligible makes are shown; "
         "the minimum count reduces very small-group comparisons but does not remove sampling bias.", fig)
    return charts


# 5. Findings and reproducible evidence exports
def build_findings(clean: pd.DataFrame, results: dict) -> list[str]:
    priced = clean["price"].dropna()
    makes = clean["make"].value_counts()
    fuel = clean["fuel-type"].value_counts()
    corr, ns = results["correlations"], results["pair_counts"]
    eligible = results["brand_prices"].query("count >= 5")
    leader = eligible.iloc[0]
    price_flags = results["outliers"].loc["price"]
    return [
        f"Prices are right-skewed: mean {priced.mean():,.0f}, median {priced.median():,.0f}, "
        f"skewness {priced.skew():.2f} across {len(priced)} known prices.",
        f"{makes.index[0].title()} is the most represented make: {makes.iloc[0]}/{len(clean)} records "
        f"({100*makes.iloc[0]/len(clean):.1f}%). This is sample composition, not market share.",
        f"The fuel mix is imbalanced: " + ", ".join(f"{name} {int(n)}" for name, n in fuel.items()) + ".",
        f"Larger engines are associated with higher prices: Pearson r={corr.loc['engine-size', 'price']:.3f} "
        f"using {ns.loc['engine-size', 'price']} complete pairs.",
        f"Horsepower is negatively associated with highway MPG: Pearson r={corr.loc['horsepower', 'highway-mpg']:.3f} "
        f"using {ns.loc['horsepower', 'highway-mpg']} complete pairs.",
        f"{eligible.index[0]} has the highest mean price among makes with at least five known prices: "
        f"{leader['mean']:,.0f} (n={int(leader['count'])}).",
        f"The price IQR rule flags {int(price_flags['flagged'])}/{int(price_flags['n'])} records outside "
        f"[{price_flags['lower_fence']:,.0f}, {price_flags['upper_fence']:,.0f}]. These observations are retained.",
    ]


def export_results(raw, clean, results, charts, findings, output_dir, data_path, metadata):
    tables = output_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    raw.head(5).to_csv(tables / "raw_sample.csv", index=False)
    clean.to_csv(tables / "cleaned_cars.csv", index=True)
    schema = pd.DataFrame({"column": COLUMNS, "raw_dtype": [str(raw[c].dtype) for c in COLUMNS],
                           "clean_dtype": [str(clean[c].dtype) for c in COLUMNS],
                           "kind": ["categorical" if c in CATEGORICAL else "numerical" for c in COLUMNS],
                           "description": DESCRIPTIONS})
    schema.to_csv(tables / "schema.csv", index=False)
    quality = pd.DataFrame({"missing_before": results["audit"]["missing_before"],
                            "missing_after": results["audit"]["missing_after"]})
    quality.index.name = "column"
    quality.to_csv(tables / "missing_values.csv")
    for key in ["numerical", "categorical", "outliers", "brand_prices", "body_prices",
                "fuel_summary", "correlations", "pair_counts"]:
        results[key].to_csv(tables / f"{key}.csv", index=True, float_format="%.6f")
    results["flagged_records"].to_csv(tables / "outlier_records.csv", index=False)
    counts = pd.concat([clean[c].value_counts().rename_axis("category").reset_index(name="count").assign(column=c)
                        for c in CATEGORICAL], ignore_index=True)
    counts.to_csv(tables / "category_counts.csv", index=False)
    manifest = [{k: v for k, v in chart.items() if k != "path"} for chart in charts]
    summary = {"metadata": metadata, "source": {"page": SOURCE_PAGE, "doi": SOURCE_DOI,
                "archive": SOURCE_ZIP, "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
                "matches_documented_uci_source": hashlib.sha256(data_path.read_bytes()).hexdigest() == SOURCE_SHA256},
               "audit": results["audit"], "charts": manifest, "findings": findings,
               "versions": {"python": platform.python_version(), "pandas": pd.__version__,
                            "numpy": np.__version__, "matplotlib": matplotlib.__version__,
                            "reportlab": reportlab.Version},
               "correlations": results["correlations"].to_dict(),
               "correlation_pair_counts": results["pair_counts"].to_dict()}
    (output_dir / "analysis_summary.json").write_text(json.dumps(native(summary), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Cars EDA findings", "", f"Student: {metadata['student']} | Batch: {metadata['batch']}", "",
             *[f"{i}. {finding}" for i, finding in enumerate(findings, 1)], "", "## Chart observations", ""]
    for chart in charts:
        lines += [f"### {chart['number']}. {chart['title']}", "", f"![{chart['title']}](charts/{chart['file']})", "", chart["observation"], ""]
    lines += ["## Limits", "", "Historical, nonrandom sample; unequal group sizes; missing values use different denominators.",
              "No vehicle age, transmission, odometer mileage, or inflation adjustment. Associations do not establish causation.",
              "", f"Source: Schlimmer, J. (1985). Automobile. UCI. {SOURCE_DOI}. CC BY 4.0."]
    (output_dir / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# 6. An eight-page report containing evidence, not a code listing
def create_report(raw, clean, results, charts, findings, metadata, destination):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", fontName="Helvetica-Bold", fontSize=30,
                              leading=35, textColor=colors.HexColor(NAVY), spaceAfter=18))
    styles.add(ParagraphStyle(name="ReportHeading", fontName="Helvetica-Bold", fontSize=16,
                              leading=20, textColor=colors.HexColor(NAVY), spaceBefore=9, spaceAfter=10))
    styles.add(ParagraphStyle(name="ReportBody", fontName="Helvetica", fontSize=9.3, leading=13,
                              textColor=colors.HexColor(NAVY), spaceAfter=7))
    styles.add(ParagraphStyle(name="SmallBody", fontName="Helvetica", fontSize=8, leading=10.4,
                              textColor=colors.HexColor(GRAY), spaceAfter=5))
    styles.add(ParagraphStyle(name="TableCell", fontName="Helvetica", fontSize=7.3, leading=9,
                              textColor=colors.HexColor(NAVY)))
    styles.add(ParagraphStyle(name="TableHead", fontName="Helvetica-Bold", fontSize=7.3, leading=9,
                              textColor=colors.white))
    styles.add(ParagraphStyle(name="Kicker", fontName="Helvetica-Bold", fontSize=10, leading=13,
                              textColor=colors.HexColor(TEAL), spaceAfter=12))
    width = A4[0] - 84
    story = []

    def paragraph(text, style="ReportBody"):
        return Paragraph(escape(str(text)), styles[style])

    def heading(text):
        story.append(paragraph(text, "ReportHeading"))

    def table(rows, widths, font_style="TableCell"):
        cells = [[paragraph(v, "TableHead" if i == 0 else font_style) for v in row] for i, row in enumerate(rows)]
        item = Table(cells, colWidths=widths, hAlign="LEFT", repeatRows=1)
        item.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F0F5F8"), colors.white]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor(TEAL)),
        ]))
        story.append(item)
        story.append(Spacer(1, 8))

    # Page 1: cover, provenance, scope, and objective.
    story.append(Spacer(1, 38))
    story.append(paragraph("AI MINOR PROJECT  /  EXPLORATORY DATA ANALYSIS", "Kicker"))
    story.append(paragraph("Understanding cars\nthrough data".replace("\n", " "), "ReportTitle"))
    story.append(paragraph("An exploratory study of the UCI Automobile dataset", "ReportHeading"))
    story.append(Spacer(1, 12))
    table([["Student", "Batch", "Report date"], [metadata["student"], metadata["batch"], metadata["report_date"]]],
          [width * 0.5, width * 0.2, width * 0.3])
    table([["Original records", "Original columns", "Charts / types"],
           [len(raw), len(raw.columns), f"{len(charts)} / {len(set(c['type'] for c in charts))}"]], [width / 3] * 3)
    heading("Objective")
    story.append(paragraph("Inspect and improve data quality, summarize automobile specifications, and explain associations "
                           "between price, vehicle characteristics, and fuel economy. The work is descriptive EDA."))
    heading("Research questions")
    for i, question in enumerate(QUESTIONS, 1):
        story.append(paragraph(f"{i}. {question}"))
    heading("Dataset source and scope")
    story.append(paragraph("Schlimmer, J. (1985). Automobile [Dataset]. UCI Machine Learning Repository. " + SOURCE_DOI))
    story.append(paragraph("205 historical vehicle records combine 1985 automobile specifications and insurance attributes. "
                           "The downloaded source has 26 columns, including price. UCI lists 25 features separately from the total source fields."))
    story.append(paragraph("CC BY 4.0. Original data are preserved. Prices and unspecified dimensions use source units; "
                           "no conversion or inflation adjustment is applied. Source and license links appear on page 8.", "SmallBody"))
    story.append(PageBreak())

    # Page 2: all source fields, correct types, and sample records.
    heading("01  /  Dataset overview")
    story.append(paragraph(f"Shape: {len(raw)} rows x {len(raw.columns)} columns. The headerless source is read as strings, "
                           f"then explicitly parsed into {len(NUMERICAL)} numerical and {len(CATEGORICAL)} categorical fields. "
                           "Door and cylinder labels become nullable integer counts; symboling is an ordinal rating."))
    schema_rows = [["Column", "Clean dtype", "Meaning / interpretation"]]
    schema_rows += [[c, str(clean[c].dtype), description] for c, description in zip(COLUMNS, DESCRIPTIONS)]
    table(schema_rows, [114, 65, width - 179])
    story.append(paragraph("First three cleaned records (selected fields)", "Kicker"))
    sample_rows = [["Source row", "Make", "Fuel", "Engine size", "HP", "Price"]]
    sample_rows += [[int(i), row["make"], row["fuel-type"], f"{row['engine-size']:.0f}",
                     f"{row['horsepower']:.0f}", f"{row['price']:,.0f}"] for i, row in clean.head(3).iterrows()]
    table(sample_rows, [57, 112, 55, 88, 55, width - 367])
    story.append(paragraph("No model year, transmission, or odometer distance column is present. MPG is fuel economy, "
                           "so this dataset cannot answer depreciation or distance-driven questions.", "SmallBody"))
    story.append(PageBreak())

    # Page 3: honest missing-data handling and concise descriptive statistics.
    heading("02  /  Quality, cleaning, and summary")
    audit = results["audit"]
    story.append(paragraph(f"Before: {audit['raw_shape'][0]} x 26. After: {audit['clean_shape'][0]} x 26. "
                           f"Exact duplicate rows before cleaning: {audit['raw_exact_duplicates']}; "
                           f"duplicates removed after normalization: {audit['duplicates_after_normalization']}. "
                           f"Price comparisons use {audit['price_analysis_rows']} records; other analyses keep available data."))
    quality_rows = [["Field with missing values", "Before", "After", "Treatment"]]
    for c in COLUMNS:
        if audit["missing_before"][c] or audit["missing_after"][c]:
            quality_rows.append([c, audit["missing_before"][c], audit["missing_after"][c], "Keep missing; omit per analysis"])
    table(quality_rows, [133, 43, 43, width - 219])
    story.append(paragraph("Cleaning decisions: '?' becomes missing; labels are trimmed and lowercased; "
                           f"alfa-romero -> alfa-romeo ({audit['make_label_corrections']['alfa-romero']} rows) and "
                           f"peugot -> peugeot ({audit['make_label_corrections']['peugot']} rows). "
                           "Measurements are parsed numerically, and door/cylinder words become counts. "
                           f"Unexpected numeric strings: {sum(audit['numeric_conversion_errors'].values())}; "
                           f"invalid numerical domain values: {sum(audit['invalid_domain_values'].values())}. "
                           "No numerical values are imputed, avoiding artificial shifts in distributions.", "SmallBody"))
    story.append(paragraph("Numerical descriptive statistics (available observations)", "Kicker"))
    stat_rows = [["Field", "n", "Mean", "SD", "Median", "Min", "Max"]]
    for c in ["price", "engine-size", "horsepower", "curb-weight", "city-mpg", "highway-mpg"]:
        s = results["numerical"].loc[c]
        stat_rows.append([c, int(s["count"]), *[f"{s[k]:,.1f}" for k in ["mean", "std", "50%", "min", "max"]]])
    table(stat_rows, [95, 30, 77, 77, 77, 77, width - 433])
    story.append(paragraph("Categorical summary (all cleaned records)", "Kicker"))
    cat_rows = [["Field", "Unique", "Most common label", "Count", "Share"]]
    for c, row in results["categorical"].iterrows():
        cat_rows.append([c, int(row["unique"]), row["mode"], int(row["mode_count"]), f"{row['mode_share_percent']:.1f}%"])
    table(cat_rows, [111, 48, 194, 57, width - 410])
    price_flags = results["outliers"].loc["price"]
    story.append(paragraph(f"Outlier rule: values below Q1 - 1.5 x IQR or above Q3 + 1.5 x IQR are flagged. "
                           f"For price, Q1={price_flags['q1']:,.0f}, Q3={price_flags['q3']:,.0f}; "
                           f"{int(price_flags['flagged'])} records are flagged. Plausible extremes are retained. "
                           "The exported outlier table covers all numerical fields; flags on ordinal/count variables are only screening indicators.", "SmallBody"))
    story.append(PageBreak())

    # Pages 4-7: two readable charts per page, each with its own observation.
    chart_page_titles = ["03  /  Price and dataset composition", "04  /  Fuel mix and body style",
                         "05  /  Bivariate and multivariate patterns", "06  /  Correlations and make comparisons"]
    for page_index in range(4):
        heading(chart_page_titles[page_index])
        for chart in charts[page_index * 2:page_index * 2 + 2]:
            picture = Image(chart["path"], width=width, height=width * 3.6 / 8.5)
            block = [picture, Spacer(1, 5), paragraph(f"Figure {chart['number']}. {chart['title']}", "Kicker"),
                     paragraph("Observation: " + chart["observation"]), Spacer(1, 12)]
            story.append(KeepTogether(block))
        story.append(PageBreak())

    # Page 8: evidence-based findings and boundaries of interpretation.
    heading("07  /  Findings and conclusion")
    for i, finding in enumerate(findings, 1):
        story.append(paragraph(f"{i}. {finding}"))
    heading("Limitations")
    story.append(paragraph("This is a small historical collection, not a random sample of the present market. "
                           "Makes and fuel groups have unequal representation, and some group sizes are small. "
                           "Complete-pair analysis preserves observed values but can be biased if missingness is systematic. "
                           "Brand, size, power, weight, and body style overlap, so pooled correlations are not independent causal effects. "
                           "No year, transmission, odometer distance, or modern electric-vehicle data are available."))
    heading("Conclusion and learning")
    story.append(paragraph("Price has a long upper tail and is associated with engine and vehicle characteristics. "
                           "Fuel economy tends to decline with horsepower, while categorical summaries reveal strong sample imbalance. "
                           "The main challenges were interpreting missing markers, converting encoded counts, retaining legitimate extremes, "
                           "and using the correct denominator for each question. Future work could add contemporary, representative data, "
                           "compare patterns within makes, and check how conclusions change under justified missing-data treatments."))
    heading("Reproducibility and references")
    story.append(paragraph(f"Analysis date: {metadata['report_date']}. One Python file produces eight charts, data-quality and "
                           "statistics tables, a machine-readable summary, and this report. Numerical results are calculated from the data, "
                           "rather than typed into the report. The source is verified by SHA-256 when automatically downloaded.", "SmallBody"))
    story.append(paragraph("Schlimmer, J. (1985). Automobile [Dataset]. UCI Machine Learning Repository. " + SOURCE_DOI, "SmallBody"))
    story.append(paragraph("Source and original data dictionary: " + SOURCE_PAGE, "SmallBody"))
    story.append(paragraph("Dataset license: https://creativecommons.org/licenses/by/4.0/ . "
                           "Derived changes: category-label correction, numeric parsing, and per-analysis missing-value exclusion.", "SmallBody"))

    def page_frame(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor(TEAL))
        canvas.setLineWidth(1)
        canvas.line(42, A4[1] - 35, A4[0] - 42, A4[1] - 35)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawString(42, 25, "CARS EDA  |  " + metadata["student"])
        canvas.drawRightString(A4[0] - 42, 25, f"{doc.page} / 8")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=42, leftMargin=42,
                            topMargin=48, bottomMargin=42, title="Cars EDA Minor Project",
                            author=metadata["student"], subject="Exploratory data analysis of UCI Automobile")
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)


# 7. Verification: cleaning behaviour and actual generated artefacts
def verify_outputs(clean, results, charts, findings, report_path):
    if len(charts) < 6 or len({c["type"] for c in charts}) < 4 or len(findings) < 5:
        raise AssertionError("The minimum chart/type/finding requirements were not met.")
    if list(clean.columns) != COLUMNS or clean.duplicated().any():
        raise AssertionError("Cleaned schema or duplicate check failed.")
    if not np.isfinite(clean[NUMERICAL].astype(float).to_numpy()[clean[NUMERICAL].notna().to_numpy()]).all():
        raise AssertionError("A nonfinite numerical value remains.")
    for chart in charts:
        if not chart["observation"] or Path(chart["path"]).stat().st_size < 10_000:
            raise AssertionError("A chart or its observation is missing.")
    reader = PdfReader(str(report_path))
    if len(reader.pages) != 8:
        raise AssertionError(f"Expected an eight-page report; found {len(reader.pages)} pages. Review layout.")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if text.count("Observation:") != 8 or SOURCE_DOI not in text:
        raise AssertionError("The report is missing observations or dataset attribution.")
    if sum(len(page.images) for page in reader.pages) != 8:
        raise AssertionError("The PDF does not contain all eight chart images.")
    if results["audit"]["price_analysis_rows"] != int(clean["price"].notna().sum()):
        raise AssertionError("The audit and price-analysis denominator disagree.")
    return {"status": "passed", "pdf_pages": 8, "charts": 8, "chart_types": 5,
            "findings": len(findings), "pdf_chart_images": 8}


class CleaningTests(unittest.TestCase):
    """Small edge cases validate decisions that can materially change results."""

    def example(self):
        values = ["0", "100", "toyota", "gas", "std", "four", "sedan", "fwd", "front",
                  "95", "170", "65", "54", "2200", "ohc", "four", "120", "mpfi", "3.2",
                  "3.1", "9", "100", "5000", "25", "32", "10000"]
        return pd.DataFrame([values], columns=COLUMNS, dtype="string")

    def test_normalization_precedes_duplicate_detection(self):
        first = self.example()
        second = first.copy()
        second.loc[0, "make"] = " TOYOTA "
        second.loc[0, "fuel-type"] = " GAS "
        clean, audit = clean_data(pd.concat([first, second], ignore_index=True))
        self.assertEqual(len(clean), 1)
        self.assertEqual(audit["raw_exact_duplicates"], 0)
        self.assertEqual(audit["duplicates_after_normalization"], 1)

    def test_missing_price_does_not_discard_other_information(self):
        raw = self.example()
        raw.loc[0, ["price", "horsepower"]] = "?"
        clean, audit = clean_data(raw)
        self.assertEqual(len(clean), 1)
        self.assertTrue(pd.isna(clean.iloc[0]["price"]))
        self.assertTrue(pd.isna(clean.iloc[0]["horsepower"]))
        self.assertEqual(audit["price_analysis_rows"], 0)
        self.assertEqual(clean.iloc[0]["make"], "toyota")

    def test_counts_label_correction_and_source_preservation(self):
        raw = self.example()
        raw.loc[0, "make"] = "peugot"
        clean, audit = clean_data(raw)
        self.assertEqual(clean.iloc[0]["make"], "peugeot")
        self.assertEqual(clean.iloc[0]["num-of-doors"], 4)
        self.assertEqual(str(clean["num-of-doors"].dtype), "Int64")
        self.assertEqual(raw.iloc[0]["make"], "peugot")
        self.assertEqual(audit["make_label_corrections"]["peugot"], 1)

    def test_impossible_and_nonfinite_values_become_missing(self):
        raw = self.example()
        raw.loc[0, ["price", "horsepower", "num-of-doors", "symboling"]] = ["-10", "inf", "3", "1.5"]
        raw.loc[0, "peak-rpm"] = "not-a-number"
        clean, audit = clean_data(raw)
        self.assertTrue(clean[["price", "horsepower", "num-of-doors", "symboling", "peak-rpm"]].isna().all().all())
        self.assertEqual(audit["numeric_conversion_errors"]["peak-rpm"], 1)
        self.assertEqual(sum(audit["invalid_domain_values"].values()), 4)

    def test_plausible_extremes_are_retained(self):
        raw = pd.concat([self.example()] * 12, ignore_index=True)
        raw["price"] = [str(6000 + i * 500) for i in range(11)] + ["45000"]
        raw.loc[11, "make"] = "mercedes-benz"
        clean, audit = clean_data(raw)
        results = analyse(clean, audit)
        self.assertEqual(len(clean), 12)
        self.assertEqual(clean["price"].max(), 45000)
        self.assertGreater(results["outliers"].loc["price", "flagged"], 0)

    def test_wrong_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            clean_data(self.example().drop(columns=["price"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=None, help="Optional headerless CSV in the original 26-column UCI schema")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--student", default="Padmavari Aditya")
    parser.add_argument("--batch", default="AI")
    parser.add_argument("--report-date", default=datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat(),
                        help="ISO date, e.g. 2026-11-19")
    parser.add_argument("--self-test", action="store_true", help="Run six cleaning edge-case tests and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(CleaningTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    try:
        report_date = date.fromisoformat(args.report_date).isoformat()
        data_path = args.data.resolve() if args.data else ROOT / "data" / "imports-85.data"
        if not data_path.exists():
            if args.data:
                raise FileNotFoundError(f"Dataset not found: {data_path}")
            print("Dataset not found locally; downloading the documented UCI source...")
            download_dataset(data_path)
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata = {"student": args.student.strip(), "batch": args.batch.strip(), "report_date": report_date}
        if not metadata["student"] or not metadata["batch"]:
            raise ValueError("Student name and batch must be nonempty.")
        raw = load_data(data_path)
        clean, audit = clean_data(raw)
        results = analyse(clean, audit)
        charts = create_charts(clean, results, output_dir / "charts")
        findings = build_findings(clean, results)
        export_results(raw, clean, results, charts, findings, output_dir, data_path, metadata)
        report_path = output_dir / "Padmavari_Aditya_Cars_EDA_Report.pdf"
        create_report(raw, clean, results, charts, findings, metadata, report_path)
        verification = verify_outputs(clean, results, charts, findings, report_path)
        (output_dir / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        submission = ROOT / "submission"
        submission.mkdir(exist_ok=True)
        shutil.copy2(Path(__file__), submission / Path(__file__).name)
        shutil.copy2(report_path, submission / report_path.name)
        print(f"Raw dataset: {raw.shape[0]} rows x {raw.shape[1]} columns")
        print(f"Clean dataset: {clean.shape[0]} rows x {clean.shape[1]} columns; priced records: {audit['price_analysis_rows']}")
        print(f"Missing source cells: {sum(audit['missing_before'].values())}; duplicates removed: {audit['duplicates_after_normalization']}")
        print("Verification: PASSED (8 PDF pages, 8 charts, 5 chart types, 7 findings)")
        for i, finding in enumerate(findings, 1):
            print(f"{i}. {finding}")
        print(f"Report: {report_path}")
        print(f"Two-file submission: {submission}")
        return 0
    except (OSError, ValueError, AssertionError, urllib.error.URLError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
