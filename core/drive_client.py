import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

FOLDER_MIME = "application/vnd.google-apps.folder"
COMPLETED_FOLDER_NAME = "処理済み"
IMAGES_FOLDER_NAME = "問題文画像"

SERVICE_ACCOUNT_JSON_ENV_VAR = "GOOGLE_SERVICE_ACCOUNT_JSON"


def get_credentials(service_account_json_path):
    env_value = os.environ.get(SERVICE_ACCOUNT_JSON_ENV_VAR)
    if env_value:
        info = json.loads(env_value)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    return service_account.Credentials.from_service_account_file(
        service_account_json_path, scopes=SCOPES
    )


class DriveClient:
    def __init__(self, credentials):
        self.service = build("drive", "v3", credentials=credentials)

    def list_subfolders(self, parent_id):
        query = (
            f"'{parent_id}' in parents and mimeType='{FOLDER_MIME}' and trashed=false"
        )
        result = self.service.files().list(
            q=query, fields="files(id,name)", orderBy="name"
        ).execute()
        return result.get("files", [])

    def list_images(self, folder_id):
        query = (
            f"'{folder_id}' in parents and trashed=false and mimeType contains 'image/'"
        )
        result = self.service.files().list(
            q=query, fields="files(id,name,mimeType)", orderBy="name"
        ).execute()
        return result.get("files", [])

    def download_file(self, file_id, dest_path):
        request = self.service.files().get_media(fileId=file_id)
        with open(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def find_or_create_folder(self, parent_id, name):
        query = (
            f"'{parent_id}' in parents and name='{name}' "
            f"and mimeType='{FOLDER_MIME}' and trashed=false"
        )
        result = self.service.files().list(q=query, fields="files(id,name)").execute()
        files = result.get("files", [])
        if files:
            return files[0]["id"]
        metadata = {
            "name": name,
            "mimeType": FOLDER_MIME,
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=metadata, fields="id").execute()
        return folder["id"]

    def find_or_create_completed_folder(self, root_folder_id):
        return self.find_or_create_folder(root_folder_id, COMPLETED_FOLDER_NAME)

    def find_or_create_images_folder(self, root_folder_id):
        return self.find_or_create_folder(root_folder_id, IMAGES_FOLDER_NAME)

    def move_file(self, file_id, from_folder_id, to_folder_id):
        self.service.files().update(
            fileId=file_id,
            addParents=to_folder_id,
            removeParents=from_folder_id,
            fields="id,parents",
        ).execute()

    def upload_public_image(self, local_path, parent_folder_id, filename):
        metadata = {"name": filename, "parents": [parent_folder_id]}
        media = MediaFileUpload(local_path)
        file = self.service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute()
        file_id = file["id"]
        self.service.permissions().create(
            fileId=file_id, body={"type": "anyone", "role": "reader"}
        ).execute()
        return f"https://drive.google.com/uc?export=view&id={file_id}"
