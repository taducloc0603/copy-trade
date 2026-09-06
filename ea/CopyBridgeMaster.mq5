//+------------------------------------------------------------------+
//| CopyBridgeMaster.mq5                                             |
//| EA phia Master. Gan vao MOT chart bat ky cua terminal Master.     |
//|                                                                  |
//| EA nay GUI su kien va thuc thi lenh DONG (CLOSE, CLOSE_PARTIAL).  |
//| No KHONG BAO GIO mo vi the: khong co duong nao tu day toi mot     |
//| lenh mo, va do la ranh gioi an toan cua tai khoan Master.         |
//|                                                                  |
//| Kha nang dong duoc them o phase 11. Truoc do EA nay tu choi MOI   |
//| command, nen D-09 (cascade dong Master) va TEST-21 (dong khan     |
//| cap) khong the chay - nghiem thu tren demo 2026-09-06 phat hien   |
//| bang cach bam nut that va nhan ve "Command type not supported by  |
//| this agent role".                                                 |
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

//+------------------------------------------------------------------+
//| Agent phia Master: chi them duong DONG, tuyet doi khong them MO.  |
//+------------------------------------------------------------------+
class CMasterAgent : public CBridgeAgent
  {
public:
   virtual string    OnCommand(const string command_id, const string type,
                               CJsonReader &reader)
     {
      // CO Y khong co "OPEN" o day. Tai khoan Master khong bao gio duoc mo
      // vi the tu lenh cua Bridge; no chi phan anh thao tac cua nguoi dung.
      if(type != "CLOSE" && type != "CLOSE_PARTIAL")
         return(CBridgeAgent::OnCommand(command_id, type, reader));

      CJsonReader payload;
      string raw = reader.GetRaw("payload");
      if(StringLen(raw) == 0 || !payload.Parse(raw))
         return(SendAck(command_id, "rejected", 0, "Missing or invalid payload", -1, 0, 1));

      string refused = Guard(type, payload, reader.GetStr("deadline_ts"));
      if(StringLen(refused) > 0)
        {
         CbLog("WARNING", "Tu choi command " + command_id + ": " + refused);
         return(SendAck(command_id, "rejected", 0, refused, -1, 0, 1));
        }

      if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
         return(SendAck(command_id, "rejected", 0,
                        "Auto trading is disabled in the terminal", -1, 0, 1));

      if(type == "CLOSE")
         return(DoClose(command_id, payload));
      return(DoClosePartial(command_id, payload));
     }
  };

CMasterAgent g_agent;
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

   // Tu phase 11 EA Master PHAI dat duoc lenh dong, neu khong thi nut dung khan
   // cap va cascade (D-09) khong lam gi duoc ngoai viec bao loi.
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      CbLog("ERROR", "Auto trading dang TAT. EA Master van gui su kien duoc nhung se " +
            "TU CHOI moi lenh dong cho toi khi bat len.");

   if(!g_agent.Init(BridgeHost, BridgePort, AgentToken, "MASTER", MagicNumber))
     {
      CbLog("CRITICAL", "Khong khoi tao duoc agent.");
      return(INIT_FAILED);
     }

   // Dung timer chu KHONG dua vao OnTick: khi thi truong dong cua hoac symbol
   // khong co tick, OnTick khong chay nhung ta van can doc socket va gui heartbeat.
   EventSetMillisecondTimer(100);

   CbLog("INFO", "CopyBridgeMaster khoi dong [co kha nang DONG lenh]. Tai khoan " +
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
