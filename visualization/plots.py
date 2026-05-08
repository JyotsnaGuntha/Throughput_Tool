import os
from typing import Optional
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from ..utils.logger import get_logger

logger = get_logger(__name__)


class VisualizationEngine:
    def __init__(self):
        sns.set(style="whitegrid")

    def generate_all(self, analyzed_df: pd.DataFrame, out_dir: str):
        os.makedirs(out_dir, exist_ok=True)
        try:
            self.anomaly_heatmap(analyzed_df, out_dir)
            self.frame_spike_graphs(analyzed_df, out_dir)
            self.rolling_average_plots(analyzed_df, out_dir)
            self.latency_distribution(analyzed_df, out_dir)
        except Exception as e:
            logger.exception(f"Error generating visuals: {e}")

    def anomaly_heatmap(self, df: pd.DataFrame, out_dir: str):
        frame_cols = [c for c in df.columns if c.startswith("Frame_")]
        if not frame_cols:
            return
        mask = (df['Status'] != 'Normal')
        data = df[frame_cols].copy()
        plt.figure(figsize=(12, 6))
        sns.heatmap(data.T, cmap='coolwarm', cbar=True)
        path = os.path.join(out_dir, 'anomaly_heatmap.png')
        plt.title('Frame Values Heatmap')
        plt.tight_layout()
        plt.savefig(path)
        plt.close()
        logger.info(f"Saved heatmap to {path}")

    def frame_spike_graphs(self, df: pd.DataFrame, out_dir: str, top_n=6):
        frame_cols = [c for c in df.columns if c.startswith("Frame_")]
        if not frame_cols:
            return
        # rank by max variance
        ranks = df[frame_cols].std().sort_values(ascending=False).head(top_n).index.tolist()
        for col in ranks:
            plt.figure(figsize=(10, 3))
            plt.plot(df['Time_Second'], df[col], label=col)
            plt.title(f"Frame spike - {col}")
            plt.xlabel('Time_Second')
            plt.ylabel('us')
            plt.tight_layout()
            path = os.path.join(out_dir, f"{col}_spike.png")
            plt.savefig(path)
            plt.close()
            logger.info(f"Saved spike graph to {path}")

    def rolling_average_plots(self, df: pd.DataFrame, out_dir: str):
        frame_cols = [c for c in df.columns if c.startswith("Frame_")]
        if not frame_cols:
            return
        mean_col = df[frame_cols].mean(axis=1)
        plt.figure(figsize=(10, 3))
        plt.plot(df['Time_Second'], mean_col, label='Rolling Mean')
        plt.title('Rolling Mean across frames')
        plt.xlabel('Time_Second')
        plt.tight_layout()
        path = os.path.join(out_dir, 'rolling_mean.png')
        plt.savefig(path)
        plt.close()
        logger.info(f"Saved rolling mean to {path}")

    def latency_distribution(self, df: pd.DataFrame, out_dir: str):
        frame_cols = [c for c in df.columns if c.startswith("Frame_")]
        if not frame_cols:
            return
        data = df[frame_cols].stack().reset_index(drop=True)
        plt.figure(figsize=(8, 4))
        sns.histplot(data, bins=50)
        plt.title('Latency Distribution')
        plt.tight_layout()
        path = os.path.join(out_dir, 'latency_distribution.png')
        plt.savefig(path)
        plt.close()
        logger.info(f"Saved latency distribution to {path}")
