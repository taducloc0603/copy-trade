"""Pipe server THỬ cho Bước 0 của hướng A (named pipe thay TCP). Không phải code sản phẩm.

Trả lời bốn câu hỏi, đi cặp với ``PipeSpike.mq5``:

1. EA đọc pipe trong ``OnTimer`` mà không treo không?  -> EA tự đo, server chỉ đẩy ``tick``.
2. Server chết / khởi động lại thì EA có biết và nối lại không?  -> Ctrl+C rồi chạy lại.
3. Server chạy bằng LocalSystem thì MT5 (tài khoản thường) có mở được pipe không?
   -> ``chay-bang-system.ps1``. Thêm ``--dacl-mac-dinh`` để thấy DACL mặc định chặn EA ghi.
4. Hai EA (Master + Client) nối cùng lúc?  -> mỗi EA một instance pipe, log ghi PID từng bên.

Chỉ dùng thư viện chuẩn (ctypes), một luồng cho mỗi EA, thăm dò bằng ``PeekNamedPipe``: ở bản
thử, đọc chặn và ghi trên cùng một handle đồng bộ sẽ khoá nhau, nên không dùng ``ReadFile`` chặn.

    python spike\\pipe\\pipe_server.py [--ten copybridge-spike] [--log file.log] [--dacl-mac-dinh]
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import threading
import time
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
PIPE_UNLIMITED_INSTANCES = 255
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
ERROR_PIPE_CONNECTED = 535
ERROR_BROKEN_PIPE = 109
SDDL_REVISION_1 = 1

# SYSTEM, Administrators, chủ sở hữu: toàn quyền. Authenticated Users: đọc + ghi.
# Không có dòng AU thì một dịch vụ LocalSystem tạo pipe mà tài khoản thường chỉ ĐỌC được.
SDDL = "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;OW)(A;;GRGW;;;AU)"


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", wintypes.LPVOID),
                ("bInheritHandle", wintypes.BOOL)]


k32.CreateNamedPipeW.restype = wintypes.HANDLE
k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.POINTER(SECURITY_ATTRIBUTES)]
k32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
k32.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                              ctypes.POINTER(wintypes.DWORD)]
k32.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                         ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
k32.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
k32.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
k32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
k32.CloseHandle.argtypes = [wintypes.HANDLE]
adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.ULONG)]

_log_file = None
_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with _log_lock:
        print(line, flush=True)
        if _log_file is not None:
            _log_file.write(line + "\n")
            _log_file.flush()


def security_attributes(mac_dinh: bool) -> ctypes.POINTER(SECURITY_ATTRIBUTES) | None:
    if mac_dinh:
        return None
    sd = wintypes.LPVOID()
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            SDDL, SDDL_REVISION_1, ctypes.byref(sd), None):
        raise ctypes.WinError(ctypes.get_last_error())
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), sd, False)
    return ctypes.pointer(sa)


class PhienEA:
    """Một EA đang nối vào một instance pipe."""

    def __init__(self, handle: int, stt: int) -> None:
        self.h = handle
        self.stt = stt
        pid = wintypes.ULONG()
        k32.GetNamedPipeClientProcessId(handle, ctypes.byref(pid))
        self.pid = pid.value
        self.ten = f"#{stt} pid={self.pid}"
        self.buf = b""
        self.so_dong = 0
        self.tick = 0

    def ghi(self, obj: dict) -> bool:
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
        n = wintypes.DWORD()
        if not k32.WriteFile(self.h, data, len(data), ctypes.byref(n), None) or n.value != len(data):
            log(f"{self.ten} ghi loi, err={ctypes.get_last_error()}")
            return False
        return True

    def chay(self) -> None:
        log(f"{self.ten} NOI VAO")
        tick_ke = time.monotonic() + 2
        try:
            while True:
                avail = wintypes.DWORD()
                if not k32.PeekNamedPipe(self.h, None, 0, None, ctypes.byref(avail), None):
                    err = ctypes.get_last_error()
                    log(f"{self.ten} NGAT (err={err}{' BROKEN_PIPE' if err == ERROR_BROKEN_PIPE else ''})"
                        f", da nhan {self.so_dong} dong")
                    return
                if avail.value:
                    chunk = ctypes.create_string_buffer(avail.value)
                    n = wintypes.DWORD()
                    if not k32.ReadFile(self.h, chunk, avail.value, ctypes.byref(n), None):
                        log(f"{self.ten} doc loi err={ctypes.get_last_error()}")
                        return
                    self.buf += chunk.raw[:n.value]
                    while b"\n" in self.buf:
                        dong, self.buf = self.buf.split(b"\n", 1)
                        self.xu_ly(dong)
                if time.monotonic() >= tick_ke:
                    self.tick += 1
                    if not self.ghi({"type": "tick", "n": self.tick}):
                        return
                    tick_ke = time.monotonic() + 2
                time.sleep(0.002)
        finally:
            k32.DisconnectNamedPipe(self.h)
            k32.CloseHandle(self.h)

    def xu_ly(self, dong: bytes) -> None:
        self.so_dong += 1
        try:
            msg = json.loads(dong)
        except ValueError:
            log(f"{self.ten} dong hong: {dong[:120]!r}")
            return
        loai = msg.get("type")
        if loai == "ping":
            self.ghi({"type": "pong", "id": msg.get("id"), "us": msg.get("us")})
        elif loai == "hello":
            self.ten = f"#{self.stt} {msg.get('role', '?')} acc={msg.get('account')} pid={self.pid}"
            log(f"{self.ten} HELLO {dong.decode(errors='replace')}")
            self.ghi({"type": "hello_ack", "server_pid": _pid()})
        elif loai == "report":
            log(f"{self.ten} BAO CAO {dong.decode(errors='replace')}")
        else:
            log(f"{self.ten} <- {dong.decode(errors='replace')[:200]}")


def _pid() -> int:
    import os
    return os.getpid()


def main() -> int:
    global _log_file
    ap = argparse.ArgumentParser()
    ap.add_argument("--ten", default="copybridge-spike")
    ap.add_argument("--log")
    ap.add_argument("--dacl-mac-dinh", action="store_true",
                    help="dung DACL mac dinh cua Windows (de thay no chan EA khi chay bang SYSTEM)")
    args = ap.parse_args()
    if args.log:
        _log_file = open(args.log, "a", encoding="utf-8")

    ten = rf"\\.\pipe\{args.ten}"
    sa = security_attributes(args.dacl_mac_dinh)
    import getpass
    log(f"pipe server pid={_pid()} user={getpass.getuser()} ten={ten} "
        f"dacl={'MAC DINH' if args.dacl_mac_dinh else SDDL}")

    # HAI vòng chờ song song. Một vòng thì giữa lúc một EA vừa nối và lúc tạo instance kế tiếp,
    # pipe KHÔNG có instance nào rảnh: EA thứ hai mở đúng lúc đó nhận ERROR_PIPE_BUSY (231) — đã
    # gặp thật khi tự kiểm. Hai vòng thì luôn còn một instance đang chờ.
    for _ in range(2):
        threading.Thread(target=vong_cho_ea, args=(ten, sa), daemon=True).start()
    # Luồng chính chỉ ngủ: ConnectNamedPipe chặn trong C nên đặt nó ở luồng chính thì Ctrl+C vô hiệu.
    while True:
        time.sleep(0.5)


_stt = 0
_stt_lock = threading.Lock()


def vong_cho_ea(ten: str, sa) -> None:
    global _stt
    while True:
        h = k32.CreateNamedPipeW(
            ten, PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, sa)
        if h == INVALID_HANDLE_VALUE:
            log(f"CreateNamedPipe loi err={ctypes.get_last_error()}")
            return
        # Chặn tới khi có EA mở pipe. ERROR_PIPE_CONNECTED: EA mở kịp trước lời gọi này — vẫn là nối.
        if not k32.ConnectNamedPipe(h, None) and ctypes.get_last_error() != ERROR_PIPE_CONNECTED:
            log(f"ConnectNamedPipe loi err={ctypes.get_last_error()}")
            k32.CloseHandle(h)
            continue
        with _stt_lock:
            _stt += 1
            stt = _stt
        threading.Thread(target=PhienEA(h, stt).chay, daemon=True).start()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("dung (Ctrl+C)")
