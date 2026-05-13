"""
Module 3 — AI Logic (Gemini API Integration)
Uses the current google-genai SDK. Client is lazy-initialized.
"""

import json
import time
import logging
from config import Config

logger = logging.getLogger(__name__)

_client = None

def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _client


SYSTEM_PROMPT = (
    "You are an expert ATS analyst and career coach. "
    "Return ONLY a valid JSON object — no markdown fences, no explanations."
)

ANALYSIS_PROMPT_TEMPLATE = """Analyze this resume against the job description. Return ONLY this JSON:

{{
  "ai_match_score": <integer 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "found_skills": ["<skill>"],
  "missing_skills": ["<skill>"],
  "strengths": ["<point>"],
  "weaknesses": ["<point>"],
  "ats_flags": ["<flag>"]
}}

--- RESUME ---
{resume_text}

--- JOB DESCRIPTION ---
{job_description}
"""

INTERVIEW_PROMPT_TEMPLATE = """Generate 3 interview questions per missing skill. Return ONLY this JSON array:
[{{"skill": "<name>", "questions": ["<q1>", "<q2>", "<q3>"]}}]

Missing skills: {missing_skills}
"""


def _call_gemini(prompt: str) -> str:
    from google.genai import types
    client = _get_client()
    last_error = None
    for attempt in range(1, Config.MAX_RETRY + 1):
        try:
            response = client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    max_output_tokens=2048,
                ),
            )
            return response.text
        except Exception as e:
            last_error = e
            logger.warning("Gemini attempt %d/%d failed: %s", attempt, Config.MAX_RETRY, e)
            if attempt < Config.MAX_RETRY:
                time.sleep(Config.RETRY_DELAY_SEC * attempt)
    raise RuntimeError(f"Gemini API failed after {Config.MAX_RETRY} attempts: {last_error}")


def _parse_json(raw: str):
    cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(cleaned)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[...truncated...]"
    return text


def analyze_resume(resume_text: str, job_description: str) -> dict:
    half = Config.MAX_INPUT_CHARS // 2
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        resume_text=_truncate(resume_text, half),
        job_description=_truncate(job_description, half),
    )
    raw    = _call_gemini(prompt)
    result = _parse_json(raw)

    defaults = {
        "ai_match_score": 0, "summary": "Analysis unavailable.",
        "found_skills": [], "missing_skills": [],
        "strengths": [], "weaknesses": [], "ats_flags": [],
    }
    for key, default in defaults.items():
        result.setdefault(key, default)
    return result


def generate_interview_questions(missing_skills: list) -> list:
    if not missing_skills:
        return []
    prompt = INTERVIEW_PROMPT_TEMPLATE.format(missing_skills=", ".join(missing_skills))
    raw    = _call_gemini(prompt)
    result = _parse_json(raw)
    return result if isinstance(result, list) else []
