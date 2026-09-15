import io

from pathlib import Path

from urllib.parse import (
    parse_qs,
    urlparse,
)

from urllib.request import (
    Request,
    urlopen,
)

from PIL import Image

from .template_builder import (
    generate_template,
)


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}


MAX_REFERENCE_SIZE = 25 * 1024 * 1024


# -------------------------------------------------------------------
# URL validation
# -------------------------------------------------------------------

def is_valid_http_url(
    value: str,
) -> bool:
    """
    Return True only for a normal HTTP/HTTPS URL.

    Browser-only URLs such as blob:http://... are intentionally rejected
    here because a FastAPI backend cannot access a browser blob URL.
    """
    try:
        parsed = urlparse(value.strip())

        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
        )

    except Exception:
        return False


# -------------------------------------------------------------------
# YouTube helpers
# -------------------------------------------------------------------

def extract_youtube_video_id(
    url: str,
) -> str | None:
    parsed = urlparse(url)

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
        query = parse_qs(parsed.query)

        if query.get("v"):
            return query["v"][0]

        parts = [
            part
            for part in parsed.path.split("/")
            if part
        ]

        if (
            len(parts) >= 2
            and parts[0] in {
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
    video_id = extract_youtube_video_id(url)

    if not video_id:
        raise ValueError(
            "Unable to extract the YouTube video ID from the URL."
        )

    return (
        "https://i.ytimg.com/vi/"
        f"{video_id}/hqdefault.jpg"
    )


# -------------------------------------------------------------------
# Content validation
# -------------------------------------------------------------------

def validate_image_bytes(
    data: bytes,
    filename: str = "reference",
) -> tuple[bytes, str]:
    """
    Validate that data contains an actual readable image.

    Returns:
        (data, detected_format)

    This prevents HTML/JSON responses from external URLs or Drive from
    being passed into template_builder as if they were images.
    """
    if not data:
        raise ValueError(
            "The reference returned an empty response."
        )

    if len(data) > MAX_REFERENCE_SIZE:
        raise ValueError(
            "The reference is larger than the 25 MB limit."
        )

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()

        with Image.open(io.BytesIO(data)) as image:
            image_format = (
                image.format or ""
            ).lower()

        return data, image_format

    except Exception as exc:
        raise ValueError(
            "The reference does not contain a valid readable image "
            f"({filename})."
        ) from exc


# -------------------------------------------------------------------
# External reference download
# -------------------------------------------------------------------

def download_url(
    url: str,
) -> tuple[bytes, str]:
    """
    Download an external HTTP/HTTPS image.

    The response is validated before it is returned. This means an HTML
    page, JSON error, or other non-image response cannot accidentally be
    saved as a PNG/JPG reference.
    """
    if not is_valid_http_url(url):
        raise ValueError(
            "A valid HTTP or HTTPS URL is required."
        )

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": (
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
            data = response.read()

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

    if len(data) > MAX_REFERENCE_SIZE:
        raise ValueError(
            "The reference is larger than the 25 MB limit."
        )

    # Validate the actual bytes rather than trusting Content-Type.
    validate_image_bytes(
        data,
        filename=Path(
            urlparse(url).path
        ).name or "external-reference",
    )

    return (
        data,
        content_type,
    )


# -------------------------------------------------------------------
# Local uploaded-reference helpers
# -------------------------------------------------------------------

def read_local_reference(
    reference_path: Path,
) -> tuple[bytes, str]:
    """
    Read and validate an image that was uploaded to the backend.

    This is the path used for manual image/GIF uploads.
    """
    reference_path = Path(reference_path)

    if not reference_path.exists():
        raise FileNotFoundError(
            f"Reference file was not found: {reference_path}"
        )

    if not reference_path.is_file():
        raise ValueError(
            f"Reference path is not a file: {reference_path}"
        )

    if reference_path.stat().st_size > MAX_REFERENCE_SIZE:
        raise ValueError(
            "The reference is larger than the 25 MB limit."
        )

    data = reference_path.read_bytes()

    validate_image_bytes(
        data,
        filename=reference_path.name,
    )

    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(
        reference_path.suffix.lower(),
        "",
    )

    return (
        data,
        content_type,
    )


# -------------------------------------------------------------------
# GIF preparation
# -------------------------------------------------------------------

def prepare_image_bytes(
    data: bytes,
    filename: str,
    content_type: str = "",
) -> bytes:
    """
    Convert a GIF reference to its first frame as PNG.

    Static PNG/JPG/WEBP references are preserved as their original bytes.
    """
    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    is_gif = (
        extension == ".gif"
        or content_type.lower() == "image/gif"
    )

    if not is_gif:
        return data

    try:
        with Image.open(
            io.BytesIO(data)
        ) as image:
            image.seek(0)

            frame = image.convert("RGB")

            output = io.BytesIO()

            frame.save(
                output,
                format="PNG",
            )

            return output.getvalue()

    except Exception as exc:
        raise ValueError(
            "Unable to read the GIF reference: "
            f"{exc}"
        ) from exc


# -------------------------------------------------------------------
# Safe local filename
# -------------------------------------------------------------------

def build_save_name(
    filename: str,
    content_type: str = "",
) -> str:
    """
    Create a safe image filename for the generated local reference.
    """
    original_name = (
        Path(filename).name
        or "reference"
    )

    extension = (
        Path(original_name)
        .suffix
        .lower()
    )

    if (
        extension == ".gif"
        or content_type.lower() == "image/gif"
    ):
        return (
            f"{Path(original_name).stem or 'reference'}"
            "_frame.png"
        )

    if extension not in IMAGE_EXTENSIONS:
        return (
            f"{Path(original_name).stem or 'reference'}"
            ".png"
        )

    return original_name


# -------------------------------------------------------------------
# Generate template from local file
# -------------------------------------------------------------------

def generate_template_from_file(
    reference_path: Path,
    uploads_dir: Path | None = None,
    filename: str = "",
    content_type: str = "",
):
    """
    Generate a template from a local image file.

    This supports:
      - manually uploaded PNG/JPG/JPEG/WEBP
      - manually uploaded GIF
      - Google Drive images after the backend downloads them locally

    No content prompt is used for template generation.
    """
    reference_path = Path(reference_path)

    data, detected_content_type = read_local_reference(
        reference_path
    )

    effective_content_type = (
        detected_content_type
        or content_type
        or ""
    )

    source_filename = (
        filename
        or reference_path.name
    )

    prepared = prepare_image_bytes(
        data,
        source_filename,
        effective_content_type,
    )

    if uploads_dir is None:
        uploads_dir = reference_path.parent

    uploads_dir = Path(uploads_dir)

    uploads_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    save_name = build_save_name(
        source_filename,
        effective_content_type,
    )

    output_path = (
        uploads_dir
        / save_name
    )

    output_path.write_bytes(
        prepared
    )

    return generate_template(
        reference_path=output_path,
        prompt="",
    )


# -------------------------------------------------------------------
# Generate template from raw bytes
# -------------------------------------------------------------------

def generate_template_from_bytes(
    data: bytes,
    uploads_dir: Path,
    filename: str = "reference.png",
    content_type: str = "",
):
    """
    Generate a template directly from image bytes.

    This is useful for Google Drive media when the main API already has
    the downloaded bytes and does not need another HTTP request.
    """
    uploads_dir = Path(uploads_dir)

    uploads_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    validate_image_bytes(
        data,
        filename=filename,
    )

    prepared = prepare_image_bytes(
        data,
        filename,
        content_type,
    )

    save_name = build_save_name(
        filename,
        content_type,
    )

    reference_path = (
        uploads_dir
        / save_name
    )

    reference_path.write_bytes(
        prepared
    )

    return generate_template(
        reference_path=reference_path,
        prompt="",
    )


# -------------------------------------------------------------------
# Automatic template generation from external URL
# -------------------------------------------------------------------

def generate_template_from_url(
    url: str,
    uploads_dir: Path,
    filename: str = "reference",
    content_type: str = "",
    is_youtube: bool = False,
):
    """
    Generate a template from an external image URL or YouTube URL.

    Supported:
      - HTTP/HTTPS image URLs
      - YouTube watch URLs
      - YouTube Shorts URLs
      - YouTube embed URLs
      - YouTube live URLs
      - youtu.be URLs

    Important:
      Browser blob: URLs are NOT supported here. A blob URL exists only
      inside the browser and cannot be downloaded by FastAPI.
    """
    url = url.strip()

    if not is_valid_http_url(url):
        raise ValueError(
            "A valid HTTP or HTTPS URL is required."
        )

    uploads_dir = Path(uploads_dir)

    uploads_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------------
    # Resolve YouTube URL to thumbnail.
    # ---------------------------------------------------------------

    target_url = (
        youtube_thumbnail_url(url)
        if is_youtube
        else url
    )

    # ---------------------------------------------------------------
    # Download external image.
    # ---------------------------------------------------------------

    data, detected_content_type = download_url(
        target_url
    )

    effective_content_type = (
        detected_content_type
        or content_type
        or ""
    )

    # ---------------------------------------------------------------
    # Determine source filename.
    # ---------------------------------------------------------------

    source_filename = (
        Path(
            urlparse(
                target_url
            ).path
        ).name
        or filename
        or "reference.png"
    )

    # YouTube thumbnails normally have .jpg.
    if (
        not Path(source_filename).suffix
        and effective_content_type == "image/jpeg"
    ):
        source_filename = (
            f"{source_filename}.jpg"
        )

    # ---------------------------------------------------------------
    # Validate and prepare image.
    # ---------------------------------------------------------------

    validate_image_bytes(
        data,
        filename=source_filename,
    )

    prepared = prepare_image_bytes(
        data,
        source_filename,
        effective_content_type,
    )

    # ---------------------------------------------------------------
    # Save prepared reference.
    # ---------------------------------------------------------------

    save_name = build_save_name(
        filename or source_filename,
        effective_content_type,
    )

    reference_path = (
        uploads_dir
        / save_name
    )

    reference_path.write_bytes(
        prepared
    )

    # ---------------------------------------------------------------
    # Generate template without content prompt.
    # ---------------------------------------------------------------

    return generate_template(
        reference_path=reference_path,
        prompt="",
    )


# -------------------------------------------------------------------
# Generic reference entry point
# -------------------------------------------------------------------

def generate_template_from_reference(
    source_type: str,
    source,
    uploads_dir: Path,
    filename: str = "reference",
    content_type: str = "",
    is_youtube: bool = False,
):
    """
    Single entry point for the application's reference flow.

    source_type:
      - "upload"
      - "manual-upload"
      - "google-drive"
      - "input-folder"
      - "external-url"
      - "youtube"

    source:
      - local Path/string for uploaded or already-downloaded Drive files
      - bytes for already-downloaded Drive media
      - HTTP/HTTPS URL for external references

    Google Drive:
      The preferred integration is for main.py to download the Drive
      file using its authenticated Google Drive service and pass either
      the resulting local Path or raw bytes here.

    Template generation itself remains independent of the content prompt.
    """
    normalized_source_type = (
        str(source_type or "")
        .strip()
        .lower()
    )

    # ---------------------------------------------------------------
    # Local upload / local file / input-folder reference.
    # ---------------------------------------------------------------

    if normalized_source_type in {
        "upload",
        "manual-upload",
        "input-folder",
        "local",
    }:
        return generate_template_from_file(
            reference_path=Path(str(source)),
            uploads_dir=uploads_dir,
            filename=filename,
            content_type=content_type,
        )

    # ---------------------------------------------------------------
    # Google Drive.
    #
    # Main.py should pass the already downloaded Drive file path or
    # bytes. A browser blob URL must never be passed as `source`.
    # ---------------------------------------------------------------

    if normalized_source_type == "google-drive":
        if isinstance(source, (bytes, bytearray)):
            return generate_template_from_bytes(
                data=bytes(source),
                uploads_dir=uploads_dir,
                filename=filename,
                content_type=content_type,
            )

        source_path = Path(str(source))

        return generate_template_from_file(
            reference_path=source_path,
            uploads_dir=uploads_dir,
            filename=filename,
            content_type=content_type,
        )

    # ---------------------------------------------------------------
    # External URL / YouTube.
    # ---------------------------------------------------------------

    if normalized_source_type in {
        "external-url",
        "youtube",
        "url",
    }:
        url = str(source).strip()

        youtube = (
            is_youtube
            or normalized_source_type == "youtube"
        )

        return generate_template_from_url(
            url=url,
            uploads_dir=uploads_dir,
            filename=filename,
            content_type=content_type,
            is_youtube=youtube,
        )

    raise ValueError(
        "Unsupported reference source type: "
        f"{source_type}"
    )
