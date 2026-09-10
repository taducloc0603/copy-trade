"""Đọc và in ra cấu trúc giao diện MT5: cửa sổ, control, menu, danh sách. **Không bấm gì.**

Sinh ra vì `dialog.py` chôn cứng các `ctrlID` đo trên *Connext-Demo build 5.00*, mà mỗi sàn phát
hành một bản MT5 riêng. Khi clicker gặp một terminal lạ và hành xử khác dự đoán, câu hỏi đầu tiên
luôn là "hộp thoại của bản này có hình dạng gì" — và trước đây không có cách nào trả lời ngoài mô
tả bằng lời, vốn là thứ tệ nhất để dựa vào khi phải chọn hằng số.

Nay nó còn là **dụng cụ đo của Bước 0** cho việc đổi đường ĐÓNG sang giao diện. Bốn câu hỏi phải
trả lời trước khi thiết kế bất cứ thứ gì:

* **C1** — tab Trade của Toolbox có control Win32 thật không? → cây control của cửa sổ terminal
* **C2** — từng dòng vị thế có đọc được không? → `--listview`
* **C3** — hộp thoại đóng có hình dạng gì? → mở nó bằng tay rồi chạy công cụ này
* **C4** — có ID lệnh menu nào mở được nó? → `--menu`

**Một phép đo âm cũng là kết quả.** `--listview` không đọc được nghĩa là control đó do MT5 tự vẽ,
và khi đó từng dòng không có HWND, không nhắm được bằng `PostMessage`, và cả hướng đi phải xem lại.

Ranh giới an toàn, nói chính xác chứ không nói cho gọn: file này **không gửi message nào làm MT5
thay đổi trạng thái giao dịch**. Không `PostMessage`, không `BM_CLICK`, không `WM_SETTEXT`, không
`WM_CHAR`. Riêng `--listview` có cấp phát một vùng nhớ tạm trong tiến trình MT5 vì
`LVM_GETITEMTEXTW` đòi hỏi vậy (xem `win32.listview_item_text`); vùng đó do chính ta cấp phát và
giải phóng ngay, không đụng tới dữ liệu của MT5.

    python -m clicker.ui.dump                       # mọi hộp thoại của mọi terminal
    python -m clicker.ui.dump --title 538287        # chỉ terminal có tiêu đề chứa chuỗi này
    python -m clicker.ui.dump --title 538287 --menu # kèm cây menu và ID lệnh
    python -m clicker.ui.dump --all-controls        # kể cả control ẩn
    python -m clicker.ui.dump --listview 0x1A2B3C   # thử đọc một control như ListView
"""

from __future__ import annotations

import argparse

from clicker.ui import probe, win32

#: Sâu hơn mức này thì cây menu gần như chắc chắn đang đi vòng. Chặn để công cụ đo không tự treo.
MENU_MAX_DEPTH = 4

#: Số dòng và số cột in ra khi thử đọc một ListView. Đủ để trả lời "có đọc được ticket không";
#: không cần đổ hết vài trăm dòng ra màn hình.
LISTVIEW_MAX_ROWS = 20
LISTVIEW_MAX_COLS = 10


def doc_hwnd(text: str) -> int:
    """Đọc HWND từ dòng lệnh, chấp nhận cả `0x1A2B3C` lẫn số thập phân.

    Người dùng sẽ chép handle từ chính bản in của công cụ này, nên nó phải nhận cả hai dạng —
    bắt gõ lại đúng hệ cơ số là một cách hay để đo nhầm cửa sổ.
    """
    text = text.strip()
    return int(text, 16) if text.lower().startswith("0x") else int(text, 10)


def cay_theo_thu_bac(cha: dict[int, int], goc: int) -> list[tuple[int, int]]:
    """Xếp danh sách phẳng của `EnumChildWindows` thành cây, trả `(hwnd, độ_sâu)`.

    `EnumChildWindows` trả về **toàn bộ hậu duệ** chứ không chỉ con trực tiếp, nên bản in phẳng
    trước đây không cho biết control nào nằm trong control nào — mà với tab Trade, đó chính là
    thông tin cần.

    Node có cha không nằm trong tập (hoặc tạo thành vòng) được treo ở gốc thay vì bị bỏ rơi: mất
    một control khỏi bản đo nguy hiểm hơn nhiều so với việc nó hiện sai chỗ một bậc.
    """
    con: dict[int, list[int]] = {}
    for hwnd, parent in cha.items():
        con.setdefault(parent if parent in cha or parent == goc else goc, []).append(hwnd)

    ket_qua: list[tuple[int, int]] = []
    da_tham: set[int] = set()

    def di(hwnd: int, do_sau: int) -> None:
        if hwnd in da_tham:
            return
        da_tham.add(hwnd)
        if hwnd != goc:
            ket_qua.append((hwnd, do_sau))
        for child in con.get(hwnd, []):
            di(child, do_sau + 1)

    di(goc, -1)
    # Vòng lặp trong quan hệ cha-con: vẫn phải in ra, ở gốc.
    for hwnd in cha:
        if hwnd not in da_tham:
            ket_qua.append((hwnd, 0))
    return ket_qua


def _in_ra_cua_so(hwnd: int, nhan: str, hien_het: bool) -> None:
    tieu_de = win32.get_window_text(hwnd)
    left, top, right, bottom = win32.get_window_rect(hwnd)
    print(f"\n{nhan} hwnd=0x{hwnd:X} pid={win32.get_process_id(hwnd)} "
          f"visible={win32.is_visible(hwnd)} {right - left}x{bottom - top}")
    print(f"  tieu de: {tieu_de!r}")

    controls = win32.enum_children(hwnd)
    if not controls:
        print("  (khong co control con)")
        return

    theo_hwnd = {c.hwnd: c for c in controls}
    cha = {c.hwnd: win32.get_parent(c.hwnd) for c in controls}

    print(f"  {'hwnd':>10}  {'ctrl_id':>8}  {'visible':>7}  {'w x h':>11}  class / text")
    print(f"  {'-' * 10}  {'-' * 8}  {'-' * 7}  {'-' * 11}  {'-' * 46}")
    for child_hwnd, do_sau in cay_theo_thu_bac(cha, hwnd):
        control = theo_hwnd[child_hwnd]
        if not hien_het and not control.visible:
            continue
        c_left, c_top, c_right, c_bottom = win32.get_window_rect(child_hwnd)
        kich_thuoc = f"{c_right - c_left}x{c_bottom - c_top}"
        text = control.text if len(control.text) <= 40 else control.text[:37] + "..."
        print(f"  0x{child_hwnd:08X}  {control.ctrl_id:>8}  {str(control.visible):>7}  "
              f"{kich_thuoc:>11}  {'  ' * do_sau}{control.class_name} {text!r}")


def _in_menu(hwnd: int) -> None:
    """Cây menu của terminal kèm ID lệnh — nguồn duy nhất của những hằng số như `MENU_NEW_ORDER`."""
    hmenu = win32.get_menu(hwnd)
    if not hmenu:
        print("\nMENU: cua so khong co thanh menu Win32 chuan (GetMenu tra 0).")
        print("  Nghia la MT5 tu ve thanh menu -> KHONG co ID lenh nao de PostMessage.")
        return

    print(f"\nMENU hmenu=0x{hmenu:X}")

    def di(menu: int, do_sau: int) -> None:
        if do_sau > MENU_MAX_DEPTH:
            return
        for i in range(win32.get_menu_item_count(menu)):
            chu = win32.get_menu_string(menu, i)
            con = win32.get_sub_menu(menu, i)
            item_id = win32.get_menu_item_id(menu, i)
            thut = "  " * (do_sau + 1)
            if con:
                print(f"{thut}[{chu or 'owner-drawn'}]")
                di(con, do_sau + 1)
            else:
                print(f"{thut}{item_id:>7}  {chu or 'owner-drawn hoac vach ngan'}")

    di(hmenu, 0)
    print(f"  (de doi chieu: MENU_NEW_ORDER dang dung la {win32.MENU_NEW_ORDER})")


def _in_listview(hwnd: int) -> int:
    """Thử đọc một control như thể nó là `SysListView32`. In ra cả khi thất bại."""
    if not win32.is_window(hwnd):
        print(f"hwnd 0x{hwnd:X} khong phai mot cua so hop le.")
        return 2

    lop = win32.get_class_name(hwnd)
    dung_lop = lop == win32.LISTVIEW_CLASS
    print(f"\nLISTVIEW hwnd=0x{hwnd:X} class={lop!r} pid={win32.get_process_id(hwnd)}")
    if not dung_lop:
        print(f"  CANH BAO: class khong phai {win32.LISTVIEW_CLASS!r}. Moi con so duoi day deu")
        print("  dang ngo — mot control la nhan message LVM_* se tra 0 chu khong bao loi.")

    so_dong = win32.listview_item_count(hwnd)
    if so_dong is None:
        print("  LVM_GETITEMCOUNT khong tra loi (control dang treo hoac qua han).")
        return 1

    print(f"  LVM_GETITEMCOUNT = {so_dong}")
    if so_dong == 0:
        print("  KET LUAN: khong doc duoc dong nao.")
        if not dung_lop:
            print("  Class sai + dem ra 0 => control nay do MT5 tu ve. Tung dong KHONG co HWND")
            print("  rieng, khong doc duoc text, khong nham duoc bang PostMessage. Day la cau")
            print("  tra loi DO cho cau hoi C2 cua Buoc 0.")
        else:
            print("  Class dung nhung rong. Neu tab Trade dang co vi the that thi van la cau")
            print("  tra loi DO: control tra loi message nhung khong giu du lieu o dang ListView.")
        return 1

    for row in range(min(so_dong, LISTVIEW_MAX_ROWS)):
        o = [win32.listview_item_text(hwnd, row, col) for col in range(LISTVIEW_MAX_COLS)]
        while o and not o[-1]:
            o.pop()
        print(f"  dong {row:>3}: {o}")
    if so_dong > LISTVIEW_MAX_ROWS:
        print(f"  ... con {so_dong - LISTVIEW_MAX_ROWS} dong nua")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m clicker.ui.dump",
        description="In cau truc giao dien MT5. Chi doc, khong bam gi.")
    parser.add_argument("--title", default="",
                        help="Chi lay hop thoai cua terminal co tieu de chua chuoi nay")
    parser.add_argument("--all-controls", action="store_true",
                        help="In ca control an (mac dinh chi in control dang hien)")
    parser.add_argument("--menu", action="store_true",
                        help="In cay menu cua terminal kem ID lenh (can --title)")
    parser.add_argument("--listview", default="",
                        help="Thu doc mot control nhu ListView, nhan 0x... hoac so thap phan")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not win32.is_available():
        print("Khong goi duoc Win32 o moi truong nay (chi chay tren Windows).")
        return 2

    if args.listview:
        return _in_listview(doc_hwnd(args.listview))

    pid_can = None
    if args.title:
        ket_qua = probe.find_terminal(args.title)
        if not ket_qua or ket_qua.hwnd is None:
            print(f"Khong khoa duoc terminal: {ket_qua.detail}")
            return 2
        pid_can = win32.get_process_id(ket_qua.hwnd)
        print(f"Terminal: {ket_qua.title!r} (pid {pid_can})")
        _in_ra_cua_so(ket_qua.hwnd, "TERMINAL", args.all_controls)
        if args.menu:
            _in_menu(ket_qua.hwnd)
    elif args.menu:
        print("--menu can --title de biet doc menu cua terminal nao.")
        return 2

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
