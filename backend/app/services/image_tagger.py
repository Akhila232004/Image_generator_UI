import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types


# -------------------------------------------------------------------
# Environment
# -------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"

load_dotenv(ENV_FILE)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)


# -------------------------------------------------------------------
# Gemini client
# -------------------------------------------------------------------

def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. "
            "Add GEMINI_API_KEY=your_api_key_here "
            "to backend/.env."
        )

    return genai.Client(api_key=api_key)


# -------------------------------------------------------------------
# Image helpers
# -------------------------------------------------------------------

def _get_mime_type(image_path: Path) -> str:
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }

    extension = image_path.suffix.lower()

    mime_type = mime_types.get(extension)

    if not mime_type:
        raise ValueError(
            f"Unsupported image format: {extension}"
        )

    return mime_type


def _read_image_bytes(
    image_path: Path,
) -> tuple[bytes, str]:

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image file does not exist: {image_path}"
        )

    image_bytes = image_path.read_bytes()

    if not image_bytes:
        raise ValueError(
            f"Image file is empty: {image_path.name}"
        )

    mime_type = _get_mime_type(
        image_path
    )

    return image_bytes, mime_type


# -------------------------------------------------------------------
# Tag cleanup
# -------------------------------------------------------------------

def _clean_tag(value: str) -> str:
    """
    Clean Gemini's response and keep only the
    semantic tag.
    """

    tag = value.strip()

    if not tag:
        return "Uncategorized"

    # ---------------------------------------------------------------
    # Handle accidental JSON response
    # ---------------------------------------------------------------

    try:
        parsed = json.loads(tag)

        if isinstance(parsed, dict):
            tag = str(
                parsed.get("tag", "")
            ).strip()

    except json.JSONDecodeError:
        pass

    # ---------------------------------------------------------------
    # Remove unwanted formatting
    # ---------------------------------------------------------------

    tag = tag.replace("\n", " ").strip()

    tag = tag.strip("`")
    tag = tag.strip('"')
    tag = tag.strip("'")

    # Remove accidental prefixes.
    prefixes = [
        "tag:",
        "tag -",
        "tag–",
        "tag—",
    ]

    lower_tag = tag.lower()

    for prefix in prefixes:
        if lower_tag.startswith(prefix):
            tag = tag[len(prefix):].strip()
            break

    # ---------------------------------------------------------------
    # Remove accidental numbering
    # ---------------------------------------------------------------

    tag = re.sub(
        r"^\s*\d+[\.\)\-:]\s*",
        "",
        tag,
    )

    # ---------------------------------------------------------------
    # Remove accidental trailing punctuation
    # ---------------------------------------------------------------

    tag = tag.rstrip(".;,:-–—").strip()

    if not tag:
        return "Uncategorized"

    return tag


# -------------------------------------------------------------------
# AI image tagging
# -------------------------------------------------------------------

def generate_image_tag(
    image_path: Path,
) -> str:
    """
    Analyze the actual visual content of an image
    using Gemini and generate exactly one concise,
    meaningful 3–5 word semantic tag.
    """

    client = _get_client()

    image_bytes, mime_type = _read_image_bytes(
        image_path
    )

    prompt = """
Analyze the actual visual content of this image very carefully.

Your task is to identify the MAIN SUBJECT and PURPOSE
of the image and create ONE meaningful semantic tag.

The tag MUST contain 3 to 5 words.

The tag must specifically describe WHAT THE IMAGE IS ABOUT,
not simply what the image visually looks like.

For example, if the image is about a course, identify
the subject of the course whenever it is visible.

If the image is about marketing, identify the marketing
topic or campaign.

If the image is about Google Drive, identify the relevant
Google Drive activity or concept.

If the image contains an architecture or process diagram,
identify the actual technology, system, or process.

If the image is educational material, identify the
specific subject or technology being taught.

Examples of GOOD tags:

Python Course Details
Java Programming Course
SQL Server Training
AI/ML Pipeline Architecture
Machine Learning Workflow
Cloud Computing Architecture
AWS Cloud Architecture
Database System Architecture
Database Design Overview
Google Drive File Management
Digital Marketing Campaign
Social Media Marketing Strategy
Business Analytics Dashboard
Software Development Lifecycle
DevOps Deployment Pipeline
API Integration Architecture
Web Development Training
Cybersecurity Training Overview
Network Security Architecture
Data Engineering Pipeline

Examples of BAD tags:

Course
Marketing
Drive
Architecture
Image
Diagram
Screenshot
Technology
Training
Content
Programming

IMPORTANT RULES:

1. Return EXACTLY ONE tag.
2. The tag MUST contain 3 to 5 words.
3. Describe the MAIN SUBJECT of the image.
4. Be specific whenever the subject is visible.
5. For courses, include the course subject when possible.
6. For marketing images, identify the marketing topic.
7. For architecture diagrams, identify the technology/system.
8. For software diagrams, identify the actual process or technology.
9. For dashboards, identify the type of analytics/business information.
10. Do NOT use the filename.
11. Do NOT invent information that cannot be determined from the image.
12. Do NOT return a generic tag when a specific subject is visible.
13. Use Title Case.
14. Do NOT add a period.
15. Do NOT add quotation marks.
16. Do NOT provide any explanation.
17. Do NOT return multiple tags.

Return ONLY the final 3–5 word tag.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
                prompt,
            ],
        )

    except Exception as exc:
        raise RuntimeError(
            "Gemini image analysis failed for "
            f"'{image_path.name}': {exc}"
        ) from exc

    tag = _clean_tag(
        response.text or ""
    )

    if tag == "Uncategorized":
        raise RuntimeError(
            "Gemini returned an empty tag for "
            f"'{image_path.name}'."
        )

    # ---------------------------------------------------------------
    # Normalize whitespace
    # ---------------------------------------------------------------

    tag = re.sub(
        r"\s+",
        " ",
        tag,
    ).strip()

    # ---------------------------------------------------------------
    # Validate word count
    #
    # We don't automatically rewrite the AI response here because
    # rewriting could destroy the actual meaning identified from
    # the image.
    # ---------------------------------------------------------------

    word_count = len(
        tag.split()
    )

    if word_count < 3 or word_count > 5:
        raise RuntimeError(
            "Gemini returned a tag outside the required "
            f"3–5 word range for '{image_path.name}': "
            f"'{tag}'"
        )

    return tag


# -------------------------------------------------------------------
# Metadata
# -------------------------------------------------------------------

def load_tag_metadata(
    metadata_path: Path,
) -> dict[str, Any]:

    if not metadata_path.exists():
        return {}

    try:
        return json.loads(
            metadata_path.read_text(
                encoding="utf-8"
            )
        )

    except (
        json.JSONDecodeError,
        OSError,
    ):
        return {}


def save_tag_metadata(
    metadata_path: Path,
    metadata: dict[str, Any],
) -> None:

    metadata_path.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def get_cached_tag(
    metadata: dict[str, Any],
    filename: str,
) -> str | None:

    item = metadata.get(filename)

    if not isinstance(item, dict):
        return None

    tag = item.get("tag")

    if not tag:
        return None

    return str(tag)


# -------------------------------------------------------------------
# Generate + cache
# -------------------------------------------------------------------

def generate_and_cache_tag(
    image_path: Path,
    metadata_path: Path,
) -> str:

    metadata = load_tag_metadata(
        metadata_path
    )

    # ---------------------------------------------------------------
    # Do not call Gemini again if a tag already exists.
    # ---------------------------------------------------------------

    existing_tag = get_cached_tag(
        metadata,
        image_path.name,
    )

    if existing_tag:
        return existing_tag

    # ---------------------------------------------------------------
    # Generate new semantic tag using Gemini.
    # ---------------------------------------------------------------

    tag = generate_image_tag(
        image_path
    )

    # ---------------------------------------------------------------
    # Cache the generated tag.
    # ---------------------------------------------------------------

    metadata[image_path.name] = {
        "tag": tag
    }

    save_tag_metadata(
        metadata_path,
        metadata,
    )

    return tag