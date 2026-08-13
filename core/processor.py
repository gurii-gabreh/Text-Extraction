import tempfile
from pathlib import Path

from PIL import Image

from .claude_extractor import SCHEMA, ExtractionError, extract_from_image
from .config import load_config, missing_required_keys
from .drive_client import DriveClient, get_credentials
from .sheets_client import SheetsClient

TEXT_FIELDS = [k for k in SCHEMA["properties"] if k != "image_regions"]
CHOICE_FIELDS = ["choice_a", "choice_b", "choice_c", "choice_d"]
CROP_MARGIN_PERCENT = 4


def _is_readable(value):
    return bool(value) and value != "UNREADABLE"


def _is_complete(data):
    return all(_is_readable(data.get(key)) for key in TEXT_FIELDS)


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
    for key in TEXT_FIELDS:
        va = primary.get(key)
        vb = partner.get(key)
        if _is_readable(va):
            merged[key] = va
        elif _is_readable(vb):
            merged[key] = vb
        else:
            merged[key] = va or "UNREADABLE"

    if primary.get("image_regions"):
        merged["image_regions"] = primary["image_regions"]
        merged["image_source"] = "primary"
    elif partner.get("image_regions"):
        merged["image_regions"] = partner["image_regions"]
        merged["image_source"] = "partner"
    else:
        merged["image_regions"] = []
        merged["image_source"] = None
    return merged


def _combined_crop_box(image_regions, width, height):
    top = min(r["top"] for r in image_regions)
    left = min(r["left"] for r in image_regions)
    bottom = max(r["bottom"] for r in image_regions)
    right = max(r["right"] for r in image_regions)

    top = max(0, top - CROP_MARGIN_PERCENT)
    left = max(0, left - CROP_MARGIN_PERCENT)
    bottom = min(100, bottom + CROP_MARGIN_PERCENT)
    right = min(100, right + CROP_MARGIN_PERCENT)

    return (
        int(left / 100 * width),
        int(top / 100 * height),
        int(right / 100 * width),
        int(bottom / 100 * height),
    )


def _crop_and_upload(drive, source_path, image_regions, images_folder_id, filename):
    with Image.open(source_path) as img:
        box = _combined_crop_box(image_regions, img.width, img.height)
        cropped = img.crop(box)
        crop_path = Path(source_path).parent / f"tmp_{filename}"
        cropped.save(crop_path)
    return drive.upload_public_image(str(crop_path), images_folder_id, filename)


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
    images_folder_id = drive.find_or_create_images_folder(config["root_folder_id"])

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

            image_url = ""
            image_regions = merged.get("image_regions")
            if image_regions:
                if partner_index is None:
                    image_source_index = index
                else:
                    image_source_index = index if merged.get("image_source") == "primary" else partner_index
                try:
                    crop_filename = f"crop_{Path(images[image_source_index]['name']).stem}.png"
                    image_url = _crop_and_upload(
                        drive,
                        local_path_for(image_source_index),
                        image_regions,
                        images_folder_id,
                        crop_filename,
                    )
                except Exception as e:
                    log(f"WARN: 画像切り抜き・アップロードに失敗しました（テキストのみ登録します）: {image['name']} - {e}")

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
                        image_url,
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
