from googleapiclient.discovery import build

HEADER = ["問題番号", "問題文", "選択肢ア", "選択肢イ", "選択肢ウ", "選択肢エ", "正解", "元ファイル名"]


class SheetsClient:
    def __init__(self, credentials, spreadsheet_id):
        self.service = build("sheets", "v4", credentials=credentials)
        self.spreadsheet_id = spreadsheet_id

    def ensure_header(self, sheet_name):
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=f"{sheet_name}!A1:H1"
        ).execute()
        if not result.get("values"):
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
