"""Pandas-based data processing pipeline for FinanceNarrate AI.

Provides pure functions that load financial data from CSV or Excel files,
compute key metrics (monthly revenue, MoM growth, top expense categories,
expense anomalies, revenue dips), and orchestrate them into a MetricsResult.
"""

from pathlib import Path

import pandas as pd

from models import (
    ExpenseAnomaly,
    MetricsResult,
    MoMGrowth,
    MonthlyRevenue,
    RevenueDip,
    TopCategory,
)


def load_dataframe(path: Path) -> pd.DataFrame:
    """Load a CSV or Excel file and return a parsed DataFrame.

    Reads the file at *path*, auto-detecting format from the file extension
    (``.csv`` → :func:`pandas.read_csv`, ``.xlsx``/``.xls`` →
    :func:`pandas.read_excel`).  The ``Date`` column is coerced to
    :class:`pandas.Timestamp` via ``parse_dates``.

    Args:
        path: Filesystem path to the CSV or Excel file.

    Returns:
        A :class:`pandas.DataFrame` with at least the columns ``Date``,
        ``Revenue``, ``Expenses``, and ``Category``, where ``Date`` is of
        dtype ``datetime64``.

    Raises:
        ValueError: If the file extension is not ``.csv``, ``.xlsx``, or
            ``.xls``.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path, parse_dates=["Date"])
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, parse_dates=["Date"])
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    return df


def compute_monthly_revenue(df: pd.DataFrame) -> dict[str, float]:
    """Aggregate total revenue by calendar month.

    Groups the DataFrame by the ``YYYY-MM`` representation of the ``Date``
    column and sums the ``Revenue`` column for each group.

    Args:
        df: DataFrame containing at least ``Date`` (datetime) and
            ``Revenue`` (numeric) columns.

    Returns:
        A :class:`dict` mapping ``"YYYY-MM"`` month strings to their
        corresponding total revenue, sorted chronologically (ascending).
    """
    month_key = df["Date"].dt.to_period("M").astype(str)
    grouped = df.groupby(month_key)["Revenue"].sum()
    grouped = grouped.sort_index()
    return {month: float(total) for month, total in grouped.items()}


def compute_mom_growth(monthly: dict[str, float]) -> dict[str, float]:
    """Compute month-over-month revenue growth percentages.

    Iterates over the chronologically sorted *monthly* dict and, for each
    consecutive pair (previous month P, current month C), computes::

        growth_pct = (C - P) / P * 100

    The first month has no predecessor and is therefore excluded from the
    result.

    Args:
        monthly: A ``dict[str, float]`` mapping ``"YYYY-MM"`` month strings
            to total revenue values, as returned by
            :func:`compute_monthly_revenue`.

    Returns:
        A :class:`dict` mapping each month (except the first) to its
        growth percentage relative to the immediately preceding month.
        The dict is sorted chronologically.
    """
    sorted_items = sorted(monthly.items())
    result: dict[str, float] = {}
    for i in range(1, len(sorted_items)):
        prev_month, prev_revenue = sorted_items[i - 1]
        curr_month, curr_revenue = sorted_items[i]
        if prev_revenue != 0:
            growth = (curr_revenue - prev_revenue) / prev_revenue * 100.0
        else:
            growth = 0.0
        result[curr_month] = float(growth)
    return result


def compute_top_categories(df: pd.DataFrame, n: int = 3) -> list[dict]:
    """Return the top N expense categories by total spend.

    Groups the DataFrame by the ``Category`` column, sums the ``Expenses``
    column for each group, and returns the top *n* categories sorted in
    descending order of total expenses.

    Args:
        df: DataFrame containing at least ``Category`` (str) and
            ``Expenses`` (numeric) columns.
        n: Number of top categories to return.  Defaults to ``3``.

    Returns:
        A list of dicts, each with keys:

        - ``"category"`` (:class:`str`): the category name.
        - ``"total_expenses"`` (:class:`float`): summed expenses for that
          category.

        The list is sorted in descending order by ``total_expenses`` and
        contains at most *n* entries.
    """
    grouped = df.groupby("Category")["Expenses"].sum()
    top_n = grouped.nlargest(n).reset_index()
    return [
        {"category": row["Category"], "total_expenses": float(row["Expenses"])}
        for _, row in top_n.iterrows()
    ]


def detect_expense_anomalies(df: pd.DataFrame) -> list[dict]:
    """Flag rows whose expenses exceed 2 standard deviations above the mean.

    Computes the mean (μ) and standard deviation (σ) of the ``Expenses``
    column across all rows, then flags every row where
    ``Expenses > μ + 2σ``.

    Args:
        df: DataFrame containing at least ``Date`` (datetime),
            ``Category`` (str), and ``Expenses`` (numeric) columns.

    Returns:
        A list of dicts for each flagged row, each containing:

        - ``"row_index"`` (:class:`int`): zero-based index in the original
          DataFrame.
        - ``"date"`` (:class:`str`): ISO-formatted date string of the row.
        - ``"category"`` (:class:`str`): expense category.
        - ``"expenses"`` (:class:`float`): the anomalous expense value.
        - ``"z_score"`` (:class:`float`): number of standard deviations
          above the mean.

        Returns an empty list when the DataFrame has fewer than 2 rows or
        when the standard deviation is zero.
    """
    if len(df) < 2:
        return []

    mean = df["Expenses"].mean()
    std = df["Expenses"].std()

    if std == 0:
        return []

    threshold = mean + 2 * std
    anomalies = []
    for idx, row in df[df["Expenses"] > threshold].iterrows():
        z_score = (row["Expenses"] - mean) / std
        anomalies.append(
            {
                "row_index": int(idx),
                "date": str(row["Date"].date()) if hasattr(row["Date"], "date") else str(row["Date"]),
                "category": str(row["Category"]),
                "expenses": float(row["Expenses"]),
                "z_score": float(z_score),
            }
        )
    return anomalies


def detect_revenue_dips(monthly: dict[str, float]) -> list[dict]:
    """Flag months where revenue dropped more than 15% from the prior month.

    Iterates over the chronologically sorted *monthly* dict and, for each
    consecutive pair (previous month P, current month C), flags C when::

        (C - P) / P * 100 < -15.0

    Args:
        monthly: A ``dict[str, float]`` mapping ``"YYYY-MM"`` month strings
            to total revenue values, as returned by
            :func:`compute_monthly_revenue`.

    Returns:
        A list of dicts for each flagged month, each containing:

        - ``"month"`` (:class:`str`): the dip month in ``"YYYY-MM"`` format.
        - ``"revenue"`` (:class:`float`): revenue total for the dip month.
        - ``"previous_month"`` (:class:`str`): the preceding month.
        - ``"previous_revenue"`` (:class:`float`): revenue total for the
          preceding month.
        - ``"drop_pct"`` (:class:`float`): percentage drop as a negative
          value (e.g. ``-18.3``).

        Returns an empty list when *monthly* has fewer than 2 entries or
        when the previous month's revenue is zero.
    """
    sorted_items = sorted(monthly.items())
    dips = []
    for i in range(1, len(sorted_items)):
        prev_month, prev_revenue = sorted_items[i - 1]
        curr_month, curr_revenue = sorted_items[i]
        if prev_revenue == 0:
            continue
        drop_pct = (curr_revenue - prev_revenue) / prev_revenue * 100.0
        if drop_pct < -15.0:
            dips.append(
                {
                    "month": curr_month,
                    "revenue": float(curr_revenue),
                    "previous_month": prev_month,
                    "previous_revenue": float(prev_revenue),
                    "drop_pct": float(drop_pct),
                }
            )
    return dips


def build_metrics(path: Path, file_id: str) -> MetricsResult:
    """Orchestrate the full processing pipeline and return a MetricsResult.

    Loads the file at *path*, runs all sub-functions in sequence, and
    assembles the results into a fully populated :class:`MetricsResult`.

    Pipeline steps:

    1. :func:`load_dataframe` — parse CSV/Excel into a DataFrame.
    2. :func:`compute_monthly_revenue` — aggregate revenue by month.
    3. :func:`compute_mom_growth` — compute MoM growth percentages.
    4. :func:`compute_top_categories` — identify top 3 expense categories.
    5. :func:`detect_expense_anomalies` — flag high-expense rows.
    6. :func:`detect_revenue_dips` — flag months with large revenue drops.

    Args:
        path: Filesystem path to the CSV or Excel file to process.
        file_id: Unique identifier for the uploaded file; stored in the
            returned :class:`MetricsResult`.

    Returns:
        A fully populated :class:`MetricsResult` containing all computed
        financial metrics for the given file.
    """
    df = load_dataframe(path)

    monthly = compute_monthly_revenue(df)
    mom = compute_mom_growth(monthly)
    top_cats = compute_top_categories(df)
    anomalies = detect_expense_anomalies(df)
    dips = detect_revenue_dips(monthly)

    monthly_revenue_list = [
        MonthlyRevenue(month=month, total=total)
        for month, total in monthly.items()
    ]

    mom_growth_list = [
        MoMGrowth(month=month, growth_pct=pct)
        for month, pct in mom.items()
    ]

    top_categories_list = [
        TopCategory(category=cat["category"], total_expenses=cat["total_expenses"])
        for cat in top_cats
    ]

    expense_anomalies_list = [
        ExpenseAnomaly(
            row_index=a["row_index"],
            date=a["date"],
            category=a["category"],
            expenses=a["expenses"],
            z_score=a["z_score"],
        )
        for a in anomalies
    ]

    revenue_dips_list = [
        RevenueDip(
            month=d["month"],
            revenue=d["revenue"],
            previous_month=d["previous_month"],
            previous_revenue=d["previous_revenue"],
            drop_pct=d["drop_pct"],
        )
        for d in dips
    ]

    return MetricsResult(
        file_id=file_id,
        monthly_revenue=monthly_revenue_list,
        mom_growth=mom_growth_list,
        top_categories=top_categories_list,
        expense_anomalies=expense_anomalies_list,
        revenue_dips=revenue_dips_list,
    )
