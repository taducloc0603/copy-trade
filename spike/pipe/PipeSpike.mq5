//+------------------------------------------------------------------+
//| PipeSpike.mq5 -- EA THU cho Buoc 0 cua huong A (named pipe).      |
//| KHONG phai EA san pham. Khong dat lenh, khong doc gia.            |
//|                                                                  |
//| Tu do va tu bao cao, moi 10 giay mot dong "report" gui len        |
//| server va in ra tab Experts:                                      |
//|  - pump_max_us: lan doc pipe lau nhat trong OnTimer (cau 1:       |
//|    doc co bi treo khong). Duoi vai nghin us la on.                |
//|  - rtt: ping -> pong qua pipe.                                    |
//|  - so lan noi lai (cau 2: tat server roi bat lai).                |
//| Khong can "Allow WebRequest", khong can "Allow DLL imports".      |
//+------------------------------------------------------------------+
#property copyright "CopyBridge"
#property version   "1.00"
#property strict

input string PipeName = "copybridge-spike";   // Ten pipe (khop --ten cua pipe_server.py)
input string Role     = "MASTER";             // Chi de phan biet trong log: MASTER / CLIENT

int      g_h = INVALID_HANDLE;
uchar    g_buf[];
int      g_buf_len = 0;
ulong    g_next_retry_us = 0;
int      g_retry_ms = 1000;
int      g_last_open_err = -1;

int      g_so_lan_noi = 0;
int      g_ping_id = 0;
ulong    g_next_ping_us = 0;
ulong    g_next_report_us = 0;

// Thong ke trong cua so 10 giay
ulong    g_pump_max_us = 0;
int      g_pong = 0;
ulong    g_rtt_sum_us = 0;
ulong    g_rtt_max_us = 0;
int      g_tick = 0;
int      g_write_fail = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetMillisecondTimer(100);   // dung nhip cua EA that
   PrintFormat("PipeSpike: pipe=\\\\.\\pipe\\%s role=%s", PipeName, Role);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   Dong("OnDeinit");
   Comment("");
  }

//+------------------------------------------------------------------+
void Dong(const string ly_do)
  {
   if(g_h != INVALID_HANDLE)
     {
      FileClose(g_h);
      g_h = INVALID_HANDLE;
      PrintFormat("PipeSpike: DONG pipe (%s)", ly_do);
     }
   g_buf_len = 0;
   g_next_retry_us = GetMicrosecondCount() + (ulong)g_retry_ms * 1000;
  }

//+------------------------------------------------------------------+
bool Gui(const string line)
  {
   if(g_h == INVALID_HANDLE)
      return(false);
   uchar b[];
   int n = StringToCharArray(line + "\n", b, 0, WHOLE_ARRAY, CP_UTF8) - 1;   // bo \0 cuoi
   ResetLastError();
   uint w = FileWriteArray(g_h, b, 0, n);
   FileFlush(g_h);
   int err = GetLastError();
   if((int)w != n || err != 0)
     {
      g_write_fail++;
      PrintFormat("PipeSpike: GHI LOI %u/%d err=%d -> coi nhu server da mat", w, n, err);
      Dong("ghi loi");
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
void ThuMo()
  {
   if(GetMicrosecondCount() < g_next_retry_us)
      return;
   ResetLastError();
   g_h = FileOpen("\\\\.\\pipe\\" + PipeName, FILE_READ | FILE_WRITE | FILE_BIN);
   if(g_h == INVALID_HANDLE)
     {
      int err = GetLastError();
      // Chi in khi ma loi doi, khong ngap log moi giay.
      if(err != g_last_open_err)
         PrintFormat("PipeSpike: chua mo duoc pipe, err=%d (server chua chay / pipe ban). Thu lai moi %d ms",
                     err, g_retry_ms);
      g_last_open_err = err;
      g_next_retry_us = GetMicrosecondCount() + (ulong)g_retry_ms * 1000;
      return;
     }
   g_last_open_err = -1;
   g_so_lan_noi++;
   PrintFormat("PipeSpike: DA NOI pipe (lan %d)", g_so_lan_noi);
   Gui(StringFormat("{\"type\":\"hello\",\"role\":\"%s\",\"account\":%I64d,\"lan_noi\":%d}",
                    Role, AccountInfoInteger(ACCOUNT_LOGIN), g_so_lan_noi));
  }

//+------------------------------------------------------------------+
//| Doc het nhung gi dang cho, KHONG cho them. Day la cau hoi 1.       |
//+------------------------------------------------------------------+
void Pump()
  {
   ulong t0 = GetMicrosecondCount();
   ResetLastError();
   ulong avail = FileSize(g_h);          // voi pipe: so byte dang cho (CFilePipe::WaitForRead dung dung cach nay)
   int err = GetLastError();
   if(err != 0)
     {
      PrintFormat("PipeSpike: FileSize loi err=%d -> coi nhu server da mat", err);
      Dong("FileSize loi");
      return;
     }
   if(avail > 0)
     {
      if(ArraySize(g_buf) < g_buf_len + (int)avail)
         ArrayResize(g_buf, g_buf_len + (int)avail + 4096);
      uint r = FileReadArray(g_h, g_buf, g_buf_len, (int)avail);
      g_buf_len += (int)r;
     }
   ulong dt = GetMicrosecondCount() - t0;
   if(dt > g_pump_max_us)
      g_pump_max_us = dt;

   // Cat tung dong
   int start = 0;
   for(int i = 0; i < g_buf_len; i++)
     {
      if(g_buf[i] != 10)
         continue;
      string line = CharArrayToString(g_buf, start, i - start, CP_UTF8);
      XuLy(line);
      start = i + 1;
     }
   if(start > 0)
     {
      uchar con[];
      ArrayCopy(con, g_buf, 0, start, g_buf_len - start);
      g_buf_len -= start;
      ArrayCopy(g_buf, con, 0, 0, g_buf_len);
     }
  }

//+------------------------------------------------------------------+
long LaySo(const string line, const string key)
  {
   int p = StringFind(line, "\"" + key + "\":");
   if(p < 0)
      return(-1);
   return(StringToInteger(StringSubstr(line, p + StringLen(key) + 3)));
  }

//+------------------------------------------------------------------+
void XuLy(const string line)
  {
   if(StringFind(line, "\"pong\"") >= 0)
     {
      ulong rtt = GetMicrosecondCount() - (ulong)LaySo(line, "us");
      g_pong++;
      g_rtt_sum_us += rtt;
      if(rtt > g_rtt_max_us)
         g_rtt_max_us = rtt;
     }
   else
      if(StringFind(line, "\"tick\"") >= 0)
         g_tick++;
      else
         PrintFormat("PipeSpike: <- %s", line);
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   if(g_h == INVALID_HANDLE)
     {
      ThuMo();
      HienThi();
      return;
     }
   Pump();
   if(g_h == INVALID_HANDLE)
     {
      HienThi();
      return;
     }

   ulong now = GetMicrosecondCount();
   // Ping moi giay: vua do rtt, vua la cach phat hien server chet (cau 2) -- ghi vao pipe gay se loi.
   if(now >= g_next_ping_us)
     {
      g_ping_id++;
      Gui(StringFormat("{\"type\":\"ping\",\"id\":%d,\"us\":%I64u}", g_ping_id, now));
      g_next_ping_us = now + 1000000;
     }
   if(g_h != INVALID_HANDLE && now >= g_next_report_us)
     {
      if(g_next_report_us != 0)
         BaoCao();
      g_next_report_us = now + 10000000;
     }
   HienThi();
  }

//+------------------------------------------------------------------+
void BaoCao()
  {
   ulong rtt_avg = g_pong > 0 ? g_rtt_sum_us / g_pong : 0;
   string s = StringFormat("{\"type\":\"report\",\"role\":\"%s\",\"lan_noi\":%d,\"pump_max_us\":%I64u,"
                           "\"pong\":%d,\"rtt_avg_us\":%I64u,\"rtt_max_us\":%I64u,\"tick\":%d,\"ghi_loi\":%d}",
                           Role, g_so_lan_noi, g_pump_max_us, g_pong, rtt_avg, g_rtt_max_us, g_tick,
                           g_write_fail);
   Print("PipeSpike: BAO CAO ", s);
   Gui(s);
   g_pump_max_us = 0;
   g_pong = 0;
   g_rtt_sum_us = 0;
   g_rtt_max_us = 0;
   g_tick = 0;
  }

//+------------------------------------------------------------------+
void HienThi()
  {
   Comment(StringFormat("PipeSpike [%s]  %s\nlan noi: %d   ghi loi: %d\npump max (10s): %I64u us",
                        Role, g_h == INVALID_HANDLE ? "CHUA NOI / DANG THU LAI" : "DA NOI",
                        g_so_lan_noi, g_write_fail, g_pump_max_us));
  }
//+------------------------------------------------------------------+
