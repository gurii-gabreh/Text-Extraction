from flask import Flask, jsonify, render_template, request

from core.config import load_config, missing_required_keys, save_config
from core.drive_client import DriveClient, get_credentials
from core.processor import run_processing

app = Flask(__name__)


@app.route("/")
def index():
    config = load_config()
    return render_template("index.html", config=config, missing=missing_required_keys(config))


@app.route("/settings", methods=["POST"])
def settings():
    config = load_config()
    for key in [
        "root_folder_id",
        "target_subfolder_id",
        "target_subfolder_name",
        "spreadsheet_id",
        "sheet_name",
        "service_account_json_path",
        "claude_model",
        "batch_schedule_hour",
    ]:
        value = request.form.get(key)
        if value is not None and value != "":
            config[key] = value
    save_config(config)
    return jsonify({"ok": True, "config": config})


@app.route("/api/subfolders")
def api_subfolders():
    parent_id = request.args.get("parent_id", "").strip()
    if not parent_id:
        return jsonify({"ok": False, "error": "root_folder_id が未入力です"}), 400

    config = load_config()
    try:
        credentials = get_credentials(config["service_account_json_path"])
        drive = DriveClient(credentials)
        folders = drive.list_subfolders(parent_id)
        return jsonify({"ok": True, "folders": folders})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/run", methods=["POST"])
def run():
    logs = []

    def log(msg):
        print(msg, flush=True)
        logs.append(msg)

    try:
        result = run_processing(log=log)
        return jsonify({"ok": True, "result": result, "logs": logs})
    except Exception as e:
        logs.append(f"エラー: {e}")
        return jsonify({"ok": False, "error": str(e), "logs": logs}), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
