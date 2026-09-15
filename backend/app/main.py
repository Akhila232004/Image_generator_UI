from pathlib import Path
import io
import json
import os
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    Body,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)
from pydantic import BaseModel

from fastapi.responses import (
    FileResponse,
    StreamingResponse,
)

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

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

MANUAL_UPLOADS_DIR = (
    BASE_DIR /
    "manual_uploads"
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


MANUAL_UPLOADS_DIR.mkdir(
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
# API key setup / in-memory session
# -------------------------------------------------------------------

DRIVE_OAUTH_KEY_ID = "__GOOGLE_DRIVE_OAUTH__"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

API_KEY_STATE = {
    "keys": {},
    "selected_ids": set(),
    "drive_folder_id": "",
    "drive_folder_name": "",
    "gemini_model": "gemini-3.5-flash-lite",
}


class ApiKeySelection(BaseModel):
    selected_ids: list[str]


def normalize_key_name(name: str) -> str:
    return re.sub(
        r"[^A-Z0-9]+",
        "_",
        name.strip().upper(),
    ).strip("_")


def display_api_name(key_name: str) -> str:
    normalized = normalize_key_name(key_name)

    if "DRIVE" in normalized and "API" in normalized:
        return "Google Drive API"

    if "GEMINI" in normalized:
        return "Gemini API"

    if (
        "GOOGLE_AI" in normalized
        or "GOOGLEAI" in normalized
        or "GENERATIVE_AI" in normalized
    ):
        return "Google AI API"

    if "GOOGLE" in normalized and "API" in normalized:
        return "Google API"

    words = normalized.replace("_API_KEY", "").replace("_KEY", "").split("_")
    words = [word.title() for word in words if word]

    return " ".join(words) + " API" if words else "API"

def parse_api_key_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
            or line.startswith("//")
        ):
            continue

        line = line.rstrip(",")

        if line.startswith("{") or line.startswith("}"):
            continue

        match = re.match(
            r'^\s*["\']?([A-Za-z0-9_.\-\s]+)["\']?\s*(?:=|:)\s*(.*?)\s*$',
            line,
        )

        if not match:
            continue

        raw_name = match.group(1).strip()
        raw_value = match.group(2).strip()

        raw_value = raw_value.rstrip(",").strip()
        raw_value = raw_value.strip('"').strip("'").strip()

        if not raw_name or not raw_value:
            continue

        key_name = normalize_key_name(
            raw_name
        )

        values[key_name] = raw_value

    return values


def parse_api_key_file(
    file_bytes: bytes,
    filename: str,
) -> dict[str, str]:
    text = file_bytes.decode(
        "utf-8-sig",
        errors="replace",
    )

    if Path(filename).suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "The JSON API key file is not valid JSON."
            ) from exc

        values: dict[str, str] = {}

        def collect(
            item,
            prefix: str = "",
        ):
            if isinstance(item, dict):
                for key, value in item.items():
                    next_prefix = (
                        f"{prefix}_{key}"
                        if prefix
                        else str(key)
                    )
                    collect(
                        value,
                        next_prefix,
                    )
            elif isinstance(item, (str, int, float)):
                if item != "":
                    values[
                        normalize_key_name(prefix)
                    ] = str(item)

        collect(payload)
        return values

    return parse_api_key_text(text)


def find_config_value(
    values: dict[str, str],
    patterns: tuple[str, ...],
) -> str:
    for key, value in values.items():
        normalized = normalize_key_name(key)

        if any(
            pattern in normalized
            for pattern in patterns
        ):
            return value

    return ""


def selected_key_value(
    category: str,
) -> str:
    selected = API_KEY_STATE["selected_ids"]
    keys = API_KEY_STATE["keys"]

    if category != "gemini":
        return ""

    preferred_names = (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_AI_API_KEY",
        "GENERATIVE_AI_API_KEY",
    )

    for key_name in preferred_names:
        if key_name not in selected:
            continue

        item = keys.get(key_name)
        if not item:
            continue

        value = str(item.get("value", "")).strip()
        if value:
            return value

    for key_id in selected:
        item = keys.get(key_id)
        if not item:
            continue

        if item.get("service") == "gemini":
            value = str(item.get("value", "")).strip()
            if value:
                return value

    return ""


def configure_selected_environment():
    # Credentials are held only in the running backend process.
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_MODEL", None)

    gemini_key = selected_key_value("gemini")

    # Do not mirror the Gemini key into GOOGLE_API_KEY. The google-genai
    # client otherwise reports that both credentials are configured and may
    # choose GOOGLE_API_KEY unexpectedly.
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

    model = str(
        API_KEY_STATE.get("gemini_model")
        or "gemini-3.5-flash-lite"
    ).strip()
    os.environ["GEMINI_MODEL"] = model


def normalize_drive_folder_id(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""

    match = re.search(
        r"/folders/([A-Za-z0-9_-]+)",
        value,
    )
    if match:
        return match.group(1)

    return value


def drive_oauth_available() -> bool:
    return CREDENTIALS_FILE.exists()


def drive_oauth_selected() -> bool:
    """
    Google Drive is available when its OAuth files and folder configuration
    are present. It does not depend on the frontend selecting a synthetic
    "Google Drive API" checkbox.
    """
    return (
        CREDENTIALS_FILE.exists()
        and TOKEN_FILE.exists()
        and bool(
            normalize_drive_folder_id(
                API_KEY_STATE.get("drive_folder_id", "")
            )
            or API_KEY_STATE.get("drive_folder_name", "")
        )
    )


def get_drive_service():
    if not CREDENTIALS_FILE.exists():
        raise RuntimeError(
            "Google Drive OAuth credentials.json was not found in the backend folder."
        )

    credentials = None

    if TOKEN_FILE.exists():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(TOKEN_FILE),
                DRIVE_SCOPES,
            )
        except Exception:
            credentials = None

    if credentials and credentials.valid:
        return build(
            "drive",
            "v3",
            credentials=credentials,
        )

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleAuthRequest())
            TOKEN_FILE.write_text(
                credentials.to_json(),
                encoding="utf-8",
            )
            return build(
                "drive",
                "v3",
                credentials=credentials,
            )
        except Exception as exc:
            raise RuntimeError(
                "Google Drive authorization has expired and could not be refreshed. "
                "Run 'python test_google_drive.py' once to authorize again."
            ) from exc

    raise RuntimeError(
        "Google Drive is not authorized yet. Run 'python test_google_drive.py' "
        "once from the backend folder, then restart the backend."
    )


def require_drive_configuration():
    """
    Validate Google Drive configuration.

    The uploaded configuration file only needs the Drive folder ID/name.
    OAuth authentication comes from credentials.json and token.json in the
    backend folder.
    """
    folder_id = normalize_drive_folder_id(
        API_KEY_STATE.get("drive_folder_id", "")
    )
    folder_name = str(
        API_KEY_STATE.get("drive_folder_name", "")
    ).strip()

    if not folder_id and not folder_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "No Google Drive folder was configured. Add "
                "GOOGLE_DRIVE_FOLDER_ID to the uploaded API file."
            ),
        )

    if not CREDENTIALS_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=(
                "Google Drive credentials.json was not found in the backend folder."
            ),
        )

    if not TOKEN_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=(
                "Google Drive token.json was not found in the backend folder."
            ),
        )

    return folder_id, folder_name


def resolve_drive_folder_id(
    service,
    folder_id: str,
    folder_name: str,
) -> str:
    if folder_id:
        return folder_id

    escaped_name = folder_name.replace("'", "\\'")

    result = service.files().list(
        q=(
            f"name = '{escaped_name}' "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        ),
        pageSize=20,
        fields="files(id,name)",
    ).execute()

    folders = result.get("files", [])

    if not folders:
        raise RuntimeError(
            f'Google Drive folder "{folder_name}" was not found.'
        )

    return str(folders[0]["id"])


def get_drive_files(
    service,
    folder_id: str,
) -> list[dict]:
    files: list[dict] = []
    page_token = None

    while True:
        result = service.files().list(
            q=(
                f"'{folder_id}' in parents "
                "and trashed = false"
            ),
            pageSize=100,
            orderBy="name",
            fields=(
                "nextPageToken,"
                "files(id,name,mimeType,size,modifiedTime)"
            ),
            pageToken=page_token,
        ).execute()

        for item in result.get("files", []):
            mime_type = str(item.get("mimeType", ""))

            if not mime_type.startswith("image/"):
                continue

            if mime_type == "image/svg+xml":
                continue

            name = str(item.get("name", "Drive Reference"))
            size = int(item.get("size", 0) or 0)
            extension = Path(name).suffix.lower()

            file_type = (
                "gif"
                if extension == ".gif" or mime_type == "image/gif"
                else "image"
            )

            drive_id = str(item["id"])
            file_data = {
                "id": f"drive:{drive_id}",
                "name": name,
                "type": file_type,
                "mimeType": mime_type,
                "size": size,
                "sizeFormatted": format_file_size(size),
                "url": f"/api/drive/file/{drive_id}",
                "source": "google-drive",
                "driveFileId": drive_id,
            }

            metadata = load_tag_metadata(METADATA_FILE)
            cached = metadata.get(f"drive:{drive_id}")
            if isinstance(cached, dict) and cached.get("tag"):
                file_data["tag"] = str(cached["tag"])

            files.append(file_data)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return files


def download_drive_file(
    service,
    file_id: str,
    destination: Path,
) -> Path:
    """
    Download the real Google Drive media bytes.

    The previous implementation used MediaIoBaseDownload. In this project
    that endpoint was returning a small JSON document instead of the image
    bytes, so this implementation performs an authenticated Drive REST GET
    explicitly with alt=media and verifies the response before saving it.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Reuse the credentials already loaded by the Drive service.
    credentials = getattr(service, "_http", None)
    credentials = getattr(credentials, "credentials", None)

    if credentials is None:
        raise RuntimeError(
            "Unable to access the authenticated Google Drive credentials."
        )

    # Make sure an expired access token is refreshed before the request.
    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleAuthRequest())
        else:
            raise RuntimeError(
                "Google Drive authorization is not valid. "
                "Run 'python test_google_drive.py' once to authorize again."
            )

    from google.auth.transport.requests import AuthorizedSession

    session = AuthorizedSession(credentials)

    url = (
        "https://www.googleapis.com/drive/v3/files/"
        f"{quote(str(file_id), safe='')}"
    )

    try:
        response = session.get(
            url,
            params={
                "alt": "media",
            },
            timeout=60,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Google Drive media request failed: {exc}"
        ) from exc

    if response.status_code != 200:
        body = response.text[:500]
        raise RuntimeError(
            "Google Drive media request returned "
            f"HTTP {response.status_code}: {body}"
        )

    data = response.content

    if not data:
        raise RuntimeError("Google Drive returned an empty file.")

    content_type = str(
        response.headers.get("Content-Type", "")
    ).lower()

    # Drive must return image bytes for an image reference. If the response
    # is JSON, include a short diagnostic instead of saving it as an image.
    if "application/json" in content_type or data.lstrip().startswith(
        (b"{", b"[")
    ):
        preview = data[:300].decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(
            "Google Drive returned JSON instead of image bytes. "
            f"Response: {preview}"
        )

    temp_path = destination.with_name(
        f".{destination.name}.download"
    )

    try:
        temp_path.write_bytes(data)
        temp_path.replace(destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Google Drive returned an empty file.")

    return destination

def is_valid_image_file(path: Path) -> bool:
    """
    Check that a cached Drive file is actually a readable image.
    This prevents old metadata JSON from being returned as image/png.
    """
    if not path.exists() or not path.is_file() or path.stat().st_size == 0:
        return False

    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()

        return True
    except Exception:
        return False


def safe_drive_filename(
    file_id: str,
    filename: str,
) -> Path:
    clean_name = Path(filename).name
    if not clean_name:
        clean_name = "drive_reference"

    return UPLOADS_DIR / f"drive_{file_id}_{clean_name}"


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
# API key setup
# -------------------------------------------------------------------

@app.post(
    "/api/api-keys/upload"
)
async def upload_api_keys_file(
    file: UploadFile = File(...),
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No API key filename provided.",
        )

    filename = Path(
        file.filename
    ).name

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in {
        ".env",
        ".txt",
        ".json",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "API key files must be .env, .txt or .json."
            ),
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="The API key file is empty.",
        )

    if len(file_bytes) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="The API key file is too large.",
        )

    try:
        values = parse_api_key_file(
            file_bytes,
            filename,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not values:
        raise HTTPException(
            status_code=400,
            detail=(
                "No key=value or key:value entries were found "
                "in the uploaded API key file."
            ),
        )

    API_KEY_STATE["keys"] = {}
    API_KEY_STATE["selected_ids"] = set()

    gemini_aliases = {
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_AI_API_KEY",
        "GENERATIVE_AI_API_KEY",
    }

    # Configuration values are not API services.
    configuration_names = {
        "GEMINI_MODEL",
        "GOOGLE_AI_MODEL",
        "MODEL",
        "GOOGLE_DRIVE_FOLDER_ID",
        "GDRIVE_FOLDER_ID",
        "DRIVE_FOLDER_ID",
        "GOOGLE_DRIVE_FOLDER_URL",
        "GDRIVE_FOLDER_URL",
        "DRIVE_FOLDER_URL",
        "GOOGLE_DRIVE_FOLDER_NAME",
        "GDRIVE_FOLDER_NAME",
        "GOOGLE_DRIVE_NAME",
        "GDRIVE_NAME",
        "DRIVE_FOLDER_NAME",
        "DRIVE_NAME",
    }

    # Treat all Gemini/Google AI key aliases as ONE logical Gemini service.
    gemini_key_name = next(
        (name for name in (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_AI_API_KEY",
            "GENERATIVE_AI_API_KEY",
        ) if values.get(name)),
        None,
    )

    if gemini_key_name:
        API_KEY_STATE["keys"]["GEMINI_API_KEY"] = {
            "key_name": "GEMINI_API_KEY",
            "value": str(values[gemini_key_name]).strip(),
            "display_name": "Gemini API",
            "auth_type": "api-key",
            "service": "gemini",
        }

    # Add any other genuine API-key credentials, but never add configuration
    # values such as folder IDs or model names.
    for key_name, value in values.items():
        normalized = normalize_key_name(key_name)

        if not value or normalized in configuration_names:
            continue

        if normalized in gemini_aliases:
            continue

        if "API" not in normalized and "KEY" not in normalized:
            continue

        display_name = display_api_name(normalized)
        existing_names = {
            item.get("display_name")
            for item in API_KEY_STATE["keys"].values()
        }

        if display_name in existing_names:
            continue

        API_KEY_STATE["keys"][normalized] = {
            "key_name": normalized,
            "value": str(value).strip(),
            "display_name": display_name,
            "auth_type": "api-key",
            "service": "other",
        }

    drive_folder_id = find_config_value(
        values,
        (
            "GOOGLE_DRIVE_FOLDER_ID",
            "GDRIVE_FOLDER_ID",
            "DRIVE_FOLDER_ID",
            "GOOGLE_DRIVE_FOLDER_URL",
            "GDRIVE_FOLDER_URL",
            "DRIVE_FOLDER_URL",
        ),
    )
    drive_folder_id = normalize_drive_folder_id(drive_folder_id)

    drive_folder_name = find_config_value(
        values,
        (
            "GOOGLE_DRIVE_FOLDER_NAME",
            "GDRIVE_FOLDER_NAME",
            "GOOGLE_DRIVE_NAME",
            "GDRIVE_NAME",
            "DRIVE_FOLDER_NAME",
            "DRIVE_NAME",
        ),
    )

    API_KEY_STATE["drive_folder_id"] = drive_folder_id
    API_KEY_STATE["drive_folder_name"] = drive_folder_name
    API_KEY_STATE["gemini_model"] = (
        find_config_value(
            values,
            ("GEMINI_MODEL", "GOOGLE_AI_MODEL", "MODEL"),
        )
        or "gemini-3.5-flash-lite"
    )

    # Google Drive is an OAuth service, not another API-key credential.
    if drive_oauth_available() and (drive_folder_id or drive_folder_name):
        API_KEY_STATE["keys"][DRIVE_OAUTH_KEY_ID] = {
            "key_name": DRIVE_OAUTH_KEY_ID,
            "value": "",
            "display_name": "Google Drive API",
            "auth_type": "oauth",
            "service": "google-drive",
        }

    response_keys = [
        {
            "id": key_id,
            "name": item["display_name"],
            "keyName": key_id,
            "authType": item.get("auth_type", "api-key"),
        }
        for key_id, item in API_KEY_STATE["keys"].items()
    ]

    return {
        "success": True,
        "keys": response_keys,
    }


@app.post(
    "/api/api-keys/select"
)
def select_api_keys(
    selection: ApiKeySelection,
):
    available = API_KEY_STATE["keys"]

    if not available:
        raise HTTPException(
            status_code=400,
            detail="Upload an API key file first.",
        )

    selected_ids = [
        key_id
        for key_id in selection.selected_ids
        if key_id in available
    ]

    if not selected_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one valid API.",
        )

    API_KEY_STATE["selected_ids"] = set(
        selected_ids
    )

    configure_selected_environment()

    selected_names = [
        available[key_id]["display_name"]
        for key_id in selected_ids
    ]

    return {
        "success": True,
        "selected": selected_names,
    }


@app.get(
    "/api/api-keys/status"
)
def api_key_status():
    available = API_KEY_STATE["keys"]

    return {
        "configured": bool(available),
        "selected": [
            available[key_id]["display_name"]
            for key_id in API_KEY_STATE["selected_ids"]
            if key_id in available
        ],
    }


# -------------------------------------------------------------------
# Google Drive input files
# -------------------------------------------------------------------

@app.get(
    "/api/drive/inputs"
)
def get_drive_inputs():
    folder_id, folder_name = require_drive_configuration()

    try:
        service = get_drive_service()
        resolved_folder_id = resolve_drive_folder_id(
            service,
            folder_id,
            folder_name,
        )

        API_KEY_STATE["drive_folder_id"] = resolved_folder_id

        return get_drive_files(
            service,
            resolved_folder_id,
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/drive/file/{file_id}"
)
def get_drive_file(
    file_id: str,
):
    """
    Serve a Google Drive image through the backend.

    The browser never needs direct access to Google Drive. The file is
    downloaded once into the backend uploads cache and returned with an
    inline image response.
    """

    require_drive_configuration()

    file_id = str(
        file_id or ""
    ).strip()

    if not file_id:
        raise HTTPException(
            status_code=400,
            detail="Google Drive file ID is required.",
        )

    try:
        service = get_drive_service()

        metadata = (
            service.files()
            .get(
                fileId=file_id,
                fields="id,name,mimeType,size",
            )
            .execute()
        )

        mime_type = str(
            metadata.get(
                "mimeType",
                "",
            )
        ).strip()

        if not mime_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "The selected Google Drive file is "
                    "not a supported image."
                ),
            )

        clean_name = (
            Path(
                str(
                    metadata.get(
                        "name",
                        "reference",
                    )
                )
            ).name
            or "reference"
        )

        # v2 avoids preview files created by older code that could contain
        # Google Drive metadata JSON instead of the actual image.
        cache_path = (
            UPLOADS_DIR
            / f"drive_preview_v3_{file_id}_{clean_name}"
        )

        if not is_valid_image_file(cache_path):
            if cache_path.exists():
                try:
                    cache_path.unlink()
                except OSError:
                    pass

            download_drive_file(
                service,
                file_id,
                cache_path,
            )

        # Do not return a file just because it exists. Verify its bytes first.
        if not is_valid_image_file(cache_path):
            raise RuntimeError(
                "Google Drive did not return valid image bytes. "
                "The response was not a readable image."
            )

        return FileResponse(
            path=cache_path,
            media_type=(
                mime_type
                or get_mime_type(cache_path)
            ),
            filename=clean_name,
            headers={
                "Content-Disposition":
                    f'inline; filename="{clean_name}"',
                "Cache-Control":
                    "no-cache, no-store, must-revalidate",
                "Pragma":
                    "no-cache",
                "Expires":
                    "0",
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        print(
            "Google Drive preview failed:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve the Google Drive "
                f"reference: {exc}"
            ),
        ) from exc


# -------------------------------------------------------------------
# Input files
# -------------------------------------------------------------------

def get_input_files() -> list[dict]:
    """
    Return references from the configured Google Drive folder plus
    locally uploaded images.

    Google Drive loading is based on the uploaded folder configuration and
    the OAuth files in the backend folder. It does not depend on a frontend
    checkbox.
    """
    drive_files: list[dict] = []

    has_drive_configuration = bool(
        normalize_drive_folder_id(
            API_KEY_STATE.get("drive_folder_id", "")
        )
        or API_KEY_STATE.get("drive_folder_name", "")
    )

    if (
        has_drive_configuration
        and CREDENTIALS_FILE.exists()
        and TOKEN_FILE.exists()
    ):
        try:
            folder_id = normalize_drive_folder_id(
                API_KEY_STATE.get("drive_folder_id", "")
            )
            folder_name = str(
                API_KEY_STATE.get("drive_folder_name", "")
            ).strip()

            service = get_drive_service()

            resolved_folder_id = resolve_drive_folder_id(
                service,
                folder_id,
                folder_name,
            )

            API_KEY_STATE["drive_folder_id"] = resolved_folder_id

            drive_files = get_drive_files(
                service,
                resolved_folder_id,
            )

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Unable to load Google Drive references: "
                    f"{exc}"
                ),
            ) from exc

    manual_files = get_manual_upload_files()

    return sorted(
        drive_files + manual_files,
        key=lambda item: item["name"].lower(),
    )


# -------------------------------------------------------------------
# Manual uploads
# -------------------------------------------------------------------

def get_manual_upload_files() -> list[dict]:
    files = []

    metadata = load_tag_metadata(
        METADATA_FILE
    )

    supported_extensions = IMAGE_EXTENSIONS

    for path in sorted(
        MANUAL_UPLOADS_DIR.iterdir(),
        key=lambda item: item.name.lower(),
    ):
        if not path.is_file():
            continue

        if path.suffix.lower() not in supported_extensions:
            continue

        file_type = get_file_type(path)
        file_data = {
            "id": f"manual:{path.name}",
            "name": path.name,
            "type": file_type,
            "mimeType": get_mime_type(path),
            "size": path.stat().st_size,
            "sizeFormatted": format_file_size(path.stat().st_size),
            "url": f"/api/manual/file/{path.name}",
            "source": "manual-upload",
        }

        cached_item = metadata.get(path.name)

        if (
            isinstance(cached_item, dict)
            and cached_item.get("tag")
        ):
            file_data["tag"] = str(
                cached_item["tag"]
            )

        files.append(file_data)

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
# Serve manual upload
# -------------------------------------------------------------------

@app.get(
    "/api/manual/file/{filename:path}"
)
def get_manual_file(
    filename: str,
):
    file_path = MANUAL_UPLOADS_DIR / Path(filename).name

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Manual upload not found.",
        )

    return FileResponse(
        file_path,
        media_type=get_mime_type(file_path),
    )


# -------------------------------------------------------------------
# Upload image / GIF as a manual reference
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
                "are supported for manual references."
            ),
        )

    destination = (
        MANUAL_UPLOADS_DIR /
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

        if selected_key_value("gemini"):
            tag = generate_and_cache_tag(
                destination,
                METADATA_FILE,
            )
        else:
            tag = ""

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
                f"/api/manual/file/"
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
    """
    Generate tags for every image available to the workspace.

    Google Drive images are identified by their stable Drive file ID.
    Manual uploads are identified by their filename.

    Existing cached tags are reused. Only images without a cached tag
    are sent to Gemini.
    """

    results = []
    errors = []

    if not selected_key_value("gemini"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Gemini API is not selected. Upload the API "
                "configuration file and select Gemini API first."
            ),
        )

    # ---------------------------------------------------------------
    # Manual uploads
    # ---------------------------------------------------------------

    if MANUAL_UPLOADS_DIR.exists():
        for path in sorted(
            MANUAL_UPLOADS_DIR.iterdir(),
            key=lambda item: item.name.lower(),
        ):
            if (
                not path.is_file()
                or path.suffix.lower()
                not in IMAGE_EXTENSIONS
            ):
                continue

            cache_key = (
                f"manual:{path.name}"
            )

            try:
                tag = generate_and_cache_tag(
                    path,
                    METADATA_FILE,
                    cache_key=cache_key,
                )

                results.append(
                    {
                        "id":
                            f"manual:{path.name}",
                        "filename":
                            path.name,
                        "tag":
                            tag,
                    }
                )

            except Exception as exc:
                errors.append(
                    {
                        "id":
                            f"manual:{path.name}",
                        "filename":
                            path.name,
                        "error":
                            str(exc),
                    }
                )

    # ---------------------------------------------------------------
    # Google Drive images
    # ---------------------------------------------------------------

    if (
        drive_oauth_available()
        and TOKEN_FILE.exists()
        and (
            API_KEY_STATE.get("drive_folder_id")
            or API_KEY_STATE.get("drive_folder_name")
        )
    ):

        try:
            folder_id, folder_name = (
                require_drive_configuration()
            )

            service = get_drive_service()

            resolved_folder_id = (
                resolve_drive_folder_id(
                    service,
                    folder_id,
                    folder_name,
                )
            )

            API_KEY_STATE[
                "drive_folder_id"
            ] = resolved_folder_id

            drive_files = get_drive_files(
                service,
                resolved_folder_id,
            )

            metadata = load_tag_metadata(
                METADATA_FILE
            )

            for drive_file in drive_files:

                drive_id = str(
                    drive_file.get(
                        "driveFileId",
                        "",
                    )
                ).strip()

                if not drive_id:
                    continue

                cache_key = (
                    f"drive:{drive_id}"
                )

                cached = metadata.get(
                    cache_key
                )

                # Reuse an existing tag.
                if (
                    isinstance(
                        cached,
                        dict,
                    )
                    and cached.get("tag")
                ):
                    results.append(
                        {
                            "id":
                                f"drive:{drive_id}",
                            "filename":
                                drive_file["name"],
                            "tag":
                                str(
                                    cached["tag"]
                                ),
                        }
                    )
                    continue

                try:
                    cache_path = (
                        safe_drive_filename(
                            drive_id,
                            drive_file["name"],
                        )
                    )

                    # Download the actual Drive media so Gemini receives
                    # image bytes rather than Drive metadata JSON.
                    download_drive_file(
                        service,
                        drive_id,
                        cache_path,
                    )

                    tag = (
                        generate_and_cache_tag(
                            cache_path,
                            METADATA_FILE,
                            cache_key=cache_key,
                        )
                    )

                    results.append(
                        {
                            "id":
                                f"drive:{drive_id}",
                            "filename":
                                drive_file["name"],
                            "tag":
                                tag,
                        }
                    )

                except Exception as exc:
                    errors.append(
                        {
                            "id":
                                f"drive:{drive_id}",
                            "filename":
                                drive_file["name"],
                            "error":
                                str(exc),
                        }
                    )

        except Exception as exc:
            errors.append(
                {
                    "filename":
                        "Google Drive",
                    "error":
                        str(exc),
                }
            )

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
        "google-drive",
        "upload",
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

    if source_type == "upload":
        reference_path = MANUAL_UPLOADS_DIR / Path(source).name

        if not reference_path.exists() or not reference_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Manual uploaded reference was not found.",
            )

        if reference_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="AI prompt generation supports images and GIFs only.",
            )

        try:
            prompt = generate_image_prompt(
                image_path=reference_path,
                filename=reference_path.name,
                content_type=get_mime_type(reference_path),
            )
            return {
                "success": True,
                "prompt": prompt,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"AI prompt generation failed: {exc}",
            ) from exc

    if source_type == "google-drive":
        require_drive_configuration()

        try:
            service = get_drive_service()
            cache_path = safe_drive_filename(
                source,
                filename,
            )

            # Do not reuse an old cached Drive response.
            if cache_path.exists():
                try:
                    cache_path.unlink()
                except OSError:
                    pass

            download_drive_file(
                service,
                source,
                cache_path,
            )

            prompt = generate_image_prompt(
                image_path=cache_path,
                filename=filename,
                content_type=(
                    content_type
                    or get_mime_type(cache_path)
                ),
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
                "Google Drive AI prompt generation failed:",
                repr(exc),
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Google Drive AI prompt generation failed: "
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
        "google-drive",
        "upload",
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


        if source_type == "upload":
            reference_path = MANUAL_UPLOADS_DIR / Path(source).name

            if not reference_path.exists() or not reference_path.is_file():
                raise HTTPException(
                    status_code=404,
                    detail="Manual uploaded reference was not found.",
                )

            if reference_path.suffix.lower() not in IMAGE_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail="Automatic template generation currently supports images and GIFs only.",
                )

            if reference_path.suffix.lower() == ".gif":
                from PIL import Image

                with Image.open(reference_path) as image:
                    image.seek(0)
                    frame = image.convert("RGB")
                    frame_path = UPLOADS_DIR / f"{reference_path.stem}_frame.png"
                    frame.save(frame_path, format="PNG")
                    result = generate_template(
                        reference_path=frame_path,
                        prompt="",
                    )
            else:
                result = generate_template(
                    reference_path=reference_path,
                    prompt="",
                )

            return {
                "success": True,
                "template": result,
            }

        if source_type == "google-drive":
            require_drive_configuration()

            try:
                cache_path = safe_drive_filename(
                    source,
                    filename,
                )

                # Do not reuse an old cached Drive response.
                if cache_path.exists():
                    try:
                        cache_path.unlink()
                    except OSError:
                        pass

                service = get_drive_service()
                download_drive_file(
                    service,
                    source,
                    cache_path,
                )

                if (
                    cache_path.suffix.lower()
                    == ".gif"
                ):
                    from PIL import Image

                    with Image.open(
                        cache_path
                    ) as image:
                        image.seek(0)

                        frame = image.convert(
                            "RGB"
                        )

                        frame_path = (
                            UPLOADS_DIR /
                            f"{cache_path.stem}_frame.png"
                        )

                        frame.save(
                            frame_path,
                            format="PNG",
                        )

                        result = generate_template(
                            reference_path=frame_path,
                            prompt="",
                        )
                else:
                    result = generate_template(
                        reference_path=cache_path,
                        prompt="",
                    )

                return {
                    "success": True,
                    "template": result,
                }

            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=str(exc),
                ) from exc

            except Exception as exc:
                print(
                    "Google Drive template generation failed:",
                    repr(exc),
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Google Drive template generation failed: "
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