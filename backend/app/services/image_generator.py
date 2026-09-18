import json
import os

from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.1-flash-image"


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. "
            "Upload the API key file and select Gemini API."
        )

    return genai.Client(
        api_key=api_key
    )


def _get_mime_type(
    filename: str,
    content_type: str | None = None,
) -> str:

    if (
        content_type
        and content_type.startswith("image/")
    ):
        return content_type

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }

    mime_type = mime_types.get(extension)

    if not mime_type:
        raise ValueError(
            "Unsupported reference image format. "
            "Use PNG, JPG, JPEG, WEBP or GIF."
        )

    return mime_type


def _build_generation_prompt(
    user_prompt: str,
    template: dict,
) -> str:

    template_json = json.dumps(
        template,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
Create a new output image by editing or recreating
the supplied reference image.

The supplied reference image is the primary visual
source.

Preserve the reference image's overall composition,
proportions, visual hierarchy, layout, color
relationships, spacing, and visual style unless the
user's content prompt explicitly requests a change.

The generated template below is the structural
description of the reference image.

Use the template as additional layout guidance
together with the actual reference image.

Do not render the JSON template itself inside the
generated image.

GENERATED TEMPLATE:

{template_json}

USER CONTENT PROMPT:

{user_prompt}

GENERATION RULES:

- Apply the user's requested changes to the
  reference-based design.

- Keep the reference layout and visual identity
  wherever the prompt does not request a change.

- Replace, add, remove, or modify content only as
  requested by the user.

- Preserve the relative placement and hierarchy
  of major visual regions.

- Maintain the reference's professional visual
  style, colors, typography feel, shapes,
  spacing, and background treatment unless the
  prompt explicitly changes them.

- If the prompt asks for text, render the requested
  text clearly and legibly.

- Do not invent unrelated content.

- The output must be a finished image.

- Return the generated image only.
""".strip()


def generate_output_image(
    reference_bytes: bytes,
    filename: str,
    content_type: str | None,
    user_prompt: str,
    template: dict,
) -> tuple[
    bytes,
    str,
    str,
]:

    if not reference_bytes:
        raise ValueError(
            "The selected reference image is empty."
        )

    prompt = user_prompt.strip()

    if not prompt:
        raise ValueError(
            "Content prompt is required."
        )

    mime_type = _get_mime_type(
        filename,
        content_type,
    )

    model = (
        os.getenv(
            "GEMINI_IMAGE_MODEL",
            DEFAULT_MODEL,
        )
        .strip()
        or DEFAULT_MODEL
    )

    client = _get_client()

    generation_prompt = _build_generation_prompt(
        prompt,
        template,
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(
                    data=reference_bytes,
                    mime_type=mime_type,
                ),
                generation_prompt,
            ],
            config=types.GenerateContentConfig(
                response_modalities=[
                    "IMAGE"
                ],
            ),
        )

    except Exception as exc:
        raise RuntimeError(
            f"Gemini image generation failed: {exc}"
        ) from exc

    for part in response.parts or []:

        inline_data = getattr(
            part,
            "inline_data",
            None,
        )

        if inline_data is None:
            continue

        # ---------------------------------------------------------
        # Preferred method:
        # Gemini returns the actual image bytes through inline_data.
        # ---------------------------------------------------------

        raw_data = getattr(
            inline_data,
            "data",
            None,
        )

        if raw_data:
            return (
                bytes(raw_data),
                "image/png",
                model,
            )

        # ---------------------------------------------------------
        # Fallback:
        # If the SDK exposes a PIL-compatible image, convert it
        # using PIL rather than calling the SDK image wrapper's
        # save(format=...) method.
        # ---------------------------------------------------------

        try:
            image = part.as_image()
        except Exception:
            image = None

        if image is None:
            continue

        try:
            from PIL import Image

            output = BytesIO()

            pil_image = Image.fromarray(
                image
            )

            pil_image.save(
                output,
                format="PNG",
            )

            data = output.getvalue()

            if data:
                return (
                    data,
                    "image/png",
                    model,
                )

        except Exception as exc:
            raise RuntimeError(
                "Gemini returned image data that "
                "could not be converted to PNG: "
                f"{exc}"
            ) from exc

    raise RuntimeError(
        "Gemini did not return an output image."
    )