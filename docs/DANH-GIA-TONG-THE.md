# Đánh giá tổng thể và rà soát độc lập

*Thực hiện ngày 2026-09-06, sau khi Phase 10 hoàn tất (commit `2a77989`). Kiểm toán độc lập:
không sửa một dòng code nào. Mọi kết luận neo vào code (`file:dòng`), database thật
`data/bridge.db`, hoặc quan sát trực tiếp trên hai terminal demo 538216 / 538217.*

---

# PHẦN A — SẴN SÀNG CHẠY TIỀN THẬT CHƯA

## Kết luận: **NO-GO.**

Không phải vì những mục còn thiếu đã biết (Tailscale, dịch vụ Windows, TEST-19). Mà vì lượt kiểm
toán này tìm ra **ba lỗi đang hoạt động**, trong đó một lỗi khiến **nút dừng khẩn cấp không làm
được việc của nó** — và cả ba đều nằm ngoài mọi danh sách hiện có.

Phần mềm này chạy đúng trong luồng bình thường: 27 cặp lệnh trên demo, độ trễ ổn định, không mở
trùng, không đóng nhầm cặp. Vấn đề nằm ở các đường **bất thường** — đúng những đường chỉ chạy khi
đã có sự cố.

## Ba rủi ro mới lộ ra trong lượt này

### F-01 — Nút đóng khẩn cấp không đóng phía Master. **Nghiêm trọng nhất.**

`emergency_close_all()` (`bridge/engine/closing.py:496-515`) có docstring ghi *"Đóng toàn bộ cặp
đang quản lý: **Client trước, Master sau**"*, và alert CRITICAL nó phát ra cũng nói y hệt. Nhưng
trong thân hàm **không có một dòng nào gửi lệnh đóng cho Master.** Vòng lặp gửi `CLOSE` cho Client
rồi kết thúc.

Đo trực tiếp lúc 05:30:33 hôm nay:

```
POST /api/emergency          -> {"ok":true,"closed":3}
pair PAIR-20260906-000001    -> status=CLOSED, master_current_volume=0.0
master_position 71489729     -> status=OPEN,   current_volume=0.02   <-- van con mo
lenh CLOSE gui cho AG-MASTER -> 0   (trong TOAN BO lich su database)
```

Con số cuối là bằng chứng mạnh nhất: **trong suốt vòng đời dự án, Bridge chưa từng một lần gửi
lệnh đóng nào cho Master.**

Hậu quả: bấm nút dừng khẩn cấp trên một sổ đang hedge đầy đủ sẽ **cắt sạch một chân hedge và để
nguyên chân kia**, biến trạng thái an toàn thành trạng thái phơi nhiễm một chiều. Sổ sách ghi
`CLOSED`, `master_current_volume = 0.0`, nên cả danh sách cặp lẫn bộ đối chiếu đều không còn coi
đó là việc phải xử lý. Người vận hành nhận alert CRITICAL nói rằng đã đóng "Client trước Master
sau" và tin rằng mình đã an toàn.

Chứng thực từ phía ngược lại: khi vị thế Master bị bỏ lại được đóng tay lúc 05:34:47, Bridge ghi
`Vi the Master khong thuoc cap nao` — nó đã quên hẳn vị thế đó.

**Vì sao 484 test không bắt được:** `tests/test_close_flow.py:486`
`test_emergency_dong_het_client_truoc` chỉ khẳng định `so == 2`, cặp về `CLOSED`, và có alert.
Nó **không kiểm gì về phía Master**. Tên test hứa "Client trước" — hàm ý "Master sau" — nhưng
không có dòng nào kiểm vế sau. Đây là một test đang **khoá lại chính khiếm khuyết**.

**Cách biết đã sửa xong:** sau khi bấm khẩn cấp, `SELECT COUNT(*) FROM master_position WHERE
status='OPEN'` phải bằng 0, và phải có `CLOSE` gửi tới `AG-MASTER` cho từng cặp.

### F-02 — Dashboard không xác thực với cấu hình mặc định

`can_dang_nhap()` (`bridge/web/app.py:57-64`) trả `False` khi chưa đặt mật khẩu, và khi đó
`hop_le()` (dòng 75-78) trả `True` cho **mọi** request, kể cả không có cookie. Cơ chế này là có
chủ đích và có ghi chú. Vấn đề là **mặc định**: `config.example.toml` ship
`dashboard_password = ""`, `host = "0.0.0.0"`, và toàn bộ mục 6 của `RUNBOOK.md` (Tailscale ACL,
firewall) còn nguyên chưa tick.

Đo trực tiếp — gọi **không kèm cookie, không đăng nhập**:

```
curl -X POST -d {"phrase":"DONG TAT CA"} http://127.0.0.1:8080/api/emergency
-> HTTP 200  {"ok":true,"closed":3}
```

Ai đi tới được cổng 8080 đều đóng được toàn bộ vị thế và đổi được `run_mode`. Làm đúng theo
RUNBOOK mục 2 sẽ ra đúng cấu hình này.

**Cách biết đã sửa xong:** gọi `/api/emergency` không cookie phải trả 401; hoặc từ chối khởi động
khi `host` không phải loopback mà `dashboard_password` rỗng.

### F-03 — Clicker rơi OFFLINE vì biên heartbeat bằng 0

`clicker/link.py:35` `DEFAULT_HEARTBEAT_SEC = 5.0`. `system_config.heartbeat_timeout_ms = 5000`.
Chu kỳ gửi **bằng đúng** ngưỡng hết hạn, nên bất kỳ chậm trễ nào cũng vượt ngưỡng. EA thì gửi mỗi
`1000` ms với cùng ngưỡng 5000 — biên gấp 5 lần. Chỉ riêng clicker là không có biên.

Quan sát trực tiếp trong phiên ~10 phút hôm nay: alert #37 `AGENT_OFFLINE` cho `AG-CLICKER` lúc
05:32:37, sau đó tự ONLINE lại.

Điều này quan trọng vì **D-25**: clicker không `ONLINE` thì Bridge từ chối gửi `OPEN_UI` — tức là
**ngừng copy**. Một cú nhấp nháy trạng thái là một cửa sổ mất copy, kèm alert
`CLICKER_NOT_AVAILABLE`. Đây không phải lỗi thiết kế D-25; cổng đó đúng. Đây là tham số sai làm
cổng đúng bị kích hoạt nhầm.

**Cách biết đã sửa xong:** chạy 1 giờ liên tục, số alert `AGENT_OFFLINE` của `AG-CLICKER` bằng 0.

## Rủi ro đã biết nhưng **chưa đo** (giữ nguyên từ trước)

| | Vì sao quan trọng | Cách biết là đã thoả |
|---|---|---|
| **TEST-19 — chưa từng rút điện thật** | Toàn bộ lập luận "không mất event" dựa vào `synchronous = FULL`, tức *cấu hình đúng*, không phải *quan sát*. | Rút điện giữa lúc có lệnh đang bay; sau khi bật lại, event khớp journal và đối chiếu bắt đúng sai lệch. |
| **Mục 6 RUNBOOK chưa tick dòng nào** | Tailscale ACL, firewall, dịch vụ Windows, Scheduled Task cho clicker. F-02 biến mục này từ "nên làm" thành "phải làm trước". | Máy thứ ba không chạm được 8787/8080. |
| **Chưa chạy 24 giờ** | Rò rỉ bộ nhớ và tốc độ tăng DB chỉ lộ sau nhiều giờ. F-03 cho thấy loại lỗi chỉ hiện theo thời gian là có thật. | 24 giờ liên tục, bộ nhớ không tăng đều. |
| **Chưa gửi tin Telegram thật lần nào** | Đường gửi có test với sender giả, nhưng chưa tin nào tới điện thoại. | Ép một alert CRITICAL, thấy tin trên máy. |
| **B-01 — mỗi terminal Client chỉ copy một symbol** | Hẹp hơn phạm vi MVP ở `plan/00` mục 2. | Đo ComboBox 10331/10325 rồi chạy hai symbol đồng thời. |
| **Cascade và nhiều Client chưa chạy trên demo** | TEST-05, TEST-15 chỉ có test tự động. F-01 cho thấy đường đóng phía Master là đường yếu nhất, mà cascade chính là đường đó. | Dựng 2 Client thật, bật `can_close_master`. |

## Rủi ro **đã đo** và chấp nhận được

- Không mở trùng: chứng minh trên demo qua khởi động lại EA và gửi lại cùng `command_id`.
- Không đóng nhầm cặp: tra theo `position_id`, có cặp đối chứng cùng symbol, khoá thêm bằng
  `test_khong_co_cau_sql_nao_dong_lenh_theo_symbol`.
- `DEAL_REASON_CLIENT`: `python -m bridge.admin kiem-reason` → **27/27** sau lượt này.
- Chống vòng lặp đóng (D-08): quan sát live, event đóng phía Client bị `IGNORED` với lý do
  `Do bot gay ra, khong lan truyen`.
- Độ trễ ổn định: mở **662 ms**, đóng **336 ms** đo hôm nay, khớp mốc cũ (604 ms / 400–460 ms).

## Điều kiện tối thiểu để chuyển sang GO

Xếp theo rủi ro, không theo độ dễ:

1. Sửa **F-01** và thêm test kiểm phía Master. Đây là điều kiện chặn.
2. Sửa **F-02**, rồi hoàn thành mục 6 `RUNBOOK.md`.
3. Sửa **F-03**.
4. Trả lời dứt điểm **F-04** (lệch hợp đồng D-19) — sửa code hoặc sửa quyết định.
5. Chạy **TEST-19** thật.
6. Chạy 24 giờ liên tục, gửi được tin Telegram thật.
7. Chạy lại toàn bộ nghiệm thu sau khi sửa; riêng TEST-21 phải đạt cả vế Master.
8. Rồi mới tới điều kiện cũ: một tuần ổn định trên demo, đọc điều khoản broker, bắt đầu bằng
   volume nhỏ nhất và một symbol.

---

# PHẦN B — CHẤT LƯỢNG KỸ THUẬT VÀ NỢ KỸ THUẬT

## Kiến trúc: chỗ vững và chỗ sẽ vỡ

**Vững.** Tách EA mỏng / Bridge dày (D-01) được giữ nghiêm: `ea/` 2.136 dòng và không chứa một
phép tính volume nào. Khung NDJSON có lập luận đúng về việc JSON hợp lệ luôn escape newline.
Idempotency ghi nhật ký trước khi hành động. Đường đóng tra theo `position_id` chứ không theo
symbol, và có test cấu trúc khoá lại điều đó. `tests/test_ea_protocol_contract.py` grep thẳng mã
nguồn MQL5 để đối chiếu với schema Pydantic — đây là thứ hiếm và thật sự có giá trị, vì nó bắt
được lệch EA↔Bridge mà không cần terminal.

**Sẽ vỡ.** Các đường **sự cố** không được đối xử ngang hàng với đường bình thường. F-01 là ví dụ
rõ nhất: hàm quan trọng nhất trong tình huống xấu nhất lại là hàm ngắn nhất và ít test nhất.
Tương tự, `_soi_lech_volume` — bộ dò lệch volume duy nhất — bị tắt đúng trên những cặp có thể
lệch (F-05). Mẫu chung: cơ chế được viết ra, được đặt tên đúng, được ghi chú kỹ, nhưng **nhánh
cuối cùng thì thiếu**, và không có test nào đi tới nhánh đó.

## Chất lượng test: tốt hơn trung bình, nhưng có điểm mù hệ thống

Không có "test theater" theo nghĩa test khẳng định chính mock của nó. `MockAgent` (437 dòng) ép
được `retcode`, cắt kết nối, bơm byte thô — đủ để dựng kịch bản thật. Bộ test bắt được sai số
float, lỗi khuếch đại gửi bù, trạng thái ONLINE cũ.

Ba điểm yếu cụ thể:

1. **Test khoá khiếm khuyết.** `test_emergency_dong_het_client_truoc` — xem F-01. Đây là loại
   nguy hiểm nhất vì nó tạo cảm giác đã kiểm.
2. **Khẳng định dừng ở nửa đường.** Nhiều test đóng chỉ kiểm `pair.status` — mà `pair.status` do
   chính ack của Client quyết định. Không test nào kiểm `master_position` sau khi đóng. Đó chính
   là khe hở F-01 chui qua.
3. **Hệ số 1.0 che mất cả một lớp lỗi.** Phần lớn test dùng `volume_multiplier` 1.0, khi đó
   "tỷ lệ trên volume còn lại" và "`effective_multiplier` đã khoá" cho **kết quả giống hệt nhau**
   — nên F-04 không thể lộ ra. Hôm nay chạy hệ số 0.5 trên demo là lần đầu nhánh đó chạm sàn thật.

484 test xanh **sau khi** đã tìm ra F-01. Con số test không phải thước đo an toàn.

## F-04 — Lệch hợp đồng D-19 (theo quy tắc 2: báo cáo, không tự chọn hướng)

D-19 nói: *"`effective_multiplier` được khoá tại thời điểm mở cặp và **dùng cho mọi phép tính đóng
một phần về sau**"*.

Thực tế `bridge/engine/closing.py:250-253`:

```python
con_lai = to_decimal(pair["client_current_volume"] or 0.0)
ty_le   = to_decimal(delta) / to_decimal(truoc)      # ty le Master dong
can_dong = round_to_step(con_lai * ty_le, step, "DOWN")
```

`effective_multiplier` **không xuất hiện trong đường đóng**. Toàn dự án nó chỉ được *ghi* lúc tạo
cặp và được *đọc* đúng một chỗ: `reconcile.py:350`, tức bộ dò lệch. Nghĩa là **bộ thực thi và bộ
kiểm tra đang dùng hai công thức khác nhau**.

Hai công thức trùng nhau khi không có làm tròn, nhưng lệch khi có. Mô phỏng bằng chính
`round_to_step` của dự án (Master 1.00, hệ số 0.5, step 0.01, đóng 0.25 ba lần):

```
dang cai (ty le tren con lai) -> Client con 0.130
theo chu D-19 (delta x he so) -> Client con 0.140
ly tuong                      -> 0.125
```

Bản đang cài **gần lý tưởng hơn** vì nó tự hiệu chỉnh phần dư tích luỹ. Nhiều khả năng nó **đúng
hơn** chữ của D-19. Nhưng đó là quyết định thuộc về bạn, không thuộc về tôi — nên tôi dừng ở đây
và báo cáo. Phase 10 đã ghi D-19 là "khớp", dẫn chứng "`effective_multiplier` khoá lúc tạo pair",
tức chỉ kiểm nửa đầu của quyết định và bỏ qua nửa sau.

Một hệ quả phụ đáng lo hơn, mô phỏng cho thấy: Master 1.00 hệ số 0.5, đóng 0.01 hai mươi lần liên
tiếp → Client **không đóng một lần nào** (mỗi lần 0.005 → làm tròn xuống 0), Master về 0.80 trong
khi Client vẫn 0.50. Alert `PARTIAL_CLOSE_ROUNDS_TO_ZERO` nói *"phần lệch tích luỹ lại"*, nhưng
không có cơ chế nào **giải phóng** phần tích luỹ đó, và nó ở mức WARNING.

## F-05 — Cặp `ORPHANED` không bao giờ được đối chiếu lại

`LIVE_STATUSES` (`reconcile.py:44`) cố ý loại `ORPHANED`, với lý do hợp lý: tránh đẻ finding trùng
cho việc người ta đã biết. Hệ quả không lường: **một khi đã `ORPHANED` thì cặp đó không bao giờ
được xem lại**. Khi người vận hành xử lý xong trên terminal, sổ sách không bao giờ được cập nhật.

Chứng minh bằng đối chứng có sẵn trong DB thật — hai cặp, **cùng một tình huống ngoài đời** (cả
hai vị thế Master đều đã đóng tay):

| Cặp | Trạng thái sổ sách | Có trong `LIVE_STATUSES`? | Đối chiếu phát hiện? |
|---|---|---|---|
| `PAIR-20260905-000027` | `PARTIALLY_CLOSED` | có | **có** — finding #2 `BOTH_CLOSED` |
| `PAIR-20260905-000025` | `ORPHANED` | **không** | **không có gì**, suốt từ 05-09 |

`ORPHANED` là trạng thái *chờ người can thiệp* — tức đúng lúc sắp có thay đổi ngoài đời, hệ thống
lại ngừng quan sát.

## F-06 — "0 sai lệch" nghĩa là "0 finding **mới**"

`reconcile.py:106-111` cố ý đếm số dòng ghi trong vòng chạy này, vì cổng chống trùng ở
`_create_finding` có thể đã bỏ bớt. Nhưng câu log và alert đều đọc là *"phát hiện N sai lệch giữa
sổ sách và thực tế"*.

Quan sát lúc 05:25:57 hôm nay: cả hai terminal báo **0 vị thế**, DB có 2 cặp còn "đang mở" và một
finding `PENDING` chưa ai xử lý, log ghi:

```
Doi chieu REC-20260906-052557-120 (AGENT_ONLINE): 0 sai lech
```

Người vận hành đọc dòng này sẽ kết luận sổ sách khớp thực tế. Thực tế là **2/2 cặp đều sai**.

## F-07 — Mức alert không nhất quán cho cùng một hậu quả

Phase 10 nâng `UI_OPEN_BUSY` từ WARNING lên ERROR với lập luận đúng: bỏ một lệnh copy là mất
hedge, mà chỉ ERROR trở lên mới ra được Telegram. Lập luận đó không được áp cho các trường hợp
cùng hậu quả:

| Mã | Hậu quả | Mức | Quan sát |
|---|---|---|---|
| `UI_OPEN_BUSY` | bỏ một lệnh copy | ERROR | đã sửa ở Phase 10 |
| `VOLUME_BELOW_MIN` | **bỏ một lệnh copy** | WARNING | alert #32 hôm nay |
| `PARTIAL_CLOSE_ROUNDS_TO_ZERO` | phần đóng bị bỏ, lệch tích luỹ | WARNING | xem F-04 |
| `RECONCILE_FINDINGS` | sổ sách lệch thực tế | WARNING | alert #33/34/36 hôm nay |
| `KHOI_DONG_EP_PAUSED` | **đã ngừng copy hoàn toàn** | WARNING | alert #31 hôm nay |

Dòng cuối là chỗ nghịch lý nhất: D-15 tồn tại cho tình huống *máy tự bật lại lúc 3 giờ sáng khi
không ai nhìn màn hình* — và đúng trong tình huống đó, alert ở mức không gửi đi đâu cả.

## F-08 — Finding `PENDING` bị bỏ quên, không có gì nhắc lại

Finding #2 ở trạng thái `PENDING` từ 03:57:43 ngày 06-09. Cả phiên Phase 10 chạy sau đó không ai
nhìn tới. Hiện có **4 finding `PENDING`**. Không có cơ chế nhắc lại, và alert duy nhất báo về
chúng ở mức WARNING (F-07).

## Phát hiện nhỏ

- **F-09** — `ACCEPTANCE.md` tự tuyên bố *"DEMO 13 · TEST 9 · KHÔNG 3"* trong khi đếm chính bảng
  của nó ra **DEMO 11 · TEST 12 · KHÔNG 2**. Bản tự khai **phóng đại số mục đã chạm sàn thật thêm
  2 mục** và giảm số mục chưa từng chạm sàn đi 3.
- **F-10** — `/api/emergency` trả `{"closed": N}` với `N = len(pairs)` là *số cặp được xét*, không
  phải số cặp đóng được. Hôm nay trả `closed: 3` trong khi hai trong ba cặp vốn đã đóng từ trước.
- **F-11** — Test canh gác D-16 (`tests/test_labels.py`) chỉ quét `bridge/`, không quét `clicker/`.
  Hiện `clicker/` có 0 vi phạm nên đây thuần là rủi ro hồi quy.
- **F-12** — Không có lệnh nào đổi được `copy_mode` / `volume_multiplier`. Để chạy TEST-01 tôi phải
  `UPDATE` thẳng vào DB. Đây là cái giá thật của B-05, và nó cao hơn mức "trang cấu hình mới ở mức
  đọc" gợi ý.
- **Không phải lỗi:** `canary_at = last_seen_at if broker_connected` thoạt nhìn giống như đang hiển
  thị giờ heartbeat thay vì giờ canary. Kiểm `clicker/link.py:79-83,156-160` cho thấy clicker chạy
  probe giao diện **thật** ở mỗi nhịp heartbeat rồi đặt kết quả vào `broker_connected`, nên ngữ
  nghĩa là đúng.

## Đối chiếu D-01…D-26 với code

**Khớp, có điểm neo cụ thể (24/27):** D-01 (`ea/` không có phép tính volume) · D-02
(`framing.py:1-12`) · D-03 (`server.py:147`) · D-04 (`repo.py:30-35`) · D-05 (dashboard không tham
chiếu ra ngoài) · D-06 (`CopyBridgeCommon.mqh:1321,1480`) · D-07b (`processor.py:63` `open_tag_for`,
tra `(client_id, client_position_id)`) · D-08 (`closing.py:102,292`) · D-09/D-10
(`closing.py:373-401`, `DEFAULT_CASCADE_WAIT_MS = 15000`) · D-11 (`closing.py:301`) · D-12
(`closing.py:125`) · D-13 (`reconcile.py:476-484`, mặc định `NONE`) · D-14
(`CopyBridgeCommon.mqh:1525`, `closing.py:88-90`) · D-17 (`retention.py` chỉ đụng `event` và
`command`) · D-18 (`sizing.py:114` `ROUND_FLOOR`) · D-20 (`schema.sql:65` `DEFAULT 0`) · D-21/D-22
(`schema.sql:251-255`, `OPEN_UI` là loại riêng) · D-23 (`processor.py:729,818` — nhiều ứng viên thì
không đoán) · D-24 (`processor.py:712-715`; `flush_pending` chỉ gửi lại `PENDING`, không có đường
gửi lại cái đã `SENT`) · D-25 (`processor.py:652`) · D-26 (`win32.py:44` `MENU_NEW_ORDER = 32848`,
`dialog.py:88`).

**Hai bản sửa của Phase 10 — kiểm lại: cả hai đúng.**

- **D-15** đúng, và xác minh được **trên đường chạy thật** chứ không chỉ bằng unit test. Đặt
  `run_mode = RUNNING` rồi khởi động Bridge, log ghi:
  `run_mode dang la RUNNING, da dat ve PAUSED (D-15)`. Kèm theo, `BridgeServer.start()` đánh 2
  agent về `OFFLINE` đúng như thiết kế. Chỉ vướng mức alert — xem F-07.
- **D-16** đúng. Test canh gác quét AST thật sự chặt, chỉ soi đối số chuỗi của `log.*` và
  `create_alert`. Phạm vi còn thiếu `clicker/` — xem F-11.

**Lệch: 1/27** — D-19, xem F-04.

## Đối chiếu plan với thực tế

Không tìm thấy mục nào của plan bị bỏ mà không ai ghi lại. Tài liệu lạc hậu còn hai chỗ, đều vô
hại: `plan/01` và `plan/10` vẫn viết "D-01…D-20" (hợp đồng nay là 26 + D-07b), và `plan/07` vẫn
lấy mốc hồi quy "383 test". Đây là file đặc tả lịch sử nên lạc hậu là bình thường; ghi lại để
không ai dùng chúng làm mốc.

`docs/BACKLOG.md` (B-01…B-07) mô tả **trung thực**, không có món nào là lỗi đang hoạt động bị đặt
tên nhẹ đi. Cần bổ sung F-01, F-02, F-03 vào đó với mức cao hơn toàn bộ B-01…B-07 hiện có.

---

## Bảng "test và thực tế"

Mỗi giả định quan trọng, nơi nó được mã hoá, và nó đã được sàn thật xác nhận chưa.

| Giả định | Mã hoá ở | Đã xác nhận trên sàn thật? | Bằng chứng |
|---|---|---|---|
| Lệnh mở qua giao diện mang `DEAL_REASON_CLIENT` | `test_ui_open_flow.py` | **Rồi** | `kiem-reason` → 27/27 (2026-09-06) |
| `WM_CHAR` mới đổi được trạng thái nội bộ MT5, `WM_SETTEXT` thì không | `win32.py` + chú thích | **Rồi**, đo ở phase 6b | 10/10 lệnh đúng volume |
| Copy **cùng chiều** với hệ số **phân số** | `test_sizing.py`, `test_open_flow.py` | **Rồi — lần đầu hôm nay** | `SAME`/0.5: Master BUY 0.02 → Client BUY 0.01, `em = 0.5`, hai lần |
| Volume dưới tối thiểu thì bỏ lệnh, không tự nâng (D-18) | `test_sizing.py` | **Rồi — lần đầu hôm nay** | 0.01 × 0.5 = 0.005 → `ZERO_AFTER_ROUNDING`, không có vị thế Client |
| `PAUSE_NEW_ENTRIES` chặn mở nhưng vẫn đồng bộ đóng | `test_close_flow.py:460` | **Rồi — lần đầu hôm nay** | Master mở → `IGNORED`; Master đóng → Client đóng sau **336 ms** |
| Chống vòng lặp đóng bằng `caused_by_command_id` | `test_close_flow.py` | **Rồi** | event Client đóng → `Do bot gay ra, khong lan truyen` |
| Đóng khẩn cấp đóng **cả hai** phía | `test_close_flow.py:486` | **KHÔNG — và thực tế bác bỏ** | F-01: 0 lệnh đóng nào tới Master |
| Đóng một phần dùng `effective_multiplier` đã khoá (D-19) | không nơi nào | **Không** | F-04: code dùng công thức khác |
| Đối chiếu bắt được sổ sách lệch thực tế | `test_reconcile.py` | **Một phần** | Bắt `PARTIALLY_CLOSED`, mù với `ORPHANED` (F-05) |
| Cascade đóng Master rồi mới sang Client khác | `test_close_flow.py:362` | **Không** | Cần ≥2 Client; chưa từng chạy trên demo |
| Close-by để lại phần dư | `test_close_flow.py:566` | **Không thể** | Broker Connext-Demo không hỗ trợ Close By |
| Thiếu margin → xử lý đúng | `test_client_execution.py` | **Không thể** | Demo có ~1.000.000 USD, không ép được `10019` |
| Không mất event khi mất điện | cấu hình `synchronous = FULL` | **Không** | Chưa từng rút điện thật |

## Bảng ACCEPTANCE sau lượt này

Xuất phát từ **số đếm thật** của bảng (DEMO 11 · TEST 12 · KHÔNG 2), không phải từ dòng tổng kết
sai trong file (xem F-09).

| Mã | Trước | Sau | Vì sao đổi |
|---|---|---|---|
| TEST-01 | TEST | **DEMO** | `SAME` hệ số 0.5 chạy thật hai lần, Client đúng chiều và đúng 0.01 |
| TEST-11 | TEST | **DEMO** | 0.005 dưới mức tối thiểu → bỏ lệnh, có alert, không nâng volume |
| TEST-22 | TEST | **DEMO** | Cả hai vế: chặn mở mới, vẫn đồng bộ đóng (336 ms) |
| TEST-21 | TEST | **KHÔNG ĐẠT** | F-01 — đóng khẩn cấp không đóng phía Master |
| TEST-03 | DEMO | DEMO | Kiểm chứng lại độc lập hôm nay, vẫn đạt |
| TEST-23 | DEMO | DEMO | Kiểm chứng lại: 27/27 |

**Tổng kết mới: DEMO 14 · TEST 8 · KHÔNG 3.**

TEST-21 chuyển sang KHÔNG ĐẠT là thay đổi quan trọng nhất trong bảng: trước lượt này nó được ghi
là "đã khoá bằng test", và niềm tin đó không có cơ sở.

---

## Đã làm gì trên demo và trong DB

**5 lệnh Master đặt qua hộp thoại New Order** (ngân sách 15, không vượt):

| Giờ | Lệnh | Kết quả |
|---|---|---|
| 12:28:20 | BUY 0.02 | `PAIR-20260906-000001`, Client BUY 0.01 — TEST-01 |
| 12:28:44 | BUY 0.01 | Không copy, `ZERO_AFTER_ROUNDING` — TEST-11 |
| 12:29:16 | SELL 0.02 | Không copy, `run_mode = PAUSE_NEW_ENTRIES` — TEST-22 |
| 12:30:33 | *(bấm đóng khẩn cấp)* | Đóng 3 cặp phía Client — TEST-21, lộ F-01 |
| 12:32:00 | BUY 0.02 | `PAIR-20260906-000002`, Client BUY 0.01 |
| 12:34:31 | *(người dùng đóng tay)* | Client đóng theo sau 336 ms — TEST-03/22 |

**Thay đổi trong DB, đã hoàn nguyên hết:**

- `client_account`: `OPPOSITE`/1.0 → `SAME`/0.5 → **đã trả về `OPPOSITE`/1.0**.
- `run_mode`: PAUSED → RUNNING → PAUSE_NEW_ENTRIES → EMERGENCY → **đã trả về `PAUSED`**.
- Cấp token mới cho `AG-CLICKER` để chạy phiên đo, **đã thu hồi** sau khi xong. Lần dùng tới phải
  cấp lại bằng `python -m bridge.admin cap-token AG-CLICKER`.
- Sao lưu trước khi bắt đầu: `data/backup/bridge-20260906-052444.db`.

**Dữ liệu mới sinh ra, cố ý giữ lại làm bằng chứng:** 2 cặp mới (đều `CLOSED`), 7 alert (#31–#37),
3 finding `UNPAIRED_MASTER` — chính là ba vị thế Master mà nút khẩn cấp bỏ lại.

**Trạng thái để lại:** `run_mode = PAUSED`; Bridge và clicker đã tắt; hai terminal demo **không
còn vị thế nào**; 27 cặp `CLOSED`, 2 cặp `OPEN_FAILED`, không cặp nào đang mở; 4 finding `PENDING`
(giữ nguyên, vì xử lý chúng là sửa dữ liệu và lượt này không sửa gì).

## Kiểm chứng cuối

```
pytest -q -m "not cham"   ->  484 passed, 3 deselected
ruff check .              ->  All checks passed!
```

Cả hai xanh — **sau khi** đã tìm ra F-01. Đó là kết luận đáng nhớ nhất của lượt kiểm toán này.
