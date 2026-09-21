import json
import os
from pathlib import Path

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.5-flash-lite"


def _get_api_key() -> str:
    """
    Read only the Gemini credential activated by the backend.

    GOOGLE_API_KEY is intentionally not used here. The backend activates
    GEMINI_API_KEY after the user selects Gemini API.
    """

    api_key = os.environ.get(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "Gemini API is not active. Upload the API configuration "
            "file and select Gemini API first."
        )

    return api_key


def _get_model() -> str:
    return (
        os.environ.get(
            "GEMINI_MODEL",
            "",
        ).strip()
        or DEFAULT_MODEL
    )


def _mime_type(
    path: Path,
) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(
        path.suffix.lower(),
        "application/octet-stream",
    )


def _clean_tag(
    value: str,
) -> str:
    tag = " ".join(
        (value or "").strip().split()
    )

    tag = tag.strip(
        "`\"'.,:;!?- "
    )

    if tag.lower().startswith("tag:"):
        tag = tag[4:].strip()

    # Remove accidental markdown/list prefixes.
    tag = tag.lstrip(
        "0123456789.)- "
    ).strip()

    return tag


def _generate_once(
    client: genai.Client,
    image_bytes: bytes,
    mime_type: str,
    instruction: str,
) -> str:
    response = client.models.generate_content(
        model=_get_model(),
        contents=[
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            ),
            instruction,
        ],
    )

    return _clean_tag(
        getattr(
            response,
            "text",
            "",
        )
    )


def generate_tag(
    image_path: Path,
) -> str:

    image_path = Path(
        image_path
    )

    if (
        not image_path.exists()
        or not image_path.is_file()
    ):
        raise FileNotFoundError(
            f"Image not found: {image_path.name}"
        )

    image_bytes = (
        image_path.read_bytes()
    )

    if not image_bytes:
        raise ValueError(
            f"Image is empty: {image_path.name}"
        )

    mime_type = _mime_type(
        image_path
    )

    if not mime_type.startswith("image/"):
        raise ValueError(
            f"Unsupported image type: {image_path.name}"
        )

    client = genai.Client(
        api_key=_get_api_key()
    )

    instruction = """
Analyze the actual visual content of this image.

Return exactly ONE semantic tag describing what the image visibly represents.

Rules:
- Exactly 3 to 5 words.
- Title Case.
- Describe the actual visual content.
- Do not use the filename as evidence.
- Be specific and meaningful.
- Identify the visible subject, technology, topic, system, campaign,
  dashboard, architecture, course subject, or other meaningful visual
  concept when it is clearly visible.
- Do not invent information.
- Avoid generic tags such as:
  Image
  Screenshot
  Diagram
  Architecture
  Technology
  Training
  Course
  Marketing
  Drive
  Programming
  Content
- Return only the tag.
- No explanation.
- No numbering.
- No bullets.
- No quotes.
- No punctuation.
- No markdown.
"""

    try:
        tag = _generate_once(
            client,
            image_bytes,
            mime_type,
            instruction,
        )
    except Exception as exc:
        raise RuntimeError(
            "Gemini image tagging failed for "
            f"'{image_path.name}': {exc}"
        ) from exc

    words = tag.split()

    # If Gemini returned a longer phrase, keep the first five semantic
    # words rather than failing the complete reference list.
    if len(words) > 5:
        tag = " ".join(
            words[:5]
        )
        words = tag.split()

    if len(words) < 3:
        # One strict retry can recover occasional very short responses.
        retry_instruction = """
Analyze this image again.

Return ONE and ONLY ONE semantic tag.
The tag MUST contain exactly 3 to 5 words.
Use Title Case.
Describe what is visibly represented in the image.
Do not use the filename.
Do not invent information.
Do not use generic words like Image, Screenshot, Diagram, Technology,
Training, Course, Marketing, Architecture, Programming, or Content.
Return only the 3-5 word tag, with no punctuation or explanation.
"""

        try:
            tag = _generate_once(
                client,
                image_bytes,
                mime_type,
                retry_instruction,
            )
        except Exception as exc:
            raise RuntimeError(
                "Gemini image tagging failed during retry for "
                f"'{image_path.name}': {exc}"
            ) from exc

        words = tag.split()

        if len(words) > 5:
            tag = " ".join(
                words[:5]
            )
            words = tag.split()

    if len(words) < 3:
        raise RuntimeError(
            "Gemini returned an invalid tag for "
            f"'{image_path.name}': {tag or '[empty response]'}"
        )

    return tag


def load_tag_metadata(
    metadata_file: Path,
) -> dict:

    metadata_file = Path(
        metadata_file
    )

    if not metadata_file.exists():
        return {}

    try:
        payload = json.loads(
            metadata_file.read_text(
                encoding="utf-8"
            )
        )

        return (
            payload
            if isinstance(
                payload,
                dict,
            )
            else {}
        )

    except Exception:
        return {}


def save_tag_metadata(
    metadata_file: Path,
    metadata: dict,
) -> None:

    metadata_file = Path(
        metadata_file
    )

    metadata_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata_file.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def generate_and_cache_tag(
    image_path: Path,
    metadata_file: Path,
    cache_key: str | None = None,
) -> str:

    image_path = Path(
        image_path
    )

    key = (
        cache_key
        or image_path.name
    )

    metadata = load_tag_metadata(
        metadata_file
    )

    cached = metadata.get(
        key
    )

    if (
        isinstance(
            cached,
            dict,
        )
        and cached.get("tag")
    ):
        return str(
            cached["tag"]
        )

    if (
        isinstance(
            cached,
            str,
        )
        and cached.strip()
    ):
        return cached.strip()

    tag = generate_tag(
        image_path
    )

    metadata[key] = {
        "tag":
            tag,
        "filename":
            image_path.name,
    }

    save_tag_metadata(
        metadata_file,
        metadata,
    )

    return tag