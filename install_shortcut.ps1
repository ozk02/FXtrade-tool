$ErrorActionPreference = 'Stop'

# このスクリプトと同じ場所をプロジェクトルートとみなす。
$proj = $PSScriptRoot
$target = Join-Path $proj 'run_ui.bat'

if (-not (Test-Path (Join-Path $proj 'fxtrade'))) {
    Write-Host 'エラー: このスクリプトは FXtrade-tool のフォルダ内に置いて実行してください。' -ForegroundColor Red
    return
}

$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'FXデモトレード.lnk'

$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = $target
$lnk.WorkingDirectory = $proj
$lnk.Description = 'FX自動売買 デモトレード'
# アイコンは Python のものを流用（あれば）。
try {
    $py = (Get-Command python -ErrorAction Stop).Source
    if ($py) { $lnk.IconLocation = "$py,0" }
} catch {}
$lnk.Save()

Write-Host ''
Write-Host 'OK: デスクトップに『FXデモトレード』アイコンを作成しました。' -ForegroundColor Green
Write-Host 'アイコンをダブルクリックすると、ブラウザでデモ画面が開きます。'
