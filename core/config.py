import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_CONFIG = {
    "root_folder_id": "",
    "target_subfolder_id": "",
    "target_subfolder_name": "",
    "spreadsheet_id": "",
    "sheet_name": "シート1",
    "service_account_json_path": "credentials/service_account.json",
    "claude_model": "sonnet",
    "batch_schedule_hour": "9",
}

REQUIRED_KEYS = [
    "root_folder_id",
    "target_subfolder_id",
    "spreadsheet_id",
    "service_account_json_path",
]


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULT_CONFIG, **data}
    return dict(DEFAULT_CONFIG)


def save_config(config):
    merged = {**DEFAULT_CONFIG, **config}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def missing_required_keys(config):
    return [key for key in REQUIRED_KEYS if not config.get(key)]
