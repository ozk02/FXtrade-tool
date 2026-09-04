# FXtrade-tool デモ/検証UI コンテナ
#
# 外部ライブラリに一切依存しないので、Python の公式イメージだけで動く。
# NAS(UGREEN UGOS Pro / Synology / QNAP など)や任意のDocker環境で使える。
#
#   docker build -t fxtrade-tool .
#   docker run -d --name fxtrade-ui -p 8000:8000 --restart unless-stopped fxtrade-tool
#   → ブラウザで http://<NASのIP>:8000
FROM python:3.12-slim

WORKDIR /app

# NAS上で root のまま動かさないよう、専用ユーザーを用意する。
RUN useradd --create-home --uid 1000 fxtrade

# 必要なのはアプリ本体と設定例だけ（テストやWindows用スクリプトは含めない）。
COPY fxtrade/ ./fxtrade/
COPY config.example.yaml config.regime.example.yaml ./

RUN mkdir -p /app/data && chown -R fxtrade:fxtrade /app
USER fxtrade

# ログをすぐ流す（NASのログ画面で見えるように）
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/').read(1)" || exit 1

# コンテナ外からアクセスするため 0.0.0.0 で待ち受ける。
CMD ["python", "-m", "fxtrade", "ui", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
