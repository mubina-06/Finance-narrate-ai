"""Tests for processor.py using the sample CSV fixture."""

import math
from pathlib import Path

import pytest

from processor import (
    build_metrics,
    compute_mom_growth,
    compute_monthly_revenue,
    compute_top_categories,
    detect_expense_anomalies,
    detect_revenue_dips,
    load_dataframe,
)
from models import MetricsResult

# Path to the sample CSV relative to this file
SAMPLE_CSV = Path(__file__).parent.parent.parent.parent / "finance_narrate" / "sample_data" / "sample_finance.csv"


@pytest.fixture(scope="module")
def df():
    return load_dataframe(SAMPLE_CSV)


@pytest.fixture(scope="module")
def monthly(df):
    return compute_monthly_revenue(df)


# ---------------------------------------------------------------------------
# 1. load_dataframe
# ---------------------------------------------------------------------------

class TestLoadDataframe:
    def test_loads_correct_row_count(self, df):
        assert len(df) == 24

    def test_has_required_columns(self, df):
        for col in ("Date", "Revenue", "Expenses", "Category"):
            assert col in df.columns

    def test_date_column_is_datetime(self, df):
        import pandas as pd
        assert pd.api.types.is_datetime64_any_dtype(df["Date"])

    def test_raises_on_unsupported_extension(self, tmp_path):
        bad_file = tmp_path / "data.txt"
        bad_file.write_text("dummy")
        with pytest.raises(ValueError, match="Unsupported file type"):
            load_dataframe(bad_file)


# ---------------------------------------------------------------------------
# 2. compute_monthly_revenue
# ---------------------------------------------------------------------------

class TestComputeMonthlyRevenue:
    def test_returns_twelve_months(self, monthly):
        assert len(monthly) == 12

    def test_january_total(self, monthly):
        # 120000 + 95000
        assert monthly["2023-01"] == pytest.approx(215000.0)

    def test_november_total(self, monthly):
        # 120000 + 100000
        assert monthly["2023-11"] == pytest.approx(220000.0)

    def test_december_total(self, monthly):
        # 175000 + 165000
        assert monthly["2023-12"] == pytest.approx(340000.0)

    def test_sorted_chronologically(self, monthly):
        keys = list(monthly.keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# 3. compute_mom_growth
# ---------------------------------------------------------------------------

class TestComputeMomGrowth:
    def test_excludes_first_month(self, monthly):
        growth = compute_mom_growth(monthly)
        assert "2023-01" not in growth

    def test_returns_eleven_entries(self, monthly):
        growth = compute_mom_growth(monthly)
        assert len(growth) == 11

    def test_february_growth(self, monthly):
        # (240000 - 215000) / 215000 * 100 ≈ 11.628
        growth = compute_mom_growth(monthly)
        assert growth["2023-02"] == pytest.approx(11.628, rel=1e-3)

    def test_november_negative_growth(self, monthly):
        # (220000 - 330000) / 330000 * 100 ≈ -33.333
        growth = compute_mom_growth(monthly)
        assert growth["2023-11"] < -15.0

    def test_december_recovery(self, monthly):
        # (340000 - 220000) / 220000 * 100 ≈ 54.545
        growth = compute_mom_growth(monthly)
        assert growth["2023-12"] > 0


# ---------------------------------------------------------------------------
# 4. compute_top_categories
# ---------------------------------------------------------------------------

class TestComputeTopCategories:
    def test_returns_three_categories(self, df):
        top = compute_top_categories(df)
        assert len(top) == 3

    def test_operations_is_top_due_to_anomaly(self, df):
        # Operations has the 95000 anomaly row, making it the highest spender
        top = compute_top_categories(df)
        top_names = [c["category"] for c in top]
        assert "Operations" in top_names
        assert top[0]["category"] == "Operations"

    def test_sorted_descending(self, df):
        top = compute_top_categories(df)
        totals = [c["total_expenses"] for c in top]
        assert totals == sorted(totals, reverse=True)

    def test_custom_n(self, df):
        top = compute_top_categories(df, n=2)
        assert len(top) == 2


# ---------------------------------------------------------------------------
# 5. detect_expense_anomalies
# ---------------------------------------------------------------------------

class TestDetectExpenseAnomalies:
    def test_detects_known_anomaly(self, df):
        anomalies = detect_expense_anomalies(df)
        assert len(anomalies) >= 1

    def test_anomaly_is_operations_95000(self, df):
        anomalies = detect_expense_anomalies(df)
        expenses = [a["expenses"] for a in anomalies]
        assert 95000.0 in expenses

    def test_anomaly_has_positive_z_score(self, df):
        anomalies = detect_expense_anomalies(df)
        for a in anomalies:
            assert a["z_score"] > 2.0

    def test_anomaly_fields_present(self, df):
        anomalies = detect_expense_anomalies(df)
        for a in anomalies:
            for key in ("row_index", "date", "category", "expenses", "z_score"):
                assert key in a

    def test_empty_df_returns_empty(self):
        import pandas as pd
        empty = pd.DataFrame(columns=["Date", "Revenue", "Expenses", "Category"])
        assert detect_expense_anomalies(empty) == []


# ---------------------------------------------------------------------------
# 6. detect_revenue_dips
# ---------------------------------------------------------------------------

class TestDetectRevenueDips:
    def test_detects_november_dip(self, monthly):
        dips = detect_revenue_dips(monthly)
        dip_months = [d["month"] for d in dips]
        assert "2023-11" in dip_months

    def test_dip_drop_pct_is_negative(self, monthly):
        dips = detect_revenue_dips(monthly)
        for d in dips:
            assert d["drop_pct"] < -15.0

    def test_november_dip_details(self, monthly):
        dips = detect_revenue_dips(monthly)
        nov = next(d for d in dips if d["month"] == "2023-11")
        assert nov["previous_month"] == "2023-10"
        assert nov["revenue"] == pytest.approx(220000.0)
        assert nov["previous_revenue"] == pytest.approx(330000.0)
        assert nov["drop_pct"] == pytest.approx(-33.333, rel=1e-3)

    def test_no_dip_for_single_month(self):
        assert detect_revenue_dips({"2023-01": 100000.0}) == []


# ---------------------------------------------------------------------------
# 7. build_metrics
# ---------------------------------------------------------------------------

class TestBuildMetrics:
    def test_returns_metrics_result_instance(self):
        result = build_metrics(SAMPLE_CSV, file_id="test-001")
        assert isinstance(result, MetricsResult)

    def test_file_id_preserved(self):
        result = build_metrics(SAMPLE_CSV, file_id="abc-123")
        assert result.file_id == "abc-123"

    def test_monthly_revenue_populated(self):
        result = build_metrics(SAMPLE_CSV, file_id="test-001")
        assert len(result.monthly_revenue) == 12

    def test_mom_growth_populated(self):
        result = build_metrics(SAMPLE_CSV, file_id="test-001")
        assert len(result.mom_growth) == 11

    def test_top_categories_populated(self):
        result = build_metrics(SAMPLE_CSV, file_id="test-001")
        assert len(result.top_categories) == 3

    def test_expense_anomalies_detected(self):
        result = build_metrics(SAMPLE_CSV, file_id="test-001")
        assert len(result.expense_anomalies) >= 1

    def test_revenue_dips_detected(self):
        result = build_metrics(SAMPLE_CSV, file_id="test-001")
        assert len(result.revenue_dips) >= 1
