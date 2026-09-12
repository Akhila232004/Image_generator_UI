import io
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from PIL import Image
from google import genai
from google.genai import types


# -------------------------------------------------------------------
# Environment
# -------------------------------------------------------------------

SERVICE_DIR = Path(__file__).resolve().parent
APP_DIR = SERVICE_DIR.parent
BACKEND_DIR = APP_DIR.parent

load_dotenv(BACKEND_DIR / ".env")
load_dotenv()


GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "",
).strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
).strip()


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}


# -------------------------------------------------------------------
# URL helpers
# -------------------------------------------------------------------

def is_valid_http_url(
    value: str,
) -> bool:

    try:

        parsed = urlparse(
            value.strip()
        )

        return (
            parsed.scheme
            in {
                "http",
                "https",
            }
            and bool(
                parsed.netloc
            )
        )

    except Exception:
        return False


def extract_youtube_video_id(
    url: str,
) -> str | None:

    parsed = urlparse(
        url
    )

    hostname = (
        parsed.hostname or ""
    ).lower()

    if hostname in {
        "youtu.be",
        "www.youtu.be",
    }:

        return (
            parsed.path
            .strip("/")
            .split("/")[0]
            or None
        )


    if "youtube.com" in hostname:

        query = parse_qs(
            parsed.query
        )

        if query.get("v"):

            return query["v"][0]


        parts = [
            part
            for part
            in parsed.path.split("/")
            if part
        ]


        if (
            len(parts) >= 2
            and parts[0]
            in {
                "shorts",
                "embed",
                "live",
            }
        ):

            return parts[1]


    return None


def youtube_thumbnail_url(
    url: str,
) -> str:

    video_id = (
        extract_youtube_video_id(
            url
        )
    )

    if not video_id:

        raise ValueError(
            "Unable to extract the YouTube video ID from the URL."
        )


    return (
        "https://i.ytimg.com/vi/"
        f"{video_id}/hqdefault.jpg"
    )


# -------------------------------------------------------------------
# Download helpers
# -------------------------------------------------------------------

def download_url(
    url: str,
) -> tuple[bytes, str]:

    request = Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0",

            "Accept":
                (
                    "image/avif,"
                    "image/webp,"
                    "image/apng,"
                    "image/*,"
                    "*/*;q=0.8"
                ),
        },
    )


    try:

        with urlopen(
            request,
            timeout=30,
        ) as response:

            data = (
                response.read()
            )

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    "",
                )
                .split(";")[0]
                .strip()
                .lower()
            )


    except Exception as exc:

        raise RuntimeError(
            "Unable to download reference URL: "
            f"{exc}"
        ) from exc


    if not data:

        raise ValueError(
            "The reference URL returned an empty response."
        )


    if (
        len(data)
        > 25 * 1024 * 1024
    ):

        raise ValueError(
            "The reference is larger than the 25 MB limit."
        )


    return (
        data,
        content_type,
    )


# -------------------------------------------------------------------
# Image preparation
# -------------------------------------------------------------------

def _mime_type_from_extension(
    extension: str,
) -> str:

    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }


    return mapping.get(
        extension.lower(),
        "image/png",
    )


def prepare_image_bytes(
    data: bytes,
    filename: str,
    content_type: str = "",
) -> tuple[bytes, str]:

    extension = (
        Path(filename)
        .suffix
        .lower()
    )


    is_gif = (
        extension == ".gif"
        or content_type ==
            "image/gif"
    )


    if not is_gif:

        return (
            data,
            content_type
            or _mime_type_from_extension(
                extension
            ),
        )


    try:

        with Image.open(
            io.BytesIO(data)
        ) as image:

            image.seek(0)

            frame = (
                image.convert(
                    "RGB"
                )
            )

            output = (
                io.BytesIO()
            )

            frame.save(
                output,
                format="PNG",
            )

            return (
                output.getvalue(),
                "image/png",
            )


    except Exception as exc:

        raise ValueError(
            "Unable to read the GIF reference: "
            f"{exc}"
        ) from exc


# -------------------------------------------------------------------
# Local reference loading
# -------------------------------------------------------------------

def load_local_image(
    image_path: Path,
) -> tuple[bytes, str]:

    if not image_path.exists():

        raise FileNotFoundError(
            f"Reference image not found: {image_path}"
        )


    if not image_path.is_file():

        raise ValueError(
            "The reference path is not a file."
        )


    if (
        image_path.suffix.lower()
        not in IMAGE_EXTENSIONS
    ):

        raise ValueError(
            "AI prompt generation supports images and GIFs only."
        )


    try:

        data = (
            image_path.read_bytes()
        )


    except Exception as exc:

        raise RuntimeError(
            "Unable to read the reference image: "
            f"{exc}"
        ) from exc


    if not data:

        raise ValueError(
            "The reference image is empty."
        )


    if (
        len(data)
        > 25 * 1024 * 1024
    ):

        raise ValueError(
            "The reference is larger than the 25 MB limit."
        )


    return prepare_image_bytes(
        data,
        image_path.name,
        _mime_type_from_extension(
            image_path.suffix
        ),
    )


# -------------------------------------------------------------------
# Generic reference loading
# -------------------------------------------------------------------

def load_reference(
    image_path: Path | None = None,
    image_url: str | None = None,
    filename: str = "reference",
    content_type: str | None = None,
    is_youtube: bool = False,
) -> tuple[bytes, str]:

    if image_path is not None:

        return load_local_image(
            image_path
        )


    url = (
        image_url or ""
    ).strip()


    if not url:

        raise ValueError(
            "A local image path or image URL is required."
        )


    if not is_valid_http_url(
        url
    ):

        raise ValueError(
            "A valid HTTP or HTTPS URL is required."
        )


    target_url = (
        youtube_thumbnail_url(
            url
        )
        if is_youtube
        else url
    )


    data, detected_content_type = (
        download_url(
            target_url
        )
    )


    detected_type = (
        detected_content_type
        or content_type
        or ""
    )


    source_filename = (
        Path(
            urlparse(
                target_url
            ).path
        ).name
        or filename
    )


    return prepare_image_bytes(
        data,
        source_filename,
        detected_type,
    )


# -------------------------------------------------------------------
# Gemini client
# -------------------------------------------------------------------

def _get_client() -> genai.Client:

    if not GEMINI_API_KEY:

        raise ValueError(
            "GEMINI_API_KEY is not configured in backend/.env."
        )


    return genai.Client(
        api_key=GEMINI_API_KEY
    )


# -------------------------------------------------------------------
# Gemini prompt
# -------------------------------------------------------------------

def _build_prompt() -> str:

    return """
Analyze the supplied reference image carefully and write one
high-quality image-generation prompt that recreates the visual
composition while allowing the requested content to be generated.

Inspect the actual image. Do not infer the visual design from the
filename.

Describe only what is visibly supported by the reference, including
when applicable:

- canvas orientation and composition
- background treatment
- main visual placement
- major objects, diagrams, icons, illustrations or UI elements
- text placement and hierarchy when text is visibly present
- spacing, alignment and relative proportions
- colors and contrast
- typography style when visually apparent
- borders, cards, connectors, shadows and other structural elements
- overall visual style

The prompt must be useful for an image-generation system.

Do not invent facts, brands, people, technologies or text that are not
visibly supported by the reference.

Return only the final prompt as plain text.

Do not add a title, explanation, quotation marks, bullets or markdown.
""".strip()


# -------------------------------------------------------------------
# Gemini generation
# -------------------------------------------------------------------

def _generate_with_gemini(
    image_bytes: bytes,
    mime_type: str,
) -> str:

    client = _get_client()


    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=(
                    mime_type
                    or "image/png"
                ),
            ),
            _build_prompt(),
        ],
    )


    text = (
        getattr(
            response,
            "text",
            None,
        )
        or ""
    ).strip()


    if not text:

        raise RuntimeError(
            "Gemini returned an empty image prompt."
        )


    return text


# -------------------------------------------------------------------
# Public function
# -------------------------------------------------------------------

def generate_image_prompt(
    image_path: Path | str | None = None,
    image_url: str | None = None,
    filename: str = "reference",
    content_type: str | None = None,
    is_youtube: bool = False,
) -> str:
    """
    Generate an image-generation prompt from the actual reference.

    Supports:

    1. Backend/input local images
    2. Local GIF files
    3. External image URLs
    4. YouTube URLs

    The function accepts both image_path and image_url because
    backend/app/main.py uses image_path for local references and
    image_url for external references.
    """

    local_path = (
        Path(image_path)
        if image_path is not None
        else None
    )


    image_bytes, mime_type = (
        load_reference(
            image_path=local_path,
            image_url=image_url,
            filename=filename,
            content_type=content_type,
            is_youtube=is_youtube,
        )
    )


    return _generate_with_gemini(
        image_bytes=image_bytes,
        mime_type=mime_type,
    )