//+------------------------------------------------------------------+
//| CopyBridgeCommon.mqh                                             |
//| Phan dung chung cho EA Master (phase 4) va EA Client (phase 5).   |
//|                                                                  |
//| EA la agent MONG (D-01). No KHONG tinh volume, KHONG anh xa       |
//| symbol, KHONG biet database ton tai, va chi echo lai pair_id.     |
//| Ngoai le duy nhat: tu chon filling mode theo SYMBOL_FILLING_MODE, |
//| vi do la chi tiet ky thuat cua broker (dung o phase 5).           |
//|                                                                  |
//| CHU Y: toan bo file nay viet bang tieng Anh khong dau, ke ca chu  |
//| thich. MetaEditor va cac ban build MT5 khac nhau xu ly encoding   |
//| file nguon khong thong nhat, nen dau tieng Viet trong .mqh la     |
//| nguon loi bien dich rat kho tim.                                  |
//+------------------------------------------------------------------+
#property strict

#define COPYBRIDGE_PROTOCOL_VERSION 1
#define COPYBRIDGE_DIR              "copybridge"
#define COPYBRIDGE_MAX_LINE         262144   // 256 KB, khop MAX_LINE_BYTES cua Bridge
#define COPYBRIDGE_CMD_MEMORY_SEC   86400    // giu 24 gio command_id da xu ly
#define COPYBRIDGE_SPEC_INTERVAL_SEC 21600   // 6 gio, day lai symbol specs
#define COPYBRIDGE_CAUSE_WINDOW_SEC 10       // cua so gan caused_by_command_id

//+------------------------------------------------------------------+
//| 1. Chuoi UTF-8                                                   |
//|                                                                  |
//| Day la cai bay lon nhat cua MQL5. Bo qua CP_UTF8 thi moi ten      |
//| symbol hoac comment ngoai ASCII se hong. CHI dung hai ham boc     |
//| duoi day, khong goi StringToCharArray/CharArrayToString truc tiep |
//| o bat ky cho nao khac.                                           |
//+------------------------------------------------------------------+
int CbUtf8Encode(const string text, uchar &out[])
  {
   int len = StringToCharArray(text, out, 0, WHOLE_ARRAY, CP_UTF8);
   // StringToCharArray them mot byte 0 ket thuc. Byte do khong duoc gui di.
   if(len > 0)
      len--;
   return(len);
  }

string CbUtf8Decode(const uchar &data[], const int start, const int count)
  {
   if(count <= 0)
      return("");
   return(CharArrayToString(data, start, count, CP_UTF8));
  }

//+------------------------------------------------------------------+
//| 2. JSON: escape va build                                         |
//|                                                                  |
//| Escape day du dac biet la newline. Mot ky tu xuong dong lot vao   |
//| chuoi se pha vo khung NDJSON (D-02) va lam Bridge doc sai ranh    |
//| gioi message.                                                    |
//+------------------------------------------------------------------+
string CbJsonEscape(const string text)
  {
   string out = "";
   int n = StringLen(text);
   for(int i = 0; i < n; i++)
     {
      ushort c = StringGetCharacter(text, i);
      switch(c)
        {
         case '"':  out += "\\\"";  break;
         case '\\': out += "\\\\";  break;
         case '\n': out += "\\n";   break;
         case '\r': out += "\\r";   break;
         case '\t': out += "\\t";   break;
         case 8:    out += "\\b";   break;
         case 12:   out += "\\f";   break;
         default:
            if(c < 0x20)
               out += StringFormat("\\u%04x", c);
            else
               out += ShortToString(c);
            break;
        }
     }
   return(out);
  }

//| Bo cac so 0 thua o duoi. JSON chap nhan ca hai, nhung log doc bang
//| mat thi "0.5" de hon "0.50000000".
string CbNum(const double value, const int digits = 8)
  {
   string text = DoubleToString(value, digits);
   if(StringFind(text, ".") >= 0)
     {
      while(StringLen(text) > 0 && StringGetCharacter(text, StringLen(text) - 1) == '0')
         text = StringSubstr(text, 0, StringLen(text) - 1);
      if(StringLen(text) > 0 && StringGetCharacter(text, StringLen(text) - 1) == '.')
         text = StringSubstr(text, 0, StringLen(text) - 1);
     }
   if(text == "" || text == "-")
      text = "0";
   return(text);
  }

//+------------------------------------------------------------------+
//| Bo dung JSON object toi gian.                                    |
//+------------------------------------------------------------------+
class CJsonWriter
  {
private:
   string            m_body;
   bool              m_first;

   void              Sep()
     {
      if(!m_first)
         m_body += ",";
      m_first = false;
     }

public:
                     CJsonWriter() { Reset(); }

   void              Reset()
     {
      m_body = "";
      m_first = true;
     }

   void              Str(const string key, const string value)
     {
      Sep();
      m_body += "\"" + CbJsonEscape(key) + "\":\"" + CbJsonEscape(value) + "\"";
     }

   void              Int(const string key, const long value)
     {
      Sep();
      m_body += "\"" + CbJsonEscape(key) + "\":" + IntegerToString(value);
     }

   void              Dbl(const string key, const double value, const int digits = 8)
     {
      Sep();
      m_body += "\"" + CbJsonEscape(key) + "\":" + CbNum(value, digits);
     }

   void              Bool(const string key, const bool value)
     {
      Sep();
      m_body += "\"" + CbJsonEscape(key) + "\":" + (value ? "true" : "false");
     }

   void              Null(const string key)
     {
      Sep();
      m_body += "\"" + CbJsonEscape(key) + "\":null";
     }

   //| Chen mot doan JSON da dung san (object hoac array con).
   void              Raw(const string key, const string json)
     {
      Sep();
      m_body += "\"" + CbJsonEscape(key) + "\":" + json;
     }

   string            Build() const { return("{" + m_body + "}"); }
  };

//+------------------------------------------------------------------+
//| 3. JSON: doc                                                     |
//|                                                                  |
//| Chi tach mot object o TANG NGOAI CUNG thanh cap key/value. Object |
//| va array long ben trong duoc giu nguyen dang chuoi tho de nguoi   |
//| goi tu parse tiep. Du dung cho schema o phase 3, khong can tong   |
//| quat hon.                                                        |
//+------------------------------------------------------------------+
class CJsonReader
  {
private:
   string            m_keys[];
   string            m_values[];   // gia tri tho, chuoi da bo ngoac kep va da unescape
   bool              m_isString[];
   int               m_count;
   bool              m_ok;

   static bool       IsWs(const ushort c)
     {
      return(c == ' ' || c == '\t' || c == '\n' || c == '\r');
     }

   static void       SkipWs(const string text, int &pos)
     {
      int n = StringLen(text);
      while(pos < n && IsWs(StringGetCharacter(text, pos)))
         pos++;
     }

   //| Doc mot chuoi JSON bat dau tai dau nhay kep. Tra ve false neu hong.
   static bool       ReadString(const string text, int &pos, string &out)
     {
      int n = StringLen(text);
      if(pos >= n || StringGetCharacter(text, pos) != '"')
         return(false);
      pos++;
      out = "";
      while(pos < n)
        {
         ushort c = StringGetCharacter(text, pos);
         if(c == '"')
           {
            pos++;
            return(true);
           }
         if(c == '\\')
           {
            pos++;
            if(pos >= n)
               return(false);
            ushort e = StringGetCharacter(text, pos);
            switch(e)
              {
               case 'n':  out += ShortToString(10);  break;
               case 'r':  out += ShortToString(13);  break;
               case 't':  out += ShortToString(9);   break;
               case 'b':  out += ShortToString(8);   break;
               case 'f':  out += ShortToString(12);  break;
               case '"':  out += "\"";               break;
               case '\\': out += "\\";               break;
               case '/':  out += "/";                break;
               case 'u':
                 {
                  // StringToInteger() KHONG doc duoc chuoi hex, phai tu tinh.
                  if(pos + 4 >= n)
                     return(false);
                  int code = 0;
                  for(int k = 1; k <= 4; k++)
                    {
                     ushort h = StringGetCharacter(text, pos + k);
                     int digit;
                     if(h >= '0' && h <= '9')
                        digit = h - '0';
                     else
                        if(h >= 'a' && h <= 'f')
                           digit = 10 + (h - 'a');
                        else
                           if(h >= 'A' && h <= 'F')
                              digit = 10 + (h - 'A');
                           else
                              return(false);
                     code = code * 16 + digit;
                    }
                  out += ShortToString((ushort)code);
                  pos += 4;
                  break;
                 }
               default:
                  out += ShortToString(e);
                  break;
              }
            pos++;
            continue;
           }
         out += ShortToString(c);
         pos++;
        }
      return(false);
     }

   //| Doc mot gia tri bat ky, tra ve dang chuoi tho.
   static bool       ReadValue(const string text, int &pos, string &out, bool &isString)
     {
      SkipWs(text, pos);
      int n = StringLen(text);
      if(pos >= n)
         return(false);
      ushort c = StringGetCharacter(text, pos);
      isString = false;

      if(c == '"')
        {
         isString = true;
         return(ReadString(text, pos, out));
        }

      if(c == '{' || c == '[')
        {
         // Giu nguyen doan long nhau. Dem do sau, va bo qua dau ngoac nam
         // trong chuoi - day la cho de sai nhat cua mot parser viet tay.
         ushort open  = c;
         ushort close = (c == '{') ? '}' : ']';
         int depth = 0;
         int start = pos;
         while(pos < n)
           {
            ushort d = StringGetCharacter(text, pos);
            if(d == '"')
              {
               string ignored;
               if(!ReadString(text, pos, ignored))
                  return(false);
               continue;
              }
            if(d == open)
               depth++;
            else
               if(d == close)
                 {
                  depth--;
                  if(depth == 0)
                    {
                     pos++;
                     out = StringSubstr(text, start, pos - start);
                     return(true);
                    }
                 }
            pos++;
           }
         return(false);
        }

      // So, true, false, null: doc toi dau phan cach.
      int start = pos;
      while(pos < n)
        {
         ushort d = StringGetCharacter(text, pos);
         if(d == ',' || d == '}' || d == ']' || IsWs(d))
            break;
         pos++;
        }
      out = StringSubstr(text, start, pos - start);
      return(StringLen(out) > 0);
     }

   int               IndexOf(const string key) const
     {
      for(int i = 0; i < m_count; i++)
         if(m_keys[i] == key)
            return(i);
      return(-1);
     }

public:
                     CJsonReader() { m_count = 0; m_ok = false; }

   bool              Ok() const { return(m_ok); }

   bool              Parse(const string json)
     {
      m_count = 0;
      m_ok = false;
      ArrayResize(m_keys, 0);
      ArrayResize(m_values, 0);
      ArrayResize(m_isString, 0);

      int pos = 0;
      SkipWs(json, pos);
      if(pos >= StringLen(json) || StringGetCharacter(json, pos) != '{')
         return(false);
      pos++;

      while(true)
        {
         SkipWs(json, pos);
         if(pos >= StringLen(json))
            return(false);
         ushort c = StringGetCharacter(json, pos);
         if(c == '}')
           {
            m_ok = true;
            return(true);
           }
         if(c == ',')
           {
            pos++;
            continue;
           }

         string key = "";
         if(!ReadString(json, pos, key))
            return(false);
         SkipWs(json, pos);
         if(pos >= StringLen(json) || StringGetCharacter(json, pos) != ':')
            return(false);
         pos++;

         string value = "";
         bool isString = false;
         if(!ReadValue(json, pos, value, isString))
            return(false);

         ArrayResize(m_keys, m_count + 1);
         ArrayResize(m_values, m_count + 1);
         ArrayResize(m_isString, m_count + 1);
         m_keys[m_count] = key;
         m_values[m_count] = value;
         m_isString[m_count] = isString;
         m_count++;
        }
      // Khong bao gio toi day: vong lap chi thoat bang return. Trinh bien dich
      // MQL5 khong suy luan duoc dieu do nen van doi mot lenh return o cuoi ham.
      return(false);
     }

   bool              Has(const string key) const { return(IndexOf(key) >= 0); }

   bool              IsNull(const string key) const
     {
      int i = IndexOf(key);
      return(i < 0 || (!m_isString[i] && m_values[i] == "null"));
     }

   string            GetStr(const string key, const string fallback = "") const
     {
      int i = IndexOf(key);
      if(i < 0 || (!m_isString[i] && m_values[i] == "null"))
         return(fallback);
      return(m_values[i]);
     }

   long              GetInt(const string key, const long fallback = 0) const
     {
      int i = IndexOf(key);
      if(i < 0 || (!m_isString[i] && m_values[i] == "null"))
         return(fallback);
      return(StringToInteger(m_values[i]));
     }

   double            GetDbl(const string key, const double fallback = 0.0) const
     {
      int i = IndexOf(key);
      if(i < 0 || (!m_isString[i] && m_values[i] == "null"))
         return(fallback);
      return(StringToDouble(m_values[i]));
     }

   bool              GetBool(const string key, const bool fallback = false) const
     {
      int i = IndexOf(key);
      if(i < 0)
         return(fallback);
      return(m_values[i] == "true");
     }

   //| Doan JSON tho cua mot object/array con, de parse tiep.
   string            GetRaw(const string key) const
     {
      int i = IndexOf(key);
      if(i < 0)
         return("");
      return(m_values[i]);
     }
  };

//+------------------------------------------------------------------+
//| 4. Thoi gian                                                     |
//|                                                                  |
//| Bridge luu moi timestamp dang UTC ISO 8601 co mili giay va hau to |
//| Z. EA phai sinh dung dinh dang do, neu khong Bridge se khong doc  |
//| duoc latency.                                                    |
//+------------------------------------------------------------------+
string CbNowIso()
  {
   datetime now = TimeGMT();
   MqlDateTime dt;
   TimeToStruct(now, dt);

   // MQL5 khong co dong ho tuong ung mili giay cho gio thuc. Cach lay phan le
   // dung: neo GetTickCount() vao dung thoi diem TimeGMT() nhay sang giay moi,
   // roi dem tu do. Sai so bang chu ky goi ham (100ms), thay vi la mot so
   // ngau nhien trong 0..999 nhu khi lay GetTickCount() % 1000 - cach do cho ra
   // ca latency AM, tuc la vo nghia.
   static datetime anchor_sec  = 0;
   static uint     anchor_tick = 0;
   uint tick = GetTickCount();
   if(now != anchor_sec)
     {
      anchor_sec  = now;
      anchor_tick = tick;
     }
   int ms = (int)(tick - anchor_tick);
   if(ms < 0)
      ms = 0;
   if(ms > 999)
      ms = 999;
   return(StringFormat("%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
                       dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec, ms));
  }

//+------------------------------------------------------------------+
//| 5. Ghi log                                                       |
//|                                                                  |
//| KHONG BAO GIO log token. Khong them ham nao lam viec do.          |
//+------------------------------------------------------------------+
void CbLog(const string level, const string message)
  {
   Print("[", level, "] ", message);
  }

//+------------------------------------------------------------------+
//| 6. Tep: doc/ghi UTF-8 dang nhi phan                              |
//|                                                                  |
//| Dung FILE_BIN chu khong phai FILE_TXT: FILE_TXT ghi theo ANSI va  |
//| se lam hong moi ky tu ngoai ASCII trong ten symbol.               |
//+------------------------------------------------------------------+
bool CbFileAppendLine(const string path, const string line)
  {
   int handle = FileOpen(path, FILE_READ | FILE_WRITE | FILE_BIN |
                         FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(handle == INVALID_HANDLE)
     {
      CbLog("ERROR", "Khong mo duoc file " + path + ", ma loi " +
            IntegerToString(GetLastError()));
      return(false);
     }
   FileSeek(handle, 0, SEEK_END);
   uchar bytes[];
   int n = CbUtf8Encode(line + "\n", bytes);
   if(n > 0)
      FileWriteArray(handle, bytes, 0, n);
   FileFlush(handle);
   FileClose(handle);
   return(true);
  }

//| Doc toan bo file thanh mang dong. Tra ve so dong.
int CbFileReadLines(const string path, string &lines[])
  {
   ArrayResize(lines, 0);
   if(!FileIsExist(path))
      return(0);
   int handle = FileOpen(path, FILE_READ | FILE_BIN | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(handle == INVALID_HANDLE)
      return(0);
   int size = (int)FileSize(handle);
   uchar bytes[];
   if(size > 0)
     {
      ArrayResize(bytes, size);
      FileReadArray(handle, bytes, 0, size);
     }
   FileClose(handle);

   int count = 0;
   int start = 0;
   for(int i = 0; i < size; i++)
     {
      if(bytes[i] == 10)
        {
         if(i > start)
           {
            ArrayResize(lines, count + 1);
            lines[count] = CbUtf8Decode(bytes, start, i - start);
            count++;
           }
         start = i + 1;
        }
     }
   if(start < size)
     {
      ArrayResize(lines, count + 1);
      lines[count] = CbUtf8Decode(bytes, start, size - start);
      count++;
     }
   return(count);
  }

bool CbFileWriteLines(const string path, const string &lines[], const int count)
  {
   int handle = FileOpen(path, FILE_WRITE | FILE_BIN | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(handle == INVALID_HANDLE)
     {
      CbLog("ERROR", "Khong ghi duoc file " + path);
      return(false);
     }
   for(int i = 0; i < count; i++)
     {
      uchar bytes[];
      int n = CbUtf8Encode(lines[i] + "\n", bytes);
      if(n > 0)
         FileWriteArray(handle, bytes, 0, n);
     }
   FileFlush(handle);
   FileClose(handle);
   return(true);
  }

//+------------------------------------------------------------------+
//| 7. Agent                                                         |
//+------------------------------------------------------------------+
struct CbPendingCause
  {
   string            command_id;
   long              position_id;
   datetime          at;
  };

class CBridgeAgent
  {
private:
   // -- cau hinh --
   string            m_host;
   int               m_port;
   string            m_token;      // KHONG BAO GIO ghi ra log
   string            m_role;
   long              m_magic;
   long              m_login;

   // -- socket --
   int               m_socket;
   bool              m_connected;      // socket da mo
   bool              m_handshaked;     // da nhan hello_ack
   datetime          m_next_retry;
   int               m_backoff_index;
   int               m_backoff[5];

   // -- bo dem nhan --
   uchar             m_recv[];
   int               m_recv_len;

   // -- trang thai --
   string            m_agent_id;
   long              m_seq;            // seq cua event ke tiep, ben qua khoi dong lai
   long              m_bridge_last_seq;
   datetime          m_last_heartbeat;
   datetime          m_last_specs;
   int               m_heartbeat_interval_ms;

   // -- duong dan file --
   string            m_path_state;
   string            m_path_outbox;
   string            m_path_commands;

   // -- bo nho command da thuc thi --
   string            m_cmd_ids[];
   string            m_cmd_acks[];
   datetime          m_cmd_at[];
   int               m_cmd_count;

   // -- cua so gan caused_by_command_id --
   CbPendingCause    m_causes[];
   int               m_cause_count;

   //+---------------------------------------------------------------+
   void              LoadState()
     {
      string lines[];
      int n = CbFileReadLines(m_path_state, lines);
      if(n > 0)
        {
         CJsonReader reader;
         if(reader.Parse(lines[0]))
            m_seq = reader.GetInt("seq", 0);
        }
      CbLog("INFO", "Khoi dong voi seq = " + IntegerToString(m_seq));
     }

   void              SaveState()
     {
      CJsonWriter writer;
      writer.Int("seq", m_seq);
      string lines[1];
      lines[0] = writer.Build();
      CbFileWriteLines(m_path_state, lines, 1);
     }

   void              LoadCommandMemory()
     {
      string lines[];
      int n = CbFileReadLines(m_path_commands, lines);
      m_cmd_count = 0;
      ArrayResize(m_cmd_ids, 0);
      ArrayResize(m_cmd_acks, 0);
      ArrayResize(m_cmd_at, 0);
      datetime cutoff = TimeGMT() - COPYBRIDGE_CMD_MEMORY_SEC;
      for(int i = 0; i < n; i++)
        {
         CJsonReader reader;
         if(!reader.Parse(lines[i]))
            continue;
         datetime at = (datetime)reader.GetInt("at", 0);
         if(at < cutoff)
            continue;   // qua 24 gio thi bo
         ArrayResize(m_cmd_ids, m_cmd_count + 1);
         ArrayResize(m_cmd_acks, m_cmd_count + 1);
         ArrayResize(m_cmd_at, m_cmd_count + 1);
         m_cmd_ids[m_cmd_count]  = reader.GetStr("command_id");
         m_cmd_acks[m_cmd_count] = reader.GetStr("ack");
         m_cmd_at[m_cmd_count]   = at;
         m_cmd_count++;
        }
      // Ghi lai file da loc de no khong phinh mai.
      string kept[];
      ArrayResize(kept, m_cmd_count);
      for(int i = 0; i < m_cmd_count; i++)
        {
         CJsonWriter writer;
         writer.Str("command_id", m_cmd_ids[i]);
         writer.Int("at", (long)m_cmd_at[i]);
         writer.Str("ack", m_cmd_acks[i]);
         kept[i] = writer.Build();
        }
      CbFileWriteLines(m_path_commands, kept, m_cmd_count);
     }

   //+---------------------------------------------------------------+
   //| Cat bo phan hang doi Bridge da xac nhan.                       |
   //+---------------------------------------------------------------+
   void              TrimOutbox(const long last_seq)
     {
      string lines[];
      int n = CbFileReadLines(m_path_outbox, lines);
      if(n == 0)
         return;
      string kept[];
      int count = 0;
      for(int i = 0; i < n; i++)
        {
         CJsonReader reader;
         if(!reader.Parse(lines[i]))
            continue;
         if(reader.GetInt("seq", 0) <= last_seq)
            continue;
         ArrayResize(kept, count + 1);
         kept[count] = lines[i];
         count++;
        }
      CbFileWriteLines(m_path_outbox, kept, count);
      if(n != count)
         CbLog("INFO", "Cat bo " + IntegerToString(n - count) +
               " event da duoc Bridge xac nhan, con lai " + IntegerToString(count));
     }

   //+---------------------------------------------------------------+
   //| Gui bu moi event con trong hang doi.                           |
   //+---------------------------------------------------------------+
   void              ResendFrom(const long from_seq)
     {
      string lines[];
      int n = CbFileReadLines(m_path_outbox, lines);
      int sent = 0;
      for(int i = 0; i < n; i++)
        {
         CJsonReader reader;
         if(!reader.Parse(lines[i]))
            continue;
         if(reader.GetInt("seq", 0) < from_seq)
            continue;
         if(SendLine(lines[i]))
            sent++;
        }
      CbLog("INFO", "Gui bu " + IntegerToString(sent) + " event tu seq " +
            IntegerToString(from_seq));
     }

   //+---------------------------------------------------------------+
   //| Gui mot dong da dung san qua socket.                           |
   //+---------------------------------------------------------------+
   bool              SendLine(const string line)
     {
      if(!m_connected)
         return(false);
      uchar bytes[];
      int n = CbUtf8Encode(line + "\n", bytes);
      if(n <= 0)
         return(false);
      int written = SocketSend(m_socket, bytes, n);
      if(written != n)
        {
         CbLog("WARNING", "Gui khong tron goi (" + IntegerToString(written) + "/" +
               IntegerToString(n) + "), dong ket noi de noi lai");
         Disconnect();
         return(false);
        }
      return(true);
     }

   //+---------------------------------------------------------------+
   //| Doc socket, cat ra tung dong.                                  |
   //+---------------------------------------------------------------+
   void              PumpSocket()
     {
      if(!m_connected)
         return;
      uint available = SocketIsReadable(m_socket);
      while(available > 0)
        {
         uchar chunk[];
         int read = SocketRead(m_socket, chunk, (int)available, 50);
         if(read <= 0)
            break;
         if(m_recv_len + read > COPYBRIDGE_MAX_LINE)
           {
            CbLog("ERROR", "Bridge gui dong qua dai, dong ket noi");
            m_recv_len = 0;
            Disconnect();
            return;
           }
         if(ArraySize(m_recv) < m_recv_len + read)
            ArrayResize(m_recv, m_recv_len + read + 4096);
         for(int i = 0; i < read; i++)
            m_recv[m_recv_len + i] = chunk[i];
         m_recv_len += read;
         available = SocketIsReadable(m_socket);
        }

      // Cat tung dong ket thuc bang \n.
      while(true)
        {
         int newline = -1;
         for(int i = 0; i < m_recv_len; i++)
            if(m_recv[i] == 10)
              {
               newline = i;
               break;
              }
         if(newline < 0)
            break;
         string line = "";
         if(newline > 0)
            line = CbUtf8Decode(m_recv, 0, newline);
         // Don phan da tieu thu.
         int rest = m_recv_len - newline - 1;
         for(int i = 0; i < rest; i++)
            m_recv[i] = m_recv[newline + 1 + i];
         m_recv_len = rest;
         if(StringLen(line) > 0)
            HandleLine(line);
        }
     }

   //+---------------------------------------------------------------+
   void              HandleLine(const string line)
     {
      CJsonReader reader;
      if(!reader.Parse(line))
        {
         CbLog("ERROR", "Bridge gui dong khong parse duoc: " + StringSubstr(line, 0, 200));
         return;
        }
      string kind = reader.GetStr("kind");

      if(kind == "hello_ack")
        {
         m_agent_id = reader.GetStr("agent_id");
         m_bridge_last_seq = reader.GetInt("last_seq", 0);
         m_handshaked = true;
         CbLog("INFO", "Bat tay xong, agent_id = " + m_agent_id +
               ", Bridge co last_seq = " + IntegerToString(m_bridge_last_seq));

         string config = reader.GetRaw("config");
         if(StringLen(config) > 0)
           {
            CJsonReader cfg;
            if(cfg.Parse(config))
               m_heartbeat_interval_ms = (int)cfg.GetInt("heartbeat_interval_ms",
                                                         m_heartbeat_interval_ms);
           }

         TrimOutbox(m_bridge_last_seq);
         // CO Y KHONG tu gui bu o day. Bridge phat hien lo hong va gui message
         // `resend` (phase 3, muc 3.4) - de ca hai ben cung tu quyet dinh thi moi
         // event bi gui hai lan moi lan noi lai. Rang buoc event_id UNIQUE o Bridge
         // van bat het, nhung do la lang phi chu khong phai thiet ke.
         SendSymbolSpecs();
         return;
        }

      if(kind == "resend")
        {
         long from_seq = reader.GetInt("from_seq", 1);
         CbLog("WARNING", "Bridge yeu cau gui bu tu seq " + IntegerToString(from_seq));
         ResendFrom(from_seq);
         return;
        }

      if(kind == "config")
        {
         if(reader.Has("heartbeat_interval_ms") && !reader.IsNull("heartbeat_interval_ms"))
            m_heartbeat_interval_ms = (int)reader.GetInt("heartbeat_interval_ms",
                                                         m_heartbeat_interval_ms);
         OnConfig(reader);
         return;
        }

      if(kind == "error")
        {
         CbLog("ERROR", "Bridge tu choi: " + reader.GetStr("code") + " - " +
               reader.GetStr("message"));
         return;
        }

      if(kind == "command")
        {
         HandleCommand(reader);
         return;
        }

      CbLog("WARNING", "Bridge gui kind khong biet: " + kind);
     }

   //+---------------------------------------------------------------+
   //| Tinh bat bien: command da xu ly thi tra ve ACK CU, khong thuc   |
   //| thi lan hai.                                                   |
   //+---------------------------------------------------------------+
   void              HandleCommand(CJsonReader &reader)
     {
      string command_id = reader.GetStr("command_id");
      string type = reader.GetStr("type");

      int known = FindCommand(command_id);
      if(known >= 0)
        {
         CbLog("INFO", "Command " + command_id + " da xu ly truoc do, tra lai ack cu");
         SendLine(m_cmd_acks[known]);
         return;
        }

      if(type == "REQUEST_SNAPSHOT")
        {
         string ack = SendSnapshot(command_id);
         RememberCommand(command_id, ack);
         return;
        }

      // Cac loai con lai do lop con xu ly (EA Client o phase 5). EA Master
      // khong thuc thi lenh mo hay dong.
      string ack = OnCommand(command_id, type, reader);
      if(StringLen(ack) > 0)
         RememberCommand(command_id, ack);
     }

   int               FindCommand(const string command_id) const
     {
      for(int i = 0; i < m_cmd_count; i++)
         if(m_cmd_ids[i] == command_id)
            return(i);
      return(-1);
     }

protected:
   //+---------------------------------------------------------------+
   //| Ghi nho mot command da xu ly.                                  |
   //|                                                                |
   //| Ghi vao FILE truoc khi tra ack, va o phase 5 la truoc khi goi   |
   //| OrderSend. Crash sau OrderSend ma truoc khi ghi se lam mo lenh  |
   //| hai lan khi Bridge gui lai - mot lenh THIEU an toan hon nhieu   |
   //| so voi mot lenh THUA.                                          |
   //+---------------------------------------------------------------+
   void              RememberCommand(const string command_id, const string ack_line)
     {
      ArrayResize(m_cmd_ids, m_cmd_count + 1);
      ArrayResize(m_cmd_acks, m_cmd_count + 1);
      ArrayResize(m_cmd_at, m_cmd_count + 1);
      m_cmd_ids[m_cmd_count]  = command_id;
      m_cmd_acks[m_cmd_count] = ack_line;
      m_cmd_at[m_cmd_count]   = TimeGMT();
      m_cmd_count++;

      CJsonWriter writer;
      writer.Str("command_id", command_id);
      writer.Int("at", (long)TimeGMT());
      writer.Str("ack", ack_line);
      CbFileAppendLine(m_path_commands, writer.Build());
     }

   //+---------------------------------------------------------------+
   //| Ghi nho (command_id, position_id, thoi diem) de gan            |
   //| caused_by_command_id cho deal sap phat sinh.                   |
   //|                                                                |
   //| Day la TOAN BO co che chong vong lap (D-08). Phase 4 chi cai    |
   //| san khung; no duoc dung that khi Master nhan lenh dong o phase 7|
   //+---------------------------------------------------------------+
   void              RememberCause(const string command_id, const long position_id)
     {
      ArrayResize(m_causes, m_cause_count + 1);
      m_causes[m_cause_count].command_id  = command_id;
      m_causes[m_cause_count].position_id = position_id;
      m_causes[m_cause_count].at          = TimeGMT();
      m_cause_count++;
     }

public:
   //+---------------------------------------------------------------+
   //| Tim command da gay ra mot deal tren position nay.              |
   //| Tra ve "" neu deal do KHONG phai do bot gay ra - nghia la nguoi |
   //| dung hoac broker lam, va su kien duoc phep lan truyen (D-08).   |
   //+---------------------------------------------------------------+
   string            CauseFor(const long position_id)
     {
      datetime cutoff = TimeGMT() - COPYBRIDGE_CAUSE_WINDOW_SEC;
      string found = "";
      int write = 0;
      for(int i = 0; i < m_cause_count; i++)
        {
         if(m_causes[i].at < cutoff)
            continue;   // qua cua so thi bo
         if(m_causes[i].position_id == position_id && found == "")
            found = m_causes[i].command_id;
         if(write != i)
            m_causes[write] = m_causes[i];
         write++;
        }
      m_cause_count = write;
      ArrayResize(m_causes, m_cause_count);
      return(found);
     }

                     CBridgeAgent()
     {
      m_socket = INVALID_HANDLE;
      m_connected = false;
      m_handshaked = false;
      m_seq = 0;
      m_bridge_last_seq = 0;
      m_recv_len = 0;
      m_cmd_count = 0;
      m_cause_count = 0;
      m_backoff_index = 0;
      m_next_retry = 0;
      m_last_heartbeat = 0;
      m_last_specs = 0;
      m_heartbeat_interval_ms = 1000;
      m_backoff[0] = 1;
      m_backoff[1] = 2;
      m_backoff[2] = 5;
      m_backoff[3] = 10;
      m_backoff[4] = 10;
      ArrayResize(m_recv, 8192);
     }

   //+---------------------------------------------------------------+
   bool              Init(const string host, const int port, const string token,
                          const string role, const long magic)
     {
      m_host = host;
      m_port = port;
      m_token = token;
      m_role = role;
      m_magic = magic;
      m_login = AccountInfoInteger(ACCOUNT_LOGIN);

      string prefix = COPYBRIDGE_DIR + "\\" + IntegerToString(m_login) + "_";
      m_path_state    = prefix + "state.json";
      m_path_outbox   = prefix + "outbox.ndjson";
      m_path_commands = prefix + "commands.ndjson";

      LoadState();
      LoadCommandMemory();
      return(true);
     }

   void              Shutdown()
     {
      SaveState();
      Disconnect();
     }

   // -- truy van trang thai, dung cho dong trang thai tren chart --
   bool              IsConnected() const { return(m_connected && m_handshaked); }
   string            AgentId()     const { return(m_agent_id); }
   long              Seq()         const { return(m_seq); }
   long              Magic()       const { return(m_magic); }
   string            Role()        const { return(m_role); }

   int               OutboxCount()
     {
      string lines[];
      return(CbFileReadLines(m_path_outbox, lines));
     }

   //+---------------------------------------------------------------+
   void              Disconnect()
     {
      if(m_socket != INVALID_HANDLE)
        {
         SocketClose(m_socket);
         m_socket = INVALID_HANDLE;
        }
      m_connected = false;
      m_handshaked = false;
      m_recv_len = 0;
     }

   //+---------------------------------------------------------------+
   //| Ket noi lai voi backoff 1s, 2s, 5s, 10s roi giu o 10s.          |
   //+---------------------------------------------------------------+
   void              EnsureConnected()
     {
      if(m_connected)
         return;
      if(TimeLocal() < m_next_retry)
         return;

      m_socket = SocketCreate();
      if(m_socket == INVALID_HANDLE)
        {
         ScheduleRetry();
         return;
        }
      if(!SocketConnect(m_socket, m_host, m_port, 1000))
        {
         SocketClose(m_socket);
         m_socket = INVALID_HANDLE;
         ScheduleRetry();
         return;
        }

      m_connected = true;
      m_handshaked = false;
      m_recv_len = 0;
      m_backoff_index = 0;
      CbLog("INFO", "Da ket noi toi Bridge " + m_host + ":" + IntegerToString(m_port));
      SendHello();
     }

   void              ScheduleRetry()
     {
      int wait = m_backoff[m_backoff_index];
      if(m_backoff_index < 4)
         m_backoff_index++;
      m_next_retry = TimeLocal() + wait;
     }

   //+---------------------------------------------------------------+
   void              SendHello()
     {
      CJsonWriter writer;
      writer.Int("v", COPYBRIDGE_PROTOCOL_VERSION);
      writer.Str("kind", "hello");
      writer.Str("ts", CbNowIso());
      writer.Str("token", m_token);
      writer.Str("role", m_role);
      writer.Int("account_login", m_login);
      writer.Str("broker_server", AccountInfoString(ACCOUNT_SERVER));
      writer.Int("terminal_build", TerminalInfoInteger(TERMINAL_BUILD));
      writer.Int("magic", m_magic);
      writer.Int("seq", m_seq);
      SendLine(writer.Build());
     }

   //+---------------------------------------------------------------+
   //| Day thong so symbol cua toan bo Market Watch.                  |
   //+---------------------------------------------------------------+
   void              SendSymbolSpecs()
     {
      if(!m_handshaked)
         return;
      string items = "";
      int total = SymbolsTotal(true);
      for(int i = 0; i < total; i++)
        {
         string symbol = SymbolName(i, true);
         CJsonWriter spec;
         spec.Str("symbol", symbol);
         spec.Int("digits", (long)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
         spec.Dbl("point", SymbolInfoDouble(symbol, SYMBOL_POINT));
         spec.Dbl("volume_min", SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN));
         spec.Dbl("volume_max", SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX));
         spec.Dbl("volume_step", SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP));
         spec.Dbl("contract_size", SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE));
         spec.Dbl("tick_value", SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE));
         spec.Dbl("tick_size", SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE));
         spec.Int("filling_mode", (long)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE));
         spec.Int("trade_mode", (long)SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE));
         if(StringLen(items) > 0)
            items += ",";
         items += spec.Build();
        }

      CJsonWriter writer;
      writer.Int("v", COPYBRIDGE_PROTOCOL_VERSION);
      writer.Str("kind", "symbol_specs");
      writer.Str("ts", CbNowIso());
      writer.Raw("symbols", "[" + items + "]");
      if(SendLine(writer.Build()))
        {
         m_last_specs = TimeGMT();
         CbLog("INFO", "Da day " + IntegerToString(total) + " symbol spec");
        }
     }

   //+---------------------------------------------------------------+
   //| Snapshot: gui TOAN BO vi the, ke ca vi the khong mang magic cua |
   //| bot - Bridge can biet de phan biet lenh mo tay (FR-12).         |
   //| Tra ve dong ack da gui, de ghi vao bo nho command.              |
   //+---------------------------------------------------------------+
   string            SendSnapshot(const string command_id)
     {
      string items = "";
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         CJsonWriter position;
         position.Int("position_id", (long)PositionGetInteger(POSITION_IDENTIFIER));
         position.Int("ticket", (long)ticket);
         position.Str("symbol", PositionGetString(POSITION_SYMBOL));
         position.Str("direction",
                      (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "BUY" : "SELL");
         position.Dbl("volume", PositionGetDouble(POSITION_VOLUME));
         position.Dbl("price_open", PositionGetDouble(POSITION_PRICE_OPEN));
         position.Int("magic", (long)PositionGetInteger(POSITION_MAGIC));
         if(StringLen(items) > 0)
            items += ",";
         items += position.Build();
        }

      CJsonWriter writer;
      writer.Int("v", COPYBRIDGE_PROTOCOL_VERSION);
      writer.Str("kind", "snapshot");
      writer.Str("ts", CbNowIso());
      if(StringLen(command_id) > 0)
         writer.Str("command_id", command_id);
      writer.Raw("positions", "[" + items + "]");
      SendLine(writer.Build());

      CJsonWriter ack;
      ack.Int("v", COPYBRIDGE_PROTOCOL_VERSION);
      ack.Str("kind", "ack");
      ack.Str("ts", CbNowIso());
      ack.Str("command_id", command_id);
      ack.Str("status", "ok");
      ack.Int("retcode", 10009);
      ack.Int("attempt", 1);
      string line = ack.Build();
      SendLine(line);
      return(line);
     }

   //+---------------------------------------------------------------+
   //| Heartbeat.                                                     |
   //|                                                                |
   //| broker_connected la BAT BUOC. Thieu no thi trang thai "agent    |
   //| con song nhung terminal mat ket noi san" trong giong het trang  |
   //| thai khoe manh.                                                |
   //+---------------------------------------------------------------+
   void              SendHeartbeat()
     {
      CJsonWriter writer;
      writer.Int("v", COPYBRIDGE_PROTOCOL_VERSION);
      writer.Str("kind", "heartbeat");
      writer.Str("ts", CbNowIso());
      writer.Int("seq", m_seq);
      writer.Bool("broker_connected",
                  (bool)TerminalInfoInteger(TERMINAL_CONNECTED));
      writer.Dbl("equity", AccountInfoDouble(ACCOUNT_EQUITY), 2);
      writer.Dbl("margin_level", AccountInfoDouble(ACCOUNT_MARGIN_LEVEL), 2);
      writer.Int("positions_count", PositionsTotal());
      writer.Str("ts_agent", CbNowIso());
      SendLine(writer.Build());
      m_last_heartbeat = TimeGMT();
     }

   //+---------------------------------------------------------------+
   //| Gui mot event.                                                 |
   //|                                                                |
   //| THU TU QUAN TRONG: ghi file TRUOC, gui socket SAU. Lam nguoc    |
   //| lai thi mot cu crash giua hai buoc se nuot mat su kien ma khong |
   //| ai biet. Ghi truoc thi te nhat la gui trung, va trung thi       |
   //| event_id o Bridge da lo.                                        |
   //+---------------------------------------------------------------+
   void              SendEvent(const string event_type, const string data_json,
                               const string caused_by_command_id)
     {
      m_seq++;
      string event_id = "EVT-" + IntegerToString(m_login) + "-" + IntegerToString(m_seq);

      CJsonWriter writer;
      writer.Int("v", COPYBRIDGE_PROTOCOL_VERSION);
      writer.Str("kind", "event");
      writer.Str("ts", CbNowIso());
      writer.Str("id", event_id);
      writer.Int("seq", m_seq);
      writer.Str("type", event_type);
      if(StringLen(caused_by_command_id) > 0)
         writer.Str("caused_by_command_id", caused_by_command_id);
      writer.Raw("data", data_json);
      string line = writer.Build();

      CbFileAppendLine(m_path_outbox, line);   // ghi truoc
      SaveState();                             // seq ben qua khoi dong lai
      SendLine(line);                          // gui sau
     }

   //+---------------------------------------------------------------+
   //| Goi moi 100ms tu OnTimer.                                      |
   //+---------------------------------------------------------------+
   void              Poll()
     {
      EnsureConnected();
      PumpSocket();
      if(!m_handshaked)
         return;

      if((TimeGMT() - m_last_heartbeat) * 1000 >= m_heartbeat_interval_ms)
         SendHeartbeat();
      if(TimeGMT() - m_last_specs >= COPYBRIDGE_SPEC_INTERVAL_SEC)
         SendSymbolSpecs();
     }

   //+---------------------------------------------------------------+
   //| Diem mo rong cho EA Client o phase 5. EA Master khong thuc thi  |
   //| lenh mo hay dong nao.                                          |
   //+---------------------------------------------------------------+
   virtual string    OnCommand(const string command_id, const string type,
                               CJsonReader &reader)
     {
      CbLog("WARNING", "Agent role " + m_role + " khong thuc thi command loai " + type);
      CJsonWriter ack;
      ack.Int("v", COPYBRIDGE_PROTOCOL_VERSION);
      ack.Str("kind", "ack");
      ack.Str("ts", CbNowIso());
      ack.Str("command_id", command_id);
      ack.Str("status", "rejected");
      ack.Str("retmsg", "Command type not supported by this agent role");
      ack.Int("attempt", 1);
      string line = ack.Build();
      SendLine(line);
      return(line);
     }

   virtual void      OnConfig(CJsonReader &reader) { }
  };

//+------------------------------------------------------------------+
//| 8. Bat su kien giao dich                                         |
//|                                                                  |
//| DAY LA PHAN DE SAI NHAT CUA CA DU AN.                            |
//|                                                                  |
//| MQL5 ban OnTradeTransaction NHIEU LAN cho mot hanh dong giao      |
//| dich: ORDER_ADD, ORDER_UPDATE, DEAL_ADD, HISTORY_ADD. Xu ly het   |
//| thi se copy trung 3-4 lan.                                       |
//|                                                                  |
//| CHI xu ly TRADE_TRANSACTION_DEAL_ADD. Bo qua tat ca loai con lai. |
//+------------------------------------------------------------------+
void CbProcessTransaction(CBridgeAgent &agent, const MqlTradeTransaction &trans)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(trans.deal == 0)
      return;

   // Deal vua sinh co the chua co trong lich su ngay lap tuc.
   if(!HistoryDealSelect(trans.deal))
     {
      // Thoi gian trong lich su la GIO SERVER, khong phai GMT.
      HistorySelect(TimeCurrent() - 300, TimeCurrent() + 60);
      if(!HistoryDealSelect(trans.deal))
        {
         CbLog("ERROR", "Khong chon duoc deal " + IntegerToString((long)trans.deal) +
               " trong lich su, event bi bo qua");
         return;
        }
     }

   long entry       = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   long position_id = HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   long deal_type   = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
   long magic       = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   double volume    = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
   double price     = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
   string symbol    = HistoryDealGetString(trans.deal, DEAL_SYMBOL);

   // Chi quan tam deal mua/ban. Nap tien, phi qua dem... khong phai su kien vi the.
   if(deal_type != DEAL_TYPE_BUY && deal_type != DEAL_TYPE_SELL)
      return;

   string entry_name = "";
   string event_type = "";
   double volume_after = 0.0;
   string direction = "";

   if(entry == DEAL_ENTRY_IN)
     {
      entry_name = "IN";
      event_type = "position_opened";
      direction  = (deal_type == DEAL_TYPE_BUY) ? "BUY" : "SELL";
      // Vi the vua mo; volume_after la volume that cua vi the, khong phai
      // volume cua deal (hai cai co the khac khi co nhieu deal khop tung phan).
      if(PositionSelectByTicket(position_id))
         volume_after = PositionGetDouble(POSITION_VOLUME);
      else
         volume_after = volume;
     }
   else
      if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
        {
         entry_name = (entry == DEAL_ENTRY_OUT_BY) ? "OUT_BY" : "OUT";
         // Deal dong nguoc chieu voi vi the.
         direction = (deal_type == DEAL_TYPE_BUY) ? "SELL" : "BUY";

         // Phan biet dong toan phan voi dong mot phan: con chon duoc vi the
         // thi la mot phan, khong chon duoc thi la toan phan.
         // LUON gui volume_after THAT, khong tinh bang phep tru (D-14).
         if(PositionSelectByTicket(position_id))
           {
            volume_after = PositionGetDouble(POSITION_VOLUME);
            event_type = (volume_after > 0.0) ? "position_changed" : "position_closed";
           }
         else
           {
            volume_after = 0.0;
            event_type = "position_closed";
           }
         if(entry == DEAL_ENTRY_OUT_BY)
            event_type = "position_closed";
        }
      else
         if(entry == DEAL_ENTRY_INOUT)
           {
            // Chi co o tai khoan Netting. Bot chi ho tro Hedging.
            entry_name = "INOUT";
            CbLog("CRITICAL", "Nhan DEAL_ENTRY_INOUT tren position " +
                  IntegerToString(position_id) +
                  " - tai khoan nay co the dang o che do Netting. Bot chi ho tro Hedging.");
            CJsonWriter data;
            data.Int("position_id", position_id);
            data.Int("deal_id", (long)trans.deal);
            data.Str("symbol", symbol);
            data.Dbl("volume_delta", volume);
            data.Dbl("price", price);
            data.Int("magic", magic);
            CJsonWriter extra;
            extra.Str("reason", "DEAL_ENTRY_INOUT_ON_NETTING_ACCOUNT");
            data.Raw("extra", extra.Build());
            agent.SendEvent("order_rejected", data.Build(), "");
            return;
           }
         else
            return;   // loai entry khac: bo qua

   string cause = agent.CauseFor(position_id);

   CJsonWriter data;
   data.Int("position_id", position_id);
   data.Int("deal_id", (long)trans.deal);
   data.Str("deal_entry", entry_name);
   data.Str("symbol", symbol);
   data.Str("direction", direction);
   data.Dbl("volume_delta", volume);
   data.Dbl("volume_after", volume_after);
   data.Dbl("price", price);
   data.Int("magic", magic);

   agent.SendEvent(event_type, data.Build(), cause);
  }
//+------------------------------------------------------------------+
