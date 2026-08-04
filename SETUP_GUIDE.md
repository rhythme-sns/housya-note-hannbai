# セットアップ手順書

このリポジトリは、放射線技師note下書きを毎朝自動生成してメール送信するGitHub Actionsワークフローです。
旧・Claude Codeルーティン(`radiology-note-daily-headline`)を、平文ハードコードなしの形で再現したものです。

## 0. 前提: 認証情報のローテーション(最重要)

旧ルーティンの設定に含まれていたOpenAI APIキーとGmailアプリパスワードは、
このチャットの会話ログやツール結果に平文で残っています。**このセットアップの前に、必ず両方を無効化・再発行してください。**

1. OpenAI: https://platform.openai.com/api-keys で古いキーを Revoke し、新しいキーを発行する
2. Gmail (goliath24520@gmail.com): https://myaccount.google.com/apppasswords で古いアプリパスワードを削除し、新しいものを発行する
   - 2段階認証が有効になっている必要があります

新しく発行した値だけを、このあとの手順で使ってください。

## 1. GitHubリポジトリを用意する

- 新規に作る場合: GitHub上で新しいリポジトリを作成(Private推奨)
- 既存リポジトリに追加する場合: このディレクトリの中身をそのままコピー

このフォルダの構成:
```
.github/workflows/daily-note-draft.yml   # cronワークフロー本体
scripts/generate_and_send.py             # 記事生成・画像生成・メール送信スクリプト
state/used_themes.json                   # 過去に使ったテーマの履歴(重複防止用)
requirements.txt
```

## 2. コードをpushする

```bash
git init   # 既存リポジトリなら不要
git add .
git commit -m "add daily note draft automation"
git branch -M main
git remote add origin https://github.com/<あなたのアカウント>/<リポジトリ名>.git
git push -u origin main
```

## 3. GitHub Actions Secretsを登録する

リポジトリの `Settings → Secrets and variables → Actions → New repository secret` から、以下5つを登録してください。値は手順0で再発行したものを使ってください。

| Secret名 | 値 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude APIキー(https://console.anthropic.com/ で発行) |
| `OPENAI_API_KEY` | 再発行したOpenAI APIキー |
| `GMAIL_SENDER` | `goliath24520@gmail.com`(送信元) |
| `GMAIL_APP_PASSWORD` | 再発行したGmailアプリパスワード(スペースを詰めて16文字) |
| `GMAIL_RECIPIENT` | `reon24520@gmail.com`(受信先) |

## 4. Actionsを有効化する

Privateリポジトリで新規作成した場合、`Actions` タブが自動的に有効になっているはずです。なっていない場合は `Settings → Actions → General` で許可してください。

## 5. 動作確認

`Actions` タブ → `Daily Note Draft` ワークフロー → `Run workflow` ボタンで手動実行できます(`workflow_dispatch` を有効にしてあります)。
成功すると:
- 指定した受信メールアドレスに下書きが届く
- `state/used_themes.json` が更新されてリポジトリにコミットされる

失敗した場合はActionsのログにエラーが出るので、Secretsの値やAPIキーの有効性を確認してください。

## スケジュール

`cron: '0 22 * * *'`(22:00 UTC = 07:00 JST 翌朝)で毎日自動実行されます。時刻を変更したい場合は `.github/workflows/daily-note-draft.yml` の `cron` を編集してください(UTC基準です)。

## 補足: 旧ルーティンからの変更点

- OpenAI APIキー・Gmailアプリパスワードは平文ハードコードではなく、GitHub Actions Secrets(暗号化)から注入
- 「過去のnote下書きメールをGmail検索して重複を避ける」処理は、リポジトリ内の `state/used_themes.json` を参照する方式に変更(Gmail検索より確実で、Gmail読み取り権限が不要)
- 記事本文の生成は Claude API (`claude-opus-4-8`) を直接呼び出し、構造化出力(JSON Schema)で確実にパース可能な形式を得ています
