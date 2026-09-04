//+------------------------------------------------------------------+
//| CopyBridgeMaster.mq5                                             |
//| EA phia Master. Gan vao MOT chart bat ky cua terminal Master.     |
//|                                                                  |
//| O phase 4, EA nay CHI GUI. No khong thuc thi command nao ngoai    |
//| REQUEST_SNAPSHOT. Viec Master nhan lenh dong la cua phase 7.      |
//|                                                                  |
//| EA khong chua logic nghiep vu (D-01): khong tinh volume, khong    |
//| anh xa symbol, khong biet Pair ID la gi, khong biet database.     |
//+------------------------------------------------------------------+
#property copyright "MT5 Copy Bridge"
#property version   "1.00"
#property strict

#include "CopyBridgeCommon.mqh"

//--- Tham so dau vao ------------------------------------------------
input string BridgeHost  = "127.0.0.1";   // Dia chi Bridge (Tailscale: 100.x.y.z)
input int    BridgePort  = 8787;          // Cong Bridge
input string AgentToken  = "";            // Token cua agent nay
input long   MagicNumber = 770001;        // Magic number co dinh cua bot (D-07)

CBridgeAgent g_agent;
datetime     g_last_status = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringLen(AgentToken) == 0)
     {
      CbLog("CRITICAL", "Chua dien AgentToken. EA khong khoi dong.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   // Bot chi ho tro tai khoan Hedging. Netting khong duoc ho tro.
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      CbLog("CRITICAL", "Tai khoan khong o che do Hedging. Bot chi ho tro Hedging.");
      return(INIT_FAILED);
     }

   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      CbLog("WARNING", "Auto trading dang tat. EA Master van gui su kien duoc, " +
            "nhung hay bat de dung cho phase sau.");

   if(!g_agent.Init(BridgeHost, BridgePort, AgentToken, "MASTER", MagicNumber))
     {
      CbLog("CRITICAL", "Khong khoi tao duoc agent.");
      return(INIT_FAILED);
     }

   // Dung timer chu KHONG dua vao OnTick: khi thi truong dong cua hoac symbol
   // khong co tick, OnTick khong chay nhung ta van can doc socket va gui heartbeat.
   EventSetMillisecondTimer(100);

   CbLog("INFO", "CopyBridgeMaster khoi dong. Tai khoan " +
         IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) +
         ", Bridge " + BridgeHost + ":" + IntegerToString(BridgePort));
   ShowStatus();
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   g_agent.Shutdown();
   Comment("");
   CbLog("INFO", "CopyBridgeMaster dung, ly do " + IntegerToString(reason));
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   g_agent.Poll();
   if(TimeLocal() != g_last_status)
     {
      ShowStatus();
      g_last_status = TimeLocal();
     }
  }

//+------------------------------------------------------------------+
//| Bat su kien giao dich.                                           |
//|                                                                  |
//| Toan bo phan loc nam trong CbProcessTransaction: chi xu ly        |
//| TRADE_TRANSACTION_DEAL_ADD, bo qua ORDER_ADD / ORDER_UPDATE /     |
//| HISTORY_ADD. Xu ly het cac loai do se copy trung 3-4 lan.         |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   CbProcessTransaction(g_agent, trans);
  }

//+------------------------------------------------------------------+
//| Dong trang thai tren chart.                                      |
//|                                                                  |
//| Nguoi dung can nhin thay EA con song ma khong phai mo tab Experts.|
//+------------------------------------------------------------------+
void ShowStatus()
  {
   string connection = g_agent.IsConnected() ? "DA KET NOI" : "MAT KET NOI";
   string broker = ((bool)TerminalInfoInteger(TERMINAL_CONNECTED)) ? "co" : "KHONG";
   int pending = g_agent.OutboxCount();

   string text = "CopyBridge MASTER\n";
   text += "Bridge: " + connection + "  (" + BridgeHost + ":" +
           IntegerToString(BridgePort) + ")\n";
   text += "Agent:  " + (StringLen(g_agent.AgentId()) > 0 ? g_agent.AgentId() : "-") + "\n";
   text += "Ket noi san: " + broker + "\n";
   text += "seq: " + IntegerToString(g_agent.Seq()) +
           "   hang doi: " + IntegerToString(pending) + " event\n";
   text += "Magic: " + IntegerToString(MagicNumber);
   Comment(text);
  }
//+------------------------------------------------------------------+
