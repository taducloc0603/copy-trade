"""Đường cài gửi khách: những gì khách **đọc** trong lúc cài phải khớp với tab Hướng dẫn.

Bối cảnh, vì nó là toàn bộ lý do bộ test này tồn tại: ngày 2026-09-22 bản giao bỏ đăng nhập
(D-39), viết lại tab Hướng dẫn thành 9 bước (D-40), gộp việc biên dịch + chép EA thành một nút, và
giấu phần nhiều Client (D-42). Ba thứ khách đọc **cuối cùng** — khối kết của `tro-ly.ps1`,
`canh-bao.txt`, và khối `BUOC TIEP THEO` của `cai-dat.ps1` — thì không ai sửa theo. Chúng ra lệnh
cho khách làm những việc mà tab Hướng dẫn nói là không cần làm, hoặc đã có nút bấm.

Không một lỗi nào trong số đó làm test đỏ, và không một lỗi nào làm hệ thống chạy sai. Chúng chỉ
làm một người non-tech đọc hai bản chỉ dẫn trái nhau trong vòng một phút. Bộ test này khoá lại
đúng loại lệch đó, vì nó không tự lộ ra ở đâu khác.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _doc(project_root: Path, duong: str) -> str:
    return (project_root / duong).read_text(encoding="utf-8")


def _phan_in_ra(project_root: Path, duong: str) -> str:
    """Nội dung `.ps1` đã **bỏ dòng chú thích** — tức xấp xỉ những gì khách thật sự đọc.

    Cần thiết, không phải cho gọn: các test dưới đây cấm những cụm từ như "con ba viec" hay
    "them-client", và chỗ giải thích **vì sao** chúng bị cấm lại nằm ngay trong chú thích cạnh bản
    sửa. Không bỏ chú thích thì test đỏ vì chính lời giải thích của nó — và cách sửa dễ nhất lúc
    đó là xoá lời giải thích, tức mất đúng thứ đáng giữ nhất.

    Chỉ bỏ dòng **bắt đầu** bằng `#`. Đủ cho mục đích ở đây, và không phải một bộ phân tích cú
    pháp PowerShell tự viết.
    """
    noi = _doc(project_root, duong)
    return "\n".join(d for d in noi.splitlines() if not d.lstrip().startswith("#"))


# ---------------------------------------------------------------------------------------------
# Một bản biên dịch, không phải hai
# ---------------------------------------------------------------------------------------------
def test_tro_ly_goi_bien_dich_ea_dung_chung(project_root: Path) -> None:
    """`tro-ly.ps1` phải gọi `bien-dich-ea.ps1`, không tự tìm MetaEditor.

    Bản riêng của trợ lý biên dịch ra `ea\\*.ex5` rồi **dừng ở đó** — nó không chép vào
    `MQL5\\Experts` của MT5, việc mà `bien-dich-ea.ps1` làm được nhờ `chung-mt5.ps1`. Hai bản biên
    dịch, và bản yếu hơn lại là bản khách gặp trong lúc cài: EA biên dịch xong mà Navigator của
    MT5 không thấy gì.
    """
    noi = _doc(project_root, "scripts/tro-ly.ps1")
    assert "bien-dich-ea.ps1" in noi, "tro-ly.ps1 phai goi bo bien dich dung chung"
    assert "function tim_metaeditor" not in noi, (
        "tro-ly.ps1 lai co ban tim MetaEditor rieng -- day la duong quay lai bug chep thieu .ex5"
    )


# ---------------------------------------------------------------------------------------------
# Không kể lại việc mà tab Hướng dẫn đã kể
# ---------------------------------------------------------------------------------------------
# Mỗi chuỗi kèm lý do vì sao nó là một câu SAI, không chỉ là một câu dư.
CAU_DA_SAI = (
    ("con ba viec", "tab Huong dan co CHIN buoc, khong phai ba viec"),
    # "Chep ea\*.ex5" la cau RA LENH cho khach chep tay. Khong cam noi TOI viec chep:
    # khoi giai_thich moi cua buoc bien dich noi ro nut do "tu chep .ex5 vao MQL5\Experts",
    # va cau do la cau DUNG. Mot mau rong hon da bat chinh no o lan chay dau.
    (r"Chep ea\*.ex5", "chep .ex5 gio la mot nut, khong phai viec tay"),
    ("khai SO TAI KHOAN", "Bridge tu suy so tai khoan clicker tu EA chay cung terminal"),
)


@pytest.mark.parametrize("cum,vi_sao", CAU_DA_SAI)
def test_khoi_ket_tro_ly_khong_ke_lai_viec(project_root: Path, cum: str, vi_sao: str) -> None:
    noi = _phan_in_ra(project_root, "scripts/tro-ly.ps1")
    assert cum not in noi, f"tro-ly.ps1 van con '{cum}': {vi_sao}"


def test_khoi_ket_tro_ly_tro_sang_tab_huong_dan(project_root: Path) -> None:
    """Bỏ phần kể việc thì phải còn lại một con trỏ — không phải một khoảng trống.

    Một khối kết không nói gì cả thì khách đóng cửa sổ và không biết còn việc phải làm.
    """
    noi = _doc(project_root, "scripts/tro-ly.ps1")
    assert "#huong-dan" in noi
    assert "Cai dat lan dau" in noi


def test_buoc_tiep_theo_khong_lo_lenh_them_client(project_root: Path) -> None:
    """Khối `BUOC TIEP THEO` không được in `them-client` ra màn hình khách (D-42).

    Bản giao cấu hình cho một Client và giao diện đã ẩn khối Thêm Client. In chính câu lệnh tạo
    Client ra màn hình lúc cài là tự mở lại cái cửa vừa đóng.
    """
    noi = _phan_in_ra(project_root, "scripts/cai-dat.ps1")
    assert "them-client" not in noi, "cai-dat.ps1 van in lenh them-client"
    assert "CL-02" not in noi and "CL-03" not in noi


def test_tro_ly_khong_goi_y_client_thu_hai(project_root: Path) -> None:
    noi = _phan_in_ra(project_root, "scripts/tro-ly.ps1")
    assert "CL-02" not in noi and "CL-03" not in noi


def test_buoc_tiep_theo_khong_chay_tren_duong_cap_nhat(project_root: Path) -> None:
    """`in_buoc_tiep` chỉ được gọi khi KHÔNG phải `-CapNhat`.

    `chay_tro_ly` trả `$false` cho **mọi** lần `-CapNhat`, và `CAP-NHAT.cmd` chạy đúng cờ đó. Nên
    trước bản sửa này, mỗi lần khách bấm CAP-NHAT.cmd là nhận trọn khối "BUOC TIEP THEO" của lần
    cài đầu. Đường cập nhật đã có khối kết riêng (`sau_khi_cap_nhat`).
    """
    noi = _doc(project_root, "scripts/cai-dat.ps1")
    assert "if (-not (chay_tro_ly) -and (-not $CapNhat)) { in_buoc_tiep }" in noi


# ---------------------------------------------------------------------------------------------
# canh-bao.txt
# ---------------------------------------------------------------------------------------------
def test_canh_bao_khong_bat_khai_clicker(project_root: Path) -> None:
    """Mục 7 cũ nói "PHAI KHAI SO TAI KHOAN + TIEU DE" — trái hẳn bước "thường không phải làm gì"."""
    noi = _doc(project_root, "scripts/canh-bao.txt")
    assert "PHAI KHAI SO TAI KHOAN" not in noi


def test_canh_bao_khong_bat_bien_dich_bang_tay(project_root: Path) -> None:
    """Mục 5 cũ gộp "bien dich EA" vào danh sách việc tay. Nó là một nút từ 2026-09-22."""
    noi = _doc(project_root, "scripts/canh-bao.txt")
    assert "bien dich EA, gan EA len chart" not in noi


def test_canh_bao_noi_ro_phai_giu_phien_rdp(project_root: Path) -> None:
    """B-08 chưa ai đo, và khách được gửi bản này kèm cảnh báo — nên cảnh báo phải nói hai điều.

    Một: giữ phiên RDP mở. Hai: **kiểu hỏng là dashboard vẫn xanh** trong khi cú bấm không tới
    cửa sổ nào. Chỉ nói điều thứ nhất thì khách mất kết nối một lần rồi tin rằng nó vẫn đang
    copy — và đó chính là cách mất tiền.
    """
    noi = _doc(project_root, "scripts/canh-bao.txt")
    assert "GIU PHIEN RDP MO" in noi
    assert "VAN XANH" in noi
    assert "kiem-tra.ps1" in noi


def test_canh_bao_khong_con_day_mo_chart_theo_symbol(project_root: Path) -> None:
    """Mục 4 cũ dặn "phai mo dung chart do" — đúng trước D-44, SAI từ khi clicker mở lệnh qua
    Market Watch. File này in ra cuối mọi lần cài và cập nhật, nên nó phải nói điều mới."""
    noi = _doc(project_root, "scripts/canh-bao.txt")
    assert "CHI COPY DUOC MOT SYMBOL" not in noi
    assert "Phai mo dung" not in noi
    assert "MARKET WATCH" in noi


def test_canh_bao_dung_so_muc_voi_tieu_de(project_root: Path) -> None:
    """Tiêu đề nói "7 viec" thì phải đúng bảy mục. Một con số lệch là một tài liệu mất tin."""
    noi = _doc(project_root, "scripts/canh-bao.txt")
    assert "KHONG LAM DUOC 7 VIEC" in noi
    so_muc = sum(1 for d in noi.splitlines() if re.match(r" \d\. [A-Z]", d))
    assert so_muc == 7, f"tieu de noi 7 viec nhung dem duoc {so_muc}"


# ---------------------------------------------------------------------------------------------
# kiem-tra.ps1 — chỗ đắt nhất nếu báo xanh sai
# ---------------------------------------------------------------------------------------------
def test_kiem_tra_khong_con_coi_302_la_xanh(project_root: Path) -> None:
    """Không còn `/login`, nên 302/401 giờ là hỏng thật — không phải "chưa đăng nhập".

    `kiem-tra.ps1` là thứ khách dùng để tin rằng hệ thống đang sống. Một cái báo XANH sai ở đây
    đắt hơn mọi chỗ khác trong cả bộ script.
    """
    noi = _phan_in_ra(project_root, "scripts/kiem-tra.ps1")
    assert "/login" not in noi
    assert 'xanh "dashboard tra loi $ma (chua dang nhap)"' not in noi


# ---------------------------------------------------------------------------------------------
# Mật khẩu dashboard đã bỏ (D-39) — không được còn vết nào hứa hẹn nó
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "duong", ("scripts/go-bo.ps1", "scripts/kiem-tra.ps1", "scripts/tro-ly.ps1", "README.md")
)
def test_khong_con_hua_mat_khau_dashboard(project_root: Path, duong: str) -> None:
    noi = _doc(project_root, duong).lower()
    assert "mat khau dashboard" not in noi
    assert "mật khẩu dashboard" not in noi


# ---------------------------------------------------------------------------------------------
# Dọn tài liệu nội bộ khỏi bản khách
# ---------------------------------------------------------------------------------------------
def test_don_ban_khach_chay_sau_buoc_test(project_root: Path) -> None:
    """Thứ tự này là bắt buộc, không phải sở thích.

    Bộ test đọc `PROGRESS.md` và `docs/NOI-BO-nhieu-client.md`, và `cai-dat.ps1` **huỷ cả lần
    cài** khi test đỏ. Dọn trước bước test là tự làm khách không cài được máy — và thông báo lỗi
    lúc đó sẽ là một test lạ, không hề nhắc tới việc dọn.
    """
    noi = _doc(project_root, "scripts/cai-dat.ps1")
    assert noi.index("khoi_tao_va_kiem $venvPy") < noi.index("\n    don_ban_khach")


def test_don_ban_khach_khai_tuong_minh_tung_duong(project_root: Path) -> None:
    """Danh sách phải khai từng đường, và phải giữ lại hai tài liệu khách cần.

    Một mẫu chung kiểu `docs\\*` sẽ xoá cả `CAI-DAT-VPS.md` và `RUNBOOK.md` — tức xoá đúng hai thứ
    duy nhất khách dùng để cài và để xử lý sự cố.
    """
    noi = _doc(project_root, "scripts/cai-dat.ps1")
    dau = noi.index("$script:DuongNoiBo = @(")
    danh_sach = noi[dau : noi.index(")", dau)]
    for phai_co in ("PROGRESS.md", "plan", "spike", "NOI-BO-nhieu-client.md",
                    "DECISIONS.md"):
        assert phai_co in danh_sach, f"thieu {phai_co} trong danh sach don"
    for phai_giu in ("CAI-DAT-VPS.md", "RUNBOOK.md"):
        assert phai_giu not in danh_sach, f"{phai_giu} la tai lieu khach CAN -- khong duoc xoa"
    assert "docs\\*" not in danh_sach


def test_pull_phuc_hoi_tai_lieu_truoc_khi_keo_ban_moi(project_root: Path) -> None:
    """Trạng thái git phải sạch khi vào `pull`, và thứ tự đó phải khoá lại.

    **Đã đo**, và kết quả ngược với điều tôi tưởng lúc viết: `git pull --ff-only` *không* từ chối
    khi file chỉ bị xoá khỏi thư mục làm việc — nó chạy bình thường. Nên thứ tự này không phải để
    cứu lần pull.

    Lý do thật, và nhỏ hơn: chốt thứ hai của `don_ban_khach` đọc `git status` để không xoá thứ ai
    đó đang sửa. Sau lần dọn đầu, các đường ấy báo `" D"`, và chốt đó mất khả năng phân biệt "đã
    xoá từ lần trước" với "đang sửa dở".
    """
    noi = _doc(project_root, "scripts/cai-dat.ps1")
    assert noi.index("phuc_hoi_tai_lieu_noi_bo\n") < noi.index("git -C $ThuMuc pull --ff-only")


def test_don_ban_khach_khong_xoa_thu_chua_commit(project_root: Path) -> None:
    """Chốt an toàn: một người phát triển chạy chính script này trong bản làm việc của họ.

    `git checkout` lấy lại được thứ đã commit; nó không lấy lại được thứ chưa bao giờ vào git.
    """
    noi = _doc(project_root, "scripts/cai-dat.ps1")
    assert "git -C $ThuMuc status --porcelain -- $d" in noi
    assert 'if (-not (Test-Path (Join-Path $ThuMuc ".git"))) {' in noi


def test_readme_tro_tai_lieu_noi_bo_len_github(project_root: Path) -> None:
    """Xoá tài liệu khỏi bản cài thì liên kết tương đối trong README thành liên kết chết.

    Nên chúng phải trỏ lên GitHub — một đường dẫn không bao giờ đứt vì việc dọn.
    """
    noi = _doc(project_root, "README.md")
    for ten in ("DECISIONS.md", "BACKLOG.md", "PROGRESS.md"):
        assert f"](docs/{ten})" not in noi and f"]({ten})" not in noi, (
            f"README con lien ket tuong doi toi {ten} -- se chet sau khi don"
        )
    assert "github.com/taducloc0603/copy-trade/blob/main/docs/DECISIONS.md" in noi


# ---------------------------------------------------------------------------------------------
# Ngắt dòng của hai file bấm đúp
# ---------------------------------------------------------------------------------------------
def test_gitattributes_tat_chuan_hoa_cho_cmd_va_ps1(project_root: Path) -> None:
    """Phải là `-text`, **không** phải `text eol=crlf`. Hai cái này cho kết quả ngược nhau.

    `CAI-DAT.cmd` và `scripts/cai-dat.ps1` được `curl` tải **thẳng** từ
    raw.githubusercontent.com, tức không đi qua checkout. `text eol=crlf` chuẩn hoá blob về LF rồi
    mới đổi thành CRLF *lúc checkout*, nên bản tải bằng curl sẽ nhận LF — đúng cái hỏng mà dòng đó
    tưởng là đang vá. `-text` tắt chuẩn hoá, blob giữ nguyên CRLF, cả hai đường đều đúng.

    Chỉ xét **dòng khai**, không xét chú thích: lời giải thích ngay trong `.gitattributes` có
    nhắc tới `text eol=crlf` để nói vì sao *không* dùng nó, và một test đọc cả file sẽ đỏ vì chính
    câu giải thích đó. Đã vướng đúng lỗi này hai lần trong cùng một buổi.
    """
    noi = _doc(project_root, ".gitattributes")
    khai = [d.strip() for d in noi.splitlines() if d.strip() and not d.lstrip().startswith("#")]
    assert "*.cmd -text" in khai
    assert "*.ps1 -text" in khai
    assert not any("eol=crlf" in d for d in khai), (
        "`text eol=crlf` lam ban tai raw thanh LF -- doc phan giai thich trong .gitattributes"
    )


@pytest.mark.parametrize("ten", ("CAI-DAT.cmd", "CAP-NHAT.cmd"))
def test_file_bam_dup_giu_crlf_tren_dia(project_root: Path, ten: str) -> None:
    """Đọc **byte**, không đọc dòng: mở ở chế độ text thì Python tự bỏ `\\r` và test luôn xanh.

    Đây đúng là loại test xanh-vì-lý-do-sai. `cmd.exe` xử lý nhãn `goto :ket` với LF thuần là
    không đáng tin, và đây là file *đầu tiên* khách chạy — nó hỏng thì không còn gì để gỡ.
    """
    byte = (project_root / ten).read_bytes()
    assert b"\r\n" in byte
    assert byte.count(b"\n") == byte.count(b"\r\n"), f"{ten}: co dong ket bang LF tran"


# ---------------------------------------------------------------------------------------------
# Dòng lệnh đầu tiên khách gõ
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("duong", ("CAI-DAT.cmd", "docs/CAI-DAT-VPS.md"))
def test_dong_tai_file_cai_chay_duoc_trong_powershell(project_root: Path, duong: str) -> None:
    """`curl` trần và `%USERPROFILE%` đều **sai trong PowerShell**, và cả hai nằm cùng một dòng.

    Đo được trong lúc diễn tập 2026-09-22, ngay ở dòng lệnh **đầu tiên** người dùng gõ: trong
    Windows PowerShell, `curl` là bí danh của `Invoke-WebRequest` — một cmdlet khác hẳn, không hiểu
    `-L`, và nó báo *"A parameter cannot be found that matches parameter name 'L'"*. Thông báo đó
    không nhắc một chữ nào tới bí danh, nên người dùng không có đường nào tự lần ra.

    Test nhắm vào **dòng chứa URL**, không nhắm vào cả file: phần giải thích ngay cạnh buộc phải
    nhắc tới `curl` và `%USERPROFILE%` để nói vì sao chúng sai.
    """
    dau_moi = "raw.githubusercontent.com/taducloc0603/copy-trade/main/CAI-DAT.cmd"
    dong = [d for d in _doc(project_root, duong).splitlines() if dau_moi in d and "-o" in d]
    assert dong, f"{duong}: khong thay dong tai CAI-DAT.cmd"
    for d in dong:
        assert "curl.exe" in d, f"{duong}: `curl` tran la bi danh Invoke-WebRequest -- {d.strip()}"
        assert "%USERPROFILE%" not in d, (
            f"{duong}: %USERPROFILE% chi dung trong cmd, phai la $env:USERPROFILE -- {d.strip()}"
        )
