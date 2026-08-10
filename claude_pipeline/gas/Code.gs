/**
 * text-extraction: claude_pipeline の出力(output/latest.json)をpull型でfetchし、
 * スプレッドシートへ自動で行を追記するGAS。
 *
 * 背景: 従来はローカル(Mac)のbatch.pyがclaude CLIをサブプロセス呼び出ししていたが、
 * CLIが原因不明のエラーで失敗するようになったため、Claudeの作業ルームが直接画像を読み取って
 * output/latest.json を生成する方式に切り替えた(claude_pipeline/README.md 参照)。
 * このGASはその出力をスプレッドシートへ反映する部分だけを担当する。
 *
 * デプロイ手順(ユーザーが一度だけ手動で行う):
 *   1. 対象のスプレッドシートを開き、拡張機能 → Apps Script でこのファイルの内容を貼り付ける
 *   2. 下記の SPREADSHEET_ID / SHEET_NAME を、実際のconfig.jsonの値に合わせて書き換える
 *      (このスクリプトをスプレッドシートに直接バインドした場合は SPREADSHEET_ID は省略可、
 *      その場合は SpreadsheetApp.getActiveSpreadsheet() を使うよう syncFromGithub() 内を調整すること)
 *   3. 動作確認したい場合は syncFromGithub を直接実行する
 *   4. 定期実行したい場合は setupDailyTrigger を一度だけ手動実行する(既存の同名トリガーは
 *      削除して作り直す)
 */

const SPREADSHEET_ID = ""; // config.json の spreadsheet_id をここに設定
const SHEET_NAME = "シート1"; // config.json の sheet_name をここに設定
const OUTPUT_JSON_URL = "https://raw.githubusercontent.com/gurii-gabreh/text-extraction/main/claude_pipeline/output/latest.json";
const HEADER = ["問題番号", "問題文", "選択肢ア", "選択肢イ", "選択肢ウ", "選択肢エ", "正解", "元ファイル名"];

/** メインエントリポイント。手動実行、または時間主導トリガーから呼ばれる想定。 */
function syncFromGithub() {
  const sheet = getSheet_();
  ensureHeader_(sheet);

  const res = UrlFetchApp.fetch(OUTPUT_JSON_URL, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    Logger.log("output/latest.json の取得に失敗しました: %s", res.getResponseCode());
    return { ok: false, error: "fetch failed: " + res.getResponseCode() };
  }
  const data = JSON.parse(res.getContentText());
  const items = data.items || [];

  // 既にシートに追記済みの元ファイル名を集めておき、同じJSONを誤って複数回同期しても
  // 重複行が増えないようにする(このpull型syncはprogress-tracker-dashboardのsyncFromGithub()と
  // 同じ設計思想: 何度実行しても安全なべき等な同期にする)。
  const existingFilenames = collectExistingFilenames_(sheet);

  let appended = 0;
  let skipped = 0;
  items.forEach(function (item) {
    const filename = item.source_filename || "";
    if (filename && existingFilenames[filename]) {
      skipped++;
      return;
    }
    sheet.appendRow([
      item.question_number || "",
      item.question_text || "",
      item.choice_a || "",
      item.choice_b || "",
      item.choice_c || "",
      item.choice_d || "",
      item.answer || "",
      filename,
    ]);
    if (filename) existingFilenames[filename] = true;
    appended++;
  });

  Logger.log("同期完了: %s件追記、%s件スキップ(既存)", appended, skipped);
  return { ok: true, appended: appended, skipped: skipped };
}

function getSheet_() {
  const ss = SPREADSHEET_ID ? SpreadsheetApp.openById(SPREADSHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(SHEET_NAME);
  return sheet;
}

function ensureHeader_(sheet) {
  const firstRow = sheet.getRange(1, 1, 1, HEADER.length).getValues()[0];
  const isEmpty = firstRow.every(function (v) { return v === ""; });
  if (isEmpty) sheet.getRange(1, 1, 1, HEADER.length).setValues([HEADER]);
}

/** 「元ファイル名」列(H列)の既存値を { ファイル名: true } の形で集める */
function collectExistingFilenames_(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return {};
  const values = sheet.getRange(2, HEADER.length, lastRow - 1, 1).getValues();
  const seen = {};
  values.forEach(function (row) {
    const filename = row[0];
    if (filename) seen[filename] = true;
  });
  return seen;
}

/**
 * 定期実行したい場合、一度だけ手動実行してください(既存の同名トリガーは削除して作り直します)。
 * デフォルトは毎日07:00 JST頃(実データ処理の作業ルームが動いた後を想定)。
 */
function setupDailyTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "syncFromGithub") ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger("syncFromGithub")
    .timeBased()
    .atHour(7)
    .nearMinute(0)
    .everyDays(1)
    .inTimezone("Asia/Tokyo")
    .create();
  Logger.log("日次トリガーを設定しました(毎日07:00 JST頃に syncFromGithub を実行)");
}
