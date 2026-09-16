"""GRU sequence forecaster.

**Why GRU rather than LSTM.** Three gates instead of four means roughly 25%
fewer parameters, which matters at this data scale (a few tens of thousands of
hourly samples per site); it trains faster on a CPU-only laptop; and on
sequences under ~72 steps the two are empirically hard to separate. Fewer moving
parts is worth more than architectural prestige on a four-day build. `CELL`
below is a one-line swap if you want to train and report an LSTM instead.

**Design choices that matter here:**

* *Direct multi-horizon head* - a single Linear(hidden -> 24) predicting all 24
  lead times at once, rather than feeding predictions back in. No compounding
  error, one forward pass, deterministic output.
* *log1p target* - PM2.5 in this region spans roughly 2 to 300 ug/m3 and is
  heavy-tailed. Trained on raw values, squared error is dominated by a handful
  of extreme hours and the model learns to ignore exactly the episodes the
  system exists to predict.
* *Huber loss* - robust to the remaining tail.
* *Trained jointly across all six institutions* via the site one-hot, so one
  model sees six times the data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config
from . import evaluate

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    TORCH_AVAILABLE = False

CELL = "GRU"  # swap to "LSTM" to train the alternative
HIDDEN = 64
LAYERS = 2
DROPOUT = 0.1
BATCH = 256
MAX_EPOCHS = 60
PATIENCE = 8
LR = 1e-3


class HazeGRU(nn.Module if TORCH_AVAILABLE else object):
    def __init__(self, n_features: int, horizon: int = config.FORECAST_HORIZON_HOURS):
        super().__init__()
        cell = getattr(nn, CELL)
        self.rnn = cell(
            input_size=n_features,
            hidden_size=HIDDEN,
            num_layers=LAYERS,
            dropout=DROPOUT if LAYERS > 1 else 0.0,
            batch_first=True,
        )
        self.head = nn.Sequential(
            nn.Linear(HIDDEN, HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, horizon)
        )

    def forward(self, x):
        out, _ = self.rnn(x)
        return self.head(out[:, -1, :])  # last timestep only


def make_sequences(
    df: pd.DataFrame,
    features: list[str],
    seq_len: int = config.SEQUENCE_LENGTH_HOURS,
    horizon: int = config.FORECAST_HORIZON_HOURS,
):
    """Build (n, seq_len, f) windows per institution.

    Sequences are cut per site so a window never straddles two locations, and
    any window with a gap in inputs or targets is dropped rather than imputed.
    """
    targets = [f"target_{h}h" for h in range(1, horizon + 1)]
    xs, ys, times, sites = [], [], [], []

    for site_id, group in df.groupby("institution_id"):
        group = group.sort_values("time").reset_index(drop=True)
        x = group[features].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=np.float32)
        y = group[targets].to_numpy(dtype=np.float32)
        t = group["time"].to_numpy()

        valid_x = ~np.isnan(x).any(axis=1)
        valid_y = ~np.isnan(y).any(axis=1)

        for end in range(seq_len, len(group)):
            window = slice(end - seq_len, end)
            if not valid_x[window].all() or not valid_y[end - 1]:
                continue
            xs.append(x[window])
            ys.append(y[end - 1])
            times.append(t[end - 1])
            sites.append(site_id)

    if not xs:
        return None
    return (
        np.stack(xs),
        np.stack(ys),
        np.array(times),
        np.array(sites),
    )


def train_and_evaluate(
    df: pd.DataFrame,
    features: list[str],
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> dict | None:
    """Train the GRU and report held-out metrics. Returns None if torch is absent."""
    if not TORCH_AVAILABLE:
        return None

    torch.manual_seed(42)
    np.random.seed(42)

    train_seq = make_sequences(train_df, features)
    val_seq = make_sequences(val_df, features)
    test_seq = make_sequences(test_df, features)
    if train_seq is None or test_seq is None:
        print("  not enough contiguous data to build sequences")
        return None

    x_tr, y_tr, _, _ = train_seq
    x_te, y_te, t_te, s_te = test_seq

    # Standardise inputs on training statistics only.
    mean = x_tr.reshape(-1, x_tr.shape[-1]).mean(axis=0)
    std = x_tr.reshape(-1, x_tr.shape[-1]).std(axis=0) + 1e-6

    def prep(x):
        return torch.tensor((x - mean) / std, dtype=torch.float32)

    # Heavy-tailed target: learn in log space.
    y_tr_t = torch.tensor(np.log1p(np.clip(y_tr, 0, None)), dtype=torch.float32)
    x_tr_t = prep(x_tr)

    if val_seq is not None:
        x_va, y_va, _, _ = val_seq
        x_va_t, y_va_t = prep(x_va), torch.tensor(
            np.log1p(np.clip(y_va, 0, None)), dtype=torch.float32
        )
    else:
        split = int(len(x_tr_t) * 0.9)
        x_va_t, y_va_t = x_tr_t[split:], y_tr_t[split:]
        x_tr_t, y_tr_t = x_tr_t[:split], y_tr_t[:split]

    print(f"  sequences: train={len(x_tr_t):,} val={len(x_va_t):,} test={len(x_te):,}")

    model = HazeGRU(n_features=x_tr.shape[-1])
    optimiser = torch.optim.Adam(model.parameters(), lr=LR)
    loss_fn = nn.HuberLoss()
    loader = DataLoader(TensorDataset(x_tr_t, y_tr_t), batch_size=BATCH, shuffle=True)

    best_loss = float("inf")
    best_state = None
    stale = 0

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        for xb, yb in loader:
            optimiser.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            optimiser.step()

        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(x_va_t), y_va_t))

        if val_loss < best_loss - 1e-5:
            best_loss, stale = val_loss, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= PATIENCE:
                print(f"  early stop at epoch {epoch} (val loss {best_loss:.4f})")
                break
        if epoch % 10 == 0:
            print(f"  epoch {epoch:3d}  val loss {val_loss:.4f}")

    if best_state:
        model.load_state_dict(best_state)

    # -- held-out predictions ---------------------------------------------
    model.eval()
    with torch.no_grad():
        pred_log = model(prep(x_te)).numpy()
    predictions = np.expm1(pred_log)  # back to ug/m3

    # Rebuild a frame aligned to the sequence endpoints so the shared
    # evaluation code can compare against the same baselines as the RF.
    aligned = pd.DataFrame({"time": t_te, "institution_id": s_te})
    aligned = aligned.merge(
        test_df[["time", "institution_id", "pm25"]
                + [f"target_{h}h" for h in range(1, config.FORECAST_HORIZON_HOURS + 1)]],
        on=["time", "institution_id"],
        how="left",
    )

    by_lead = {lead: predictions[:, lead - 1] for lead in (6, 12, 24)}
    horizons = evaluate.horizon_metrics(aligned, train_df, by_lead)
    alerts = evaluate.alert_metrics(
        aligned, {lead: predictions[:, lead - 1] for lead in range(1, 25)}
    )

    print(f"\n  {'lead':>5}  {'GRU':>7}  {'persist':>8}   skill")
    for row in horizons:
        print(
            f"  {row['lead_hours']:>4}h  {row['model_mae']:>7.2f}  "
            f"{row['persistence_mae']:>8.2f}   {row['improvement_vs_persistence']:+.1%}"
        )

    at24 = next((h for h in horizons if h["lead_hours"] == 24), None)
    beats = bool(at24 and at24["improvement_vs_persistence"] >= 0.15)

    torch.save(
        {
            "state_dict": model.state_dict(),
            "features": features,
            "mean": mean,
            "std": std,
            "cell": CELL,
            "hidden": HIDDEN,
            "layers": LAYERS,
        },
        config.MODELS / "gru_pm25.pt",
    )

    return {
        "horizons": horizons,
        "alerts": alerts,
        "beats_persistence": beats,
        "predictions": predictions,
    }
