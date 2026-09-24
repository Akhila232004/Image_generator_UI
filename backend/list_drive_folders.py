import pickle
from googleapiclient.discovery import build

with open("token.pickle", "rb") as token:
    credentials = pickle.load(token)

service = build("drive", "v3", credentials=credentials)

result = service.files().list(
    q="mimeType='application/vnd.google-apps.folder' and trashed=false",
    pageSize=100,
    fields="files(id,name,parents)"
).execute()

folders = result.get("files", [])

print("Google Drive folders:")
print()

for folder in folders:
    print("NAME:", folder["name"])
    print("ID:", folder["id"])
    print("PARENTS:", folder.get("parents", []))
    print("-" * 60)