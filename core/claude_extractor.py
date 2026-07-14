import json
import subprocess

SCHEMA = {
    "type": "object",
    "properties": {
        "question_number": {"type": "string"},
        "question_text": {"type": "string"},
        "choice_a": {"type": "string"},
        "choice_b": {"type": "string"},
        "choice_c": {"type": "string"},
        "choice_d": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": [
        "question_number",
        "question_text",
        "choice_a",
        "choice_b",
        "choice_c",
        "choice_d",
        "answer",
    ],
}

PROMPT_TEMPLATE = """Read the image at {image_path}.
This is a screenshot from a Japanese IT certification exam practice site
("基本情報技術者試験 過去問道場"). Extract the following, reading top to bottom:

- question_number: the line matching the pattern 第◯問 (e.g. 第3問). Ignore
  metadata lines like 令和◯年度 or ◯問目／◯問.
- question_text: all lines after the question number line and before the
  first choice line (lines starting with ア/イ/ウ/エ), excluding metadata
  lines such as 令和◯年度 or ◯問目／◯問. Join multiple lines with \\n.
- choice_a / choice_b / choice_c / choice_d: the text of the lines starting
  with ア / イ / ウ / エ respectively, with the leading kana marker removed.
- answer: the single character immediately after "正解：" (on the same line
  or the next line).

Stop reading once you reach a line starting with 分類： or 解説： — do not
use any text from those lines or anything after them.

If a value cannot be determined, use the exact string "UNREADABLE" for that
field. Output only the extracted data matching the provided schema."""


class ExtractionError(Exception):
    pass


def extract_from_image(image_path, model="sonnet", timeout=120):
    cmd = [
        "claude",
        "-p",
        PROMPT_TEMPLATE.format(image_path=image_path),
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA),
        "--tools",
        "Read",
        "--model",
        model,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ExtractionError(f"claude CLI がタイムアウトしました（{timeout}秒）")

    if proc.returncode != 0:
        raise ExtractionError(f"claude CLI が異常終了しました（code={proc.returncode}）: {proc.stderr}")

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"claude CLIの出力がJSONとして解釈できません: {e}\nstdout={proc.stdout}")

    if envelope.get("is_error"):
        raise ExtractionError(f"claude CLIがエラーを報告しました: {envelope}")

    result_text = envelope.get("result")
    if not result_text:
        raise ExtractionError(f"claude CLIの出力にresultがありません: {envelope}")

    try:
        data = json.loads(result_text)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"抽出結果がJSONとして解釈できません: {e}\nresult={result_text}")

    for key in SCHEMA["properties"]:
        if not data.get(key) or data.get(key) == "UNREADABLE":
            raise ExtractionError(f"項目 '{key}' を画像から読み取れませんでした")

    return data
