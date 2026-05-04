"""Pydantic v2 data models for the FinanceNarrate AI backend.

Defines all request/response schemas used across the API endpoints,
the Pandas processing pipeline, and the LLM narrative generation client.
"""

from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Response returned after a successful file upload.

    Attributes:
        file_id: Unique identifier assigned to the uploaded file.
        filename: Original name of the uploaded file.
        row_count: Number of data rows in the uploaded file.
        status: Upload status, always "uploaded" on success.
    """

    file_id: str
    filename: str
    row_count: int
    status: str  # "uploaded"


class MonthlyRevenue(BaseModel):
    """Total revenue aggregated for a single calendar month.

    Attributes:
        month: Month in "YYYY-MM" format.
        total: Sum of all revenue values for that month.
    """

    month: str  # "YYYY-MM"
    total: float


class MoMGrowth(BaseModel):
    """Month-over-month revenue growth percentage for a single month.

    Attributes:
        month: Month in "YYYY-MM" format.
        growth_pct: Growth percentage relative to the previous month,
            e.g. 5.2 means +5.2%.
    """

    month: str
    growth_pct: float  # e.g. 5.2 means +5.2%


class TopCategory(BaseModel):
    """An expense category ranked among the top N by total spend.

    Attributes:
        category: Name of the expense category.
        total_expenses: Summed expense total for this category.
    """

    category: str
    total_expenses: float


class ExpenseAnomaly(BaseModel):
    """A single row flagged as an expense anomaly (> 2 std deviations above mean).

    Attributes:
        row_index: Zero-based index of the row in the original DataFrame.
        date: Date string of the anomalous transaction.
        category: Expense category of the anomalous transaction.
        expenses: Expense value that triggered the anomaly flag.
        z_score: Number of standard deviations above the mean.
    """

    row_index: int
    date: str
    category: str
    expenses: float
    z_score: float


class RevenueDip(BaseModel):
    """A month flagged as a revenue dip (> 15% drop from the previous month).

    Attributes:
        month: The month in which the dip occurred ("YYYY-MM").
        revenue: Revenue total for the dip month.
        previous_month: The preceding month ("YYYY-MM").
        previous_revenue: Revenue total for the preceding month.
        drop_pct: Percentage drop as a negative value, e.g. -18.3.
    """

    month: str
    revenue: float
    previous_month: str
    previous_revenue: float
    drop_pct: float  # negative value, e.g. -18.3


class MetricsResult(BaseModel):
    """All computed financial metrics for a single uploaded file.

    Attributes:
        file_id: Identifier of the file these metrics belong to.
        monthly_revenue: List of monthly revenue totals sorted chronologically.
        mom_growth: List of month-over-month growth percentages.
        top_categories: Top 3 expense categories by total spend.
        expense_anomalies: Rows whose expenses exceed 2 standard deviations above the mean.
        revenue_dips: Months where revenue dropped more than 15% from the prior month.
    """

    file_id: str
    monthly_revenue: list[MonthlyRevenue]
    mom_growth: list[MoMGrowth]
    top_categories: list[TopCategory]
    expense_anomalies: list[ExpenseAnomaly]
    revenue_dips: list[RevenueDip]


class NarrativeResult(BaseModel):
    """AI-generated board-ready narrative for a single uploaded file.

    Attributes:
        file_id: Identifier of the file this narrative belongs to.
        executive_summary: 3–4 sentence formal executive summary.
        revenue_trends: Bullet-point list describing revenue trend observations.
        anomalies: One entry per flagged expense anomaly or revenue dip.
        recommendations: 2–3 strategic action items.
    """

    file_id: str
    executive_summary: str
    revenue_trends: list[str]   # bullet points
    anomalies: list[str]        # one entry per flagged anomaly
    recommendations: list[str]  # 2–3 action items


class ReportResult(BaseModel):
    """Combined report containing both computed metrics and the AI narrative.

    Attributes:
        file_id: Identifier of the file this report belongs to.
        metrics: The full MetricsResult for the file.
        narrative: The full NarrativeResult for the file.
    """

    file_id: str
    metrics: MetricsResult
    narrative: NarrativeResult
