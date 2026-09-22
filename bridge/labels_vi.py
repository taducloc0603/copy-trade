"""Bảng nhãn tiếng Việt (D-16).

Đây là **nơi duy nhất** trong toàn dự án được chứa chuỗi tiếng Việt hướng tới người dùng.
Enum trong DB, log và message giao thức luôn là tiếng Anh không dấu; việc dịch chỉ xảy ra
ở tầng hiển thị, qua đúng file này.

BUY, SELL và tên symbol giữ nguyên gốc, không dịch.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

PAIR_STATUS = {
    "PENDING_OPEN": "Chờ mở",
    "OPEN": "Đang hedge",
    "PARTIALLY_CLOSED": "Đóng một phần",
    "CLOSING": "Đang đóng",
    "CLOSED": "Đã đóng",
    "OPEN_FAILED": "Mở thất bại",
    "ORPHANED": "Mất hedge",
}
RUN_MODE = {
    "RUNNING": "Đang chạy",
    "PAUSE_NEW_ENTRIES": "Tạm dừng lệnh mới",
    "PAUSED": "Đã dừng",
    "EMERGENCY": "Khẩn cấp",
}
AGENT_STATUS = {"ONLINE": "Kết nối", "OFFLINE": "Mất kết nối", "DEGRADED": "Mất kết nối sàn"}
COPY_MODE = {"SAME": "Cùng chiều", "OPPOSITE": "Khác chiều"}
CLOSE_SOURCE = {"MASTER": "Từ Master", "CLIENT": "Từ Client", "BOT": "Bot đồng bộ",
                "BROKER": "Sàn đóng", "MANUAL": "Thủ công"}
ALERT_LEVEL = {"INFO": "Thông tin", "WARNING": "Cảnh báo",
               "ERROR": "Lỗi", "CRITICAL": "Nghiêm trọng"}
MASTER_POSITION_STATUS = {"OPEN": "Đang mở", "CLOSED": "Đã đóng", "UNPAIRED": "Chưa ghép cặp"}
AGENT_ROLE = {"MASTER": "Master", "CLIENT": "Client", "CLICKER": "Clicker"}
ROUTE = {"EA": "Qua EA", "UI": "Qua giao diện"}

#: Mã lỗi của `ops.LoiCauHinh` → câu hiện trên dashboard. Cùng bộ mã mà `bridge/admin.py` dịch
#: sang câu không dấu cho dòng lệnh: một chỗ kiểm, hai chỗ dịch. Dấu `{...}` được tầng web điền
#: bằng `ngu_canh` của chính lỗi đó, nên JavaScript không bao giờ phải dựng câu (D-16).
LOI_CAU_HINH = {
    "AGENT_DA_TON_TAI": "Đã có agent {agent_id}. Muốn đổi token thì dùng nút cấp lại token.",
    "KHONG_CO_AGENT": "Không có agent {agent_id}",
    "SAI_ROLE": "Agent {agent_id} đang là {role}, chỗ này cần {can}.",
    "ROLE_LA": "Vai trò {role} không hợp lệ.",
    "LOGIN_KHONG_DUONG": "Số tài khoản phải là số dương, nhận được {login}.",
    "CLIENT_DA_TON_TAI": "Đã có client {client_id}.",
    "KHONG_CO_CLIENT": "Không có client {client_id}",
    "CLIENT_CON_LICH_SU": ("{client_id} đã có {so_cap} cặp lệnh nên không xoá được — xoá là "
                           "mất luôn đường đọc lại lịch sử của chúng. Hãy TẮT Client này."),
    "CAN_CLICKER": ("Đặt {truong} qua giao diện thì Client phải có một clicker. "
                    "Chưa khai clicker thì lệnh sẽ không có ai bấm."),
    "CAN_CLICKER_MASTER": ("Đóng phía Master qua giao diện cần một clicker riêng lái terminal "
                           "Master. Khai clicker trước."),
    "CLICKER_DA_DUNG": ("Agent {agent_id} đang là clicker của Client {client_id}. "
                        "Mỗi terminal cần một clicker riêng."),
    "CLICKER_CUA_MASTER": ("Agent {agent_id} đang là clicker lái terminal Master. Dùng chung là "
                           "lệnh của Client sẽ được bấm trên terminal Master."),
    "AGENT_DA_DUNG": ("Agent {agent_id} đang là agent của Client {client_id}. Một terminal MT5 "
                      "chỉ thuộc về một Client — dùng chung là mỗi lệnh Master sinh hai lệnh mở "
                      "trên cùng terminal đó."),
    "THIEU_MA": "Thiếu mã. Điền mã client hoặc tên agent.",
    "DAT_LAI_CAN_PAUSED": "Đang ở chế độ {run_mode}. Dừng toàn bộ đồng bộ trước khi đặt lại.",
    "DAT_LAI_CON_DANG_MO": ("Còn {so_cap} cặp và {so_vi_the} vị thế Master đang mở. Xoá sổ "
                            "sách trong lúc tiền còn nằm trên sàn là cách chắc chắn nhất để "
                            "không ai biết còn gì đang mở."),
    "DAT_LAI_CON_LENH_BAY": ("Còn {so_lenh} lệnh chưa xong. Chờ chúng kết thúc rồi hãy đặt "
                             "lại — xoá giữa lúc một lệnh đang bay để lại một ack không còn "
                             "chỗ để ghi."),
    "CUM_TU_SAI": "Gõ chưa đúng cụm xác nhận.",
    "KIEU_DAT_LAI_LA": "Kiểu đặt lại {kieu} không hợp lệ.",
    "MA_BUOC_LA": "Không có bước hướng dẫn nào mã {ma_buoc}.",
    "HANH_DONG_CHAM_MT5": ("{hanh_dong} là hành động gửi lệnh xuống MT5. Dashboard chỉ xem và "
                           "cấu hình — đóng tay trong MT5 rồi bấm Bỏ qua kèm ghi chú."),
    "KHONG_TIM_THAY_MAC_DINH": "Không tìm thấy câu gieo mặc định trong schema.sql.",
    "HE_SO_KHONG_DUONG": "Hệ số volume phải lớn hơn 0, nhận được {gia_tri}.",
    "CHIEU_COPY_LA": "Chiều copy {gia_tri} không hợp lệ.",
    "DUONG_LA": "Giá trị {gia_tri} không hợp lệ cho {truong}.",
    "THIEU_SYMBOL": "Thiếu tên symbol.",
    "SAN_KHONG_CO_SYMBOL": ("Sàn Client chưa báo có symbol {client_symbol}. Kiểm tra EA Client "
                            "đang chạy và symbol đã kéo vào Market Watch."),
    "KHONG_CO_ANH_XA": "Không có ánh xạ cho {master_symbol}",
    "KHONG_CO_FILE_CONFIG": "Bridge không nạp config.toml nào nên không có gì để sửa.",
    "KHONG_CO_GI_DOI": "Không có giá trị nào được đổi.",
    "TIEU_DE_KHONG_CO_SO_TK": ("Tiêu đề {tieu_de} không chứa số tài khoản {login}. "
                               "Cửa sổ MT5 mở đầu bằng số tài khoản, và đó là thứ clicker "
                               "đối chiếu trước khi bấm."),
    "KHOA_NGOAI_DANH_SACH": "Khoá {khoa} không sửa được trên dashboard.",
    "GIA_TRI_LA": "Giá trị không hợp lệ cho {khoa}.",
    "NGOAI_MIEN": "{khoa} phải trong khoảng {tu}…{den}, nhận được {gia_tri}.",
}

#: Nhóm nhãn **ánh xạ từ enum trong DB**. Key phải là enum tiếng Anh viết hoa, đúng như giá trị
#: được lưu. Nhóm `UI` ở cuối file KHÔNG thuộc đây: key của nó là id chuỗi giao diện, không phải
#: enum, nên không chịu ràng buộc viết hoa.
ENUM_GROUPS: dict[str, dict[str, str]] = {
    "PAIR_STATUS": PAIR_STATUS,
    "RUN_MODE": RUN_MODE,
    "AGENT_STATUS": AGENT_STATUS,
    "COPY_MODE": COPY_MODE,
    "CLOSE_SOURCE": CLOSE_SOURCE,
    "ALERT_LEVEL": ALERT_LEVEL,
    "MASTER_POSITION_STATUS": MASTER_POSITION_STATUS,
    "AGENT_ROLE": AGENT_ROLE,
    "ROUTE": ROUTE,
    "LOI_CAU_HINH": LOI_CAU_HINH,
}

#: Mọi nhóm nhãn, dùng cho test và cho việc duyệt toàn bộ bảng nhãn.
ALL_GROUPS: dict[str, dict[str, str]] = dict(ENUM_GROUPS)


def label(group: dict[str, str], key: str) -> str:
    """Trả về nhãn tiếng Việt của ``key`` trong ``group``.

    Thiếu nhãn thì trả về chính ``key`` và ghi WARNING. Hàm này **không bao giờ ném exception**:
    thiếu một nhãn không đáng làm sập dashboard.
    """
    if key is None:
        _log.warning("label() nhan key None")
        return ""
    text = group.get(key)
    if text is None:
        _log.warning("Thieu nhan tieng Viet cho key %r", key)
        return key
    return text


# ---------------------------------------------------------------------------------------------
# Nhãn giao diện (phase 9).
#
# Template và JavaScript **không được** chứa chuỗi tiếng Việt nào. Chúng hiển thị đúng những gì
# tầng Python gửi xuống, và tầng Python lấy chữ từ đây. Nhờ vậy đổi cách gọi một khái niệm chỉ
# phải sửa một chỗ, và `grep` tìm chuỗi tiếng Việt lọt ra ngoài trở thành một phép kiểm được.
# ---------------------------------------------------------------------------------------------

UI = {
    "app_title": "MT5 Copy Bridge",
    "nav_main": "Tổng quan",
    "nav_findings": "Sai lệch",
    "nav_config": "Cấu hình",
    "nav_log": "Nhật ký",

    "run_mode_label": "Chế độ vận hành",
    "agents": "Trạng thái agent",
    "canary_last_ok": "Canary gần nhất",
    "trade_allowed": "Algo Trading",
    "trade_not_allowed": ("Algo Trading đang TẮT trên terminal này. Lệnh ĐÓNG sẽ thất "
                          "bại, trong khi lệnh MỞ qua giao diện vẫn chạy."),
    "canary_never": "chưa lần nào",

    "metric_p50": "Độ trễ copy p50",
    "metric_p95": "Độ trễ copy p95",
    "metric_hedged": "Cặp đang hedge",
    "metric_attention": "Cần can thiệp",

    "pairs_title": "Cặp lệnh",
    "col_pair": "Cặp",
    "col_symbol": "Symbol",
    "col_direction": "Chiều",
    "col_volume": "Vol M/C",
    "col_status": "Trạng thái",
    "orphan_master_left": "Mất hedge — còn Master",
    "orphan_client_left": "Mất hedge — còn Client",
    "reason_mismatch": "Sai kênh mở lệnh",
    "close_reason_mismatch": "Sai kênh đóng lệnh",
    "reason_mismatch_ca_hai": "Sai kênh cả mở lẫn đóng",
    "no_pairs": "Chưa có cặp lệnh nào",

    "btn_pause_new": "Tạm dừng lệnh mới",
    "btn_stop_sync": "Dừng toàn bộ đồng bộ",
    "btn_resume": "Bắt đầu copy",

    "confirm_stop_sync": "Dừng toàn bộ đồng bộ sẽ bỏ rơi các cặp đang chạy. Tiếp tục?",
    "reset_title": "Đặt lại hệ thống",
    "reset_hint": ("Chỉ làm được khi đang dừng đồng bộ, không còn cặp hay vị thế Master nào mở, "
                   "và không còn lệnh nào chưa xong. Database được sao lưu trước khi xoá."),
    "btn_reset_data": "Đặt lại dữ liệu (giữ cấu hình)",
    "btn_reset_all": "Đặt lại toàn bộ (kể cả cấu hình)",
    "reset_phrase_data": "DAT LAI DU LIEU",
    "reset_phrase_all": "DAT LAI TAT CA",
    "confirm_reset_data": ("Xoá toàn bộ lịch sử giao dịch: cặp lệnh, vị thế Master, event, lệnh đã "
                           "gửi, cảnh báo, sai lệch. Giữ agent, client, ánh xạ symbol và khoá hệ "
                           "thống, nên hệ thống chạy tiếp được ngay. Gõ đúng cụm dưới đây:"),
    "confirm_reset_all": ("Xoá lịch sử giao dịch VÀ cấu hình nghiệp vụ: client, ánh xạ symbol, "
                          "khoá hệ thống về mặc định. Agent và token được giữ, nên không phải dán "
                          "lại token vào EA. Gõ đúng cụm dưới đây:"),
    "reset_done": "Đã đặt lại. Bản sao lưu: {ban_sao}",

    "findings_title": "Sai lệch cần xử lý",
    "findings_safe": "An toàn — khắc phục chỉ gồm đóng lệnh hoặc sửa sổ sách",
    "findings_decision": "Cần quyết định — dính tới mở lệnh hoặc đóng Master",
    "evidence_db": "Sổ sách",
    "evidence_master": "Master thực tế",
    "evidence_client": "Client thực tế",
    "btn_accept": "Chấp nhận",
    "accept_refused": ("Không áp dụng được. Thường là vì tình trạng cặp đã đổi kể từ lúc phát "
                       "hiện (finding cũ). Xem lại bằng chứng, hoặc Bỏ qua kèm ghi chú."),
    "btn_skip": "Bỏ qua",
    "finding_lam_o_mt5": ("Sai lệch này cần đóng (hoặc mở) một vị thế thật. Dashboard không làm "
                          "việc đó: đóng tay trong MT5, rồi quay lại bấm Bỏ qua kèm ghi chú."),
    "skip_note_prompt": "Lý do bỏ qua (sẽ để lại một cảnh báo tồn tại):",
    "no_findings": "Không có sai lệch nào",
    "confirm_resume_with_findings": "Còn {n} sai lệch chưa xử lý:",

    "cfg_title": "Cấu hình",
    "cfg_effect_now": "Có hiệu lực ngay",
    "cfg_effect_next_open": ("Chỉ áp dụng cho lệnh mở sau khi lưu. "
                             "Các cặp đang chạy giữ nguyên tỷ lệ."),
    "cfg_multiplier": "Hệ số volume",
    "cfg_preview": "Xem trước",
    "cfg_open_route": "Kênh mở lệnh phía Client",
    # Chinh cot nay quyet dinh deal DONG mang CLIENT hay EXPERT, nen no phai nhin thay duoc
    # tren dashboard chu khong chi qua `bridge.admin cau-hinh-client`.
    "cfg_close_route": "Kênh đóng lệnh phía Client",
    "cfg_master_close_always": "Master đóng thì Client đóng: LUÔN BẬT, không tắt được",
    "cfg_can_close_master": "Cho phép Client đóng ngược Master",
    # Hai nhãn này là CÂU, không phải "Bật"/"Tắt": ô chọn nói luôn hậu quả, vì đây là chỗ
    # quyết định Master có bị đóng theo hay không.
    "cfg_close_master_off": "TẮT — đóng ở Client thì Master vẫn mở",
    "cfg_close_master_on": "BẬT — đóng ở Client thì Master đóng theo",
    "confirm_can_close_master": ("Bật mục này nghĩa là khi một Client đóng, Bridge sẽ đóng "
                                 "Master, rồi đóng nốt các Client còn lại. Tiếp tục?"),
    "confirm_open_route_ui": ("Chuyển sang kênh giao diện: thông lượng còn khoảng một lệnh mỗi "
                              "giây, độ trễ copy tăng lên khoảng nửa giây tới vài giây. "
                              "Bắt buộc phải có một clicker đang kết nối. Tiếp tục?"),
    "cfg_copy_mode": "Chiều copy",
    "cfg_same": "Cùng chiều",
    "cfg_opposite": "Khác chiều (Master BUY thì Client SELL)",
    "cfg_route_ea": "Qua EA",
    "cfg_route_ui": "Qua giao diện MT5",
    "cfg_save": "Lưu",
    "cfg_saved": "Đã lưu",
    "cfg_open_pairs_keep": "{n} cặp đang chạy giữ nguyên tỷ lệ cũ",
    "cfg_client_title": "Cấu hình copy —",
    "cfg_client_enabled": "Trạng thái Client",
    "cfg_client_on": "ĐANG COPY",
    "cfg_client_off": "ĐÃ TẮT — không copy lệnh mới, cặp đang mở vẫn đóng theo Master",
    "confirm_client_off": ("Tắt Client này: lệnh mới của Master sẽ không được copy sang "
                           "nữa. Cặp đang mở giữ nguyên và vẫn đóng theo Master. Tiếp tục?"),
    "cfg_client_new": "Thêm Client",
    "cfg_client_id": "Mã client",
    "cfg_client_agent": "Agent CLIENT (EA trên terminal đó)",
    "cfg_client_clicker": "Clicker lái terminal đó",
    "cfg_client_new_hint": ("Mỗi Client cần một terminal MT5 riêng, một agent CLIENT riêng, "
                            "và nếu đi qua giao diện thì một clicker riêng nữa. Hệ thống "
                            "hiện chạy được hai clicker: của Client và của Master."),
    "btn_delete": "Xoá",
    "confirm_client_delete": ("Xoá hẳn Client này khỏi cấu hình, kèm ánh xạ symbol của nó. "
                              "Chỉ làm được khi nó chưa có cặp lệnh nào — có rồi thì hãy "
                              "TẮT, vì xoá là mất luôn đường đọc lại lịch sử. Tiếp tục?"),
    "cfg_system_title": "Khoá hệ thống",
    "cfg_system_hint": "Mỗi khoá lưu riêng. Đổi là có hiệu lực ngay, không cần khởi động lại.",
    "cfg_file_restart_short": "Có hiệu lực sau khi khởi động lại dịch vụ.",
    "cfg_file_title": "config.toml — cấu hình khởi động",
    "cfg_file_masked": "(đã đặt)",
    "cfg_file_restart": ("Sửa ở đây được kiểm lại rồi mới ghi, và bản cũ được sao lưu. "
                         "Giá trị mới CHỈ có hiệu lực sau khi khởi động lại dịch vụ "
                         "CopyBridge."),
    "cfg_file_secret_hint": "Để trống là giữ nguyên. Gõ giá trị mới để thay.",
    "cfg_file_readonly": ("Bản cài cũ còn giá trị trong file — file THẮNG database. Xoá "
                          "dòng này trong config.toml để dùng giá trị khai trên dashboard."),
    "cfg_file_saved": "Đã lưu. Khởi động lại dịch vụ CopyBridge để có hiệu lực.",

    # -- khối "Cần làm" ------------------------------------------------------------------------
    #
    # Mỗi câu phải nói **làm gì ở đâu**, không chỉ nói cái gì sai: đây là thứ người vận hành đọc
    # ngay sau khi cài xong, và họ chưa biết trang này có những khối nào.
    "can_lam_title": "Cần làm",
    "can_lam_xong": "Đủ rồi — không còn việc nào đang chặn việc copy lệnh.",
    "can_lam_muc_chan": "CHẶN",
    "can_lam_muc_luu_y": "Lưu ý",
    "can_lam_chan_hint": ("Còn mục CHẶN thì hệ thống **không** copy được lệnh nào, dù dashboard "
                          "trông bình thường."),
    "can_lam_chua_co_agent": ("Chưa có agent nào. Khối Agent bên dưới → Thêm agent (Master, "
                              "Client, và một Clicker cho mỗi Client đi đường giao diện)."),
    "can_lam_chua_co_client": "Chưa có Client nào. Khối Thêm Client bên dưới.",
    "can_lam_clicker_chua_khai": ("Clicker {agent_id} chưa khai số tài khoản hoặc tiêu đề cửa sổ "
                                  "terminal. Khối Agent bên dưới. Chưa khai thì clicker thoát và "
                                  "thử lại mỗi 60 giây — không bấm được lệnh nào."),
    "can_lam_clicker_lech": ("Clicker {agent_id} khai số tài khoản {khai}, nhưng EA trên chính "
                             "terminal đó ({tu_agent}) báo {suy}. Một trong hai sai: hoặc clicker "
                             "đang lái nhầm terminal, hoặc terminal vừa đăng nhập sang tài khoản "
                             "khác. Sửa ở khối Agent bên dưới."),
    "can_lam_tieu_de_lech": ("Tiêu đề cửa sổ của {agent_id} là “{tieu_de}” nhưng không chứa số "
                             "tài khoản {login}. Đó là thứ clicker đối chiếu trước MỖI cú bấm, "
                             "nên nó sẽ không bấm — hoặc bấm vào terminal khác."),
    # Hai câu, không một câu nước đôi: agent EA và agent clicker hỏng vì hai lý do khác hẳn nhau
    # và sửa bằng hai việc khác hẳn nhau. Một câu chung buộc phải viết "hoặc...", và một hướng dẫn
    # có chữ "hoặc" là một hướng dẫn bắt người đọc tự chẩn đoán.
    "can_lam_agent_chua_online": ("{agent_id} ({role}) đang {status}. Gắn EA lên chart của "
                                  "terminal này và dán đúng token của agent."),
    "can_lam_clicker_chua_online": ("{agent_id} đang {status}. Clicker là một tiến trình trên "
                                    "VPS, không phải EA: kiểm tác vụ Clicker đang chạy và đọc "
                                    "logs\\clicker-wrapper.log."),
    "can_lam_algo_tat": ("Algo Trading đang TẮT trên terminal của {agent_id}. Bật nút Algo "
                         "Trading trong MT5: đó là lưới cuối của đường đóng lệnh."),
    "can_lam_thieu_anh_xa": ("Client {client_id} chưa có ánh xạ symbol nào đang bật. Khối Ánh xạ "
                             "symbol bên dưới. Thiếu là MỌI lệnh Master bị bỏ qua."),
    "can_lam_client_thieu_clicker": ("Client {client_id} đi đường giao diện nhưng chưa gán "
                                     "clicker. Xoá rồi tạo lại Client kèm clicker (gán clicker "
                                     "chỉ đặt được lúc tạo)."),
    "can_lam_master_thieu_clicker": ("Đường đóng Master đặt UI nhưng chưa khai clicker của "
                                     "Master. Khối Đường đóng phía Master bên dưới."),
    "can_lam_config_con_khoa": ("config.toml còn khai {khoa} cho clicker. File THẮNG database, "
                                "nên khai trên trang này sẽ không có tác dụng."),
    "can_lam_chua_bat_copy": ("Đang ở chế độ {run_mode}. Xong các mục trên thì bấm Bắt đầu copy "
                              "ở thanh trên cùng."),

    # -- trang Hướng dẫn -----------------------------------------------------------------------
    #
    # Mỗi bước có **bốn** phần, và cả bốn đều bắt buộc trừ `_bay`:
    #
    #   `hd_<ma>`        một dòng để quét mắt. KHÔNG nhồi hướng dẫn vào đây.
    #   `hd_<ma>_viec`   TUPLE các việc con, theo đúng thứ tự phải làm. Mỗi phần tử là một hành
    #                    động làm được, không phải một lời khuyên.
    #   `hd_<ma>_kiem`   tự kiểm bước này xong chưa: nhìn thấy gì thì coi là xong.
    #   `hd_<ma>_bay`    cái bẫy ĐÃ bắt được người thật. Không có thì để trống, đừng bịa.
    #
    # Bản đầu chỉ có dòng một, và mọi thứ phải nhồi vào đó: bước gắn EA gói sáu hành động vào một
    # câu, không thứ tự, không nói làm ở đâu, không cách tự kiểm. Lần chạy thử tài liệu trên VPS
    # 2026-09-22 tắc ngay ở bước ấy.
    #
    # Người đọc trang này vừa cài xong và CHƯA biết trang có những khối nào — nên mỗi việc con
    # phải nói rõ khối nào, nút nào, cửa sổ nào.
    "nav_guide": "Hướng dẫn",
    "hd_title": "Làm theo thứ tự này",
    "hd_nhom_lan_dau": "Cài đặt lần đầu",
    # KHÔNG ghi số việc vào đây. Bản cũ ghi "Chín việc" trong khi danh sách có tám, và không ai
    # sửa — số bước đã đổi ba lần rồi. Giao diện tự đếm và hiện số việc còn lại ở tiêu đề nhóm.
    "hd_nhom_lan_dau_chu": ("Theo đúng thứ tự này — bước sau cần kết quả của bước trước. Mở Chi "
                            "tiết ở mỗi bước để xem từng việc con, cách tự kiểm và cái bẫy hay "
                            "gặp. Việc nào dashboard tự kiểm được thì nó tự chuyển sang Đã xong "
                            "và nói rõ đang còn thiếu cái gì; việc nằm trong MT5 thì bạn tự tích."),
    "hd_nhom_sau_update": "Sau khi cập nhật code",
    "hd_nhom_sau_update_chu": ("Làm sau mỗi lần chạy cai-dat.ps1 -CapNhat. Ô tự tích được xoá "
                               "sạch ở mỗi lần cập nhật, nên danh sách này luôn nói về lần gần "
                               "nhất."),
    "hd_moc_cap_nhat": "Lần cập nhật gần nhất: {moc}",
    "hd_xong": "Đã xong",
    "hd_con_thieu": "Còn thiếu",
    "hd_tu_tich": "Tự tích khi xong",
    "hd_het_viec": "Không còn việc nào trong mục này.",
    "hd_lenh_hint": "Chạy trong PowerShell, tại C:\\CopyBridge:",

    # Nhãn của khối chi tiết.
    "hd_chi_tiet": "Chi tiết",
    "hd_nhan_noi": "Làm ở",
    "hd_noi_dashboard": "chính trang này (dashboard)",
    "hd_noi_mt5": "trong MT5",
    "hd_noi_powershell": "PowerShell trên VPS",
    "hd_nhan_viec": "Từng việc, theo thứ tự",
    "hd_nhan_kiem": "Biết là xong khi",
    "hd_nhan_bay": "Bẫy hay gặp",
    "hd_nhan_thieu": "Đang còn thiếu",
    "hd_nhan_lenh": "Đường dòng lệnh (bấm để chọn hết)",

    # -- Cài đặt lần đầu -----------------------------------------------------------------------
    "hd_ld_bien_dich": "Biên dịch hai EA thành .ex5 rồi chép vào MT5",
    "hd_ld_bien_dich_viec": (
        "Chạy lệnh dưới đây một lần cho CopyBridgeMaster.mq5.",
        "Chạy lại, đổi Master thành Client, để biên dịch CopyBridgeClient.mq5.",
        "Mở logs\\compile.log và xem dòng cuối: phải là 0 errors.",
        "Trong MT5 của Master: File > Open Data Folder > MQL5 > Experts. Chép "
        "ea\\CopyBridgeMaster.ex5 vào đó.",
        "Làm lại cho terminal Client với CopyBridgeClient.ex5.",
        "Trong mỗi MT5: Navigator (Ctrl+N) > chuột phải Expert Advisors > Refresh. EA phải hiện "
        "ra trong danh sách.",
    ),
    "hd_ld_bien_dich_kiem": ("Navigator của cả hai terminal đều thấy EA của mình — "
                            "CopyBridgeMaster ở terminal Master, CopyBridgeClient ở Client."),
    "hd_ld_bien_dich_bay": ("Mỗi terminal MT5 có một thư mục dữ liệu RIÊNG. Chép .ex5 vào một "
                           "terminal rồi tưởng cả hai đã có là lỗi hay gặp nhất — luôn vào File > "
                           "Open Data Folder của CHÍNH terminal đó, đừng đoán đường dẫn."),

    "hd_ld_gan_ea": "Gắn EA lên chart và dán token, mỗi terminal đúng một chart",
    "hd_ld_gan_ea_viec": (
        "Sang tab Cấu hình > khối Agent. Bấm Cấp lại token ở dòng AG-MASTER: token hiện ra MỘT "
        "LẦN ngay trên trang, chép ngay và đừng đóng trang.",
        "Trong MT5 của Master: mở đúng một chart của symbol bạn sẽ copy, rồi kéo CopyBridgeMaster "
        "từ Navigator lên chart đó.",
        "Hộp thoại mở ra, tab Inputs: AgentToken = token vừa chép, BridgeHost = 127.0.0.1, "
        "BridgePort = 8787. Bấm OK.",
        "Góc trên phải chart phải có mặt cười. Mặt buồn nghĩa là EA chưa chạy.",
        "Về dashboard, Cấp lại token cho AG-CLIENT, rồi làm lại đúng các bước trên trong terminal "
        "Client với CopyBridgeClient.",
        "Terminal thứ ba, nếu bạn có mở thêm: KHÔNG gắn EA lên.",
    ),
    "hd_ld_gan_ea_kiem": ("Khối Agent hiện AG-MASTER và AG-CLIENT đều ONLINE. Hoặc chạy lệnh "
                         "liet-ke dưới đây."),
    "hd_ld_gan_ea_bay": ("Hai chart cùng gắn EA là hai kết nối dùng CÙNG một token, và chúng đá "
                        "nhau liên tục: agent nhảy ONLINE/OFFLINE không dừng. Mỗi terminal đúng "
                        "MỘT chart. Và mỗi lần Cấp lại token là token cũ hết hiệu lực ngay — cấp "
                        "lại mà quên dán vào EA thì agent tắt luôn."),

    "hd_ld_khai_clicker": "Khai số tài khoản và tiêu đề cửa sổ cho từng clicker",
    "hd_ld_khai_clicker_viec": (
        "Trong MT5 của Master, đọc thanh tiêu đề trên cùng của cửa sổ và chép nguyên văn. Nó "
        "thường có dạng: <số tài khoản> - <tên broker> - ...",
        "Sang tab Cấu hình > khối Agent > dòng AG-CLICKER-MASTER: điền số tài khoản và tiêu đề "
        "cửa sổ, rồi Lưu.",
        "Làm lại cho AG-CLICKER với tiêu đề của terminal Client.",
        "Chờ tới 70 giây rồi mới kết luận. Xem phần Bẫy hay gặp.",
    ),
    "hd_ld_khai_clicker_kiem": ("AG-CLICKER và AG-CLICKER-MASTER chuyển sang ONLINE trong khối "
                               "Agent, và logs\\clicker-wrapper.log không còn dòng thoat 4 mới."),
    "hd_ld_khai_clicker_bay": ("Tiêu đề PHẢI chứa số tài khoản: đó là thứ clicker đối chiếu với "
                              "cửa sổ thật trước MỖI cú bấm, nên một tiêu đề chung như MetaTrader "
                              "5 sẽ khớp cả terminal khác. Và khai xong KHÔNG có tác dụng tức "
                              "thì: clicker ngủ 60 giây giữa hai lần thử, nên trang còn báo đỏ "
                              "thêm khoảng một phút là bình thường."),

    "hd_ld_algo": "Bật Algo Trading trên mọi terminal MT5",
    "hd_ld_algo_viec": (
        "Trong mỗi terminal: bấm nút Algo Trading trên thanh công cụ, hoặc Ctrl+E.",
        "Nút phải sáng XANH. Xám là đang tắt.",
        "Làm cho cả terminal Master và terminal Client.",
    ),
    "hd_ld_algo_kiem": "Khối Agent không còn dòng nào báo Algo Trading tắt.",
    "hd_ld_algo_bay": ("Đường mở và đường đóng bình thường đi qua giao diện nên KHÔNG cần Algo "
                      "Trading — vì thế tắt nó đi thì mọi thứ vẫn trông bình thường. Nhưng nó là "
                      "LƯỚI CUỐI: clicker hỏng thì đường đóng rơi về OrderSend của EA, và lúc ấy "
                      "Algo Trading là thứ duy nhất còn giữ cho vị thế đóng được. Kiểm lại sau "
                      "MỖI lần VPS khởi động lại hoặc MT5 tự cập nhật."),

    "hd_ld_toolbox": "Mở Toolbox và để ở tab Trade trên mọi terminal",
    "hd_ld_toolbox_viec": (
        "Trong mỗi terminal: Ctrl+T để mở Toolbox.",
        "Chọn tab Trade, không phải History hay Journal.",
        "Để nguyên như vậy: đừng đóng, đừng chuyển sang tab khác.",
    ),
    "hd_ld_toolbox_kiem": "Cả hai terminal đều thấy danh sách vị thế ở nửa dưới cửa sổ.",
    "hd_ld_toolbox_bay": ("Clicker đọc danh sách vị thế từ đúng tab này để đóng lệnh. Đóng Toolbox "
                         "hoặc chuyển tab là không đóng được lệnh qua giao diện nữa — và triệu "
                         "chứng chỉ hiện ra lúc cần đóng, tức lúc đắt nhất."),

    "hd_ld_anh_xa": "Khai ánh xạ symbol cho từng Client",
    "hd_ld_anh_xa_viec": (
        "Trong MT5 của Client: mở Market Watch (Ctrl+M) và kéo vào đó symbol bạn sẽ copy. Bridge "
        "chỉ thấy symbol nào đã có trong Market Watch.",
        "Sang tab Cấu hình > khối Ánh xạ symbol.",
        "Chọn symbol bên Master, rồi symbol tương ứng bên Client. Trang đã đề xuất sẵn cặp khớp "
        "nếu tìm được — kiểm lại rồi Lưu.",
        "Làm cho từng symbol bạn định copy.",
    ),
    "hd_ld_anh_xa_kiem": "Khối Ánh xạ symbol có ít nhất một dòng đang bật cho mỗi Client.",
    "hd_ld_anh_xa_bay": ("Thiếu ánh xạ thì MỌI lệnh của Master bị bỏ qua TRONG IM LẶNG: không "
                        "lỗi, không cảnh báo, chỉ là không có gì xảy ra. Đây là lỗi tốn thời gian "
                        "nhất để tự tìm ra."),

    "hd_ld_cau_hinh_copy": "Xem lại cấu hình copy của từng Client",
    "hd_ld_cau_hinh_copy_viec": (
        "Tab Cấu hình > khối Client. Với từng Client, xem ba giá trị dưới đây.",
        "Chiều copy: SAME đi cùng chiều Master, REVERSE đi ngược.",
        "Hệ số volume: 1.0 là copy đúng khối lượng Master. Bấm Xem trước để thấy lệnh nào bị rớt "
        "vì khối lượng tối thiểu của sàn.",
        "Cho phép Client đóng ngược Master: bật thì đóng lệnh ở Client sẽ đóng cả bên Master.",
        "Đây là lựa chọn, không phải thứ còn thiếu — xem xong thì tự tích.",
    ),
    "hd_ld_cau_hinh_copy_kiem": "Bạn đã xem và đồng ý ba giá trị trên cho từng Client.",

    "hd_ld_bat_copy": "Bấm Bắt đầu copy",
    "hd_ld_bat_copy_viec": (
        "Kiểm mọi bước trên đã xanh. Bật copy khi còn bước đỏ là mở đường cho lệnh đi vào một cấu "
        "hình chưa xong.",
        "Bấm Bắt đầu copy ở thanh trên cùng — nút này thấy được ở mọi tab.",
        "Nhãn trạng thái phải chuyển sang RUNNING.",
    ),
    "hd_ld_bat_copy_kiem": "Thanh trên cùng hiện RUNNING thay vì PAUSED.",
    "hd_ld_bat_copy_bay": ("Bridge LUÔN khởi động ở chế độ dừng, kể cả khi VPS tự bật lại lúc 3 "
                          "giờ sáng — đó là chủ đích. Nghĩa là sau MỖI lần khởi động lại dịch vụ "
                          "bạn phải bấm lại nút này. Dịch vụ đang chạy KHÔNG có nghĩa là hệ thống "
                          "đang copy."),

    "hd_ld_thu_demo": "Thử một lệnh demo khối lượng nhỏ nhất",
    "hd_ld_thu_demo_viec": (
        "Trong MT5 của Master: mở một lệnh với khối lượng nhỏ nhất sàn cho phép.",
        "Xem terminal Client: phải có lệnh tương ứng trong khoảng 1 giây.",
        "Đóng lệnh ở Master. Client phải đóng theo.",
        "Chạy hai lệnh kiểm dưới đây. Cả hai phải không báo dòng nào.",
    ),
    "hd_ld_thu_demo_kiem": ("Client vào và ra theo Master, và kiem-reason / kiem-dong-sai không "
                           "báo dòng nào."),
    "hd_ld_thu_demo_bay": ("Làm việc này trên tài khoản DEMO. Và mỗi terminal Client chỉ copy "
                          "được MỘT symbol: hộp thoại New Order lấy symbol theo chart đang mở, "
                          "nên phải mở đúng chart đó và giữ nguyên."),

    # -- Sau khi cập nhật code -----------------------------------------------------------------
    "hd_up_ctrl_f5": "Bấm Ctrl+F5 trên mọi tab dashboard mở từ trước lần cập nhật",
    "hd_up_ctrl_f5_viec": (
        "Với mỗi tab dashboard đang mở: bấm Ctrl+F5, không phải F5.",
        "Tab mới mở sau khi cập nhật thì không cần.",
    ),
    "hd_up_ctrl_f5_kiem": "Trang tải lại và bạn thấy thay đổi của bản mới.",

    "hd_up_gan_lai_ea": "Biên dịch lại EA rồi GỠ khỏi chart và GẮN LẠI",
    "hd_up_gan_lai_ea_viec": (
        "Chạy lệnh biên dịch dưới đây cho từng EA đã đổi.",
        "Chép .ex5 mới vào MQL5\\Experts của từng terminal.",
        "GỠ EA khỏi chart: chuột phải > Expert Advisors > Remove.",
        "Kéo EA lên chart lại, dán lại token và BridgeHost / BridgePort.",
    ),
    "hd_up_gan_lai_ea_kiem": "Hai agent EA ONLINE lại, và Journal của MT5 báo EA vừa nạp.",
    "hd_up_gan_lai_ea_bay": ("Đổi khung thời gian KHÔNG làm MT5 đọc lại .ex5 từ đĩa. Phải gỡ rồi "
                            "gắn lại, không có đường tắt nào."),

    "hd_up_agent_online": "Kiểm mọi agent ONLINE lại",
    "hd_up_agent_online_viec": (
        "Chạy lệnh liet-ke dưới đây.",
        "Clicker cần khoảng 10-45 giây sau khi dịch vụ lên. Chờ rồi chạy lại.",
    ),
    "hd_up_agent_online_kiem": "Cả bốn agent đều ONLINE.",
    "hd_up_agent_online_bay": ("Một agent còn OFFLINE sau hai phút thì đọc "
                              "logs\\clicker-wrapper.log: thoat 4 nghĩa là chưa khai số tài "
                              "khoản, thoat 2 là thiếu token."),

    "hd_up_code_cu": "Kiểm không còn tiến trình nào chạy code CŨ",
    "hd_up_code_cu_viec": (
        "Chạy kiem-tra.ps1 dưới đây.",
        "Xem mục 4b: nó phải xanh.",
    ),
    "hd_up_code_cu_kiem": "Mục 4b của kiem-tra.ps1 xanh.",

    "hd_up_config_sot": "Xoá khoá clicker còn sót trong config.toml",
    "hd_up_config_sot_viec": (
        "Tab Cấu hình > khối config.toml, tìm dòng đỏ.",
        "Mở C:\\CopyBridge\\config.toml bằng Notepad, xoá account_login và terminal_title khỏi "
        "mục [clicker] và [clicker_master]. Lưu dạng UTF-8 không BOM.",
        "Chạy .\\scripts\\khoi-dong-lai.ps1.",
    ),
    "hd_up_config_sot_kiem": "Khối config.toml không còn dòng đỏ nào.",
    "hd_up_config_sot_bay": ("Còn hai khoá đó trong file thì FILE THẮNG DATABASE: khai trên "
                            "dashboard sẽ không có tác dụng, và không script nào báo cho bạn."),

    "hd_up_bat_copy": "Bấm Bắt đầu copy",
    "hd_up_bat_copy_viec": (
        "Bấm Bắt đầu copy ở thanh trên cùng.",
        "Nhãn trạng thái phải chuyển sang RUNNING.",
    ),
    "hd_up_bat_copy_kiem": "Thanh trên cùng hiện RUNNING.",

    "hd_up_tinh_hinh": "Chạy tinh-hinh để xem lần cập nhật có để lại gì",
    "hd_up_tinh_hinh_viec": (
        "Chạy lệnh tinh-hinh dưới đây.",
        "Đọc phần mục cần chú ý ở cuối.",
    ),
    "hd_up_tinh_hinh_kiem": "tinh-hinh thoát 0, hoặc mọi mục nó nêu đều là thứ bạn đã biết.",

    # Câu lệnh để copy
    "hd_lenh_kiem_demo": (".\\.venv\\Scripts\\python.exe -m bridge.admin kiem-reason\n"
                          ".\\.venv\\Scripts\\python.exe -m bridge.admin kiem-dong-sai"),
    "hd_lenh_bien_dich": ('& "C:\\Program Files\\MetaTrader 5\\MetaEditor64.exe" '
                          '/compile:"C:\\CopyBridge\\ea\\CopyBridgeMaster.mq5" '
                          '/log:"C:\\CopyBridge\\logs\\compile.log"'),
    "hd_lenh_liet_ke": ".\\.venv\\Scripts\\python.exe -m bridge.admin liet-ke",
    "hd_lenh_kiem_tra": ".\\scripts\\kiem-tra.ps1",
    "hd_lenh_tinh_hinh": ".\\.venv\\Scripts\\python.exe -m bridge.admin tinh-hinh",
    # Bốn lệnh dưới đây là đường CLI của đúng bốn bước làm trên dashboard. Khi đường dashboard tắc
    # thì trước đây không còn đường nào khác — đã xảy ra thật ở lần chạy thử 2026-09-22.
    "hd_lenh_sua_agent": (".\\.venv\\Scripts\\python.exe -m bridge.admin sua-agent "
                          "AG-CLICKER-MASTER --login <so-tk> --terminal-title <tieu-de>"),
    "hd_lenh_anh_xa": (".\\.venv\\Scripts\\python.exe -m bridge.admin anh-xa-symbol CL-01 "
                       "<symbol-master> --client-symbol <symbol-client>"),
    "hd_lenh_cau_hinh_client": (".\\.venv\\Scripts\\python.exe -m bridge.admin cau-hinh-client "
                                "CL-01"),
    "hd_lenh_run_mode": ".\\.venv\\Scripts\\python.exe -m bridge.admin run-mode RUNNING",
    # -- thêm Client bằng một nút --------------------------------------------------------------
    "cfg_client_new_ma": ("Bấm nút dưới đây là hệ thống tạo trọn bộ cho {ma}: agent của EA, agent "
                          "clicker, token clicker ghi thẳng vào config.toml, và dòng cấu hình "
                          "copy đi qua giao diện. Mọi cái tên đều sinh từ mã Client nên không thể "
                          "đặt lệch nhau."),
    "confirm_client_new": ("Tạo một Client mới kèm hai agent và một mục clicker trong config.toml?"),
    "cfg_client_new_done": "Đã tạo {ma} — còn hai việc phải làm tay",
    "cfg_client_new_agent": "Agent của EA: {agent} · clicker: {clicker}",
    "cfg_client_new_token": ("1. Token của EA — hiện MỘT LẦN, chép ngay và dán vào tham số "
                             "AgentToken của EA trên terminal mới:"),
    "cfg_client_new_task": ("2. Đăng ký tác vụ clicker trên VPS (PowerShell Administrator, tại "
                            "C:\\CopyBridge). Trình duyệt không làm được việc này:"),
    "map_client": "Client",
    "map_de_xuat": ("Đề xuất từ danh sách symbol thật của hai bên. Bấm Nhận để điền, rồi vẫn phải "
                    "bấm Thêm ánh xạ — hệ thống không tự tạo, vì chọn sai symbol không báo lỗi mà "
                    "chỉ copy sang một thị trường khác."),
    "map_de_xuat_nhan": "Nhận",
    "map_de_xuat_can_xem": "(tên khác nhau — xem kỹ)",

    "loi_khong_ro": ("Không thực hiện được, và máy chủ không nói rõ vì sao. "
                     "Xem logs\\bridge.log để biết chi tiết."),
    "cfg_nang_cao": "Nâng cao",
    "cfg_nang_cao_hint": ("Khoá kỹ thuật, config.toml và Đặt lại. Một bản cài bình thường không "
                          "cần mở mục này — mọi khoá ở đây đều có mặc định an toàn."),

    "cfg_clicker_new_title": "Thêm token cho một clicker mới",
    "cfg_clicker_new_hint": ("Mỗi Client đi đường giao diện cần một clicker riêng, và mỗi clicker "
                             "một mục trong config.toml. Đặt tên theo mã Client, ví dụ cl02 cho "
                             "CL-02, rồi dán token của agent clicker vào đây. Sau khi lưu, đăng ký "
                             "tác vụ trên VPS bằng: scripts\\tao-dich-vu.ps1 -ChiTacVuClicker "
                             "-TacVuClicker clicker_cl02"),
    "cfg_clicker_new_name": "Tên (sau chữ clicker_)",
    "cfg_clicker_new_token": "Token của clicker",
    "cfg_clicker_new_missing": "Cần cả tên mục và token.",
    "cfg_master_close_title": "Đường đóng phía Master",
    "cfg_master_clicker": "Clicker lái terminal Master",
    "cfg_master_route": "Kênh đóng lệnh phía Master",
    "confirm_master_close_ui": ("Đóng phía Master sẽ đi qua giao diện MT5: terminal Master phải "
                                "luôn mở Toolbox ở tab Trade và clicker Master phải đang chạy. "
                                "Tiếp tục?"),

    "agent_title": "Agent",
    "agent_role": "Vai trò",
    "agent_login": "Số tài khoản",
    "agent_terminal": "Tiêu đề cửa sổ terminal",
    "agent_terminal_hint": ("Clicker nhận hai giá trị này lúc kết nối. Lưu xong, clicker "
                            "nối lại sau vài giây — không phải khởi động lại tác vụ."),
    "agent_status": "Trạng thái",
    "agent_new": "Thêm agent",
    "agent_magic": "Magic number",
    "btn_new_token": "Cấp lại token",
    "confirm_new_token": ("Cấp token mới làm token cũ hết hiệu lực ngay: EA hoặc clicker đang "
                          "dùng nó sẽ rớt cho tới khi bạn dán token mới. Tiếp tục?"),
    "token_once": "Token chỉ hiện một lần, không đọc lại được. Chép ngay bây giờ.",
    "btn_close": "Đóng",

    "map_title": "Ánh xạ symbol",
    "map_master_symbol": "Symbol phía Master",
    "map_client_symbol": "Symbol phía Client",
    "map_add": "Thêm ánh xạ",
    "map_add_hint": "Kiểm với sàn Client rồi mới lưu.",
    "map_disable": "Tắt",
    "map_enabled": "Đang bật",
    "map_disabled": "Đã tắt",
    "confirm_map_disable": "Tắt ánh xạ này thì Master vào lệnh symbol đó sẽ không được copy. Tiếp tục?",
    "map_delete": "Xoá",
    "confirm_map_delete": ("Xoá hẳn ánh xạ này khỏi danh sách. Lệnh MỚI của symbol đó sẽ "
                           "không được copy nữa; cặp đang mở vẫn đóng được bình thường. "
                           "Muốn giữ lại để bật sau thì bấm Tắt. Tiếp tục?"),
    "btn_verify": "Kiểm tra với sàn",
    "map_unverified": "Chưa kiểm tra — không lưu được",
    "map_verify_failed": "Sàn Client không có symbol này",

    "log_title": "Nhật ký cảnh báo",
    "btn_ack": "Đã xử lý",
    "no_alerts": "Không có cảnh báo nào",

}

ALL_GROUPS["UI"] = UI

