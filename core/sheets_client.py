from googleapiclient.discovery import build

OLD_HEADER = ["問題番号", "問題文", "選択肢ア", "選択肢イ", "選択肢ウ", "選択肢エ", "正解", "元ファイル名"]
HEADER = OLD_HEADER + ["問題文画像"]


class SheetsClient:
    def __init__(self, credentials, spreadsheet_id):
        self.service = build("sheets", "v4", credentials=credentials)
        self.spreadsheet_id = spreadsheet_id

    def ensure_header(self, sheet_name):
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=f"{sheet_name}!A1:I1"
        ).execute()
        existing = result.get("values")
        if not existing:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                body={"values": [HEADER]},
            ).execute()
        elif existing[0] == OLD_HEADER:
            # 既存シートに新しい列を追記する（既存データの列はそのまま変更しない）
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                body={"values": [HEADER]},
            ).execute()

    def append_row(self, row, sheet_name):
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
