import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Security ---
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

    # --- Gemini AI ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL   = "gemini-2.5-flash"

    
    # --- File Upload ---
    MAX_FILE_SIZE_MB     = 5
    MAX_CONTENT_LENGTH   = MAX_FILE_SIZE_MB * 1024 * 1024  # Flask uses bytes
    ALLOWED_EXTENSIONS   = {"pdf", "docx"}
    UPLOAD_FOLDER        = os.path.join(os.path.dirname(__file__), "uploads")

    # --- Scoring Weights ---
    AI_SCORE_WEIGHT      = 0.60
    KEYWORD_SCORE_WEIGHT = 0.40

    # --- AI Prompt ---
    MAX_INPUT_CHARS = 28_000   # stay within Gemini context limits
    MAX_RETRY       = 3
    RETRY_DELAY_SEC = 2
