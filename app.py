"""
Resume Analyzer — Flask Application
All routes wired together.
"""

import os
import uuid

import logging
import json
from flask import (
    Flask, request, render_template, redirect, url_for,
    session, jsonify, send_file, send_from_directory, flash
)
from config import Config
from modules.parser   import safe_save, extract_text
from modules.ai_engine import analyze_resume, generate_interview_questions
from modules.scorer   import keyword_match_score, run_ats_checks, compute_final_score
from modules.report   import generate_pdf_report

# ──────────────────────────────────────────────
#  App Setup
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
app.config["UPLOAD_FOLDER"]      = Config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


# ──────────────────────────────────────────────
#  Route 1 — Upload Form  (GET /)
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────
#  Route 2 — Analyze  (POST /analyze)
# ──────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
def analyze():
    # ── 1. Grab inputs ──────────────────────────
    file = request.files.get("resume")
    jd   = request.form.get("job_description", "").strip()

    if not file or not jd:
        flash("Please upload a resume AND paste a job description.", "error")
        return redirect(url_for("index"))

    # ── 2. Save & parse ─────────────────────────
    try:
        filepath, _ = safe_save(file)
        resume_text = extract_text(filepath)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))

    # ── 3. AI Analysis ──────────────────────────
    try:
        analysis = analyze_resume(resume_text, jd)
    except RuntimeError as e:
        logger.error("Gemini API error: %s", e)
        flash(
            "Our AI is currently busy. Please wait a moment and try again.",
            "error"
        )
        return redirect(url_for("index"))

    # ── 4. Scoring ──────────────────────────────
    kw_score, kw_matched, kw_total = keyword_match_score(resume_text, jd)
    scoring    = compute_final_score(analysis["ai_match_score"], kw_score)
    ats_checks = run_ats_checks(resume_text)

    # ── 5. Persist to session ───────────────────
    session["analysis"]   = analysis
    session["scoring"]    = scoring
    session["ats_checks"] = ats_checks
    session["kw_matched"] = kw_matched
    session["kw_total"]   = kw_total

    return redirect(url_for("results"))


# ──────────────────────────────────────────────
#  Route 3 — Results Dashboard  (GET /results)
# ──────────────────────────────────────────────

@app.route("/results")
def results():
    analysis   = session.get("analysis")
    scoring    = session.get("scoring")
    ats_checks = session.get("ats_checks")

    if not analysis:
        flash("No analysis found. Please upload a resume first.", "error")
        return redirect(url_for("index"))

    return render_template(
        "results.html",
        analysis=analysis,
        scoring=scoring,
        ats_checks=ats_checks,
        kw_matched=session.get("kw_matched", 0),
        kw_total=session.get("kw_total", 0),
    )

# ──────────────────────────────────────────────
#  Route 4 — Interview Questions  (GET /interview)
# ──────────────────────────────────────────────

@app.route("/interview")
def interview():
    analysis = session.get("analysis")
    if not analysis:
        flash("Please analyze a resume first.", "error")
        return redirect(url_for("index"))

    missing_skills = analysis.get("missing_skills", [])

    try:
        questions = generate_interview_questions(missing_skills)
    except Exception as e:
        logger.error("Interview generation failed: %s", e)
        flash("Could not generate interview questions. Please try again.", "error")
        return redirect(url_for("results"))

    return render_template("interview.html", questions=questions)


# ──────────────────────────────────────────────
#  Route 5 — Voice Feedback  (GET /voice)
# ──────────────────────────────────────────────

@app.route("/voice")
def voice():
    analysis = session.get("analysis")
    scoring  = session.get("scoring")

    if not analysis:
        return jsonify({"error": "No analysis in session."}), 400

    score   = scoring["final_score"]
    grade   = scoring["grade"]
    summary = analysis.get("summary", "")
    found   = ", ".join(analysis.get("found_skills",   [])[:5]) or "none"
    missing = ", ".join(analysis.get("missing_skills", [])[:5]) or "none"

    speech_text = (
        f"Resume Analysis Summary. "
        f"Your final match score is {score} out of 100, rated as {grade}. "
        f"{summary} "
        f"Key skills found include: {found}. "
        f"Skills to develop: {missing}."
    )

    try:
        from gtts import gTTS
        audio_dir  = os.path.join(app.root_path, "static", "audio")
        os.makedirs(audio_dir, exist_ok=True)
        audio_file = "feedback.mp3"
        audio_path = os.path.join(audio_dir, audio_file)

        tts = gTTS(text=speech_text, lang="en", slow=False)
        tts.save(audio_path)

        return jsonify({"audio_url": url_for("static", filename=f"audio/{audio_file}")})

    except Exception as e:
        logger.error("gTTS error: %s", e)
        return jsonify({"error": "Voice generation failed. Please try again."}), 500


# ──────────────────────────────────────────────
#  Route 6 — PDF Report Download  (GET /report)
# ──────────────────────────────────────────────

@app.route("/report")
def report():
    analysis   = session.get("analysis")
    scoring    = session.get("scoring")
    ats_checks = session.get("ats_checks")

    if not analysis:
        flash("No analysis found. Please upload a resume first.", "error")
        return redirect(url_for("index"))

    try:
        import io
        pdf_bytes = generate_pdf_report(analysis, scoring, ats_checks)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="resume_analysis_report.pdf",
        )
    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        flash("Could not generate the PDF report.", "error")
        return redirect(url_for("results"))


# ──────────────────────────────────────────────
#  Error Handlers
# ──────────────────────────────────────────────

@app.errorhandler(413)
def file_too_large(e):
    flash(f"File too large. Maximum size is {Config.MAX_FILE_SIZE_MB} MB.", "error")
    return redirect(url_for("index"))

@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled server error")
    return render_template("index.html"), 500


# ──────────────────────────────────────────────
#  Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
