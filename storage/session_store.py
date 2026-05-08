import os
import pandas as pd
from datetime import datetime
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SessionStore:
    def __init__(self, folder):
        self.folder = folder
        self.charts_dir = os.path.join(folder, "charts")
        os.makedirs(self.charts_dir, exist_ok=True)
        self.logs_dir = os.path.join(folder, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.raw_path = None
        self.analyzed_path = None
        self.anomalies_path = None

    def append_raw_chunk(self, df_chunk: pd.DataFrame):
        # append to an internal raw buffer csv (internal only)
        temp_csv = os.path.join(self.logs_dir, "_raw_buffer.csv")
        header = not os.path.exists(temp_csv)
        df_chunk.to_csv(temp_csv, mode='a', index=False, header=header)

    def save_raw_excel(self, df: pd.DataFrame):
        raw_name = os.path.join(self.folder, "raw_data.xlsx")
        df.to_excel(raw_name, index=False, engine='openpyxl')
        self.raw_path = raw_name
        logger.info(f"Saved raw excel to {raw_name}")
        return raw_name

    def save_analyzed_excel(self, analyzed_df: pd.DataFrame):
        analyzed_name = os.path.join(self.folder, "analyzed_data.xlsx")
        analyzed_df.to_excel(analyzed_name, index=False, engine='openpyxl')
        self.analyzed_path = analyzed_name
        logger.info(f"Saved analyzed excel to {analyzed_name}")
        return analyzed_name

    def save_anomalies_csv(self, analyzed_df: pd.DataFrame):
        anomalies = analyzed_df[analyzed_df['Status'] != 'Normal']
        anomalies_name = os.path.join(self.folder, "anomalies.csv")
        anomalies.to_csv(anomalies_name, index=False)
        self.anomalies_path = anomalies_name
        logger.info(f"Saved anomalies csv to {anomalies_name}")
        return anomalies_name

    def log(self, msg: str):
        path = os.path.join(self.logs_dir, "session.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")
