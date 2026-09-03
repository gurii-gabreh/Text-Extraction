# Text Extraction

「基本情報技術者試験 過去問道場」のスクリーンショット画像から、Claude Code（`claude -p`）を使って
問題番号・問題文・選択肢ア〜エ・正解をテキストとして抽出し、Googleスプレッドシートに記録するツールです。
処理済みの画像はGoogleドライブ上の「処理済み」フォルダへ自動的に移動します。

## 1. 前提条件

- Python 3.9以上
- `claude` コマンド（Claude Code CLI）がインストール済みで、ログイン済みであること
  （`claude auth` の状態を確認してください。Claude Codeの契約プラン、または
  `ANTHROPIC_API_KEY` でのAPIキー認証のいずれかでログインしている必要があります）

## 2. Pythonライブラリのインストール

仮想環境の使用を推奨します（システムのPython環境との依存関係の衝突を避けるため）。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Google Cloud側の準備（サービスアカウント作成）

Googleドライブ・スプレッドシートへのアクセスに、サービスアカウントを使用します。
（今回はVision APIを使わないため、請求先アカウント［クレジットカード］の登録は基本的に不要です）

1. [Google Cloud Console](https://console.cloud.google.com/) で新規プロジェクトを作成
2. 「APIとサービス」→「ライブラリ」から以下の2つを有効化
   - Google Drive API
   - Google Sheets API
3. 「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」を選択し、作成
4. 作成したサービスアカウントの詳細画面 →「キー」タブ →「鍵を追加」→「新しい鍵を作成」→ JSON形式でダウンロード
5. ダウンロードしたJSONファイルを、このプロジェクトの `credentials/` フォルダに配置
   （ファイル名は変更しなくて構いません。Web設定画面でパスを指定します）
6. サービスアカウントのメールアドレス（JSONファイル内の `client_email`）を確認し、以下2箇所に「編集者」として共有してください
   - 対象のGoogleドライブのルートフォルダ
   - 出力先のGoogleスプレッドシート

## 4. Webアプリの起動

```bash
python app.py
```

ブラウザで `http://127.0.0.1:5000` を開き、以下を設定します。

- サービスアカウントJSONのパス（例: `credentials/service_account.json`）
- ルートフォルダID（GoogleドライブのフォルダURLの末尾部分）
- 処理対象サブフォルダ（「サブフォルダ一覧を取得」ボタンで一覧表示され、クリックで選択できます）
- 出力先スプレッドシートID（スプレッドシートURLの末尾部分）
- シート名（デフォルト: `シート1`）

設定後、「今すぐ処理実行」ボタンで手動実行できます。

## 5. 定時実行の設定

定時実行の方式は2通りあります。どちらか一方を選んでください（二重実行を避けるため）。

### 5-1. MacBookのcronから実行

Webアプリを常時起動しておく必要はありません。`batch.py` を直接cronから呼び出します。

```bash
crontab -e
```

例（毎日9時に実行）:

```
0 9 * * * cd /path/to/text-extraction && /usr/bin/python3 batch.py >> logs/batch.log 2>&1
```

`logs/` フォルダは事前に作成しておいてください（`mkdir logs`）。

この方式では、`credentials/` フォルダのサービスアカウントJSONファイルをそのまま使用します。

### 5-2. Claude Code RemoteのRoutine（クラウド定時トリガー）から実行

MacBookがスリープ・オフの状態でも定時実行したい場合は、Claude Code RemoteのRoutine機能を使ってクラウド上で実行できます。クラウド実行にはローカルの認証情報ファイルが存在しないため、サービスアカウントJSONの中身を環境変数 `GOOGLE_SERVICE_ACCOUNT_JSON` に設定してください（`get_credentials()` は環境変数が設定されていればそちらを優先し、なければ従来通りファイルパスから読み込みます）。

1. Claude Code RemoteでEnvironmentを用意し、環境変数 `GOOGLE_SERVICE_ACCOUNT_JSON` にサービスアカウントJSONファイルの中身をそのまま設定する
2. そのEnvironment・このリポジトリに対して、`pip install -r requirements.txt` の後に `python batch.py` を実行するRoutine（定時トリガー）を作成する
3. Web画面のヘッダーにある「定時実行(Routine)の実行時刻」欄で希望の時刻を設定・保存できます。ただし、この欄はこのアプリ内の表示・記録用であり、Routine自体のスケジュールは自動更新されません。時刻を変更したい場合は「Routine変更依頼文を作成」ボタンで依頼文を作成し、それをClaudeに渡してRoutineのスケジュール変更を依頼してください
4. クラウド実行はユーザーのClaude Pro/Maxプランの利用上限（レートリミット）を消費します。通常のClaude Code利用と共有される点に注意してください

なお、クラウド実行はユーザーのプラン利用上限を消費するため、常時起動しているMacがある場合は5-1のcron方式を継続するのも選択肢です。

## 6. 処理内容

1. 処理対象サブフォルダ内の画像を一覧取得
2. 各画像について `claude -p`（Read専用ツール、JSON Schemaによる構造化出力）でテキストを抽出
   - 抽出対象: 問題番号（第◯問）、問題文、選択肢ア〜エ、正解
   - 「分類：」「解説：」以降は読み取り対象外
   - 問題文・選択肢中に表や図（手書き図・グラフ・UIスクリーンショット等、テキスト化すると情報が失われるもの）がある場合、その領域をPillowで切り抜き、Googleドライブへアップロードして「問題文画像」列にURLを記載する（選択肢自体が図の場合は選択肢欄にラベル文字のみを記載）
   - 1枚の画像だけでは問題文・正解などの必須項目が欠ける場合、ファイル名の時刻順で前後の画像を確認し、選択肢が完全一致すれば同一問題として統合する（1問が2枚のスクリーンショットに分割されるケースへの対処）
3. 抽出できた画像はスプレッドシートに1行追記し、Googleドライブ上の「処理済み」フォルダへ移動
4. 抽出に失敗した画像（前後の画像と組み合わせても必須項目が揃わない場合を含む）はスキップし、対象サブフォルダにそのまま残す（ログに失敗理由を記録）
5. 1回の実行に処理枚数の上限は設けていません（対象サブフォルダ内の全件を毎回処理します）

## 7. 運用方法の変遷（履歴）

`claude -p` サブプロセス呼び出し（本READMEの前提の方式）が、ローカルCLI側の認証切れ等が
原因で不安定になった経緯から、別の実行方式がいくつか試され、最終的に撤回されたものがある。
将来同じ検討を繰り返さないよう、経緯を記録する。

- **2026-08時点、試行→撤回: `claude_pipeline/`（JSON出力 + GAS + レビューHTML方式）**
  `batch.py`のCLIエラーを受け、作業ルーム（Claude Codeのクラウドセッション）が直接画像を
  読み取り、結果をJSONで出力 → GAS(`gas/Code.gs`)がそのJSONをpull取得してスプレッドシートへ
  書き込む、という中継構成が別ブランチ（`claude/app-creation-resources-eenb15`、PR #1）で
  実装された。認証情報（`credentials/service_account.json`・`config.json`）がgitignore対象で
  クラウド側から参照できず、実データでの動作確認がされないまま停滞した。
  最終的に、GASという中継を挟まずマネージャアプリ経由で完結させる方式（下記）に統一する
  ことになり、`claude_pipeline/`一式は撤回・削除された。
- **現在の方針: マネージャアプリ（`progress-tracker-dashboard`）経由での運用**
  ローカルCLI・クラウドRoutineいずれも不安定になった場合の代替として、
  `gurii-gabreh/progress-tracker-dashboard`の依頼タスクタブに処理を依頼する運用がある
  （タスクID: `TEX-001`＝直近の失敗画像分、`TEX-002`＝標準の定期処理テンプレート）。
  この方式では、作業ルーム（Claude Codeのクラウドセッション）が対象フォルダの画像を直接
  読み取り、**新規のGoogleスプレッドシート（またはExcelファイル）を作成してそこへ直接
  出力する**（GAS・サービスアカウント認証情報のいずれも不要）。切り抜き画像は元画像の
  フォルダ内に新規サブフォルダを作って保存する。出力された新規スプレッドシートの内容は、
  ユーザーが本来の管理用スプレッドシートへ手動で転記する。
  依頼文の詳細・最新版は `progress-tracker-dashboard` の依頼タスクタブ（TEX-001/TEX-002）を
  参照。

## ディレクトリ構成

```
text-extraction/
├── app.py                    # Flask Webアプリ（フォルダ設定・実行ボタン）
├── batch.py                  # cron実行用バッチスクリプト
├── core/
│   ├── config.py              # 設定の読み書き（config.json）
│   ├── drive_client.py        # Google Drive操作
│   ├── sheets_client.py       # Googleスプレッドシート書き込み
│   ├── claude_extractor.py    # claude -p 呼び出し・構造化抽出
│   └── processor.py           # 全体処理フロー（Web/cron共通）
├── templates/
│   └── index.html             # 設定・実行画面
├── credentials/                 # サービスアカウントJSON配置場所（gitignore対象）
├── config.example.json          # 設定ファイルのひな形
└── requirements.txt
```
