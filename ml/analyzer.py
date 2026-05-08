import pandas as pd
import numpy as np
from datetime import timedelta
from ..utils.logger import get_logger

logger = get_logger(__name__)


ROW_THRESHOLD_US = 2000.0
WARN_Z = 2.0
CRIT_Z = 3.0
WARN_ABS_DIFF = 75.0
CRIT_ABS_DIFF = 200.0
WARN_DELTA = 120.0
CRIT_DELTA = 250.0
MIN_STD = 25.0


class Analyzer:
    """Enhanced analyzer with rolling statistics and severity scoring."""

    def __init__(self, rolling_window=30):
        self.rolling_window = rolling_window

    def analyze_dataframe(self, df: pd.DataFrame):
        base_df = df.copy()
        frame_cols = [c for c in base_df.columns if c.startswith("Frame_")]

        # fill tiny gaps
        base_df[frame_cols] = base_df[frame_cols].interpolate(axis=0).fillna(method="bfill").fillna(0)

        # core descriptive stats
        means = base_df[frame_cols].mean()
        stds = base_df[frame_cols].std(ddof=0).clip(lower=MIN_STD)

        # moving features
        rolling_mean = base_df[frame_cols].rolling(window=self.rolling_window, min_periods=1).mean()
        rolling_var = base_df[frame_cols].rolling(window=self.rolling_window, min_periods=1).var().fillna(0.0)
        deltas = base_df[frame_cols].diff().fillna(0.0)

        # z-scores relative to global stds
        diff = base_df[frame_cols].subtract(means, axis=1)
        abs_diff = diff.abs()
        z_scores = abs_diff.divide(stds, axis=1)

        # severity scoring: combine z, abs diff, rolling variance spikes
        severity = (z_scores.clip(lower=0) * 0.5) + (abs_diff / (means.replace(0, 1)) * 0.3) + (
            (rolling_var.divide(stds, axis=1)).fillna(0) * 0.2
        )

        # basic masks
        crit_mask = (z_scores >= CRIT_Z) | (abs_diff >= CRIT_ABS_DIFF) | (deltas.abs() >= CRIT_DELTA)
        warn_mask = (z_scores >= WARN_Z) | (abs_diff >= WARN_ABS_DIFF) | (deltas.abs() >= WARN_DELTA)

        # temporal instability: consecutive large deltas
        unstable = deltas.abs().rolling(window=3, min_periods=1).sum() >= (WARN_DELTA * 2)

        # compute per-row status
        row_isolation = (base_df[frame_cols] > ROW_THRESHOLD_US).any(axis=1)
        has_crit = crit_mask.any(axis=1)
        has_warn = (~has_crit) & warn_mask.any(axis=1)

        status = pd.Series("Normal", index=base_df.index)
        status.loc[has_warn | row_isolation] = "Warning"
        status.loc[has_crit] = "Critical"

        # compute summary columns
        warning_frames = warn_mask.apply(lambda r: ",".join([c for c, v in r.items() if v]), axis=1)
        critical_frames = crit_mask.apply(lambda r: ",".join([c for c, v in r.items() if v]), axis=1)
        frame_health = (1.0 - (severity.mean(axis=1) if hasattr(severity, "mean") else severity.mean())).clip(0, 2)

        out = base_df.copy()
        out["Status"] = status
        out["Warning_Frames"] = warning_frames
        out["Critical_Frames"] = critical_frames
        out["Row_Anomaly_Score"] = base_df[frame_cols].max(axis=1)
        out["Severity_Score"] = severity.mean(axis=1)
        out["Frame_Health_Score"] = frame_health if isinstance(frame_health, pd.Series) else pd.Series(frame_health, index=out.index)
        out["Unstable_Flag"] = unstable.any(axis=1)

        # meta info
        meta = {
            "rows": len(out),
            "frames": frame_cols,
            "anomalies": int((out["Status"] != "Normal").sum()),
        }

        logger.info(f"Analyzed dataframe: {meta}")
        return out, meta
