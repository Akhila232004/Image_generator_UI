from pathlib import Path

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from fastapi.responses import (
    FileResponse,
)

from app.services.image_tagger import (
    generate_and_cache_tag,
    load_tag_metadata,
)

from app.services.template_builder import (
    generate_template,
)

from app.services.template_generator import (
    generate_template_from_url,
)

from app.services.prompt_generator import (
    generate_image_prompt,
)


# -------------------------------------------------------------------
# Application
# -------------------------------------------------------------------

app = FastAPI(
    title="Image Generator API",
    version="1.0.0",
)


# -------------------------------------------------------------------
# Directories
# -------------------------------------------------------------------

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

INPUT_DIR = (
    BASE_DIR /
    "input"
)

UPLOADS_DIR = (
    BASE_DIR /
    "uploads"
)

TEMPLATES_DIR = (
    BASE_DIR /
    "templates"
)

METADATA_FILE = (
    BASE_DIR /
    "input_metadata.json"
)


INPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

UPLOADS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TEMPLATES_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# -------------------------------------------------------------------
# CORS
# -------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# Supported files
# -------------------------------------------------------------------

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}

PDF_EXTENSIONS = {
    ".pdf",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mov",
}


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def get_file_type(
    path: Path,
) -> str:

    extension = (
        path.suffix.lower()
    )

    if extension in IMAGE_EXTENSIONS:

        if extension == ".gif":
            return "gif"

        return "image"

    if extension in PDF_EXTENSIONS:
        return "pdf"

    if extension in VIDEO_EXTENSIONS:
        return "video"

    return "unknown"


def get_mime_type(
    path: Path,
) -> str:

    extension = (
        path.suffix.lower()
    )

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
    }

    return mime_types.get(
        extension,
        "application/octet-stream",
    )


def format_file_size(
    size: int,
) -> str:

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return (
            f"{size / 1024:.1f} KB"
        )

    if size < (
        1024 * 1024 * 1024
    ):
        return (
            f"{size / (1024 * 1024):.1f} MB"
        )

    return (
        f"{size / (1024 * 1024 * 1024):.1f} GB"
    )


def is_valid_http_url(
    value: str,
) -> bool:

    from urllib.parse import (
        urlparse,
    )

    try:

        parsed = urlparse(
            value
        )

        return (
            parsed.scheme
            in {"http", "https"}
            and bool(parsed.netloc)
        )

    except Exception:
        return False


# -------------------------------------------------------------------
# Input files
# -------------------------------------------------------------------

def get_input_files() -> list[dict]:

    files = []

    metadata = load_tag_metadata(
        METADATA_FILE
    )

    supported_extensions = (
        IMAGE_EXTENSIONS
        | PDF_EXTENSIONS
        | VIDEO_EXTENSIONS
    )

    for path in sorted(
        INPUT_DIR.iterdir(),
        key=lambda item:
        item.name.lower(),
    ):

        if not path.is_file():
            continue

        if (
            path.suffix.lower()
            not in supported_extensions
        ):
            continue

        file_type = get_file_type(
            path
        )

        file_data = {
            "id": path.name,
            "name": path.name,
            "type": file_type,
            "mimeType":
                get_mime_type(path),
            "size":
                path.stat().st_size,
            "sizeFormatted":
                format_file_size(
                    path.stat().st_size
                ),
            "url":
                f"/api/inputs/file/{path.name}",
        }

        cached_item = metadata.get(
            path.name
        )

        if (
            isinstance(
                cached_item,
                dict,
            )
            and cached_item.get("tag")
        ):

            file_data["tag"] = str(
                cached_item["tag"]
            )

        files.append(
            file_data
        )

    return files


# -------------------------------------------------------------------
# Health check
# -------------------------------------------------------------------

@app.get("/")
def root():

    return {
        "message":
            "Image Generator API is running"
    }


@app.get("/api/health")
def health():

    return {
        "status": "ok"
    }


# -------------------------------------------------------------------
# Get input files
# -------------------------------------------------------------------

@app.get("/api/inputs")
def get_inputs():

    return get_input_files()


# -------------------------------------------------------------------
# Serve input file
# -------------------------------------------------------------------

@app.get(
    "/api/inputs/file/{filename:path}"
)
def get_input_file(
    filename: str,
):

    file_path = (
        INPUT_DIR /
        filename
    )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Input file not found.",
        )

    if not file_path.is_file():

        raise HTTPException(
            status_code=404,
            detail="Input file not found.",
        )

    return FileResponse(
        file_path,
        media_type=
            get_mime_type(
                file_path
            ),
    )


# -------------------------------------------------------------------
# Upload image / GIF to input folder
# -------------------------------------------------------------------

@app.post(
    "/api/inputs/upload"
)
async def upload_input_file(
    file: UploadFile =
        File(...),
):

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="No filename provided.",
        )

    original_name = Path(
        file.filename
    ).name

    extension = Path(
        original_name
    ).suffix.lower()

    if (
        extension
        not in IMAGE_EXTENSIONS
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Only image and GIF files "
                "are supported for AI tagging."
            ),
        )

    destination = (
        INPUT_DIR /
        original_name
    )

    try:

        file_bytes = (
            await file.read()
        )

        if not file_bytes:

            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty.",
            )

        destination.write_bytes(
            file_bytes
        )

        tag = (
            generate_and_cache_tag(
                destination,
                METADATA_FILE,
            )
        )

    except HTTPException:

        if destination.exists():
            destination.unlink()

        raise

    except Exception as exc:

        if destination.exists():
            destination.unlink()

        raise HTTPException(
            status_code=500,
            detail=(
                "Tagging failed: "
                f"{exc}"
            ),
        ) from exc

    return {
        "id": destination.name,
        "name": destination.name,
        "type": (
            "gif"
            if extension == ".gif"
            else "image"
        ),
        "mimeType":
            get_mime_type(
                destination
            ),
        "size":
            destination.stat().st_size,
        "sizeFormatted":
            format_file_size(
                destination.stat().st_size
            ),
        "url":
            (
                f"/api/inputs/file/"
                f"{destination.name}"
            ),
        "tag": tag,
    }


# -------------------------------------------------------------------
# Tag one image
# -------------------------------------------------------------------

@app.post(
    "/api/inputs/tag/{filename:path}"
)
def tag_input_file(
    filename: str,
):

    file_path = (
        INPUT_DIR /
        filename
    )

    if not file_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Input file not found.",
        )

    if (
        file_path.suffix.lower()
        not in IMAGE_EXTENSIONS
    ):

        raise HTTPException(
            status_code=400,
            detail="Only images can be tagged.",
        )

    try:

        tag = (
            generate_and_cache_tag(
                file_path,
                METADATA_FILE,
            )
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Tagging failed: "
                f"{exc}"
            ),
        ) from exc

    return {
        "filename":
            file_path.name,
        "tag": tag,
    }


# -------------------------------------------------------------------
# Tag all images
# -------------------------------------------------------------------

@app.post(
    "/api/inputs/tag-all"
)
def tag_all_input_files():

    results = []
    errors = []

    for path in sorted(
        INPUT_DIR.iterdir(),
        key=lambda item:
        item.name.lower(),
    ):

        if not path.is_file():
            continue

        if (
            path.suffix.lower()
            not in IMAGE_EXTENSIONS
        ):
            continue

        try:

            tag = (
                generate_and_cache_tag(
                    path,
                    METADATA_FILE,
                )
            )

            results.append({
                "filename":
                    path.name,
                "tag": tag,
            })

        except Exception as exc:

            errors.append({
                "filename":
                    path.name,
                "error":
                    str(exc),
            })

    return {
        "success":
            len(errors) == 0,
        "count":
            len(results),
        "results":
            results,
        "errors":
            errors,
    }


# -------------------------------------------------------------------
# Generate AI prompt from reference
# -------------------------------------------------------------------

@app.post(
    "/api/prompts/generate"
)
async def generate_prompt_with_ai(
    source_type: str =
        Form(...),

    source: str =
        Form(...),

    filename: str =
        Form("reference"),

    content_type: str =
        Form(""),
):

    source_type = (
        source_type
        .strip()
        .lower()
    )

    source = source.strip()

    filename = Path(
        filename
    ).name

    if not source:

        raise HTTPException(
            status_code=400,
            detail="Reference source is empty.",
        )

    if source_type not in {
        "input-folder",
        "external-url",
        "youtube",
    }:

        raise HTTPException(
            status_code=400,
            detail="Unsupported reference source.",
        )

    if (
        source_type ==
        "input-folder"
    ):

        reference_path = (
            INPUT_DIR /
            Path(source).name
        )

        if (
            not reference_path.exists()
            or not reference_path.is_file()
        ):

            raise HTTPException(
                status_code=404,
                detail=(
                    "Selected input reference "
                    "was not found."
                ),
            )

        if (
            reference_path.suffix.lower()
            not in IMAGE_EXTENSIONS
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "AI prompt generation supports "
                    "images and GIFs only."
                ),
            )

        try:

            prompt = (
                generate_image_prompt(
                    image_path=
                        reference_path,
                    filename=
                        reference_path.name,
                    content_type=
                        get_mime_type(
                            reference_path
                        ),
                )
            )

            return {
                "success": True,
                "prompt": prompt,
            }

        except ValueError as exc:

            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        except Exception as exc:

            print(
                "AI prompt generation failed:",
                repr(exc),
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "AI prompt generation failed: "
                    f"{exc}"
                ),
            ) from exc

    if not is_valid_http_url(
        source
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "A valid HTTP or HTTPS URL is required."
            ),
        )

    try:

        prompt = (
            generate_image_prompt(
                image_url=source,
                filename=filename,
                content_type=
                    content_type or None,
                is_youtube=(
                    source_type ==
                    "youtube"
                ),
            )
        )

        return {
            "success": True,
            "prompt": prompt,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print(
            "AI prompt generation failed:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "AI prompt generation failed: "
                f"{exc}"
            ),
        ) from exc


# -------------------------------------------------------------------
# Generate template automatically from reference
# -------------------------------------------------------------------

@app.post(
    "/api/templates/generate"
)
async def generate_template_endpoint(
    source_type: str =
        Form(...),

    source: str =
        Form(...),

    filename: str =
        Form("reference"),

    content_type: str =
        Form(""),
):

    source_type = (
        source_type
        .strip()
        .lower()
    )

    source = source.strip()

    filename = Path(
        filename
    ).name

    if not source:

        raise HTTPException(
            status_code=400,
            detail="Reference source is empty.",
        )

    if source_type not in {
        "input-folder",
        "external-url",
        "youtube",
    }:

        raise HTTPException(
            status_code=400,
            detail="Unsupported reference source.",
        )

    try:

        if (
            source_type ==
            "input-folder"
        ):

            reference_path = (
                INPUT_DIR /
                Path(source).name
            )

            if (
                not reference_path.exists()
                or not reference_path.is_file()
            ):

                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Selected input reference "
                        "was not found."
                    ),
                )

            if (
                reference_path.suffix.lower()
                not in IMAGE_EXTENSIONS
            ):

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Automatic template generation "
                        "currently supports images "
                        "and GIFs only."
                    ),
                )

            if (
                reference_path.suffix.lower()
                == ".gif"
            ):

                from PIL import Image

                with Image.open(
                    reference_path
                ) as image:

                    image.seek(0)

                    frame = (
                        image.convert("RGB")
                    )

                    frame_path = (
                        UPLOADS_DIR /
                        f"{reference_path.stem}_frame.png"
                    )

                    frame.save(
                        frame_path,
                        format="PNG",
                    )

                    result = (
                        generate_template(
                            reference_path=
                                frame_path,
                            prompt="",
                        )
                    )

            else:

                result = (
                    generate_template(
                        reference_path=
                            reference_path,
                        prompt="",
                    )
                )

            return {
                "success": True,
                "template": result,
            }


        if not is_valid_http_url(
            source
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "A valid HTTP or HTTPS URL is required."
                ),
            )

        result = (
            generate_template_from_url(
                url=source,
                uploads_dir=
                    UPLOADS_DIR,
                filename=filename,
                content_type=
                    content_type,
                is_youtube=(
                    source_type ==
                    "youtube"
                ),
            )
        )

        return {
            "success": True,
            "template": result,
        }


    except HTTPException:
        raise

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        print(
            "Automatic template generation failed:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Automatic template generation failed: "
                f"{exc}"
            ),
        ) from exc