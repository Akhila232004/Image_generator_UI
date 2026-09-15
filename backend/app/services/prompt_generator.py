from __future__ import annotations

import os
from pathlib import Path
from urllib.request import Request, urlopen

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.5-flash-lite"


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv(
        "GOOGLE_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "Gemini API is not configured. "
            "Upload your API configuration file and select Gemini API first."
        )

    return genai.Client(
        api_key=api_key
    )


def _get_model() -> str:
    return (
        os.getenv("GEMINI_MODEL")
        or DEFAULT_MODEL
    ).strip()


def _mime_type_from_path(
    path: Path,
) -> str:
    extension = path.suffix.lower()

    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }

    return mapping.get(
        extension,
        "application/octet-stream",
    )


def _download_image(
    image_url: str,
) -> tuple[bytes, str]:
    request = Request(
        image_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64)"
            )
        },
    )

    with urlopen(
        request,
        timeout=60,
    ) as response:
        data = response.read()

        content_type = (
            response.headers.get(
                "Content-Type",
                "image/jpeg",
            )
        )

    if not data:
        raise RuntimeError(
            "The reference URL returned an empty response."
        )

    return data, content_type


def generate_image_prompt(
    image_path: Path | None = None,
    image_url: str | None = None,
    filename: str = "reference",
    content_type: str | None = None,
    is_youtube: bool = False,
) -> str:

    if is_youtube:
        raise ValueError(
            "AI prompt generation for YouTube references "
            "is not supported yet."
        )

    if image_path is not None:
        image_path = Path(
            image_path
        )

        if not image_path.exists():
            raise FileNotFoundError(
                f"Reference image not found: {image_path}"
            )

        image_bytes = image_path.read_bytes()

        mime_type = (
            content_type
            or _mime_type_from_path(
                image_path
            )
        )

    elif image_url:
        image_bytes, downloaded_type = (
            _download_image(
                image_url
            )
        )

        mime_type = (
            content_type
            or downloaded_type
        )

    else:
        raise ValueError(
            "A reference image path or URL is required."
        )

    client = _get_client()
    model = _get_model()

    prompt = """
Analyze the supplied reference image.

Create a reusable image-generation prompt that describes
the visual design of the reference.

Focus on:
- Overall composition
- Layout
- Subject placement
- Background
- Colors
- Typography
- Visual hierarchy
- Spacing
- Shapes
- Decorative elements
- Style
- Lighting
- Important visible text or labels

Do not invent information that cannot be seen.

Return only the reusable prompt.
Do not provide explanations.
"""

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            ),
            prompt,
        ],
    )

    result = (
        response.text
        if response
        else ""
    )

    result = result.strip()

    if not result:
        raise RuntimeError(
            "Gemini returned an empty prompt."
        )

    return result