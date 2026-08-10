# claude_pipeline

`batch.py`(ローカルのPythonスクリプトが `claude` CLI をサブプロセス呼び出しする方式)が、
CLI側の原因不明のエラー(`code=1`、エラーメッセージ空)で全件失敗するようになったため、
Claudeの作業ルーム自身の画像読み取り能力で直接処理する新しい方式として、このディレクトリを新設した。

既存の `core/*.py` / `batch.py` / `app.py`(ローカルPythonパイプライン)とは意図的に分離しており、
このディレクトリの仕組みが安定するまで既存パイプラインは変更していない。

## 全体の流れ

```
1. 作業ルームが対象フォルダの画像を直接読み取り、問題を抽出する
2. 抽出結果を output/latest.json として出力する(このリポジトリへコミット・push)
3. review.html で、スプレッドシートに書き込まれる前に内容をレビューする(任意)
4. gas/Code.gs が output/latest.json をpull型でfetchし、スプレッドシートへ追記する
   (デプロイ後は手動実行 or 日次トリガーで自動実行)
```

JSON → GAS → スプレッドシート という構成は、姉妹リポジトリ
[gurii-gabreh/progress-tracker-dashboard](https://github.com/gurii-gabreh/progress-tracker-dashboard)
(`gas/Code.gs` の `syncFromGithub()`)や
[gurii-gabreh/Knowledge-Dashboard](https://github.com/gurii-gabreh/Knowledge-Dashboard)
(`gas/update-spreadsheets.gs`)と同じパターンを踏襲している。

## ディレクトリ構成

```
claude_pipeline/
├── output/
│   ├── latest.json     # 最新の実行結果(このファイルをGAS・review.htmlが参照する)
│   ├── sample.json      # スキーマ確認用のサンプルデータ(3件、うち1件はわざと欠損フィールドあり)
│   └── archive/          # 過去の実行結果を <実行日時>.json として保存する場所(任意)
├── review.html           # output/latest.json を一覧表示し、欠損フィールドを警告するレビューページ
├── gas/
│   └── Code.gs            # output/latest.json をpull fetchしてスプレッドシートへ追記するGAS
└── README.md              # このファイル
```

## output/latest.json のスキーマ

```json
{
  "generatedAt": "実行日時(ISO8601)",
  "sourceFolder": "処理対象のGoogleドライブフォルダURL",
  "items": [
    {
      "question_number": "第◯問",
      "question_text": "問題文本文(メタ情報・模擬試験進捗表示は除外、「分類：」「解説：」以降は対象外)",
      "choice_a": "選択肢アの本文(ラベル除く)",
      "choice_b": "選択肢イの本文",
      "choice_c": "選択肢ウの本文",
      "choice_d": "選択肢エの本文",
      "answer": "「正解：」直後の1文字(ア〜エ)。「あなたの解答：」は無視",
      "source_filename": "元ファイル名。1問が2枚の画像に分割されていた場合はカンマ区切りで両方記録する(例: sample_0002.png,sample_0003.png)"
    }
  ]
}
```

スプレッドシートの既存の列構成(`問題番号,問題文,選択肢ア〜エ,正解,元ファイル名`)にそのまま対応する。

## 実行のたびのファイル運用

- 作業ルームは処理結果を `output/latest.json` として**上書き**する(GAS・review.htmlが常に固定のURL/パスを参照できるようにするため)
- 同時に、`output/archive/<実行日時、例: 2026-08-10T15-30-00>.json` としても同じ内容を保存し、過去の実行結果を追跡できるようにする(任意、無くても動作に支障は無い)
- 未処理のまま残った画像(必須項目が欠けたまま前後の画像と統合できなかったもの)は `items` に含めず、対象フォルダにそのまま残す(現行の `batch.py` と同じ挙動)

## GAS (`gas/Code.gs`) のデプロイ手順(ユーザーが一度だけ手動で行う)

1. 出力先のGoogleスプレッドシートを開き、拡張機能 → Apps Script で `gas/Code.gs` の内容を貼り付ける
2. ファイル先頭付近の `SPREADSHEET_ID` / `SHEET_NAME` を、実際の `config.json` の値(`spreadsheet_id` / `sheet_name`)に合わせて書き換える
   (このスクリプトをスプレッドシートに直接バインドして作成した場合は `SPREADSHEET_ID` は空のままでよい)
3. 動作確認したい場合は、エディタの関数選択ドロップダウンで `syncFromGithub` を選び、直接実行する
4. 定期的に自動反映したい場合は `setupDailyTrigger` を一度だけ手動実行する(毎日07:00 JST頃に `syncFromGithub` が走るようになる)

`syncFromGithub` は「元ファイル名」列の既存値を見て、同じ画像に対応する行を二重に追記しないようになっている(同じ `output/latest.json` に対して誤って複数回実行しても安全)。

## review.html の使い方

`output/latest.json` と同じ階層に置いた状態でブラウザで直接開く(または、このリポジトリをGitHub Pages等で公開している場合はそのURLで開く)。件数・欠損フィールドのある問題数が上部に表示され、各カードで問題文・選択肢・正解をプレビューできる。まだ実行結果が無い場合は `output/sample.json` を `output/latest.json` としてコピーすれば表示を確認できる。

## 今後実データ処理を行うセッションへの申し送り

- Google Drive/Sheetsへのアクセスには認証情報(`credentials/service_account.json` の中身、および実際の `config.json` の値)が必要。これらは `.gitignore` 対象でリポジトリに含まれずローカル専用のため、依頼者からこのチャットへ直接貼り付けてもらうなど、別の受け渡し方法を確認してから進めること
- 抽出ロジック(問題番号・問題文・選択肢・正解の切り出しルール、画像分割時の統合ルール)は、現行の `core/claude_extractor.py` のプロンプト・`README.md`「6. 処理内容」を踏襲する
