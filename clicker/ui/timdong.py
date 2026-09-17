"""Thứ tự dò các dòng của tab Trade khi tìm một vị thế cần đóng.

Module này **chỉ quyết định dòng nào mở tiếp**, không mở gì và không bấm gì. Mọi dòng nó chọn vẫn
bị `Mt5UiDriver.close` mở ra và đọc ngược ticket trước khi bấm (D-30), nên chọn sai chỉ tốn thêm
một lần mở hộp thoại chứ không bao giờ đóng nhầm vị thế.

Vì sao cần: danh sách không đọc được nội dung, nên bản trước dò **tuần tự từ dòng 0**. Có 10 vị thế,
đóng cái thứ 9 thì phải mở rồi huỷ 8 hộp thoại trước — mỗi cái ~0,3–0,4 giây (quan sát 2026-09-15).

Hai nguồn thông tin, dùng theo thứ tự:

1. **Bản đồ `ticket → dòng`** do chính những lần dò trước đọc được. Trúng thì một lần mở là xong.
2. **Tìm nhị phân theo ticket.** Tab Trade mặc định sắp theo thời gian mở và ticket MT5 tăng theo
   thời gian, nên ticket đơn điệu theo dòng: mỗi ticket đọc được cho biết đích nằm phía trên hay
   phía dưới. Chiều sắp **suy từ các ticket đã đọc**, không giả định cứng.

Hai lối thoát về dò tuần tự, và cả hai đều cố ý:

* Các ticket đọc được **mâu thuẫn với một thứ tự đơn điệu** — người dùng đã bấm sắp theo Symbol hay
  Profit. Nhị phân lúc đó sẽ loại oan cả nửa danh sách.
* **Đoạn khả dĩ đã cạn** mà chưa thấy. Vẫn phải mở **mọi** dòng còn lại: `already_closed` chỉ được
  kết luận sau khi đã mở hết (FR-18), và kết luận đó làm Bridge ghi cặp thành `CLOSED`. Suy "không
  có" từ một phép nhị phân là đặt cược sổ sách vào giả định về cách sắp xếp.
"""

from __future__ import annotations

from bridge.logging_setup import get_logger

log = get_logger(__name__)

BAN_DO = "ban-do"
NHI_PHAN = "nhi-phan"
TUAN_TU = "tuan-tu"


class PhepDo:
    """Một lần tìm một vị thế. Dùng: `tiep_theo()` → mở dòng đó → `ghi_nhan()`, lặp tới `None`."""

    def __init__(self, so_dong: int, dich: int, ban_do: dict[int, int] | None = None,
                 bo_cuoi: int = 0) -> None:
        self.so_dong = so_dong
        self.dich = dich
        #: Số dòng **cuối** danh sách đã biết không phải vị thế (dòng phụ, dòng Balance). Không lấy
        #: làm điểm giữa của phép nhị phân — đích không bao giờ nằm ở đó, và mỗi lần mở một dòng
        #: như vậy tốn trọn khoảng chờ hộp thoại. Chúng **vẫn** được mở ở lượt quét cuối, nên
        #: `already_closed` vẫn chỉ kết luận sau khi đã mở hết (FR-18).
        self.bo_cuoi = max(0, bo_cuoi)
        #: Dòng đã mở (kể cả dòng không ra hộp thoại). Không bao giờ trả lại một dòng hai lần.
        self._da_mo: set[int] = set()
        #: Dòng đã được cho mở lại một lần (xem `mo_lai`).
        self._da_mo_lai: set[int] = set()
        #: `dòng → ticket`, chỉ những dòng mở ra hộp thoại và đọc được ticket.
        self._doc: dict[int, int] = {}
        goi_y = (ban_do or {}).get(dich)
        self._goi_y = goi_y if goi_y is not None and 0 <= goi_y < so_dong else None
        self.che_do = BAN_DO if self._goi_y is not None else NHI_PHAN
        self._tuan_tu = False
        #: Dòng chứa đích, khi đã thấy.
        self.thay: int | None = None

    @property
    def so_lan_mo(self) -> int:
        return len(self._da_mo) + len(self._da_mo_lai)

    def mo_lai(self, row: int) -> bool:
        """Cho mở lại `row` **đúng một lần**. `False` nếu đã mở lại rồi.

        Dùng khi kết quả đọc ở dòng đó không tin được — điển hình là hộp thoại **mở trễ** của một
        dòng trước hiện ra đúng lúc đang chờ dòng này. Không cho mở lại thì dòng đó bị coi là "đã
        xem", và nếu đích nằm ở đó thì phép tìm kết luận sai là vị thế đã đóng.
        """
        if row in self._da_mo_lai or not 0 <= row < self.so_dong:
            return False
        self._da_mo_lai.add(row)
        self._da_mo.discard(row)
        self._doc.pop(row, None)
        return True

    def tiep_theo(self) -> int | None:
        """Dòng nên mở tiếp, hoặc `None` khi đã thấy đích hoặc đã mở hết."""
        if self.thay is not None:
            return None

        if self._goi_y is not None and self._goi_y not in self._da_mo:
            return self._goi_y

        if not self._tuan_tu:
            lo, hi = self._doan()
            ung_vien = [r for r in range(lo, hi + 1) if r not in self._da_mo]
            if ung_vien:
                # Lấy phần tử giữa, lệch về phía trên. Với hai dòng là dòng trên — giữ nguyên hành vi
                # của mọi danh sách ngắn, nơi thứ tự dò chẳng tiết kiệm được gì.
                return ung_vien[(len(ung_vien) - 1) // 2]
            self._chuyen_tuan_tu("doan kha di da can, mo not cac dong con lai truoc khi ket luan")

        con_lai = [r for r in range(self.so_dong) if r not in self._da_mo]
        return con_lai[0] if con_lai else None

    def ghi_nhan(self, row: int, ticket: int | None) -> None:
        """Kết quả của việc mở `row`. `ticket = None`: không ra hộp thoại, hoặc không đọc được."""
        self._da_mo.add(row)
        if ticket is None:
            # Dòng tổng kết Balance, hoặc tiêu đề lạ. Không mang thông tin về thứ tự.
            return
        if ticket == self.dich:
            self.thay = row
            return
        self._doc[row] = ticket
        if not self._tuan_tu and self._chieu() is None:
            self._chuyen_tuan_tu(f"ticket khong don dieu theo dong {sorted(self._doc.items())}")

    # -- nội bộ ----------------------------------------------------------------------------

    def _chieu(self) -> int | None:
        """`1` tăng dần, `-1` giảm dần, `None` khi mâu thuẫn. Chưa đủ hai điểm thì giả định tăng.

        Giả định sai chỉ tốn thêm một lần mở: `_doan()` tính lại từ đầu mỗi lần, nên điểm đọc thứ
        hai sửa luôn hướng đi.
        """
        tickets = [t for _, t in sorted(self._doc.items())]
        if len(tickets) < 2:
            return 1
        buoc = {1 if b > a else -1 for a, b in zip(tickets, tickets[1:], strict=False)}
        return buoc.pop() if len(buoc) == 1 else None

    def _doan(self) -> tuple[int, int]:
        """Đoạn dòng `[lo, hi]` còn có thể chứa đích, suy từ mọi ticket đã đọc."""
        chieu = self._chieu() or 1
        lo, hi = 0, self.so_dong - 1 - self.bo_cuoi
        for row, ticket in self._doc.items():
            if (ticket < self.dich) == (chieu == 1):
                lo = max(lo, row + 1)
            else:
                hi = min(hi, row - 1)
        return lo, hi

    def _chuyen_tuan_tu(self, ly_do: str) -> None:
        self._tuan_tu = True
        self.che_do = TUAN_TU
        log.info("Tim vi the %s: chuyen sang do tuan tu (%s)", self.dich, ly_do)


def ghi_ban_do(ban_do: dict[int, int], row: int, ticket: int | None) -> None:
    """Ghi điều vừa đọc được ở `row`. Mục cũ nào trỏ vào dòng này mà khác ticket thì đã sai — xoá."""
    for cu in [k for k, v in ban_do.items() if v == row and k != ticket]:
        del ban_do[cu]
    if ticket is not None:
        ban_do[ticket] = row


def bo_dong(ban_do: dict[int, int], ticket: int, row: int) -> None:
    """Vị thế ở `row` vừa đóng hẳn: MT5 bỏ dòng đó, mọi dòng bên dưới dịch lên một."""
    ban_do.pop(ticket, None)
    for k, v in list(ban_do.items()):
        if v > row:
            ban_do[k] = v - 1
