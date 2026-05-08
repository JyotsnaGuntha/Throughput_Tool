import os
from datetime import datetime
import pandas as pd
from ..utils.logger import get_logger
from ..visualization.plots import VisualizationEngine

logger = get_logger(__name__)


class ReportGenerator:
    def __init__(self):
        self.visuals = VisualizationEngine()

    def generate_excel_report(self, session, analyzed_df: pd.DataFrame):
        # Save analyzed Excel (already saved by session) but ensure naming
        return session.save_analyzed_excel(analyzed_df)

    def generate_pdf_report(self, session, analyzed_df: pd.DataFrame):
        # Create a simple multi-page PDF that includes cover, executive summary, and charts.
        # For simplicity we will export a basic PDF using matplotlib for charts and pandas for tables.
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except Exception as e:
            logger.warning("reportlab not installed; falling back to simple text report")
            pdf_path = os.path.join(session.folder, f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
            with open(pdf_path, "w", encoding="utf-8") as f:
                f.write("Analysis Report\n\n")
                f.write(f"Session: {session.folder}\n")
                f.write(f"Rows: {len(analyzed_df)}\n")
                f.write(f"Anomalies: {(analyzed_df['Status'] != 'Normal').sum()}\n")
            logger.info(f"Wrote fallback text report to {pdf_path}")
            return pdf_path

        pdf_path = os.path.join(session.folder, f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        c = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter
        # Cover
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(width / 2, height - 100, "Throughput Analysis Report")
        c.setFont("Helvetica", 10)
        c.drawString(72, height - 140, f"Session: {session.folder}")
        c.drawString(72, height - 155, f"Rows: {len(analyzed_df)}")
        c.drawString(72, height - 170, f"Anomalies: {(analyzed_df['Status'] != 'Normal').sum()}")
        c.showPage()

        # Executive summary
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, "Executive Summary")
        c.setFont("Helvetica", 10)
        top_anomalies = analyzed_df[analyzed_df['Status'] != 'Normal'].head(10)
        y = height - 100
        for idx, row in top_anomalies.iterrows():
            line = f"{row.get('Time_Second', idx)}: {row['Status']} - {row.get('Anomaly_Reason','')[:120]}"
            c.drawString(72, y, line)
            y -= 12
            if y < 100:
                c.showPage()
                y = height - 72

        c.showPage()
        c.save()
        logger.info(f"Generated PDF report at {pdf_path}")
        return pdf_path
