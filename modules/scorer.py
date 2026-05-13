"""
Module 4 — Scoring & Analytics Engine
Blends AI semantic score with keyword hit-rate and runs ATS checklist.
"""

import re
import logging
from config import Config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Common stopwords (lightweight, no NLTK needed)
# ──────────────────────────────────────────────

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "this", "that", "these",
    "those", "we", "you", "he", "she", "it", "they", "our", "your", "its",
    "their", "as", "if", "not", "also", "must", "about", "up", "out",
    "who", "which", "what", "when", "where", "how", "all", "any", "both",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, remove stopwords."""
    tokens = re.findall(r"[a-z0-9#+.\-]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


# ──────────────────────────────────────────────
#  Keyword Scoring
# ──────────────────────────────────────────────

def keyword_match_score(resume_text: str, job_description: str) -> tuple[int, int, int]:
    """
    Returns (score_0_100, matched_count, total_jd_keywords).
    Score = matched / total * 100, clamped to 100.
    """
    jd_tokens     = _tokenize(job_description)
    resume_tokens = _tokenize(resume_text)

    if not jd_tokens:
        return 0, 0, 0

    matched = jd_tokens & resume_tokens
    score   = int(len(matched) / len(jd_tokens) * 100)
    return min(score, 100), len(matched), len(jd_tokens)


# ──────────────────────────────────────────────
#  ATS Checklist
# ──────────────────────────────────────────────

_STANDARD_HEADINGS = [
    "experience", "education", "skills", "summary", "objective",
    "certifications", "projects", "achievements", "work history",
]

_CONTACT_PATTERNS = [
    r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}",   # email
    r"(\+?\d[\d\s\-().]{7,}\d)",         # phone
]


def run_ats_checks(resume_text: str) -> list[dict]:
    """
    Run ATS red-flag checks.
    Returns a list of {check, passed, message} dicts.
    """
    checks = []
    text_lower = resume_text.lower()

    # 1. Contact info (email + phone)
    has_email = bool(re.search(_CONTACT_PATTERNS[0], resume_text))
    has_phone = bool(re.search(_CONTACT_PATTERNS[1], resume_text))
    checks.append({
        "check":   "Contact Information",
        "passed":  has_email and has_phone,
        "message": "Email and phone number detected."
                   if has_email and has_phone
                   else "Missing email or phone number — ATS may reject.",
    })

    # 2. Standard section headings
    found_headings = [h for h in _STANDARD_HEADINGS if h in text_lower]
    checks.append({
        "check":   "Standard Section Headings",
        "passed":  len(found_headings) >= 3,
        "message": f"Found headings: {', '.join(found_headings) or 'none'}.",
    })

    # 3. Resume length (word count)
    word_count = len(resume_text.split())
    checks.append({
        "check":   "Resume Length",
        "passed":  300 <= word_count <= 900,
        "message": f"{word_count} words detected. "
                   + ("Ideal range is 300–900 words." if not (300 <= word_count <= 900) else "Good length."),
    })

    # 4. Quantified achievements (numbers / percentages)
    quant_matches = re.findall(r"\b\d+\s*(%|percent|x\b|years?|months?|\+)", resume_text, re.IGNORECASE)
    checks.append({
        "check":   "Quantified Achievements",
        "passed":  len(quant_matches) >= 2,
        "message": f"{len(quant_matches)} quantified achievement(s) found. "
                   + ("Add more numbers to stand out." if len(quant_matches) < 2 else ""),
    })

    # 5. No special characters / symbols overuse
    symbol_density = len(re.findall(r"[★●▶◆■]", resume_text))
    checks.append({
        "check":   "Special Characters",
        "passed":  symbol_density == 0,
        "message": "No ATS-unfriendly special characters found."
                   if symbol_density == 0
                   else f"{symbol_density} decorative symbol(s) detected — ATS may misread them.",
    })

    return checks


# ──────────────────────────────────────────────
#  Blended Final Score
# ──────────────────────────────────────────────

def compute_final_score(ai_score: int, kw_score: int) -> dict:
    """
    Blend AI semantic score (60%) with keyword score (40%).
    Returns dict with final_score, grade, and color.
    """
    final = round(
        ai_score  * Config.AI_SCORE_WEIGHT +
        kw_score  * Config.KEYWORD_SCORE_WEIGHT
    )

    if final >= 75:
        grade, color = "Strong Match",  "#22c55e"   # green
    elif final >= 50:
        grade, color = "Partial Match", "#f59e0b"   # amber
    else:
        grade, color = "Weak Match",    "#ef4444"   # red

    return {
        "final_score":   final,
        "ai_score":      ai_score,
        "keyword_score": kw_score,
        "grade":         grade,
        "color":         color,
    }
