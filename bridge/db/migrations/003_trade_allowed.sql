-- 003 — Bridge phai nhin thay duoc quyen giao dich cua terminal (B-09).
--
-- `MQL_TRADE_ALLOWED` truoc day chi duoc kiem BEN TRONG EA, luc khoi dong va luc nhan command,
-- nen dashboard va bo doi chieu deu mu voi no. Bat doi xung nguy hiem: duong MO phia Client di
-- qua giao dien nen khong can quyen nay, con duong DONG di qua EA nen can — mot terminal tat
-- Algo Trading van mo lenh binh thuong roi chi hong luc dong.
--
-- NULL = agent khong bao (clicker, hoac EA ban cu). "Khong biet" khac "biet la tat".
ALTER TABLE agent ADD COLUMN trade_allowed INTEGER
    CHECK (trade_allowed IS NULL OR trade_allowed IN (0, 1));
