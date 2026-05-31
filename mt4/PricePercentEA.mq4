//+------------------------------------------------------------------+
//|                                              PricePercentEA.mq4   |
//|   価格と％で売買するEA（ナンピン・トレーリングストップ対応）     |
//|   楽天MT4 等の MetaTrader 4 で動作する自動売買プログラム          |
//|                                                                  |
//|   ロジックは Python版 PricePercentStrategy と同じ:               |
//|     ・anchorから EntryDropPct 動いたらエントリ                    |
//|     ・平均建値ベースで TakeProfitPct 利確 / StopLossPct 損切り    |
//|     ・NanpinStepPct ごとに増し玉（最大 MaxNanpin 回）             |
//|     ・最有利値から TrailingPct 戻したら手仕舞い                   |
//|                                                                  |
//|   判定の優先順位: 損切り → トレーリング → 利確 → ナンピン         |
//|   ※デモ口座で十分に検証してから使うこと。投資は自己責任。         |
//+------------------------------------------------------------------+
#property copyright "FXtrade-tool"
#property version   "1.00"
#property strict

//=== 入力パラメータ ===============================================
input string  Sec_Strategy       = "===== 戦略 =====";
input int     Direction          = 0;       // 0=買い(押し目) / 1=売り(戻り)
input double  EntryDropPct        = 0.5;     // anchorから何%動いたらエントリ
input double  TakeProfitPct       = 1.0;     // 利確%(平均建値・バスケット) 0=無効
input double  StopLossPct         = 2.0;     // 損切り%(バスケット) 0=無効
input bool    TrailAnchor         = true;    // ノーポジ時にanchorを有利方向へ追従

input string  Sec_Nanpin          = "===== ナンピン(増し玉) =====";
input bool    NanpinEnabled       = false;   // ナンピン有効
input double  NanpinStepPct       = 0.5;     // 初回建値から何%ごとに増し玉
input int     MaxNanpin           = 3;       // 最大増し玉回数
input double  NanpinSizeMult      = 1.0;     // 増し玉ごとのロット倍率(>1でマーチン)

input string  Sec_Trailing        = "===== トレーリングストップ =====";
input bool    TrailingEnabled     = true;    // トレーリング有効
input double  TrailingPct         = 0.5;     // 最有利値から何%戻したら手仕舞い
input double  TrailingActivatePct = 0.5;     // 含み益が何%でトレーリング開始(0=常時)

input string  Sec_Risk            = "===== ロット/リスク =====";
input double  RiskPerTradePct     = 1.0;     // 1トレードのリスク(口座残高%)
input double  FixedLots           = 0.0;     // >0なら固定ロット(リスク計算より優先)
input double  MaxLots             = 5.0;     // 最大ロット上限
input int     Slippage            = 10;      // 許容スリッページ(point)
input int     MagicNumber         = 20240601;// EA識別番号(他EAと重複しない値)

//=== 内部状態（tickをまたいで保持） ==============================
double g_anchor       = 0.0;
bool   g_anchorSet    = false;
double g_trailBestPct = -1.0e9;
bool   g_trailActive  = false;

//+------------------------------------------------------------------+
int OnInit()
{
   if(Direction!=0 && Direction!=1)
      Print("警告: Direction は 0(買い) か 1(売り) を指定してください。");
   Print("PricePercentEA 起動: ", _Symbol,
         " dir=", (Direction==0?"BUY":"SELL"),
         " entry=", EntryDropPct, "% TP=", TakeProfitPct, "% SL=", StopLossPct, "%",
         " nanpin=", (NanpinEnabled?"ON":"OFF"), " trailing=", (TrailingEnabled?"ON":"OFF"));
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { Comment(""); }

//+------------------------------------------------------------------+
int DirSign() { return (Direction==0 ? 1 : -1); }
int EntryOpType() { return (Direction==0 ? OP_BUY : OP_SELL); }

// ロット桁数（lotstepから推定）
int LotDigits()
{
   double step = MarketInfo(_Symbol, MODE_LOTSTEP);
   if(step >= 1.0)  return 0;
   if(step >= 0.1)  return 1;
   return 2;
}

// このEAが持つ建玉を集計する
void Scan(int &count, double &totalLots, double &avgPrice, double &firstEntry)
{
   count=0; totalLots=0; avgPrice=0; firstEntry=0;
   double weighted=0; datetime firstTime=0;
   for(int i=OrdersTotal()-1; i>=0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol()!=_Symbol || OrderMagicNumber()!=MagicNumber) continue;
      if(OrderType()!=OP_BUY && OrderType()!=OP_SELL) continue;
      count++;
      totalLots += OrderLots();
      weighted  += OrderOpenPrice()*OrderLots();
      if(firstTime==0 || OrderOpenTime()<firstTime)
      {
         firstTime  = OrderOpenTime();
         firstEntry = OrderOpenPrice();
      }
   }
   if(totalLots>0) avgPrice = weighted/totalLots;
}

// リスク%または固定ロットからロット数を決める
double ComputeLots(double mult)
{
   double lots;
   if(FixedLots > 0)
   {
      lots = FixedLots * mult;
   }
   else
   {
      double equity   = AccountEquity();
      double riskAmt  = equity * RiskPerTradePct / 100.0;
      double price    = (Direction==0 ? Ask : Bid);
      double slPct    = (StopLossPct>0 ? StopLossPct : 1.0);
      double stopDist = price * slPct / 100.0;
      double tickVal  = MarketInfo(_Symbol, MODE_TICKVALUE);
      double tickSize = MarketInfo(_Symbol, MODE_TICKSIZE);
      if(tickSize<=0 || tickVal<=0) return 0;
      double lossPerLot = stopDist / tickSize * tickVal;
      if(lossPerLot<=0) return 0;
      lots = riskAmt / lossPerLot * mult;
   }

   double step = MarketInfo(_Symbol, MODE_LOTSTEP);
   double minL = MarketInfo(_Symbol, MODE_MINLOT);
   double maxL = MarketInfo(_Symbol, MODE_MAXLOT);
   if(step<=0) step=0.01;
   lots = MathFloor(lots/step)*step;
   if(lots > MaxLots) lots = MaxLots;
   if(lots > maxL)    lots = maxL;
   if(lots < minL)
   {
      Print("計算ロットが最小ロット未満のため最小ロット(", minL, ")を使用します。リスク設定を見直してください。");
      lots = minL;
   }
   return NormalizeDouble(lots, LotDigits());
}

// 新規/増し玉の発注
void OpenOrder(double mult, string tag)
{
   double lots = ComputeLots(mult);
   if(lots<=0) { Print("ロット0のため発注スキップ"); return; }
   RefreshRates();
   int    type  = EntryOpType();
   double price = (type==OP_BUY ? Ask : Bid);
   price = NormalizeDouble(price, Digits);
   int ticket = OrderSend(_Symbol, type, lots, price, Slippage, 0, 0,
                          "PricePercentEA:"+tag, MagicNumber, 0,
                          (type==OP_BUY?clrDodgerBlue:clrOrangeRed));
   if(ticket<0) Print("OrderSend 失敗 err=", GetLastError(), " (", tag, ")");
   else         Print("発注 ", (type==OP_BUY?"BUY":"SELL"), " ", lots, " lots @ ", price, " (", tag, ")");
}

// このEAの建玉を全決済
void CloseAll(string reason)
{
   for(int i=OrdersTotal()-1; i>=0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol()!=_Symbol || OrderMagicNumber()!=MagicNumber) continue;
      if(OrderType()!=OP_BUY && OrderType()!=OP_SELL) continue;
      RefreshRates();
      double price = (OrderType()==OP_BUY ? Bid : Ask);
      price = NormalizeDouble(price, Digits);
      if(!OrderClose(OrderTicket(), OrderLots(), price, Slippage, clrYellow))
         Print("OrderClose 失敗 err=", GetLastError());
   }
   Print("全決済: ", reason);
}

//+------------------------------------------------------------------+
void OnTick()
{
   int    count; double totalLots, avgPrice, firstEntry;
   Scan(count, totalLots, avgPrice, firstEntry);

   double bid = Bid, ask = Ask;

   //--- ノーポジ: エントリ判定 -----------------------------------
   if(count==0)
   {
      g_trailBestPct = -1.0e9;
      g_trailActive  = false;

      double ref = bid; // 参照価格
      if(!g_anchorSet) { g_anchor = ref; g_anchorSet = true; }
      if(TrailAnchor)
      {
         if(Direction==0) g_anchor = MathMax(g_anchor, ref);
         else             g_anchor = MathMin(g_anchor, ref);
      }
      double changePct = (ref - g_anchor)/g_anchor*100.0;

      ShowStatus(0, 0, changePct, 0);

      if(Direction==0 && changePct <= -EntryDropPct)
      {
         OpenOrder(1.0, "entry");
         g_anchorSet = false;
      }
      else if(Direction==1 && changePct >= EntryDropPct)
      {
         OpenOrder(1.0, "entry");
         g_anchorSet = false;
      }
      return;
   }

   //--- 建玉あり: 決済/増し玉判定 --------------------------------
   int    sign      = DirSign();
   double markPrice = (Direction==0 ? bid : ask);
   double movePct   = (markPrice - avgPrice)/avgPrice * sign * 100.0;

   ShowStatus(count, avgPrice, movePct, g_trailBestPct);

   // 1) 損切り
   if(StopLossPct>0 && movePct <= -StopLossPct) { CloseAll("stop loss"); return; }

   // 2) トレーリング
   if(TrailingEnabled)
   {
      if(movePct > g_trailBestPct) g_trailBestPct = movePct;
      if(!g_trailActive && movePct >= TrailingActivatePct) g_trailActive = true;
      if(g_trailActive && (g_trailBestPct - movePct) >= TrailingPct)
      {
         CloseAll("trailing stop"); return;
      }
   }

   // 3) 利確
   if(TakeProfitPct>0 && movePct >= TakeProfitPct) { CloseAll("take profit"); return; }

   // 4) ナンピン（増し玉）
   if(NanpinEnabled)
   {
      int adds = count - 1;               // これまでの増し玉回数
      if(adds < MaxNanpin && firstEntry>0)
      {
         double step = NanpinStepPct * (adds + 1);
         double moveFromFirst = (markPrice - firstEntry)/firstEntry * sign * 100.0;
         if(moveFromFirst <= -step)
            OpenOrder(MathPow(NanpinSizeMult, adds), "nanpin#"+IntegerToString(adds+1));
      }
   }
}

//+------------------------------------------------------------------+
void ShowStatus(int count, double avg, double movePct, double bestPct)
{
   string s = "PricePercentEA  ["+_Symbol+"]\n";
   s += "方向: " + (Direction==0?"買い(押し目)":"売り(戻り)") + "\n";
   s += "建玉数: " + IntegerToString(count);
   if(count>0)
   {
      s += "  平均建値: " + DoubleToString(avg, Digits);
      s += "  損益: " + DoubleToString(movePct, 3) + "%";
      if(TrailingEnabled)
         s += "  (最高益: " + DoubleToString(bestPct, 3) + "% / トレール" + (g_trailActive?"ON":"待機") + ")";
   }
   else
   {
      s += "  anchor: " + DoubleToString(g_anchor, Digits) + "  乖離: " + DoubleToString(movePct, 3) + "%";
   }
   s += "\n口座残高: " + DoubleToString(AccountEquity(), 0);
   Comment(s);
}
//+------------------------------------------------------------------+
