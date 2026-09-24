from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_FILE = "token.json"
OUTPUT_FOLDER_ID = "1CTLb8ekTqmwCDpuOjLmYA2G1ZmfjZAuF"

SCOPES = ["https://www.googleapis.com/auth/drive"]

credentials = Credentials.from_authorized_user_file(
    TOKEN_FILE,
    SCOPES
)

service = build("drive", "v3", credentials=credentials)

print("Token valid:", credentials.valid)
print("Token expired:", credentials.expired)

folder = service.files().get(
    fileId=OUTPUT_FOLDER_ID,
    fields="id,name,mimeType,parents"
).execute()

print()
print("OUTPUT FOLDER")
print("=" * 60)
print("Name:", folder["name"])
print("ID:", folder["id"])
print("Type:", folder["mimeType"])

result = service.files().list(
    q=f"'{OUTPUT_FOLDER_ID}' in parents and trashed=false",
    fields="files(id,name,mimeType,size,createdTime,modifiedTime)",
    orderBy="createdTime desc"
).execute()

files = result.get("files", [])

print()
print("FILES IN OUTPUT FOLDER")
print("=" * 60)

if not files:
    print("NO OUTPUT FILES FOUND")
else:
    for file in files:
        print("Name:", file["name"])
        print("Type:", file["mimeType"])
        print("ID:", file["id"])
        print("Size:", file.get("size", "N/A"))
        print("Created:", file.get("createdTime", "N/A"))
        print("-" * 60)