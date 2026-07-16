import tempfile
from pathlib import Path

from .claude_extractor import ExtractionError, extract_from_image
from .config import load_config, missing_required_keys
from .drive_client import DriveClient, get_credentials
from .sheets_client import SheetsClient


def run_processing(log=print):
    config = load_config()
    missing = missing_required_keys(config)
    if missing:
        raise RuntimeError(f"設定が未完了です: {', '.join(missing)}")

    credentials = get_credentials(config["service_account_json_path"])
    drive = DriveClient(credentials)
    sheets = SheetsClient(credentials, config["spreadsheet_id"])
    sheets.ensure_header(config["sheet_name"])

    completed_folder_id = drive.find_or_create_completed_folder(config["root_folder_id"])

    images = drive.list_images(config["target_subfolder_id"])
    result = {"total": len(images), "success": 0, "failed": []}

    if not images:
        log("対象フォルダに画像がありません。")
        return result

    log(f"対象画像 {len(images)} 件を処理します。")

    ext_by_mime = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        for index, image in enumerate(images):
            ext = ext_by_mime.get(image.get("mimeType"), ".png")
            local_path = Path(tmpdir) / f"image_{index}{ext}"
            try:
                drive.download_file(image["id"], str(local_path))
                data = extract_from_image(str(local_path), model=config["claude_model"])
                sheets.append_row(
                    [
                        data["question_number"],
                        data["question_text"],
                        data["choice_a"],
                        data["choice_b"],
                        data["choice_c"],
                        data["choice_d"],
                        data["answer"],
                        image["name"],
                    ],
                    config["sheet_name"],
                )
                drive.move_file(image["id"], config["target_subfolder_id"], completed_folder_id)
                result["success"] += 1
                log(f"OK: {image['name']}")
            except ExtractionError as e:
                result["failed"].append({"name": image["name"], "reason": str(e)})
                log(f"SKIP (抽出失敗): {image['name']} - {e}")
            except Exception as e:
                result["failed"].append({"name": image["name"], "reason": str(e)})
                log(f"SKIP (エラー): {image['name']} - {e}")

    log(f"完了: 成功 {result['success']} / 全体 {result['total']} 件")
    return result
