"""Random Forest models.

Two variants, deliberately separated:

* **attribution** - trained *without* PM2.5 lag features, so it cannot lean on
  persistence and must explain concentration from fire activity and weather
  alone. Its feature importances are the evidence for the transboundary claim:
  if upwind fire exposure dominates at a Sarawak receptor, the model itself has
  quantified the cross-border link.

* **forecast** - trained *with* lags, predicting +6/+12/+24h. Serves as the
  fallback forecaster and, via quantile spread across trees, as the source of
  the prediction bands the API returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from .. import config

LAG_PREFIXES = ("pm25_lag_", "pm25_roll_")

# Day-of-year encodings are excluded from the attribution model on purpose.
# Left in, they dominate: the forest learns "September is smoky", which is
# climatology dressed up as attribution and tells us nothing about whether a
# particular fire is driving a particular forecast.
SEASONAL_PREFIXES = ("doy_",)

# min_samples_leaf is set well above the sklearn default deliberately. At
# leaf=5 the 24 forests together occupied 11.5 GB on disk, which is not a
# reasonable artifact for a laptop build. Measured on held-out data at +24h:
#   leaf=5,  n=400 -> MAE 12.98, 481 MB per forest
#   leaf=20, n=300 -> MAE 13.03,  87 MB per forest   <- chosen
#   leaf=50, n=300 -> MAE 13.11,  35 MB per forest
# Five times smaller for five hundredths of a microgram is the right trade.
RF_PARAMS = dict(
    n_estimators=config.RF_N_ESTIMATORS,
    min_samples_leaf=20,
    max_features="sqrt",
    n_jobs=-1,
    random_state=42,
)


def attribution_features(features: list[str]) -> list[str]:
    """Fire and weather only - no persistence, no seasonality."""
    return [
        f
        for f in features
        if not f.startswith(LAG_PREFIXES) and not f.startswith(SEASONAL_PREFIXES)
    ]


def _xy(df: pd.DataFrame, features: list[str], target: str, log: bool = True):
    """Feature/target arrays, with the target in log1p space by default.

    PM2.5 here spans 2 to 307 ug/m3 and is heavy-tailed. Two things follow.
    First, squared error on raw values is dominated by a handful of extreme
    hours, so the forest optimises for the tail and blurs the ordinary range.
    Second, and more seriously, a tree ensemble predicts an average of training
    targets in each leaf, so it *cannot* output a value above its training
    maximum - and the held-out 2023 event peaks well above anything in the
    training window. Learning in log space will not remove that ceiling, but it
    compresses the range so the model tracks the shape of an episode and, more
    importantly, crosses alert thresholds at the right time. Getting the timing
    of a threshold crossing right is what this system is actually for.
    """
    sub = df[features + [target]].replace([np.inf, -np.inf], np.nan).dropna()
    x = sub[features].to_numpy(dtype=float)
    y = sub[target].to_numpy(dtype=float)
    if log:
        y = np.log1p(np.clip(y, 0, None))
    return x, y


def train_attribution(
    train: pd.DataFrame, features: list[str]
) -> tuple[RandomForestRegressor, list[str]]:
    """Explain current PM2.5 from fire and weather only."""
    cols = attribution_features(features)
    x, y = _xy(train, cols, "pm25")
    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(x, y)
    return model, cols


def train_forecast(
    train: pd.DataFrame, features: list[str], horizons=(6, 12, 24)
) -> dict[int, RandomForestRegressor]:
    """One forest per lead time. Direct prediction, no autoregressive rollout,
    so errors cannot compound across steps.

    Trained in raw ug/m3 space, unlike the attribution model. Back-transforming
    an averaged log prediction yields a geometric mean, which is biased low, and
    measured against real MAE that bias costs more than the heavy tail does -
    verified on held-out data, where log-space training halved the skill over
    persistence. Attribution wants relative structure; forecasting wants
    absolute error. Different objectives, different transforms.
    """
    models: dict[int, RandomForestRegressor] = {}
    for lead in horizons:
        x, y = _xy(train, features, f"target_{lead}h", log=False)
        model = RandomForestRegressor(**RF_PARAMS)
        model.fit(x, y)
        models[lead] = model
    return models


# Which target space each model is trained in. Prediction must invert exactly
# what training applied, so these are read from the saved bundle rather than
# defaulted at the call site - mismatching them silently produces expm1() of a
# raw concentration, which is not a subtle failure but is an easy one to write.
LOG_ATTRIBUTION = True
LOG_FORECAST = False


def predict(
    model: RandomForestRegressor, df: pd.DataFrame, features: list[str], log: bool
) -> np.ndarray:
    """Predictions in ug/m3, inverting the log transform used in training."""
    x = df[features].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
    pred = model.predict(x)
    return np.expm1(pred) if log else pred


def predict_quantiles(
    model: RandomForestRegressor,
    df: pd.DataFrame,
    features: list[str],
    log: bool,
    percentiles: tuple[int, ...] = (10, 50, 90),
) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """Ensemble mean plus arbitrary percentiles taken across the individual trees.

    The trees disagree most where the training data was thin - typically during
    extreme episodes - so the band widens exactly where it should.

    Every percentile comes from the same `per_tree` matrix, so asking for three
    costs no more forest evaluations than asking for one. Note what the band can
    and cannot say: each tree returns an average of training targets in a leaf,
    so *no* percentile can exceed the training maximum. A band that stops
    widening and parks just under that ceiling is the ensemble telling you it has
    run out of range, which is what `extrapolation.classify` reads.
    """
    x = df[features].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float)
    per_tree = np.stack([est.predict(x) for est in model.estimators_])
    mean = per_tree.mean(axis=0)
    quantiles = {int(p): np.percentile(per_tree, p, axis=0) for p in percentiles}
    if log:
        return np.expm1(mean), {p: np.expm1(v) for p, v in quantiles.items()}
    return mean, quantiles


def predict_with_spread(
    model: RandomForestRegressor,
    df: pd.DataFrame,
    features: list[str],
    log: bool,
    lower=config.BAND_LOWER_PERCENTILE,
    upper=config.ALERT_TRIGGER_PERCENTILE,
):
    """Point prediction plus a percentile band, as a `(mean, lower, upper)` tuple.

    Kept as the two-percentile shorthand over `predict_quantiles`; the training
    script indexes the third element to sweep trigger percentiles.
    """
    mean, quantiles = predict_quantiles(model, df, features, log, (lower, upper))
    return mean, quantiles[int(lower)], quantiles[int(upper)]


def importances(model: RandomForestRegressor, features: list[str], top: int = 12) -> list[dict]:
    order = np.argsort(model.feature_importances_)[::-1][:top]
    return [
        {"feature": features[i], "contribution": round(float(model.feature_importances_[i]), 4)}
        for i in order
    ]
