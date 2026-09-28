# 自分のFXライブ配信サイトを作る

MT4のEA（VPS上）から口座状況を送信し、自分のWebページでリアルタイム表示します。

```
VPS上のMT4(EA) --[WebRequestでJSON送信]--> 配信サーバー --> 訪問者のブラウザ
```

動画配信と違いCPUをほとんど使わないので、**FX専用VPSでも安全に動かせます**。

---

## 表示される内容

- 有効証拠金（エクイティ）と含み損益 — 大きく表示
- 残高／本日の損益／本日の取引数／証拠金維持率
- 資産推移グラフ
- 保有ポジション一覧（通貨・売買・ロット・建値・損益）
- 「配信中／オフライン」インジケーター（2分更新が無いとオフライン表示）

**公開されないもの**: パスワード、口座番号の全体（末尾4桁のみ表示）。
このページから**発注は一切できません**（表示専用）。

---

## 手順1: 配信サーバーを起動する

トークン（合言葉）は**自分で決めた推測されにくい文字列**にしてください。

```bash
python3 -m fxtrade live --port 8080 --token "ここに秘密の文字列" --title "私のFX運用ライブ"
```

- 環境変数でも指定できます: `FXTRADE_LIVE_TOKEN=...`
- トークン未指定だと**起動しません**（無防備な公開を防ぐため）

### どこで動かす？

| 置き場所 | 向き不向き |
|---|---|
| **MT4と同じVPS** | ◎ 一番簡単。EAは `http://127.0.0.1:8080/api/live` に送るだけ |
| **レンタルサーバー/クラウド** | ◎ 公開向き。VPSからインターネット経由で送信 |
| **自宅のNAS** | △ VPSから届かせるには自宅を公開する必要があり非推奨 |

Docker でも動かせます（`Dockerfile` のCMDを `live` に変えるか、`docker run` で上書き）:

```bash
docker run -d -p 8080:8080 -e FXTRADE_LIVE_TOKEN=秘密の文字列 fxtrade-tool \
  python -m fxtrade live --host 0.0.0.0 --port 8080
```

---

## 手順2: MT4で送信先URLを許可する

MT4は安全のため、許可したURL以外へは送信できません。

1. MT4の **［ツール］→［オプション］→［エキスパートアドバイザ］** タブ
2. **「WebRequest を許可する URL リスト」** にチェック
3. 送信先を追加（例 `http://127.0.0.1:8080` や `http://あなたのドメイン`）

> ⚠️ ここを設定しないと送信は必ず失敗します。EAのログにエラーが出ます。

---

## 手順3: EAの設定

チャートに乗せた `PricePercentEA` のパラメータで:

| パラメータ | 設定値 |
|---|---|
| `PublishEnabled` | `true` |
| `PublishUrl` | `http://127.0.0.1:8080/api/live`（同じVPSの場合） |
| `PublishToken` | 手順1で決めたトークンと**同じ文字列** |
| `PublishIntervalSec` | `30`（短くしすぎない） |

設定したら、ブラウザで `http://サーバーのIP:8080` を開くと表示されます。

> 💡 `WebRequest` は応答を待つ間EAが止まる同期処理です。そのため送信は
> `PublishIntervalSec` 秒に1回へ間引き、タイムアウトも3秒に設定してあります。
> 間隔を短くしすぎると取引に影響するので、30秒以上を推奨します。

---

## 公式SNS（LINE / X / Facebook / Instagram）を載せる

配信ページの下部に、公式SNSへのボタンを表示できます。**持っているSNSだけ**指定すればOKです。

```bash
python3 -m fxtrade live --port 8080 --token "秘密の文字列" --title "公式FXライブ" \
  --line-url      "https://lin.ee/xxxxxxx" \
  --x-url         "https://x.com/あなたのID" \
  --facebook-url  "https://www.facebook.com/あなたのページ" \
  --instagram-url "https://www.instagram.com/あなたのID/"
```

環境変数でも指定できます（Dockerで使うときに便利）:
`FXTRADE_LINE_URL` / `FXTRADE_X_URL` / `FXTRADE_FACEBOOK_URL` / `FXTRADE_INSTAGRAM_URL`

### 別の公式ホームページに貼りたい場合

WordPress・Wix・ペライチなど、**別の場所にある公式HP**に載せたいときは、
貼り付け用のHTMLを出力できます。

```bash
python3 -m fxtrade sns-links --line-url "https://lin.ee/xxxxxxx" --x-url "https://x.com/あなたのID" \
  --facebook-url "https://www.facebook.com/あなたのページ" --instagram-url "https://www.instagram.com/あなたのID/" \
  --out sns.html
```

`sns.html` の中身を、HP編集画面の「カスタムHTML」ブロックなどに**そのまま貼り付け**てください。
スタイルは全部タグの中に書き込んであるので、どのサイトに貼っても見た目が崩れません（白背景・黒背景どちらでも可）。

### 各SNSのURLの調べ方

| SNS | URLの例 | 調べ方 |
|---|---|---|
| 公式LINE | `https://lin.ee/xxxxxxx` | LINE Official Account Manager →「友だち追加ガイド」→ URLをコピー |
| 公式X | `https://x.com/ユーザー名` | 自分のプロフィールを開いてURLをコピー |
| 公式Facebook | `https://www.facebook.com/ページ名` | Facebookページを開いてURLをコピー |
| 公式Instagram | `https://www.instagram.com/ユーザー名/` | プロフィールを開いてURLをコピー |

> 🔒 安全のため、URLは **`https://` で始まるものだけ**受け付けます（`http://` や
> `javascript:` などはエラーになり、サーバーも起動しません）。
> ボタンは新しいタブで開き（`target="_blank"`）、`rel="noopener noreferrer"` を付けて
> 元のページが乗っ取られないようにしてあります。

## トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| ページが「データ待ち」のまま | EAがまだ送信していない。`PublishEnabled=true` か確認 |
| EAログに「URLが未許可」 | 手順2のURLリスト登録を確認（`http://` と ポート番号まで一致させる） |
| `HTTP 401` が返る | EA側とサーバー側のトークンが不一致 |
| 「オフライン」表示になる | MT4が停止／VPSが落ちている／土日で市場が閉まっている |

---

## ⚠️ 公開する前に必ず読んでください

### 法律の話（重要）

自分の取引結果を**記録として公開するだけ**なら通常は問題ありません。しかし、

- 「この通貨を買うべき」などと**助言する**
- **有料**でシグナル・EA・情報を配信する

といった行為は、**金融商品取引法上の「投資助言・代理業」の登録**が必要になる可能性があります。
無登録での営業は処罰の対象です。収益化を考えているなら、**事前に専門家か金融庁の相談窓口で
確認してください**。ページのフッターには「投資助言ではない」旨の注記を入れてあります。

### セキュリティ

- **トークンは絶対に公開しない**（ページのソースにも出していません）
- サーバーを直接インターネットに出すなら、**HTTPS化（リバースプロキシ）を強く推奨**します。
  HTTPのままだとトークンが平文で流れます
- 取引パスワードは絶対に共有しない。誰かに口座を見せたいだけなら、MT4の
  **「投資家パスワード（investor password）」**（閲覧専用）を使ってください
