from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_FILE = "token.json"
FOLDER_ID = "1JMjprxQusftbFRP12SgEIvzRE_X6wcSs"
SCOPES = ["https://www.googleapis.com/auth/drive"]

credentials = Credentials.from_authorized_user_file(
    TOKEN_FILE,
    SCOPES
)

print("Token valid:", credentials.valid)
print("Token expired:", credentials.expired)
print("Has refresh token:", bool(credentials.refresh_token))

service = build("drive", "v3", credentials=credentials)

result = service.files().list(
    q=f"'{FOLDER_ID}' in parents and trashed=false",
    fields="files(id,name,mimeType)"
).execute()

files = result.get("files", [])

print()
print("Files in reference folder:")
print("=" * 70)

if not files:
    print("NO FILES FOUND")

for file in files:
    print("Name:", file["name"])
    print("Type:", file["mimeType"])
    print("ID:", file["id"])
    print("-" * 70)