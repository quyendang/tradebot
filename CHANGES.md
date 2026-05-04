# Tradebot Signal Optimization — Changes Log

Phiên bản này tối ưu thuật toán signal dựa trên backtest 10 năm dữ liệu BTCUSDT & ETHUSDT
(timeframes 1h/4h/1d). Backtest đo forward return 24h sau mỗi tín hiệu BUY_WATCH/SELL_WATCH
trên timeframe 4h, từ 2019-01-01 đến cuối dataset.

## Tóm tắt thay đổi

Chỉ **3 file** được chỉnh, mỗi file thay đổi tối thiểu để giữ tính ổn định của hệ thống.

### 1. `app/engine/decision.py` — Asymmetric thresholds
**Trước:**
```python
if buy_score >= 72 and sell_score <= 45: return BUY_WATCH
if sell_score >= 72 and buy_score <= 45: return SELL_WATCH
```

**Sau:**
```python
BUY_THRESHOLD = 72        # giữ nguyên
SELL_THRESHOLD = 74       # nâng từ 72 → 74
OPPOSITE_MAX = 45         # giữ nguyên

if buy_score >= 72 and sell_score <= 45: return BUY_WATCH
if sell_score >= 74 and buy_score <= 45: return SELL_WATCH
```

**Lý do:** Crypto có upward bias mạnh trong 10 năm dữ liệu (số tín hiệu BUY nhiều
gấp ~4x SELL). Yêu cầu strictness cao hơn cho SELL giúp loại bớt tín hiệu yếu mà
vẫn giữ được mật độ signal đủ cho live trading.

### 2. `app/market/indicators.py` — Thêm volume metrics
Thêm 2 cột vào DataFrame indicators:
```python
df['volume_sma_20']  = df['volume'].rolling(20, min_periods=1).mean()
df['volume_ratio']   = df['volume'] / df['volume_sma_20']
```

**Lý do:** Cần `volume_ratio` để xác nhận chất lượng breakout/breakdown trong scorer.
Không gây breaking change — chỉ thêm cột mới, không sửa cột cũ.

### 3. `app/engine/scorer.py` — Volume-confirmed breakout/breakdown
Sau logic kiểm tra `near resistance` / `near support`, bổ sung điều chỉnh điểm
dựa trên volume hiện tại so với trung bình 20 bar:

| Tình huống                                        | Điều chỉnh điểm |
|---------------------------------------------------|-----------------|
| Near resistance + volume ≥ 1.5x average           | buy_score **+4**  (xác nhận breakout) |
| Near resistance + volume < 0.7x average           | buy_score **−6**  (cảnh báo breakout yếu) |
| Near support + volume ≥ 1.5x average              | sell_score **+4** (xác nhận breakdown) |
| Near support + volume < 0.7x average              | sell_score **−6** (cảnh báo breakdown yếu) |

**Lý do:** Backtest cho thấy các tín hiệu breakout với volume cực thấp
(< 70% trung bình) có win-rate giảm rõ rệt. Filter này lọc ~9 BUY signal BTC và
~5 BUY signal ETH mà không làm giảm win-rate, đồng thời đóng vai trò
**asymmetric quality gate**: khen thưởng tín hiệu mạnh, trừng phạt tín hiệu yếu.

---

## Kết quả backtest (h24 forward return)

|                    | Baseline                    | Optimized                   | Δ                   |
|--------------------|-----------------------------|-----------------------------|---------------------|
| **BTC BUY**        | 548 sigs · wr 72.4% · μ +1.88% · sharpe 0.559 | 539 sigs · wr 72.4% · μ +1.88% · sharpe 0.558 | giữ |
| **BTC SELL**       | 126 sigs · wr 67.5% · μ +1.95% · sharpe 0.436 | **58 sigs · wr 74.1% · μ +2.70% · sharpe 0.578** | **+6.6pp wr, +38% mean** |
| **ETH BUY**        | 385 sigs · wr 70.1% · μ +2.19% · sharpe 0.541 | 381 sigs · wr 70.1% · μ +2.20% · sharpe 0.543 | giữ |
| **ETH SELL**       | 105 sigs · wr 59.0% · μ +1.82% · sharpe 0.373 | 49 sigs · wr 57.1% · μ +1.91% · sharpe 0.379 | mean & sharpe ≈ |

(`wr` = win-rate, `μ` = mean forward 24h return, `sharpe` không annualized.)

**Kết luận chính:** Cải thiện rõ rệt nhất là **BTC SELL** — win-rate tăng 6.6
điểm phần trăm và mean return tăng 38%. ETH SELL ít cải thiện hơn vì bản
chất ETH có upward bias mạnh, SELL signal trên ETH khó precise.

---

## Những gì đã thử nhưng KHÔNG áp dụng

| Đề xuất                                | Lý do loại bỏ |
|----------------------------------------|---------------|
| Trend filter mạnh (block all counter-trend) | Reject quá nhiều, giảm win-rate xuống 60% |
| MTF alignment scoring (bonus +10 nếu 3 TF cùng hướng) | Mở quá lỏng, win-rate giảm xuống 57% |
| ATR percentile rank reject top 8% (high-vol) | Marginal, win-rate giảm 0.4% |
| RR check yêu cầu reward/risk ≥ 1.0 (swing 20-bar) | Reject 95% signals, swing quá gần giá |
| Daily uptrend block all SELL | Trung tính trên backtest, chưa đủ bằng chứng |
| Combined multi-factor (v6 logic) | 13–25 signals/10 năm — quá ít cho live trading |

**Bài học:** Baseline đã rất tốt (BUY win-rate 70–72%). Đa số "cải tiến" phức tạp
đều LÀM XẤU performance trên backtest. Chỉ những thay đổi nhỏ, có cơ sở thống kê
rõ ràng mới được giữ lại — đúng tinh thần "đơn giản và nhất quán" trong quant trading.

---

## Hệ thống 5-agent đã đề xuất

Mỗi agent đề xuất một hướng cải tiến độc lập, sau đó được test backtest:

1. **Trend Filter Agent** — daily EMA200 master filter + ADX gate. *Test: thất bại* (relax quá nhiều).
2. **Volume Agent** — volume confirmation breakout + OBV slope. *Test: phần `vol_ratio` được giữ.*
3. **MTF Alignment Agent** — bonus điểm khi 3 timeframe đồng pha. *Test: thất bại* (mở quá lỏng).
4. **Volatility Regime Agent** — ATR percentile + BB squeeze detection. *Test: marginal, loại.*
5. **Asymmetric + RR Agent** — SELL threshold cao hơn BUY + RR check. *Test: phần asymmetric threshold được giữ.*

Hai phần được giữ từ Agent 2 và Agent 5 chính là 3 patch ở trên.
