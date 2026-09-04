# NAS で動かす（UGREEN NASync / Synology / QNAP）

このツールの**検証UI（デモトレード画面）**を NAS 上で常時稼働させる手順です。
NAS は 24 時間動いているので、PC を立ち上げなくても **スマホやタブレットのブラウザから
いつでもデモ画面を開ける** ようになります。

> ⚠️ **これは「検証UI」を動かすものです。実際の自動売買はしません。**
> MT4 による実売買は Windows が必要なので NAS では動きません（後述）。

---

## 動くかどうかの確認（最初にこれだけ）

必要なのは **Docker が使えること** だけです。
UGREEN NASync DXP4800 シリーズは Intel 系（x86_64）CPU で **UGOS Pro** が動き、
**Docker アプリが提供されている**ので条件を満たします。

念のため、NAS に SSH で入って確認できます:

```bash
uname -m        # x86_64 と出れば OK（aarch64 でも Docker が動けば可）
docker --version
```

| CPU | 可否 |
|---|---|
| x86_64（Intel/AMD） | ✅ そのまま動く |
| aarch64（ARM） | ✅ 動く（python 公式イメージは ARM 版もある） |

> 💡 HDD/SSD を 1 台も入れていないと NAS 自体のセットアップができません。
> 先にドライブを取り付けて UGOS Pro の初期設定を済ませてください。

---

## 手順A：GUI（Docker アプリ）で入れる — おすすめ

1. **コードを NAS に置く**
   共有フォルダ（例 `docker` フォルダ）に、このリポジトリを ZIP でダウンロードして展開、
   または SSH で `git clone` します。
   ```bash
   cd /volume1/docker          # UGREEN/Synology の共有フォルダ例
   git clone -b claude/gracious-fermi-7rbwS https://github.com/ozk02/FXtrade-tool.git
   ```

2. **UGOS Pro の App Center で「Docker」をインストール**

3. Docker アプリを開き、**「プロジェクト」（Compose）** から
   `FXtrade-tool` フォルダの `docker-compose.yml` を指定して作成 → **起動**

4. ブラウザで **`http://<NASのIP>:8000`** を開く
   （NAS の IP は UGOS Pro の設定画面やルーターの管理画面で確認できます）

---

## 手順B：SSH（コマンド）で入れる

SSH を有効化して NAS に接続し、以下を実行するだけです。

```bash
cd /volume1/docker/FXtrade-tool
docker compose up -d          # 起動（イメージのビルドも自動）
```

確認・停止:

```bash
docker compose ps             # 状態確認
docker compose logs -f        # ログを見る
docker compose down           # 停止
```

`docker compose` が使えない古い環境なら:

```bash
docker build -t fxtrade-tool .
docker run -d --name fxtrade-ui -p 8000:8000 --restart unless-stopped fxtrade-tool
```

---

## 設定のポイント

| 項目 | 内容 |
|---|---|
| **ポート変更** | `docker-compose.yml` の `"8000:8000"` の**左側**を変える（例 `"8080:8000"` → `http://NASのIP:8080`） |
| **自動起動** | `restart: unless-stopped` を指定済み。NAS 再起動後も自動で立ち上がります |
| **CSVデータ** | `./data` が `/app/data` にマウントされます。ヒストリカルCSVをここに置くと UI から使えます |
| **更新** | `git pull` してから `docker compose up -d --build` |

---

## ⚠️ セキュリティ（重要）

**この UI にはパスワード認証がありません。**

- **家庭内LAN でのみ**使ってください
- ルーターの**ポート開放（ポートフォワーディング）は絶対にしない**でください
- 外出先から使いたい場合は、NAS の **VPN 機能**経由で接続してください

---

## MT4（実際の自動売買）を NAS で動かすことについて

**おすすめしません。**

MT4 は Windows 専用アプリです。x86 の NAS なら仮想マシンで Windows を動かして
MT4 を入れる方法は理論上ありますが、**Windows ライセンス代・大量のメモリ・
かなりの手間**がかかります。

24 時間の自動売買をしたいなら、業界標準の **VPS（FX用レンタルサーバー）** を使ってください。
最初から Windows + MT4 が使える状態で提供され、停電やネット断の影響も受けません。
証券会社によっては条件を満たすと無料になります。

| やりたいこと | 置き場所 |
|---|---|
| 検証・デモUIを常時使いたい | **NAS** ✅（この手順書） |
| 実際に24時間自動売買したい | **VPS** ✅（NASは非推奨） |
