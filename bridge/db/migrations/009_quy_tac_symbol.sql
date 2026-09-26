-- 009 — Quy tắc đặt tên symbol của sàn Client: tiền tố và hậu tố (D-45).
--
-- Mỗi sàn đặt tên theo một quy ước cho MỌI symbol (`XAUUSD.c`, `XAUUSDm`, `cXAUUSD`), nên khai
-- quy ước một lần thay cho từng cặp. Quy tắc KHÔNG được tra lúc chạy: nó chỉ sinh danh sách để
-- người dùng xem rồi bấm lưu thành dòng `symbol_map`. Processor vẫn tra `symbol_map` như cũ.
--
-- Quy tắc phía Master nằm ở `system_config` (`master_symbol_prefix`, `master_symbol_suffix`) vì
-- Master không có dòng `client_account` — cùng chỗ với `master_close_route`.
--
-- Chuỗi rỗng, không phải NULL: "không có tiền tố" là một quy tắc hợp lệ (HFM: `XAUUSD` trần), và
-- một cột NULL thì mọi chỗ ghép chuỗi đều phải nhớ `or ''`.

ALTER TABLE client_account ADD COLUMN symbol_prefix TEXT NOT NULL DEFAULT '';
ALTER TABLE client_account ADD COLUMN symbol_suffix TEXT NOT NULL DEFAULT '';
