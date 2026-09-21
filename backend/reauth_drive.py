from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",
    SCOPES
)

credentials = flow.run_local_server(port=0)

with open("token.json", "w") as token:
    token.write(credentials.to_json())

print()
print("Google Drive authentication successful.")
print("New token.json created with full Drive access.")