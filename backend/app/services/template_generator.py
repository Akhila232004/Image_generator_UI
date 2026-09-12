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


# -------------------------------------------------------------------
# URL validation
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


# -------------------------------------------------------------------
# YouTube helpers
# -------------------------------------------------------------------

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
# External reference download
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
# GIF preparation
# -------------------------------------------------------------------

def prepare_image_bytes(
    data: bytes,
    filename: str,
    content_type: str = "",
) -> bytes:

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

        return data


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
                output.getvalue()
            )


    except Exception as exc:

        raise ValueError(
            "Unable to read the GIF reference: "
            f"{exc}"
        ) from exc


# -------------------------------------------------------------------
# Automatic template generation from URL
# -------------------------------------------------------------------

def generate_template_from_url(
    url: str,
    uploads_dir: Path,
    filename: str = "reference",
    content_type: str = "",
    is_youtube: bool = False,
):
    """
    Download an external image or YouTube thumbnail and use it as
    the source for automatic template generation.

    Template generation intentionally does not use a content prompt.
    The content prompt is handled separately by the prompt-generation
    stage.
    """

    url = url.strip()


    if not is_valid_http_url(
        url
    ):

        raise ValueError(
            "A valid HTTP or HTTPS URL is required."
        )


    uploads_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    # ---------------------------------------------------------------
    # Resolve YouTube URL to thumbnail when required.
    # ---------------------------------------------------------------

    target_url = (
        youtube_thumbnail_url(
            url
        )
        if is_youtube
        else url
    )


    # ---------------------------------------------------------------
    # Download reference.
    # ---------------------------------------------------------------

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
    )


    # ---------------------------------------------------------------
    # Convert GIF to first frame.
    # ---------------------------------------------------------------

    prepared = (
        prepare_image_bytes(
            data,
            source_filename,
            detected_type,
        )
    )


    extension = (
        Path(source_filename)
        .suffix
        .lower()
    )


    # ---------------------------------------------------------------
    # Choose safe local filename.
    # ---------------------------------------------------------------

    if (
        extension == ".gif"
        or detected_type ==
            "image/gif"
    ):

        save_name = (
            f"{Path(filename).stem or 'reference'}"
            "_frame.png"
        )


    else:

        save_name = (
            Path(filename).name
            or "reference.png"
        )


        if (
            Path(save_name)
            .suffix
            .lower()
            not in IMAGE_EXTENSIONS
        ):

            save_name = (
                f"{Path(save_name).stem or 'reference'}"
                ".png"
            )


    reference_path = (
        uploads_dir
        / save_name
    )


    # ---------------------------------------------------------------
    # Save prepared image.
    # ---------------------------------------------------------------

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