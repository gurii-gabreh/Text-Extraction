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

PROMPT_TEMPLATE = """Read the image file located at exactly this path (the path may
contain spaces; use it verbatim, do not truncate or reinterpret it):

  "{image_path}"

This is a screenshot from a Japanese IT certification exam practice site
("基本情報技術者試験 過去問道場"). Extract the following:

- question_number: the line matching the pattern 第◯問 (e.g. 第3問), near the
  top of the image.
- question_text: the question body text below the question number and above
  the choices (ア/イ/ウ/エ). Exclude metadata lines/labels such as
  令和◯年度、問◯、◯問目／◯問 or similar, wherever they appear (they may be
  to the right of the question text rather than on their own line). Join
  multiple lines with \\n.
- choice_a / choice_b / choice_c / choice_d: the text of the four answer
  choices, each labeled with ア / イ / ウ / エ (the labels may appear inside
  boxes to the left of each choice's text). Return the choice text only,
  without the kana label.
- answer: the single character shown immediately next to the "正解：" label.
  This label appears after the choices, near a "分類：" label and a
  "解説：" label. Do NOT use the text next to "あなたの解答：" — that is a
  different, unrelated value and must be ignored.

Do not extract any field's value from the content under the 分類： or 解説：
labels themselves — those sections only exist to help you locate 正解：, not
as a source of data. Stop reading entirely once you pass the 解説： label.

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
        "--dangerously-skip-permissions",
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
            denials = envelope.get("permission_denials")
            raise ExtractionError(
                f"項目 '{key}' を画像から読み取れませんでした\n"
                f"  抽出結果全体: {data}\n"
                f"  permission_denials: {denials}"
            )

    return data
