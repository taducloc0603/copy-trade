//+------------------------------------------------------------------+
//| CopyBridgeClient.mq5                                             |
//| EA phia Client. Gan vao MOT chart bat ky cua terminal Client.     |
//|                                                                  |
//| Lam moi thu EA Master lam (bat su kien, heartbeat, hang doi,      |
//| symbol specs - tat ca nam trong CopyBridgeCommon.mqh), cong them  |
//| viec THUC THI COMMAND: OPEN, CLOSE, CLOSE_PARTIAL.                |
//|                                                                  |
//| Day la lan dau he thong gui lenh giao dich that, nen tinh BAT     |
//| BIEN khi nhan command trung la yeu cau song con. Co che do nam o  |
//| lop CBridgeAgent: giu cho command_id vao file TRUOC khi goi        |
//| OrderSend, va command da xu ly thi tra lai ack cu nguyen van.      |
//|                                                                  |
//| EA VAN KHONG CHUA LOGIC NGHIEP VU (D-01). Payload tu Bridge da    |
//| chua TAT CA thong so cuoi cung: symbol da anh xa, volume da chuan |
//| hoa, deviation, magic. EA khong tinh toan gi them.                |
//|                                                                  |
//| Ngoai le duy nhat: tu chon filling mode theo SYMBOL_FILLING_MODE, |
//| vi do la chi tiet ky thuat cua broker chu khong phai quy tac      |
//| nghiep vu.                                                        |
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
//| Agent phia Client: them phan thuc thi lenh.                      |
//+------------------------------------------------------------------+
class CClientAgent : public CBridgeAgent
  {
private:
   //+---------------------------------------------------------------+
   //| OPEN                                                           |
   //+---------------------------------------------------------------+
   string            DoOpen(const string command_id, CJsonReader &payload)
     {
      string symbol    = payload.GetStr("symbol");
      string direction = payload.GetStr("direction");
      double volume    = payload.GetDbl("volume", 0.0);
      int deviation    = (int)payload.GetInt("deviation", 20);
      string comment   = payload.GetStr("comment", "");

      if(direction != "BUY" && direction != "SELL")
         return(SendAck(command_id, "rejected", 0,
                        "Direction must be BUY or SELL, got " + direction, -1, 0, 1));

      MqlTradeRequest request;
      MqlTradeResult  result;
      int attempt = 0;

      // Thu toi da hai lan: lan hai chi khi retcode 10030 bao filling mode
      // khong duoc ho tro. Khong retry cai gi khac o day - phan loai retcode
      // va quyet dinh retry la viec cua Bridge o phase 6.
      for(int skip = 0; skip < 2; skip++)
        {
         int filling = PickFilling(symbol, skip);
         if(filling < 0)
            break;

         ZeroMemory(request);
         ZeroMemory(result);
         request.action       = TRADE_ACTION_DEAL;
         request.symbol       = symbol;
         request.volume       = volume;
         request.type         = (direction == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
         request.price        = (direction == "BUY")
                                ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                                : SymbolInfoDouble(symbol, SYMBOL_BID);
         request.deviation    = deviation;
         request.magic        = Magic();
         request.comment      = comment;
         request.type_filling = (ENUM_ORDER_TYPE_FILLING)filling;

         attempt = skip + 1;
         bool sent = OrderSend(request, result);
         if(sent && result.retcode == TRADE_RETCODE_DONE)
           {
            long position_id = (long)result.order;
            // Vi the vua mo mang position id bang ticket cua order o che do
            // Hedging. Doc lai cho chac neu chon duoc.
            if(PositionSelectByTicket(result.order))
               position_id = (long)PositionGetInteger(POSITION_IDENTIFIER);

            // Ghi nho de gan caused_by_command_id cho deal sap phat sinh (D-08).
            RememberCause(command_id, position_id);

            CbLog("INFO", "OPEN " + direction + " " + CbNum(result.volume) + " " + symbol +
                  " thanh cong, position " + IntegerToString(position_id));
            return(SendAck(command_id, "ok", (int)result.retcode, result.comment,
                           result.volume, position_id, attempt));
           }

         if(result.retcode != TRADE_RETCODE_INVALID_FILL)
            break;   // khong phai loi filling mode thi dung han
         CbLog("WARNING", "Filling mode khong duoc ho tro (10030), thu che do ke tiep");
        }

      CbLog("ERROR", "OPEN that bai, retcode " + IntegerToString(result.retcode) +
            " " + result.comment);
      return(SendAck(command_id, "failed", (int)result.retcode, result.comment,
                     -1, 0, attempt));
     }

public:
   //+---------------------------------------------------------------+
   //| Diem vao thuc thi command. Lop cha da lo phan bat bien:         |
   //| command trung thi khong bao gio toi day.                        |
   //+---------------------------------------------------------------+
   virtual string    OnCommand(const string command_id, const string type,
                               CJsonReader &reader)
     {
      if(type != "OPEN" && type != "CLOSE" && type != "CLOSE_PARTIAL")
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

      if(!CbTradeAllowed())
         return(SendAck(command_id, "rejected", 0,
                        "Trading not allowed: " + CbTradeBlockReason(), -1, 0, 1));

      if(type == "OPEN")
         return(DoOpen(command_id, payload));
      if(type == "CLOSE")
         return(DoClose(command_id, payload));
      return(DoClosePartial(command_id, payload));
     }
  };

CClientAgent g_agent;
datetime     g_last_status = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringLen(AgentToken) == 0)
     {
      CbLog("CRITICAL", "Chua dien AgentToken. EA khong khoi dong.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      CbLog("CRITICAL", "Tai khoan khong o che do Hedging. Bot chi ho tro Hedging.");
      return(INIT_FAILED);
     }

   // Khac EA Master: Client PHAI dat duoc lenh, khong thi khong lam gi duoc.
   if(!CbTradeAllowed())
      CbLog("ERROR", "KHONG dat duoc lenh: " + CbTradeBlockReason() +
            "EA Client se TU CHOI moi command cho toi khi sua xong.");

   if(!g_agent.Init(BridgeHost, BridgePort, AgentToken, "CLIENT", MagicNumber))
     {
      CbLog("CRITICAL", "Khong khoi tao duoc agent.");
      return(INIT_FAILED);
     }

   EventSetMillisecondTimer(100);

   CbLog("INFO", "CopyBridgeClient khoi dong. Tai khoan " +
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
   CbLog("INFO", "CopyBridgeClient dung, ly do " + IntegerToString(reason));
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
//| Bat su kien giao dich. Giong het EA Master: chi xu ly DEAL_ADD.   |
//| Deal do chinh EA nay dat se mang caused_by_command_id, va do la    |
//| toan bo co che chong vong lap o phase 7 (D-08).                    |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   CbProcessTransaction(g_agent, trans);
  }

//+------------------------------------------------------------------+
void ShowStatus()
  {
   string connection = g_agent.IsConnected() ? "DA KET NOI" : "MAT KET NOI";
   string broker = ((bool)TerminalInfoInteger(TERMINAL_CONNECTED)) ? "co" : "KHONG";
   string trading = CbTradeAllowed() ? "BAT" : "TAT";

   string text = "CopyBridge CLIENT\n";
   text += "Bridge: " + connection + "  (" + BridgeHost + ":" +
           IntegerToString(BridgePort) + ")\n";
   text += "Agent:  " + (StringLen(g_agent.AgentId()) > 0 ? g_agent.AgentId() : "-") + "\n";
   text += "Ket noi san: " + broker + "   Auto trading: " + trading + "\n";
   text += "seq: " + IntegerToString(g_agent.Seq()) +
           "   hang doi: " + IntegerToString(g_agent.OutboxCount()) + " event\n";
   text += "Magic: " + IntegerToString(MagicNumber);
   Comment(text);
  }
//+------------------------------------------------------------------+
