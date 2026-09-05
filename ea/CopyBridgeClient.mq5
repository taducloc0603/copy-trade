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
   //| Chon filling mode cho mot symbol.                              |
   //|                                                                |
   //| Thu tu uu tien: FOK, roi IOC, roi RETURN. `skip` cho phep bo    |
   //| qua `skip` lua chon dau tien - dung khi retcode 10030 bao la    |
   //| che do vua chon khong duoc ho tro.                              |
   //|                                                                |
   //| Tra ve -1 khi khong con lua chon nao.                           |
   //+---------------------------------------------------------------+
   int               PickFilling(const string symbol, const int skip)
     {
      long mask = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
      int modes[3];
      int count = 0;
      if((mask & SYMBOL_FILLING_FOK) != 0)
        {
         modes[count] = ORDER_FILLING_FOK;
         count++;
        }
      if((mask & SYMBOL_FILLING_IOC) != 0)
        {
         modes[count] = ORDER_FILLING_IOC;
         count++;
        }
      // RETURN khong co bit rieng trong SYMBOL_FILLING_MODE; no la lua chon
      // cuoi cung cho lenh thi truong khi broker khong khai bao gi khac.
      if(count < 3)
        {
         modes[count] = ORDER_FILLING_RETURN;
         count++;
        }
      if(skip >= count)
         return(-1);
      return(modes[skip]);
     }

   //+---------------------------------------------------------------+
   //| Hang rao an toan phia EA.                                      |
   //|                                                                |
   //| Day la cac kiem tra RE TIEN chong lai loi lap trinh o Bridge.   |
   //| Chung KHONG thay the viec Bridge phai lam dung.                 |
   //|                                                                |
   //| Tra ve "" neu hop le, nguoc lai tra ve ly do tu choi.           |
   //+---------------------------------------------------------------+
   string            Guard(const string type, CJsonReader &payload,
                           const string deadline_ts)
     {
      // Lenh cu khong duoc thuc thi muon.
      if(StringLen(deadline_ts) > 0 && CbIsoIsPast(deadline_ts))
         return("Command deadline has passed: " + deadline_ts);

      if(payload.Has("magic") && !payload.IsNull("magic"))
        {
         long magic = payload.GetInt("magic", -1);
         if(magic != Magic())
            return("Magic mismatch: payload " + IntegerToString(magic) +
                   " vs EA " + IntegerToString(Magic()));
        }

      if(type == "OPEN" || type == "CLOSE_PARTIAL")
        {
         double volume = payload.GetDbl("volume", 0.0);
         if(volume <= 0.0)
            return("Volume must be positive, got " + CbNum(volume));
        }

      if(type == "OPEN")
        {
         string symbol = payload.GetStr("symbol");
         if(StringLen(symbol) == 0)
            return("Missing symbol in payload");
         if(!SymbolSelect(symbol, true))
            return("Symbol does not exist on this terminal: " + symbol);
        }

      return("");
     }

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

   //+---------------------------------------------------------------+
   //| CLOSE - dong toan bo vi the theo position_id.                   |
   //+---------------------------------------------------------------+
   string            DoClose(const string command_id, CJsonReader &payload)
     {
      long position_id = payload.GetInt("position_id", 0);
      if(position_id <= 0)
         return(SendAck(command_id, "rejected", 0, "Missing position_id", -1, 0, 1));

      if(!PositionSelectByTicket(position_id))
        {
         // KHONG phai loi. Day la tinh huong binh thuong khi hai ben cung dong
         // gan nhu dong thoi (FR-18).
         CbLog("INFO", "Position " + IntegerToString(position_id) +
               " khong ton tai, tra ve already_closed");
         return(SendAck(command_id, "already_closed", 0, "", 0.0, 0, 1));
        }

      double volume = PositionGetDouble(POSITION_VOLUME);
      return(ClosePartOf(command_id, position_id, volume, payload));
     }

   //+---------------------------------------------------------------+
   //| CLOSE_PARTIAL - dong dung `volume` trong payload.               |
   //+---------------------------------------------------------------+
   string            DoClosePartial(const string command_id, CJsonReader &payload)
     {
      long position_id = payload.GetInt("position_id", 0);
      if(position_id <= 0)
         return(SendAck(command_id, "rejected", 0, "Missing position_id", -1, 0, 1));

      if(!PositionSelectByTicket(position_id))
        {
         CbLog("INFO", "Position " + IntegerToString(position_id) +
               " khong ton tai, tra ve already_closed");
         return(SendAck(command_id, "already_closed", 0, "", 0.0, 0, 1));
        }

      double remaining = PositionGetDouble(POSITION_VOLUME);
      double wanted    = payload.GetDbl("volume", 0.0);

      // Yeu cau lon hon phan con lai thi dong het phan con lai, ack ghi ro
      // executed_volume that. KHONG bao loi.
      double volume = (wanted > remaining) ? remaining : wanted;
      if(wanted > remaining)
         CbLog("INFO", "Yeu cau dong " + CbNum(wanted) + " nhung chi con " +
               CbNum(remaining) + ", dong het phan con lai");

      return(ClosePartOf(command_id, position_id, volume, payload));
     }

   //+---------------------------------------------------------------+
   //| Dat lenh nguoc chieu de dong `volume` cua mot vi the.           |
   //|                                                                |
   //| `volume` tinh bang lot cua san Client va PHAI da duoc Bridge    |
   //| chuan hoa theo volume_step. EA khong lam tron.                  |
   //+---------------------------------------------------------------+
   string            ClosePartOf(const string command_id, const long position_id,
                                 const double volume, CJsonReader &payload)
     {
      if(volume <= 0.0)
         return(SendAck(command_id, "rejected", 0,
                        "Close volume must be positive, got " + CbNum(volume), -1, 0, 1));

      string symbol = PositionGetString(POSITION_SYMBOL);
      long   type   = PositionGetInteger(POSITION_TYPE);
      int    deviation = (int)payload.GetInt("deviation", 20);

      MqlTradeRequest request;
      MqlTradeResult  result;
      int attempt = 0;

      for(int skip = 0; skip < 2; skip++)
        {
         int filling = PickFilling(symbol, skip);
         if(filling < 0)
            break;

         ZeroMemory(request);
         ZeroMemory(result);
         request.action       = TRADE_ACTION_DEAL;
         request.position     = position_id;
         request.symbol       = symbol;
         request.volume       = volume;
         request.type         = (type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
         request.price        = (type == POSITION_TYPE_BUY)
                                ? SymbolInfoDouble(symbol, SYMBOL_BID)
                                : SymbolInfoDouble(symbol, SYMBOL_ASK);
         request.deviation    = deviation;
         request.magic        = Magic();
         request.type_filling = (ENUM_ORDER_TYPE_FILLING)filling;

         attempt = skip + 1;
         bool sent = OrderSend(request, result);
         if(sent && result.retcode == TRADE_RETCODE_DONE)
           {
            RememberCause(command_id, position_id);
            CbLog("INFO", "Dong " + CbNum(result.volume) + " " + symbol + " cua position " +
                  IntegerToString(position_id) + " thanh cong");
            return(SendAck(command_id, "ok", (int)result.retcode, result.comment,
                           result.volume, position_id, attempt));
           }

         if(result.retcode != TRADE_RETCODE_INVALID_FILL)
            break;
         CbLog("WARNING", "Filling mode khong duoc ho tro (10030), thu che do ke tiep");
        }

      CbLog("ERROR", "Dong vi the " + IntegerToString(position_id) + " that bai, retcode " +
            IntegerToString(result.retcode) + " " + result.comment);
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

      if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
         return(SendAck(command_id, "rejected", 0,
                        "Auto trading is disabled in the terminal", -1, 0, 1));

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
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      CbLog("ERROR", "Auto trading dang TAT. EA Client se tu choi moi command " +
            "cho toi khi bat len.");

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
   string trading = MQLInfoInteger(MQL_TRADE_ALLOWED) ? "BAT" : "TAT";

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
