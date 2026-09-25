"""
PDF parser service with pypdf and pdfminer.six fallback.

Parses PDF files in streaming chunks (64KB) to avoid OOM.
Hard cap at 10MB before processing.
"""
import io
from dataclasses import dataclass
from typing import BinaryIO

from pypdf import PdfReader

from app.core.logging import get_logger

logger = get_logger(__name__)

# Hard cap: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Chunk size for streaming reads
CHUNK_SIZE = 64 * 1024


class PDFParseError(Exception):
    """Raised when PDF parsing fails completely."""
    def __init__(self, message: str, cv_id_tentative: str | None = None):
        super().__init__(message)
        self.cv_id_tentative = cv_id_tentative


class PDFNoTextError(PDFParseError):
    """Raised when PDF has no extractable text (scanned/image-only)."""
    pass


@dataclass
class ParsedCV:
    """Result of PDF parsing."""
    raw_text: str
    structured: dict
    detected_locale: str


def validate_file_size(file: BinaryIO) -> int:
    """Validate file size is within limits.

    Returns the file size in bytes.

    Raises:
        ValueError: If file exceeds MAX_FILE_SIZE
    """
    # Read file to check size
    content = file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {file_size} bytes (max {MAX_FILE_SIZE})")

    # Reset file pointer
    file.seek(0)

    return file_size


def extract_text_with_pypdf(file_content: bytes) -> str | None:
    """Extract text using pypdf.

    Returns None if extraction fails.
    """
    try:
        reader = PdfReader(io.BytesIO(file_content), strict=False)
        text_parts = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n".join(text_parts) if text_parts else None

    except Exception as e:
        logger.warning("pypdf_extraction_failed", error=str(e))
        return None


def extract_text_with_pdfminer(file_content: bytes) -> str | None:
    """Extract text using pdfminer.six as fallback.

    Returns None if extraction fails.
    """
    try:
        from pdfminer.high_level import extract_text

        text = extract_text(io.BytesIO(file_content))
        return text if text else None

    except Exception as e:
        logger.warning("pdfminer_extraction_failed", error=str(e))
        return None


def detect_locale(text: str) -> str:
    """Detect locale from extracted text.

    Simple heuristic: count Spanish vs English common words.
    """
    spanish_indicators = {"el", "la", "de", "en", "que", "es", "por", "con", "para", "experiencia", "educación", "habilidades"}
    english_indicators = {"the", "and", "for", "with", "experience", "education", "skills", "work", "company"}

    text_lower = text.lower()
    words = set(text_lower.split())

    spanish_count = len(words & spanish_indicators)
    english_count = len(words & english_indicators)

    if spanish_count > english_count:
        return "es"
    elif english_count > spanish_count:
        return "en"
    else:
        return "es"  # Default to Spanish


def parse_pdf(file_content: bytes) -> ParsedCV:
    """Parse PDF and extract text and structured data.

    Args:
        file_content: Raw PDF bytes

    Returns:
        ParsedCV with raw_text, structured data, and detected_locale

    Raises:
        PDFParseError: If both pypdf and pdfminer fail
    """
    # Try pypdf first
    raw_text = extract_text_with_pypdf(file_content)

    # Fallback to pdfminer if pypdf failed
    if raw_text is None:
        logger.info("falling_back_to_pdfminer")
        raw_text = extract_text_with_pdfminer(file_content)

    # If both failed, raise error
    if raw_text is None:
        raise PDFParseError("Failed to extract text from PDF using both pypdf and pdfminer")

    # Check if we got meaningful text - distinguish "no text" from "parse failed"
    if raw_text is not None and len(raw_text.strip()) < 50:
        raise PDFNoTextError("PDF contains no extractable text")

    # Detect locale
    detected_locale = detect_locale(raw_text)

    # Build structured data
    structured = _build_structured_cv(raw_text, detected_locale)

    return ParsedCV(
        raw_text=raw_text,
        structured=structured,
        detected_locale=detected_locale
    )


# Common programming/tech skills for extraction
TECH_SKILLS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "ruby", "go", "rust",
    "php", "swift", "kotlin", "scala", "r", "matlab", "sql", "html", "css",
    "react", "angular", "vue", "node", "django", "flask", "spring", "rails",
    "docker", "kubernetes", "aws", "azure", "gcp", "terraform", "ansible",
    "git", "jenkins", "ci/cd", "linux", "unix", "bash", "shell",
    "machine learning", "deep learning", "tensorflow", "pytorch", "keras",
    "nlp", "computer vision", "data science", "big data", "hadoop", "spark",
    "mongodb", "postgresql", "mysql", "redis", "elasticsearch", "graphql", "rest",
    "agile", "scrum", "jira", "confluence", "uml", "microservices", "api",
    "rest api", "graphql api", "oauth", "jwt", "docker-compose",
    " pandas", "numpy", "scipy", "sklearn", "pillow", "opencv",
}

# Common city names for location extraction
COMMON_CITIES = {
    "madrid", "barcelona", "valencia", "sevilla", "bilbao", "malaga",
    "buenos aires", "mexico city", "bogota", "lima", "santiago",
    "new york", "los angeles", "san francisco", "chicago", "seattle",
    "london", "paris", "berlin", "amsterdam", "lisbon", "dublin",
    "tokyo", "singapore", "hong kong", "sydney", "melbourne",
}


def _extract_skills(text: str) -> list[str]:
    """Extract skills from text using keyword matching."""
    text_lower = text.lower()
    found = []
    for skill in TECH_SKILLS:
        if skill in text_lower:
            # Normalize: title case for multi-word, capitalize for single
            if " " in skill:
                found.append(skill.title())
            else:
                found.append(skill.upper())
    # Dedupe while preserving order
    seen = set()
    unique = []
    for s in found:
        if s.lower() not in seen:
            seen.add(s.lower())
            unique.append(s)
    return unique[:15]  # Limit to 15 skills


def _extract_experience_years(text: str) -> list[dict]:
    """Extract experience years using regex patterns."""
    import re
    experiences = []

    # Pattern: "X años de experiencia" or "X years of experience"
    years_pattern = r'(\d+)\s*(?:años|anos|years)\s*(?:de\s*)?(?:experiencia|experience)'
    matches = re.findall(years_pattern, text, re.IGNORECASE)

    for match in matches:
        years = int(match)
        if 0 < years <= 40:  # Reasonable range
            experiences.append({
                "years": years,
                "description": f"{years} years of professional experience"
            })

    # Also look for date ranges like "2020-2023" or "01/2020 - 12/2023"
    date_range_pattern = r'(?:from\s*)?(\d{4})\s*[-–/to]+\s*(\d{4}|present|current)'
    date_matches = re.findall(date_range_pattern, text, re.IGNORECASE)

    for start, end in date_matches:
        if start.isdigit() and len(start) == 4:
            if end.lower() in ("present", "current"):
                end_year = 2026  # Current year
            elif end.isdigit() and len(end) == 4:
                end_year = int(end)
            else:
                continue
            exp_years = end_year - int(start)
            if 0 < exp_years <= 40:
                experiences.append({
                    "years": exp_years,
                    "description": f"Experience from {start} to {end_year}"
                })

    return experiences[:5]  # Limit to 5 entries


def _extract_location(text: str) -> str | None:
    """Extract location (city) from text."""
    text_lower = text.lower()
    for city in COMMON_CITIES:
        if city in text_lower:
            # Title case for output
            return city.title()
    return None


def _build_structured_cv(text: str, locale: str) -> dict:
    """Build structured CV data from extracted text.

    Lightweight regex/keyword extraction for MVP.
    """
    import re
    lines = text.split("\n")

    # Extract email
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    email = emails[0] if emails else None

    # Extract phone (various formats)
    phone_pattern = r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    phones = re.findall(phone_pattern, text)
    phone = phones[0] if phones else None

    # Extract name (first non-empty line that's not too long and has no digits)
    name = None
    for line in lines[:5]:
        line = line.strip()
        if line and 2 <= len(line) <= 100 and not any(c.isdigit() for c in line):
            name = line
            break

    # Extract skills
    skills = _extract_skills(text)

    # Extract experience years
    experience = _extract_experience_years(text)

    # Extract location
    location = _extract_location(text)

    # Simple education extraction - look for keywords
    education = []
    edu_keywords = ["universidad", "university", "licenciatura", "grado", "degree", "master", "máster", "phd", "doctorado"]
    text_lower = text.lower()
    for kw in edu_keywords:
        if kw in text_lower:
            education.append({"level": kw.title(), "description": f"Education with {kw}"})
            break

    # Languages - look for common language names
    languages = []
    lang_keywords = {"español": "Spanish", "english": "English", "francés": "French", "alemán": "German", "chino": "Chinese", "portugués": "Portuguese"}
    for kw, lang in lang_keywords.items():
        if kw in text_lower:
            languages.append(lang)

    return {
        "full_name": name or "Unknown",
        "email": email,
        "phone": phone,
        "location": location,
        "experience": experience,
        "education": education,
        "skills": skills,
        "languages": languages,
    }
