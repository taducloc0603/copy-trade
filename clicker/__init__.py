"""Clicker — mở lệnh trên terminal MT5 Client bằng cách điều khiển giao diện.

Nó tồn tại vì một lý do duy nhất: `DEAL_REASON` do **máy chủ broker** gán theo *kênh* gửi lệnh,
và `OrderSend` của MQL5 luôn cho ra `DEAL_REASON_EXPERT`. Muốn có `DEAL_REASON_CLIENT` thì phải
đổi kênh, tức là đi qua chính hộp thoại New Order của terminal (D-21).

Ranh giới của nó hẹp một cách cố ý: nhận `OPEN_UI`, điền hộp thoại, đọc lại, bấm, trả ack. Nó
**không** đọc database, **không** sinh event, **không** nhận lệnh đóng, và **không** biết `pair`
là gì. Việc ghép vị thế vừa mở vào cặp lệnh do Bridge làm, bằng cách tương quan với event
`position_opened` mà EA Client báo lên (D-23).
"""
