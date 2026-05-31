' =============================================================================
'  MarketSpeed II RSS 発注マクロ サンプル（テンプレート）
' =============================================================================
'  本ツール(RakutenBroker)は、発注パラメータを cell_map のセルに書き込んでから
'  このマクロを Application.Run で呼び出します。マクロ側は:
'    1) パラメータセルを読む
'    2) RSS の発注関数/オブジェクトで実発注する  ← ★各自の環境で実装
'    3) 結果(成功可否・約定価格・注文番号)を結果セルへ書き戻す
'  という責務を持ちます。
'
'  ★重要: RSS の発注関数名・引数・売買区分コードはバージョン/商品(株式/先物/FX)で
'  異なります。必ず「MARKETSPEED II RSS 関数リファレンス」を参照し、下の TODO を
'  自分の環境の正しい関数呼び出しに置き換えてください。まずは実発注をコメントアウトした
'  まま(=ステータスだけ書き戻す)で疎通確認することを推奨します。
' =============================================================================

Option Explicit

Sub RssSendOrder()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets("Sheet1")   ' config の sheet と合わせる

    ' --- 1) パラメータ読み込み（cell_map と一致させる） ---
    Dim code As String:   code = CStr(ws.Range("E1").Value)
    Dim side As String:   side = CStr(ws.Range("E2").Value)   ' "BUY"/"SELL"
    Dim qty As Long:      qty = CLng(ws.Range("E3").Value)
    Dim ordType As String: ordType = CStr(ws.Range("E4").Value) ' "MARKET"/"LIMIT"
    Dim price As Variant: price = ws.Range("E5").Value          ' 成行なら空

    On Error GoTo Failed

    ' --- 2) 実発注（★ここを公式リファレンスの発注関数に置き換える） ---
    ' 例（イメージ・要置換）:
    '   Dim ret As Variant
    '   ret = Application.Run("RssMarketOrder", code, side, qty, ordType, price)
    '   ' あるいは RSS の発注オブジェクト/関数を環境に合わせて呼ぶ
    '
    ' 疎通確認の段階では下行のように擬似的に成功を返す:
    Dim ret As String
    ret = "OK"        ' TODO: 実発注の戻り値に置き換える

    ' --- 3) 結果の書き戻し ---
    ws.Range("E6").Value = ret            ' ステータス（成功トークン or 注文番号）
    ' ws.Range("E7").Value = <約定価格>   ' 取得できれば約定価格を書く
    ' ws.Range("E8").Value = <注文番号>   ' 取得できれば注文番号を書く
    Exit Sub

Failed:
    ws.Range("E6").Value = "ERROR: " & Err.Description
End Sub
