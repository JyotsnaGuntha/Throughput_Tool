import os
from datetime import datetime
import pandas as pd

from ..ml.analyzer import Analyzer
from ..reporting.report_generator import ReportGenerator
from ..visualization.plots import VisualizationEngine
from ..storage.session_store import SessionStore
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PipelineManager:
    def __init__(self, base_path=None):
        self.base_path = base_path or os.path.join(os.getcwd(), "sessions")
        os.makedirs(self.base_path, exist_ok=True)
        self.analyzer = Analyzer()
        self.visuals = VisualizationEngine()
        self.reporter = ReportGenerator()
        self.session = None

        self._buffer = []

    def start_session(self, name=None):
        ts = datetime.now().strftime("%Y-%m-%d")
        tm = datetime.now().strftime("%H-%M-%S")
        session_folder = os.path.join(self.base_path, ts, f"session_{tm}")
        os.makedirs(session_folder, exist_ok=True)
        self.session = SessionStore(session_folder)
        logger.info(f"Started session: {session_folder}")
        return self.session

    def receive_data(self, df_chunk: pd.DataFrame):
        # accept dataframes (normalized chunk, e.g., 500 bytes -> decoded rows)
        if self.session is None:
            self.start_session()
        self._buffer.append(df_chunk.copy())
        # persist a small raw buffer to session logs intermittently
        self.session.append_raw_chunk(df_chunk)
        # maintain rolling in-memory dataframe
        logger.debug(f"Received data chunk with {len(df_chunk)} rows")

    def process_data(self):
        if not self._buffer:
            logger.warning("No data to process")
            return None
        df = pd.concat(self._buffer, ignore_index=True)
        df = self._normalize_dataframe(df)
        self.session.save_raw_excel(df)
        self._buffer = [df]
        logger.info(f"Processed data into dataframe with {len(df)} rows")
        return df

    def _normalize_dataframe(self, df: pd.DataFrame):
        # Basic normalization: ensure Time_Second exists, numeric frames
        if "Time_Second" not in df.columns:
            if "Time" in df.columns:
                df = df.rename(columns={"Time": "Time_Second"})
            else:
                df.insert(0, "Time_Second", pd.Series(range(len(df))))

        frame_cols = [c for c in df.columns if c.startswith("Frame_")]
        for col in frame_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def rolling_analyze(self):
        df = self.process_data()
        if df is None:
            return None
        analyzed_df, meta = self.analyzer.analyze_dataframe(df)
        self.session.save_analyzed_excel(analyzed_df)
        self.session.save_anomalies_csv(analyzed_df)
        # create visuals
        charts_dir = self.session.charts_dir
        self.visuals.generate_all(analyzed_df, charts_dir)
        # generate final pdf
        report_path = self.reporter.generate_pdf_report(self.session, analyzed_df)
        logger.info(f"Generated report at {report_path}")
        return {
            "session": self.session.folder,
            "analyzed_excel": self.session.analyzed_path,
            "anomalies_csv": self.session.anomalies_path,
            "report_pdf": report_path,
        }

    def finalize(self):
        # finalize and archive session
        if self.session is None:
            logger.warning("No active session to finalize")
            return None
        result = self.rolling_analyze()
        self.session.log("Session finalized")
        logger.info("Session finalized and archived")
        return result
