# Nghiệm thu — TEST-01 … TEST-29

*Chốt ngày 2026-09-06, cập nhật sau Phase 11. Hai tài khoản demo Connext-Demo: **538216 Master**,
**538217 Client**. Cấu hình khi nghiệm thu: một Client, `copy_mode = OPPOSITE`,
`volume_multiplier = 1.0`, symbol `BTCUSD.s` ở cả hai bên, `ui_fallback_match = STRICT`.*

## Cách đọc bảng này

Cột **Nguồn** là phần quan trọng nhất, và nó chỉ có ba giá trị:

| Nguồn | Nghĩa |
|---|---|
| **DEMO** | Đã chạy trên hai terminal demo thật, có đối chiếu journal của cả hai bên. |
| **TEST** | Chỉ có test tự động với mock agent. Đúng theo mô hình, **chưa từng chạm sàn thật**. |
| **KHÔNG** | Chưa đạt được bằng bất kỳ cách nào ở lượt này. Lý do ghi rõ. |

Tách ba mức này ra là có chủ đích. Một bảng toàn dấu tích không cho biết cái gì đã được sàn
thật xác nhận và cái gì mới chỉ đúng trong đầu người viết test — mà đó chính là khác biệt đáng
kể nhất khi chuyển sang tiền thật. Phase 7 là ví dụ: bộ test dùng số tròn nên **không** lộ ra lỗi
sai số float `0.030000000000000002`; chỉ phiên demo mới lộ.

**Tổng kết: DEMO 15 · TEST 8 · KHÔNG 2.**

*(Cập nhật 2026-09-06 sau phase 11. Con số của bản phase 10 ghi "DEMO 13 · TEST 9 · KHÔNG 3"
**không khớp với chính bảng bên dưới** — đếm tay ra 11 · 12 · 2; kiểm toán độc lập bắt được
chỗ này (F-09). Phase 11 nâng TEST-01, TEST-11, TEST-22 từ TEST lên DEMO, và TEST-21 lên DEMO
sau khi sửa được lỗi nút đóng khẩn cấp bỏ quên phía Master.)*

---

## Bảng nghiệm thu

| Mã | Tình huống | Nguồn | Bằng chứng |
|---|---|---|---|
| TEST-01 | Copy cùng chiều, hệ số 0.50 | **DEMO** | Chạy thật 2026-09-06 với `copy_mode = SAME`, hệ số 0.50: Master BUY 0.02 → Client **BUY** 0.01, `effective_multiplier = 0.5`, `reason = 0`. Lặp lại hai lần. Trước đó nhánh `SAME` và phép nhân phân số chưa từng chạm sàn thật. |
| TEST-02 | Copy khác chiều | **DEMO** | Phase 6 và Phase 6b Bước 5: `22:05:02.616` Master buy 0.01 → `22:05:03.819` Client sell 0.01. Journal hai terminal khớp từng cặp. **Chạy lại 2026-09-06 sau khi EA đổi lớn:** Master BUY→Client SELL và Master SELL→Client BUY, 1:1, `reason = 0` cả ba cặp. |
| TEST-03 | Master đóng một lệnh → chỉ đóng đúng cặp đó | **DEMO** | Phase 7: `PAIR-000024` `CLOSED`, `close_source = MASTER`; cặp đối chứng cùng symbol `PAIR-000026` **không bị động tới**. Khoá thêm bằng `test_khong_co_cau_sql_nao_dong_lenh_theo_symbol`. **Chạy lại 2026-09-06:** `PAIR-000013` `CLOSED` sau **272 ms**, đúng một lệnh `CLOSE` cho `71489809`; hai cặp còn lại cùng symbol không bị đụng. |
| TEST-04 | Client đóng, công tắc TẮT | **DEMO** | Phase 7: `PAIR-000025` → `ORPHANED`, `orphan_side = MASTER`, Master giữ nguyên 0.01, alert ERROR `ORPHANED_MASTER`. Journal: `22:51:47.487` Client sell → **không có deal Master nào**. |
| TEST-05 | Client đóng, công tắc BẬT → cascade | **TEST** | `test_cascade_dong_master_va_cac_client_con_lai`. Cần ≥2 Client để cascade có ý nghĩa; cấu hình demo chỉ có một. |
| TEST-06 | Đóng một phần theo tỷ lệ | **DEMO** | Phase 7: `PAIR-000027` Master 0.05→0.03, Client 0.05→**0.03**, `PARTIALLY_CLOSED`. Chính bài này lộ ra lỗi float và buộc chuyển sang `Decimal`. **Chạy lại 2026-09-06:** `PAIR-000014` Master 0.02→0.01, Client 0.02→**0.01**, `CLOSE_PARTIAL` volume đúng 0.01, sau **285 ms**. |
| TEST-07 | Nhiều lệnh cùng symbol, đóng một cái | **DEMO** | Phase 7, `PAIR-000026` là cặp đối chứng cùng symbol không bị đụng. Thêm `test_ba_lenh_dong_cai_o_giua` cho trường hợp ba cặp. **Chạy lại 2026-09-06:** ba cặp cùng `BTCUSD.s`, đóng một cặp không đụng hai cặp kia. |
| TEST-08 | Nhiều symbol đồng thời | **KHÔNG** | **Chặn bởi giới hạn đã biết:** hộp thoại New Order lấy symbol theo chart đang mở, driver chỉ *kiểm tra* rồi từ chối nếu lệch (ComboBox 10331/10325 chưa đo). Mỗi terminal Client hiện copy được **đúng một symbol**. Đã đưa vào `docs/BACKLOG.md` mục B-01. |
| TEST-09 | Khởi động lại EA và Bridge | **DEMO** | Phase 4 mục 6–7: tắt Bridge, giao dịch, bật lại → 8 event tồn về đủ, đúng thứ tự; restart EA → `seq` tiếp từ 15, không reset. Phase 5: gửi lại cùng `command_id` sau khi khởi động lại EA → **không mở lệnh thứ hai**. |
| TEST-10 | Client thiếu margin | **TEST** | `retcode = 10019` **không ép được trên demo**: tài khoản có ~1.000.000 USD. Đường xử lý lỗi được kiểm bằng ép `10014 Invalid volume` trên demo (Phase 5) và bằng test cho `10019`. |
| TEST-11 | Volume tính ra dưới mức tối thiểu | **DEMO** | Chạy thật 2026-09-06: Master 0.01 × 0.5 = 0.005 < mức tối thiểu 0.01 → event `IGNORED` với `ZERO_AFTER_ROUNDING`, alert `VOLUME_BELOW_MIN`, **không** có vị thế Client nào. Không tự nâng volume (D-18). |
| TEST-12 | Đổi hệ số khi có cặp đang chạy | **TEST** | `test_doi_multiplier_giua_chung_khong_lam_lech_cap_dang_chay`. `effective_multiplier` khoá tại lúc mở cặp (D-19). |
| TEST-13 | Master và Client cùng đóng trong 50 ms | **TEST** | `test_moi_cap_chi_mot_lenh_dong_dang_chay`, `test_ack_already_closed_van_la_dong_thanh_cong`. Trên demo có gặp `already_closed` thật (Phase 5) nhưng không dựng được đúng cửa sổ 50 ms. |
| TEST-14 | Close-by để lại phần dư | **TEST** | `test_out_by_de_lai_vi_the_du_thi_bao_unpaired_master`. **Không thể lên DEMO:** broker Connext-Demo không hỗ trợ Close By. D-12 được cài mà không có dữ liệu thực nghiệm — ghi rõ ở đây thay vì để ngầm. |
| TEST-15 | Cascade, Master không phản hồi trong 15 s | **TEST** | `test_cascade_master_khong_phan_hoi_thi_khong_dong_client_khac`. Cùng lý do TEST-05. |
| TEST-16 | Client đóng một phần, công tắc BẬT | **TEST** | `test_client_dong_mot_phan_thi_khong_cascade` (D-11). |
| TEST-17 | Client offline lúc Master mở, rồi nối lại | **DEMO** | Phase 8: dựng sai lệch thật (`run_mode = PAUSED`, người dùng đóng tay Master `71489357`), vòng đối chiếu tự chạy khi agent nối lại và sinh đúng một finding `MASTER_CLOSED_OFFLINE` với đủ ba nguồn bằng chứng. Mặc định `offline_reopen_policy = NONE`: không mở bù (D-13). |
| TEST-18 | Terminal mất kết nối broker, EA vẫn sống | **DEMO** | Phase 4 mục 8: xảy ra **thật** lúc `11:44:39` → `broker_connected = false`, agent `DEGRADED`, alert ERROR. Không phải tình huống dựng ra. |
| TEST-19 | Mất điện đột ngột máy Bridge | **KHÔNG** | Máy đo là laptop cá nhân của người vận hành; rút điện thật không thực hiện được ở đây. `synchronous = FULL` và `journal_mode = WAL` đã bật và có test (`test_repo.py`), nhưng đó là *cấu hình đúng*, không phải *bằng chứng chịu được mất điện*. Ghi vào `RUNBOOK.md` là việc **phải làm trước khi dùng tiền thật**. |
| TEST-20 | Symbol không tồn tại trên sàn Client | **TEST** | Kiểm ở tầng cấu hình (`symbol_spec` phải có symbol thì mới lưu được ánh xạ) — `test_sizing.py`, `test_dashboard.py`. Trên demo có gặp ca "symbol không tồn tại → ack lỗi, không sập EA" (Phase 5). |
| TEST-21 | Nút đóng khẩn cấp | **DEMO** | Chạy thật 2026-09-06 **sau khi sửa F-01 và cấp khả năng đóng cho EA Master**: 2 cặp đang hedge → bấm nút → `master_position` còn OPEN = **0**, hai lệnh `CLOSE` tới `AG-MASTER` đều `ACK_OK` (10009). Thứ tự đúng: Client 06:49:19.179, Master 06:49:20.304. Toàn bộ 1.125 ms. **Chạy lại 2026-09-06:** `master_position` OPEN = 0, hai lệnh đóng Master `ACK_OK`, Client 09:30:46.005 trước Master 09:30:46.598, toàn bộ 1.101 ms. **Đo lại 2026-09-11 sau khi đường đóng chuyển sang giao diện, 3 cặp:** toàn bộ **14,5 giây** (3 lệnh `CLOSE_UI` tuần tự, 4,6–13,6 giây mỗi lệnh), Master tạo lúc `06:28:17.341` — **148 ms sau** khi Client cuối cùng ack lúc `06:28:17.193`. Lần chạy **đầu** lộ ra lỗi đua khiến Master đóng **trước** Client 13 giây; xem `PROGRESS.md`. |
| TEST-22 | `PAUSE_NEW_ENTRIES` | **DEMO** | Chạy thật 2026-09-06, cả hai vế: mở lệnh Master → `IGNORED` vì `run_mode = PAUSE_NEW_ENTRIES`, không sinh cặp; rồi Master đóng → Client đóng theo sau **336 ms**. |
| TEST-23 | **Mọi deal** của bot trên Client mang `DEAL_REASON_CLIENT`, cả `entry = IN` lẫn `entry = OUT` | **DEMO** | Truy vấn tự động, không nhìn bằng mắt: `python -m bridge.admin kiem-reason` → **`TEST-23 DAT: 25/25`** trên database thật ngày 2026-09-06. Hai cặp `OPEN_FAILED` có `client_open_reason IS NULL` (chưa từng mở được vị thế nào) nên không tính. Tiền đề đã kiểm riêng ở Phase 6b mục E3: cùng tài khoản 538217, 13 deal do EA đặt đều `EXPERT (3)`, 5 deal đặt tay đều `CLIENT (0)` — chứng minh trường này **thật sự phân biệt được hai kênh**. **Chạy lại 2026-09-06 sau khi EA đổi: 40/40.** **Mở rộng sau khi đường ĐÓNG chuyển sang giao diện:** `kiem-reason` nay soi **cả** `client_open_reason` lẫn `client_close_reason`. Chỉ soi cột mở sẽ cho một kết quả "ĐẠT" hoàn toàn thật mà vẫn bỏ sót đúng nửa số deal — nửa mà yêu cầu này nhắm tới. **Chưa chạy lại trên demo sau thay đổi.** |
| TEST-24 | Clicker mất khả năng điều khiển giao diện | **DEMO** | Phase 6b diễn tập 4: canary báo đỏ → clicker `DEGRADED` → **0** command `OPEN_UI`, **0** command `OPEN`, 0 pair mới, alert `CLICKER_NOT_AVAILABLE`. Không rơi về đường EA (D-25). |
| TEST-25 | Giết clicker giữa lúc giữ chỗ và bấm, gửi lại cùng `command_id` | **DEMO** | Phase 6b diễn tập 1: ack `unknown`, command `TIMEOUT`, driver **được gọi lại 0 lần**, nhật ký ghi `clicked=None, ack=None` — bằng chứng chắc chắn chưa bấm. Không có lệnh thứ hai. |
| TEST-26 | Đóng hẳn qua giao diện | **DEMO** | Chạy thật 2026-09-10: Master đóng `72281114` → cặp `CLOSED` sau **5.122 ms**, `client_close_reason = **0**`, lệnh `CLOSE_UI` tới `AG-CLICKER`. Cặp đối chứng cùng symbol **không bị đụng**, và một vị thế **người dùng mở tay** (`72205853`) nằm ngay cạnh trong tab Trade cũng **còn nguyên** — bố trí có chủ đích để vị thế cần đóng không bao giờ nằm ở dòng 0. Không alert nào. |
| TEST-27 | Đóng một phần qua giao diện | **DEMO** | Chạy thật 2026-09-10 trên vị thế `0.04`: `CLOSE_UI_PARTIAL` volume `0.01`, MT5 đóng **đúng `0.01`** (`volume_after = 0.03`), `reason = 0`, **5.929 ms**. **Ẩn số lớn nhất đã được trả lời:** bài học `WM_CHAR` có áp cho hộp thoại đóng; bẫy `WM_SETTEXT` của phase 6b **không** tái diễn. Lần chạy đầu lộ ra lỗi sổ sách `client_current_volume` đứng yên (xem `PROGRESS.md`); đã sửa và đo lại đạt. |
| TEST-28 | Clicker chết giữa chừng, Master đóng | **DEMO** | Chạy thật 2026-09-10: tắt clicker → Master đóng → lệnh `CLOSE` tới `AG-CLIENT`, vị thế Client **vẫn đóng được** trong **342 ms**, alert CRITICAL `CLOSE_FELL_BACK_TO_EA`, `client_close_reason = 3`, và **không** kèm `UI_CLOSE_REASON_MISMATCH`. |
| TEST-29 | Bộ tương quan đóng với `can_close_master = 1` | **DEMO** | Chạy thật 2026-09-11, **cả hai chiều**. *Bot đóng:* Master đóng → đúng **2** lệnh cho cặp (`OPEN_UI` + `CLOSE_UI`), **0** lệnh `CLOSE` tới `AG-MASTER`, **0** alert — không cascade. *Người dùng đóng tay:* đóng vị thế Client bằng tay → **1** lệnh `CLOSE` tới `AG-MASTER` `ACK_OK` trong 363 ms, alert `CASCADE_STARTED`. Hai event **giống hệt nhau** từ phía EA (`caused_by_command_id = NULL` cả hai) mà Bridge phân biệt đúng cả hai. |

---

## Hai mục KHÔNG đạt, và điều đó có ý nghĩa gì

**TEST-08 (nhiều symbol)** là mục nghiêm trọng nhất, vì "nhiều symbol đồng thời" nằm trong phạm
vi MVP ở `plan/00` mục 2. Hệ thống hiện chạy đúng nhưng **hẹp hơn phạm vi đã tuyên bố**. Không
phải lỗi tiềm ẩn: driver *từ chối* khi symbol lệch thay vì đặt nhầm, nên chế độ hỏng ở đây là
"không copy và có cảnh báo", không phải "copy sai symbol".

**TEST-14 (close-by)** sẽ không bao giờ lên DEMO với broker này. Nếu chuyển sang broker khác,
đây là bài đầu tiên phải chạy lại.

**TEST-19 (mất điện)** là mục duy nhất mà việc không chạy được để lại **rủi ro chưa đo**: toàn
bộ lập luận về mất điện hiện dựa vào cấu hình SQLite chứ không dựa vào quan sát.

## Kiểm thử tải (plan 10.5)

| Bài | Kết quả |
|---|---|
| Bơm 10.000 event | Nhận 809–831 event/s, xử lý 909–953 event/s, **0 event tồn**, không mất event. |
| WAL không phình vô hạn | 4.144.752 byte → **0 byte** sau `wal_checkpoint(TRUNCATE)`. |
| 5 Client cùng lúc | Một lệnh Master → **5 pair** với 5 `client_position_id` phân biệt theo cặp `(client_id, client_position_id)`; đóng Master → **cả 5 đóng**, đúng 5 command `CLOSE`. |

Chạy bằng `pytest -m cham`. Bài **24 giờ liên tục chưa chạy** — xem `RUNBOOK.md`.

## Bộ test tự động

**524 test xanh** (`pytest -m "not cham"`) + **3 test tải**, `ruff` sạch, ngày 2026-09-06.
