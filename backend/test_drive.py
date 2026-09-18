from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

FOLDER_ID = "1b_B5PC-bptrUNol-6ROc6k3ri--9iJvy"

credentials = service_account.Credentials.from_service_account_file(
    "service-account.json",
    scopes=["https://www.googleapis.com/auth/drive"],
)

session = AuthorizedSession(credentials)

url = "https://www.googleapis.com/drive/v3/files"

params = {
    "q": f"'{FOLDER_ID}' in parents and trashed=false",
    "fields": "files(id,name,mimeType)",
    "pageSize": 100,
}

response = session.get(url, params=params)

print("STATUS:", response.status_code)
print("RESPONSE:")
print(response.text)
