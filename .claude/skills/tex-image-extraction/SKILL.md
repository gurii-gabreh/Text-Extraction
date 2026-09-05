---
name: tex-image-extraction
description: Transcribe a folder of quiz/exam screenshot images (Google Drive) into a structured spreadsheet — question number, question text, choices, and answer — cropping any diagrams/tables/graphs that would lose meaning as plain text. Use this whenever the user asks to process a Google Drive image folder for gurii-gabreh/Text-Extraction, mentions "TEX-" task IDs, asks to transcribe quiz/exam question screenshots into a spreadsheet, or references the 基本情報技術者試験 (or similar) image-to-spreadsheet workflow. Trigger even if they just paste a Drive folder URL and say "like before" or "同じ手順で" without restating the full spec — this skill IS that spec.
---

# TEX image extraction (Text-Extraction repo)

Turn a Google Drive folder of quiz-question screenshots into a spreadsheet, using your own image-reading ability directly (no local Python/CLI pipeline, no GAS). This replaces an older local `batch.py` → claude CLI subprocess pipeline that started failing unpredictably, and an even older JSON+GAS pipeline (`claude_pipeline/`) that was abandoned because running two sync paths into the same spreadsheet caused conflicts. Neither should be revived — do the extraction yourself, write straight to a new spreadsheet.

## Why this shape

Every field extracted here maps directly to a spreadsheet column, and the crop/no-crop decision is what keeps information from being silently lost when a diagram gets flattened into a text description. Get that decision right per-image and everything else is mechanical.

## Steps

1. **List the images** in the target Drive folder (`search_files` with `parentId = '<folder id>'`). Note the total count — this is what "success + failure" must add up to at the end.

2. **Read each image directly** (the Read tool renders images) and extract:
   - `question_number` (第◯問)
   - `question_text` — the question body only. Skip metadata rows and mock-exam progress indicators (e.g. "◯問目/80問", timers).
   - `choice_a` … `choice_d` (ア/イ/ウ/エ), label stripped, text only — unless the choice itself is a diagram (see crop rules below), in which case the cell holds only the label character.
   - `answer` — the single character immediately after "正解：". Ignore "あなたの解答：" (that's the site's own answer-key display, not ground truth to report).
   - Stop reading at "分類：" / "解説：" — content after that point is out of scope, don't transcribe it, don't let it influence the answer.

3. **Handle images missing a required field** (question_text or answer). Some source folders split one question across two adjacent screenshots (e.g. question+choices on one, answer+explanation on the next); others don't split at all — you won't know which pattern a given folder uses until you're partway through it, so check every image, don't assume. When a field is missing:
   - Sort images by the timestamp embedded in the filename (e.g. `screenshot_2026-08-30T02-12-27-174Z...`) to get chronological order.
   - Check the immediately adjacent image(s) in that order. If choice_a–d match exactly, treat it as the same question split across images and merge.
   - If nothing adjacent matches, mark the image as processed-but-failed (don't drop it silently) and record why. The final report's "success + failure" count must equal the total image count — there's no third bucket.

4. **Decide crop vs. transcribe for any figure**, per image:
   - Crop when the image contains a diagram, graph, handwritten figure, or UI screenshot — anything where flattening to a text description would lose real information (topology, exact shape, spatial relationships). Recent examples: a logic-circuit diagram *as* the four answer choices, a UML class diagram, a PERT/arrow diagram with dummy-task dashed lines.
   - Transcribe as text (no crop) when it's a table or numeric grid that maps cleanly to rows/columns with nothing lost — code tables, probability tables, unit-price ledgers, etc. When in doubt, ask: "if I typed this out as text, would a reader reconstruct the exact same picture?" If yes, type it. If no, crop it.
   - If the choices themselves are the figure (not just the question stem), include the choice region in the same crop as the question figure where possible; the choice cells in the spreadsheet then hold only ア/イ/ウ/エ.
   - Crop tight but complete — include any legend/key that's part of reading the diagram (e.g. a PERT chart's "凡例" box).
   - After cropping, re-save the PNG through a palette-quantization pass before uploading — `Image.open(f).convert('P', palette=Image.ADAPTIVE, colors=16)` — this typically cuts file size ~70-80% with no visible quality loss, and keeps the image well under the ~25k-token cap for reading it back to verify. Read the optimized crop back before uploading to confirm it's still fully legible.

5. **Upload crops** to a new subfolder inside the *source* Drive folder (reuse an existing crops subfolder if the folder already has one from a prior run instead of creating a second one), then put that image's URL in the spreadsheet's "問題文画像" column for that row only.

6. **Build the output.** Columns, in order: 問題番号, 問題文, 選択肢ア, 選択肢イ, 選択肢ウ, 選択肢エ, 正解, 元ファイル名, 問題文画像 (blank when no crop). If a question legitimately has more than 4 choices, add 選択肢オ/カ/… columns rather than dropping the extras. Include every image's outcome, success or failure — don't silently omit failures from the sheet.

7. **Create a new Google Sheet** (Google_Drive `create_file`, `mimeType: application/vnd.google-apps.spreadsheet` or upload CSV with `contentMimeType: text/csv` and let it auto-convert) inside the same Drive folder as the source images. Verify the written content with `read_file_content` before calling it done — don't trust the create call's response alone.

8. **Register the result in progress-tracker-dashboard**: add or update a TEX-NNN entry in `data/tasks.json` (find the next free number by grepping existing `TEX-` ids) with `status: "完了"`, the new spreadsheet URL in `output`, a `detail` describing the success/failure breakdown and which questions needed crops (and why), and a `checkHistory` entry. Commit and push to main (fetch/rebase first if the remote moved).

9. **Report to the user**: total processed, success count, failure count (with reasons), how many needed crops and which questions, and the new spreadsheet URL.

## Practical notes from running this before

- Downloading many Drive images individually produces one tool-result file per image under `tool-results/`; a small Python script that globs those files, matches by the file's `id` field against a manifest (fileId → order-in-sequence, from the timestamp sort), and decodes+writes each to `order_fileId.png` — tracked via a `{fileId: outputPath}` ledger so re-running the script after fetching more images only processes what's new — is far less error-prone than doing this by hand per image. Get the manifest sort right before you start; re-sorting mid-run is how mismatches happen.
- When reading many images in a row, batches of 3-4 Read calls per turn keeps output manageable without losing the thread on which image is which.
- MCP servers (Google_Drive especially) can disconnect/reconnect mid-task in this environment. If a deferred-tool notice appears, reload via ToolSearch and retry the specific call that failed — don't restart the whole batch.
