"""Đọc và in ra mọi control của các hộp thoại MT5 đang mở. **Chỉ đọc, không bấm gì.**

Sinh ra vì `dialog.py` chôn cứng các `ctrlID` đo trên *Connext-Demo build 5.00*, mà mỗi sàn phát
hành một bản MT5 riêng. Khi clicker gặp một terminal lạ và hành xử khác dự đoán, câu hỏi đầu tiên
luôn là "hộp thoại của bản này có hình dạng gì" — và trước đây không có cách nào trả lời ngoài mô
tả bằng lời, vốn là thứ tệ nhất để dựa vào khi phải chọn hằng số.

An toàn theo cấu tạo, không phải theo lời hứa: file này chỉ gọi các hàm `enum_*` và `get_*` của
`win32`. Không `PostMessage`, không `set_text`, không `post_click`. Chạy nó trong lúc có lệnh thật
đang mở cũng không đụng vào gì.

    python -m clicker.ui.dump                    # mọi hộp thoại của mọi terminal
    python -m clicker.ui.dump --title 538287     # chỉ terminal có tiêu đề chứa chuỗi này
    python -m clicker.ui.dump --all-controls     # kể cả control ẩn
"""

from __future__ import annotations

import argparse

from clicker.ui import probe, win32


def _in_ra_cua_so(hwnd: int, nhan: str, hien_het: bool) -> None:
    tieu_de = win32.get_window_text(hwnd)
    print(f"\n{nhan} hwnd={hwnd} pid={win32.get_process_id(hwnd)} "
          f"visible={win32.is_visible(hwnd)}")
    print(f"  tieu de: {tieu_de!r}")
    controls = win32.enum_children(hwnd)
    if not controls:
        print("  (khong co control con)")
        return
    print(f"  {'ctrl_id':>8}  {'visible':>7}  {'class':<20}  text")
    print(f"  {'-' * 8}  {'-' * 7}  {'-' * 20}  {'-' * 40}")
    for c in controls:
        if not hien_het and not c.visible:
            continue
        text = c.text if len(c.text) <= 60 else c.text[:57] + "..."
        print(f"  {c.ctrl_id:>8}  {str(c.visible):>7}  {c.class_name[:20]:<20}  {text!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m clicker.ui.dump",
        description="In cau truc hop thoai MT5. Chi doc, khong bam gi.")
    parser.add_argument("--title", default="",
                        help="Chi lay hop thoai cua terminal co tieu de chua chuoi nay")
    parser.add_argument("--all-controls", action="store_true",
                        help="In ca control an (mac dinh chi in control dang hien)")
    args = parser.parse_args(argv)

    if not win32.is_available():
        print("Khong goi duoc Win32 o moi truong nay (chi chay tren Windows).")
        return 2

    pid_can = None
    if args.title:
        ket_qua = probe.find_terminal(args.title)
        if not ket_qua or ket_qua.hwnd is None:
            print(f"Khong khoa duoc terminal: {ket_qua.detail}")
            return 2
        pid_can = win32.get_process_id(ket_qua.hwnd)
        print(f"Terminal: {ket_qua.title!r} (pid {pid_can})")
        _in_ra_cua_so(ket_qua.hwnd, "TERMINAL", args.all_controls)

    # Lọc theo pid chứ không theo thứ tự: hai terminal trên cùng một máy là cấu hình bình thường
    # của dự án này, và cả hai đều có hộp thoại lớp `#32770`.
    dialogs = [h for h in win32.enum_top_level(win32.DIALOG_CLASS)
               if pid_can is None or win32.get_process_id(h) == pid_can]
    if not dialogs:
        print("\nKhong thay hop thoai #32770 nao. Mo hop thoai roi chay lai.")
        return 1

    for i, hwnd in enumerate(dialogs, 1):
        _in_ra_cua_so(hwnd, f"HOP THOAI {i}/{len(dialogs)}", args.all_controls)

    print(f"\nTong: {len(dialogs)} hop thoai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
