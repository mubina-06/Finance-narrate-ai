"""Gemini LLM client for FinanceNarrate AI.

Uses the google-genai SDK (replaces deprecated google-generativeai).
Raises RuntimeError at module load if GEMINI_API_KEY is not set.
"""

import json
import os
import re

from dotenv import load_dotenv
from fastapi import HTTPException
from google import genai
from google.genai import types

from models import MetricsResult, NarrativeResult

# ---------------------------------------------------------------------------
# Startup key check and SDK initialisation
# ---------------------------------------------------------------------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not set.")

client = genai.Client(api_key=api_key)

MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

def build_prompt(metrics: MetricsResult) -> str:
    """Construct a Gemini prompt embedding the metrics JSON.

    Args:
        metrics: The computed financial metrics for the uploaded file.

    Returns:
        A prompt string ready to be sent to the Gemini API.
    """
    metrics_json = metrics.model_dump_json()

    return f"""You are a senior financial analyst preparing a board-ready executive report.

Below is a JSON object containing computed financial metrics for a company:

{metrics_json}

Using these metrics, produce a structured financial narrative. Your response MUST be a single valid JSON object with EXACTLY these four keys:

1. "executive_summary": A formal 3-4 sentence executive summary of the overall financial performance.
2. "revenue_trends": A list of bullet-point strings, each describing a key revenue trend observation.
3. "anomalies": A list of strings, one entry per flagged expense anomaly or revenue dip.
4. "recommendations": A list of 2-3 strategic action item strings.

Rules:
- Tone: formal and professional.
- Return ONLY the JSON object. No markdown code fences, no extra text.
"""


# ---------------------------------------------------------------------------
# call_gemini
# ---------------------------------------------------------------------------

def call_gemini(prompt: str) -> str:
    """Send a prompt to Gemini and return the raw text response.

    Args:
        prompt: The fully constructed prompt string.

    Returns:
        The raw text content of the Gemini API response.
    """
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )
    return response.text


# ---------------------------------------------------------------------------
# parse_narrative
# ---------------------------------------------------------------------------

def parse_narrative(raw: str, file_id: str) -> NarrativeResult:
    """Parse the raw Gemini response into a NarrativeResult.

    Args:
        raw: The raw text response from Gemini.
        file_id: The file identifier to embed in the result.

    Returns:
        A NarrativeResult with the four narrative sections.

    Raises:
        HTTPException: HTTP 502 if the response is not valid JSON.
    """
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())

    try:
        data = json.loads(cleaned)
        return NarrativeResult(
            file_id=file_id,
            executive_summary=data["executive_summary"],
            revenue_trends=data["revenue_trends"],
            anomalies=data["anomalies"],
            recommendations=data["recommendations"],
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HTTPException(status_code=502, detail="Malformed response from Gemini API.")


# ---------------------------------------------------------------------------
# generate_narrative
# ---------------------------------------------------------------------------

def generate_narrative(metrics: MetricsResult) -> NarrativeResult:
    """Orchestrate the full narrative generation pipeline.

    Args:
        metrics: The computed financial metrics for the uploaded file.

    Returns:
        A NarrativeResult containing the four-section board-ready narrative.
    """
    prompt = build_prompt(metrics)
    raw = call_gemini(prompt)
    return parse_narrative(raw, metrics.file_id)
