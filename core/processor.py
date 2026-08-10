import tempfile
from pathlib import Path

from .claude_extractor import SCHEMA, ExtractionError, extract_from_image
from .config import load_config, missing_required_keys
from .drive_client import DriveClient, get_credentials
from .sheets_client import SheetsClient

FIELDS = list(SCHEMA["properties"].keys())
CHOICE_FIELDS = ["choice_a", "choice_b", "choice_c", "choice_d"]


def _is_readable(value):
    return bool(value) and value != "UNREADABLE"


def _is_complete(data):
    return all(_is_readable(data.get(key)) for key in FIELDS)


def _choices_match(a, b):
    for key in CHOICE_FIELDS:
        va, vb = a.get(key), b.get(key)
        if not _is_readable(va) or not _is_readable(vb):
            return False
        if va.strip() != vb.strip():
            return False
    return True


def _merge(primary, partner):
    merged = {}
    for key in FIELDS:
        va = primary.get(key)
        vb = partner.get(key)
        if _is_readable(va):
            merged[key] = va
        elif _is_readable(vb):
            merged[key] = vb
        else:
            merged[key] = va or "UNREADABLE"
    return merged


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
        extracted_cache = {}
        consumed = set()

        def local_path_for(index):
            ext = ext_by_mime.get(images[index].get("mimeType"), ".png")
            return Path(tmpdir) / f"image_{index}{ext}"

        def get_extraction(index):
            if index not in extracted_cache:
                path = local_path_for(index)
                if not path.exists():
                    drive.download_file(images[index]["id"], str(path))
                extracted_cache[index] = extract_from_image(str(path), model=config["claude_model"])
            return extracted_cache[index]

        for index, image in enumerate(images):
            if index in consumed:
                continue
            try:
                data = get_extraction(index)
            except ExtractionError as e:
                result["failed"].append({"name": image["name"], "reason": str(e)})
                log(f"SKIP (抽出失敗): {image['name']} - {e}")
                continue
            except Exception as e:
                result["failed"].append({"name": image["name"], "reason": str(e)})
                log(f"SKIP (エラー): {image['name']} - {e}")
                continue

            merged = data
            partner_index = None
            if not _is_complete(data):
                for candidate in (index + 1, index - 1):
                    if candidate < 0 or candidate >= len(images) or candidate in consumed:
                        continue
                    try:
                        candidate_data = get_extraction(candidate)
                    except (ExtractionError, Exception):
                        continue
                    if _choices_match(data, candidate_data):
                        candidate_merged = _merge(data, candidate_data)
                        if _is_complete(candidate_merged):
                            merged = candidate_merged
                            partner_index = candidate
                            break

            if not _is_complete(merged):
                reason = "問題文または正解を読み取れませんでした（前後の画像と組み合わせても不足）"
                result["failed"].append({"name": image["name"], "reason": reason})
                log(f"SKIP (抽出失敗): {image['name']} - {reason}")
                continue

            try:
                source_name = image["name"]
                if partner_index is not None:
                    source_name = f"{image['name']} + {images[partner_index]['name']}"
                sheets.append_row(
                    [
                        merged["question_number"],
                        merged["question_text"],
                        merged["choice_a"],
                        merged["choice_b"],
                        merged["choice_c"],
                        merged["choice_d"],
                        merged["answer"],
                        source_name,
                    ],
                    config["sheet_name"],
                )
                drive.move_file(image["id"], config["target_subfolder_id"], completed_folder_id)
                if partner_index is not None:
                    drive.move_file(
                        images[partner_index]["id"], config["target_subfolder_id"], completed_folder_id
                    )
                    consumed.add(partner_index)
                result["success"] += 1
                log(f"OK: {source_name}")
            except Exception as e:
                result["failed"].append({"name": image["name"], "reason": str(e)})
                log(f"SKIP (書き込みエラー): {image['name']} - {e}")

    log(f"完了: 成功 {result['success']} / 全体 {result['total']} 件")
    return result
