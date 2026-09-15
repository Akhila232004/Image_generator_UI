import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

FOLDER_ID = "1b_B5PC-bptrUNol-6ROc6k3ri--9iJvy"


def get_drive_service():
    credentials = None

    if os.path.exists("token.json"):
        credentials = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            credentials = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(credentials.to_json())

    return build(
        "drive",
        "v3",
        credentials=credentials
    )


def main():
    service = get_drive_service()

    query = (
        f"'{FOLDER_ID}' in parents "
        "and trashed = false"
    )

    result = service.files().list(
        q=query,
        pageSize=100,
        fields="files(id,name,mimeType,size)"
    ).execute()

    files = result.get("files", [])

    print("\nImage Generator References")
    print("=" * 60)
    print(f"Folder ID: {FOLDER_ID}")
    print(f"Files found: {len(files)}")
    print("=" * 60)

    image_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif"
    )

    image_files = []

    for file in files:
        name = file.get("name", "")
        mime_type = file.get("mimeType", "")

        if (
            mime_type.startswith("image/")
            or name.lower().endswith(image_extensions)
        ):
            image_files.append(file)

    print(f"\nImage/GIF files: {len(image_files)}\n")

    for file in image_files:
        print(
            f"{file['name']} | "
            f"{file['mimeType']} | "
            f"{file['id']}"
        )


if __name__ == "__main__":
    main()