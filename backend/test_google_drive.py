from pathlib import Path
import io

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# Google Drive scope.
# Use the same full Drive scope required by the Image Generator project
# because the application can read existing references and upload generated
# output files.
SCOPES = ["https://www.googleapis.com/auth/drive"]

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

# Current Image Generator References folder.
DRIVE_FOLDER_ID = "1JMjprxQusftbFRP12SgEIvzRE_X6wcSs"


def get_drive_service():
    """Authenticate with Google Drive and return the Drive API service."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            SCOPES,
        )

    if creds and creds.expired and creds.refresh_token:
        print("Refreshing Google Drive token...")
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"credentials.json was not found at:\n{CREDENTIALS_FILE}"
            )

        print("Opening Google OAuth login...")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE),
            SCOPES,
        )
        creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

    return build(
        "drive",
        "v3",
        credentials=creds,
    )


def list_reference_files(service):
    """List files inside the configured Image Generator References folder."""
    query = (
        f"'{DRIVE_FOLDER_ID}' in parents "
        "and trashed = false"
    )

    response = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
        orderBy="name",
        pageSize=100,
    ).execute()

    files = response.get("files", [])

    print("\nFiles in Image Generator References:")
    print("-" * 70)

    if not files:
        print("No files found.")
        return files

    for index, file in enumerate(files, start=1):
        print(f"{index}. {file['name']}")
        print(f"   ID:       {file['id']}")
        print(f"   MIME:     {file.get('mimeType', '')}")
        print(f"   Size:     {file.get('size', 'N/A')}")
        print(f"   Modified: {file.get('modifiedTime', 'N/A')}")
        print()

    return files


def download_file(service, file_id, file_name):
    """Download one Drive file to a local test_downloads folder."""
    output_dir = BASE_DIR / "test_downloads"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / file_name

    request = service.files().get(
        fileId=file_id,
        alt="media",
    )

    with io.FileIO(output_path, "wb") as output:
        downloader = MediaIoBaseDownload(
            output,
            request,
            chunksize=1024 * 1024,
        )

        done = False

        while not done:
            status, done = downloader.next_chunk()

            if status:
                print(
                    f"Download progress: "
                    f"{int(status.progress() * 100)}%"
                )

    print(f"\nDownloaded successfully:")
    print(output_path)

    return output_path


def main():
    print("=" * 70)
    print("Google Drive Test - Image Generator UI")
    print("=" * 70)

    print(f"\nCredentials: {CREDENTIALS_FILE}")
    print(f"Token:       {TOKEN_FILE}")
    print(f"Folder ID:   {DRIVE_FOLDER_ID}")

    try:
        service = get_drive_service()

        about = service.about().get(
            fields="user(displayName,emailAddress)"
        ).execute()

        user = about.get("user", {})

        print("\nGoogle Drive authentication successful.")
        print(f"Account: {user.get('displayName', 'Unknown')}")
        print(f"Email:   {user.get('emailAddress', 'Unknown')}")

        files = list_reference_files(service)

        if files:
            # Download the first file as a simple end-to-end
            # authenticated Drive media test.
            first_file = files[0]

            print(
                f"Testing download with: "
                f"{first_file['name']}"
            )

            download_file(
                service,
                first_file["id"],
                first_file["name"],
            )

        print("\nGoogle Drive test completed successfully.")

    except Exception as exc:
        print("\nGoogle Drive test failed.")
        print(f"Error: {exc}")
        raise


if __name__ == "__main__":
    main()
