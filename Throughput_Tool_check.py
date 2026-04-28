"""
                                                                         Throughput Analysis Tool
                                                                              General Flow
1. To Start the Analysis Process, the Tool will send start_frame FE FE FE 80 FE FE FE
2. Then the controller will send 500 bytes of data as a chunk every second
3. The 500 bytes are percentage of total time taken for all schedulers to run for each frame, so the total frames are 500 [0-499] and one byte value is the time taken
   by the frame at that index in the chunk [so the first byte of the chunk will the time taken from frame 1 {as index = 0+1} and last byte will be time taken by frame
   500 {as index 499 + 1}]
4. When the start frame is sent a flag is set true
5. The chunks will be received by the tool every second so the receiving logic will be in a while loop which will run till that flag is true so every second each byte
   in the 500 bytes will be multiplied by 20 and be stored in the csv
6. When the user wants to stop the process it will press the stop button and send the stop frame which sets the flag false so the loop stops running and an ack is sent 
   by the controller in response to this frame, once this ack is received the tool will show a message "Analysis Done, Csv Ready to Export"
"""

import csv
import json
import os
import shutil
import subprocess
import threading
import time
import sys
import tempfile
from datetime import datetime

import serial
import serial.tools.list_ports
import webview
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ─────────────────────────────────────────────
#  Protocol constants
# ─────────────────────────────────────────────
#START_FRAME  = bytes([0xFE, 0xFE, 0xFE, 0x80, 0xFE, 0xFE, 0xFE])
START_FRAME = b'\xFE\xFE\xFE\x80\xFE\xFE\xFE'
#STOP_FRAME   = bytes([0xFE, 0xFE, 0xFE, 0x81, 0xFE, 0xFE, 0xFE])
STOP_FRAME  = b'\xFE\xFE\xFE\x81\xFE\xFE\xFE'
CHUNK_SIZE   = 500
SCALE_FACTOR = 20
ACK_TIMEOUT  = 3.0
BLOWN_THRESHOLD = 2000   # time

# ─────────────────────────────────────────────
#  Backend API
# ─────────────────────────────────────────────
class Api:
    def __init__(self):
        self._ser: serial.Serial | None = None
        self._running = False
        self._analysis_running = False
        self._lock = threading.Lock()
        self._data: list[tuple[int, int, int]] = []   # (second, frame_idx, raw_percent)
        self._thread: threading.Thread | None = None
        self._session_total_us = 0
        self._session_sample_count = 0
        self._session_blown = 0
        self._session_max_us = 0
        self._session_max_frame = 0
        self._session_max_value = -1
        self._last_exported_csv_path: str | None = None
        self._analysis_excel_path: str | None = None
        self._analysis_temp_dir: str | None = None

    def _reset_session_state(self) -> None:
        with self._lock:
            self._data = []
            self._session_total_us = 0
            self._session_sample_count = 0
            self._session_blown = 0
            self._session_max_us = 0
            self._session_max_frame = 0
            self._session_max_value = -1
        self._analysis_excel_path = None
        self._analysis_temp_dir = None
        self._last_exported_csv_path = None

    def _build_summary(self) -> dict[str, int]:
        with self._lock:
            if self._session_sample_count == 0:
                return {"rows": 0, "seconds": 0, "blown": 0, "avg_us": 0, "max_us": 0, "max_frame": 0}

            seconds = self._data[-1][0] if self._data else 0
            avg_us = self._session_total_us // self._session_sample_count
            return {
                "rows": self._session_sample_count,
                "seconds": seconds,
                "blown": self._session_blown,
                "avg_us": avg_us,
                "max_us": self._session_max_us,
                "max_frame": self._session_max_frame,
            }

    def _write_snapshot_csv(self, filepath: str) -> int:
        with self._lock:
            snapshot = list(self._data)

        if not snapshot:
            raise ValueError("No data to export.")

        chunked_data: dict[int, list[int]] = {}
        for sec, frame, pct in snapshot:
            if sec not in chunked_data:
                chunked_data[sec] = [0] * CHUNK_SIZE

            if 0 <= frame < CHUNK_SIZE:
                chunked_data[sec][frame] = pct * SCALE_FACTOR

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            header = ["Time_Second"] + [f"Frame_{i}" for i in range(CHUNK_SIZE)]
            writer.writerow(header)

            for sec in sorted(chunked_data.keys()):
                writer.writerow([sec] + chunked_data[sec])

        return len(chunked_data)

    def _prepare_analysis_input(self) -> str:
        if self._last_exported_csv_path and os.path.exists(self._last_exported_csv_path):
            return self._last_exported_csv_path

        if self._analysis_temp_dir is None:
            self._analysis_temp_dir = tempfile.mkdtemp(prefix="throughput_analysis_")

        csv_path = os.path.join(self._analysis_temp_dir, "session_export.csv")
        self._write_snapshot_csv(csv_path)
        return csv_path

    def _run_analysis_worker(self) -> None:
        try:
            input_csv = self._prepare_analysis_input()
            output_dir = os.path.dirname(input_csv)
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_ml.py")

            completed = subprocess.run(
                [sys.executable, script_path, "--input", input_csv, "--output-dir", output_dir],
                capture_output=True,
                text=True,
                check=False,
            )

            if completed.returncode != 0:
                message = completed.stderr.strip() or completed.stdout.strip() or "Analysis failed."
                window.evaluate_js(
                    f"window._app && window._app.onAnalysisError({json.dumps(message)})"
                )
                return

            try:
                result = json.loads(completed.stdout.strip() or "{}")
            except json.JSONDecodeError:
                window.evaluate_js(
                    f"window._app && window._app.onAnalysisError({json.dumps('Analysis completed but the model returned an invalid response.')})"
                )
                return

            output_path = result.get("output_path")
            if not output_path or not os.path.exists(output_path):
                window.evaluate_js(
                    f"window._app && window._app.onAnalysisError({json.dumps('Analysis completed but no Excel report was generated.')})"
                )
                return

            self._analysis_excel_path = output_path
            window.evaluate_js(
                f"window._app && window._app.onAnalysisComplete({json.dumps({'message': 'Patterns Analyzed Successfully'})})"
            )
        except Exception as exc:
            window.evaluate_js(
                f"window._app && window._app.onAnalysisError({json.dumps(str(exc))})"
            )
        finally:
            self._analysis_running = False

    def analyze(self) -> str:
        with self._lock:
            snapshot_ready = bool(self._data)

        if not snapshot_ready:
            return json.dumps({"status": "error", "message": "No data available to analyze."})
        if self._analysis_running:
            return json.dumps({"status": "error", "message": "Analysis is already running."})

        self._analysis_running = True
        worker = threading.Thread(target=self._run_analysis_worker, daemon=True)
        worker.start()
        return json.dumps({"status": "ok", "message": "Analysis started."})

    def download_excel(self) -> str:
        if not self._analysis_excel_path or not os.path.exists(self._analysis_excel_path):
            return json.dumps({"status": "error", "message": "No analyzed Excel report is available."})

        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"throughput_{ts}_ML_Analyzed.xlsx"
            result = window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=default_name,
                file_types=["Excel Files (*.xlsx)", "All files (*.*)"]
            )

            if not result:
                return json.dumps({"status": "cancelled", "message": "Download cancelled."})

            filepath = result if isinstance(result, str) else result[0]
            shutil.copyfile(self._analysis_excel_path, filepath)
            return json.dumps({"status": "ok", "path": filepath})
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)})

    def download_pdf(self) -> str:
        if not self._analysis_excel_path or not os.path.exists(self._analysis_excel_path):
            return json.dumps({"status": "error", "message": "No analyzed data available for PDF report."})

        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"throughput_{ts}_Analysis_Report.pdf"
            result = window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=default_name,
                file_types=["PDF Files (*.pdf)", "All files (*.*)"]
            )

            if not result:
                return json.dumps({"status": "cancelled", "message": "Download cancelled."})

            pdf_path = result if isinstance(result, str) else result[0]
            self._generate_pdf_report(pdf_path)
            return json.dumps({"status": "ok", "path": pdf_path})
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)})

    def _generate_pdf_report(self, output_path: str) -> None:
        """Generate a professional PDF report of the throughput analysis."""
        doc = SimpleDocTemplate(output_path, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1f2937'),
            spaceAfter=10,
            spaceBefore=12,
            fontName='Helvetica-Bold',
            borderColor=colors.HexColor('#d1d5db'),
            borderWidth=0.5,
            borderPadding=8
        )

        # Report title and metadata
        story.append(Paragraph("Throughput Analysis Report", title_style))
        story.append(Spacer(1, 0.2*inch))

        # Report info
        gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        info_data = [
            ["Report Generated:", gen_time],
            ["Device Type:", "Serial Throughput Analyzer"],
            ["Analysis Tool:", "Throughput Analysis Monitoring System v1.0"],
        ]
        info_table = Table(info_data, colWidths=[2.2*inch, 3.8*inch])
        info_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6b7280')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#111827')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f9fafb'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))

        # Session Summary
        story.append(Paragraph("Session Summary", heading_style))
        summary = self._build_summary()
        summary_data = [
            ["Metric", "Value"],
            ["Total Records Analyzed", f"{summary['rows']:,}"],
            ["Session Duration", f"{summary['seconds']} seconds"],
            ["Average Latency", f"{summary['avg_us']} µs"],
            ["Maximum Latency", f"{summary['max_us']} µs"],
            ["Peak Frame Index", f"Frame {summary['max_frame']}"],
            ["Frames Exceeding Threshold (>2000µs)", f"{summary['blown']:,}"],
        ]
        summary_table = Table(summary_data, colWidths=[2.8*inch, 3.2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 11),
            ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#6b7280')),
            ('TEXTCOLOR', (1, 1), (1, -1), colors.HexColor('#111827')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f9fafb'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.3*inch))

        # Key Performance Metrics
        story.append(Paragraph("Key Performance Metrics", heading_style))
        metrics_data = [
            ["Metric", "Value", "Status"],
            ["Average Response Time", f"{summary['avg_us']} µs", "✓ Measured"],
            ["Maximum Response Time", f"{summary['max_us']} µs", "✓ Measured"],
            ["Blown Frames Count", f"{summary['blown']}", "⚠ Alert Threshold: 2000µs"],
            ["Performance Index", f"{self._calculate_performance_index(summary)}%", "✓ Calculated"],
        ]
        metrics_table = Table(metrics_data, colWidths=[2.0*inch, 1.8*inch, 2.2*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
            ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#6b7280')),
            ('TEXTCOLOR', (1, 1), (1, -1), colors.HexColor('#111827')),
            ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#059669')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f0fdf4'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 0.3*inch))

        # Analysis Insights
        story.append(Paragraph("Analysis Insights & Observations", heading_style))
        insights = self._generate_insights(summary)
        for insight in insights:
            story.append(Paragraph(f"• {insight}", ParagraphStyle('Insight', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#374151'), spaceAfter=6, leftIndent=20)))
        story.append(Spacer(1, 0.2*inch))

        # Recommendations
        story.append(Paragraph("Recommendations", heading_style))
        recommendations = self._generate_recommendations(summary)
        for rec in recommendations:
            story.append(Paragraph(f"• {rec}", ParagraphStyle('Rec', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#374151'), spaceAfter=6, leftIndent=20)))
        story.append(Spacer(1, 0.2*inch))

        # Data Characteristics
        story.append(Paragraph("Data Characteristics", heading_style))
        characteristics_data = [
            ["Total Samples Collected", f"{summary['rows']:,}"],
            ["Session Time Span", f"{summary['seconds']} seconds"],
            ["Sampling Rate", f"~{summary['rows'] // max(summary['seconds'], 1)} samples/sec"],
            ["Data Quality", "Complete"],
        ]
        char_table = Table(characteristics_data, colWidths=[2.5*inch, 3.5*inch])
        char_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 9),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6b7280')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#111827')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f9fafb'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(char_table)
        story.append(Spacer(1, 0.3*inch))

        # Conclusion
        story.append(Paragraph("Conclusion", heading_style))
        conclusion = self._generate_conclusion(summary)
        story.append(Paragraph(conclusion, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        # Footer
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#9ca3af'), alignment=TA_CENTER)
        story.append(Paragraph("This report was automatically generated by the Throughput Analysis Tool.", footer_style))

        doc.build(story)

    def _calculate_performance_index(self, summary: dict) -> int:
        """Calculate a performance index (0-100) based on analysis metrics."""
        if summary['rows'] == 0:
            return 0
        # Performance inversely proportional to blown frames
        blown_ratio = summary['blown'] / max(summary['rows'], 1)
        performance = int(max(0, 100 - (blown_ratio * 100)))
        return performance

    def _generate_insights(self, summary: dict) -> list[str]:
        """Generate insights based on analysis data."""
        insights = []
        if summary['rows'] > 0:
            insights.append(f"Analyzed {summary['rows']:,} data points over {summary['seconds']} seconds of operation.")
            if summary['blown'] == 0:
                insights.append("All frame response times remained within the acceptable threshold (<2000µs).")
            else:
                blown_pct = (summary['blown'] / summary['rows']) * 100
                insights.append(f"{blown_pct:.2f}% of frames exceeded the 2000µs performance threshold.")
            if summary['avg_us'] < 500:
                insights.append("Average response time is excellent, indicating optimal system performance.")
            elif summary['avg_us'] < 1000:
                insights.append("Average response time is good with normal operational parameters.")
            else:
                insights.append("Average response time shows moderate latency; monitoring recommended.")
        return insights

    def _generate_recommendations(self, summary: dict) -> list[str]:
        """Generate recommendations based on analysis results."""
        recommendations = []
        if summary['blown'] > 0:
            recommendations.append("Investigate and optimize processes that caused frame delays exceeding the 2000µs threshold.")
            recommendations.append("Consider adjusting scheduler priorities or reducing concurrent workloads.")
        if summary['avg_us'] > 1500:
            recommendations.append("Review system resource utilization and background processes for potential optimization.")
        if summary['max_us'] > 3000:
            recommendations.append("The maximum latency spike indicates a potential bottleneck; prioritize performance profiling.")
        if not recommendations:
            recommendations.append("Current performance metrics are within acceptable ranges. Continue regular monitoring.")
        return recommendations

    def _generate_conclusion(self, summary: dict) -> str:
        """Generate a professional conclusion statement."""
        perf_index = self._calculate_performance_index(summary)
        if perf_index >= 95:
            return f"Overall Performance: Excellent ({perf_index}%). All systems are operating within optimal parameters with minimal frame delays. No immediate action required."
        elif perf_index >= 80:
            return f"Overall Performance: Good ({perf_index}%). System performance is satisfactory with occasional frame delays. Continue standard monitoring practices."
        elif perf_index >= 60:
            return f"Overall Performance: Fair ({perf_index}%). Noticeable frame delays detected. Review recommendations and implement optimization strategies."
        else:
            return f"Overall Performance: Poor ({perf_index}%). Significant performance degradation observed. Immediate investigation and remediation recommended."

    def get_ports(self) -> str:
        ports = serial.tools.list_ports.comports()
        return json.dumps([p.device for p in ports])

    def connect(self, port: str, baud: str) -> str:
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = serial.Serial(port, int(baud), timeout=1.5)
            return json.dumps({"status": "ok", "message": f"Connected to Com Port {port}"})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"Unable to Connect To Com Port {port}"})

    def disconnect(self) -> str:
        self._running = False
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass
        return json.dumps({"status": "ok"})

    def start_analysis(self) -> str:
        if not self._ser or not self._ser.is_open:
            return json.dumps({"status": "error", "message": "Not connected to any port."})
        try:
          self._reset_session_state()
          self._ser.reset_input_buffer()
          self._ser.write(START_FRAME)
          self._running = True
          self._thread = threading.Thread(target=self._receive_loop, daemon=True)
          self._thread.start()
          return json.dumps({"status": "ok"})
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)})

    def _receive_loop(self):
        second = 0
        while self._running:
            try:
                chunk = self._ser.read(CHUNK_SIZE)
            except Exception as exc:
                if self._running:
                    window.evaluate_js(
                        f"window._app && window._app.onError({json.dumps(str(exc))})" # check this
                    )
                break
            if len(chunk) != CHUNK_SIZE:
                continue
            second += 1
            rows: list[tuple[int, int, int]] = []
            chunk_total_us = 0
            chunk_blown = 0
            chunk_max_us = -1
            chunk_max_frame = 0
            for i, raw in enumerate(chunk):
                rows.append((second, i, raw))   # store raw percent (0-100)
                raw_us = raw * SCALE_FACTOR
                chunk_total_us += raw_us
                if raw_us > BLOWN_THRESHOLD:
                  chunk_blown += 1
                if raw_us > chunk_max_us:
                    chunk_max_us = raw_us
                    chunk_max_frame = i
            with self._lock:
                self._data.extend(rows)
                self._session_sample_count += len(chunk)
                self._session_total_us += chunk_total_us
                self._session_blown += chunk_blown
                if chunk_max_us > self._session_max_us:
                    self._session_max_us = chunk_max_us
                    self._session_max_frame = chunk_max_frame

            # Pass raw percent values for the scatter plot (frame index → percent)
            frame_data = list(chunk)   # list of 500 percent values
            stats = self._build_summary()

            window.evaluate_js(
                f"window._app && window._app.onChunk({json.dumps({'second': second, 'blown': stats['blown'], 'avg_us': stats['avg_us'], 'max_us': stats['max_us'], 'max_frame': stats['max_frame'], 'frame_data': frame_data})})"
            )

    def stop_analysis(self) -> str:
        self._running = False
        try:
            if not self._ser or not self._ser.is_open:
                return json.dumps({"status": "error", "message": "Serial port not open."})
            self._ser.write(STOP_FRAME)
            deadline = time.time() + ACK_TIMEOUT
            ack = b""
            while time.time() < deadline:
                byte = self._ser.read(1)
                if byte:
                    ack += byte
                if len(ack) >= 7:
                    break
            return json.dumps({
                "status": "ok",
                "message": "Analysis Done, Csv Ready to Export",
                "ack_received": len(ack) > 0,
            })
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)})

    def get_default_csv_name(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"throughput_{ts}.csv"
        home = os.path.expanduser("~")
        return json.dumps({"name": name, "home": home})
        
    def export_csv(self) -> str:
        with self._lock:
            snapshot = list(self._data)
            
        if not snapshot:
            return json.dumps({"status": "error", "message": "No data to export."})
            
        try:
            # 1. Generate default filename
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"throughput_{ts}.csv"
            
            # 2. Open the native Save File Dialog from Python
            result = window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=default_name,
                file_types=["CSV Files (*.csv)", "All files (*.*)"]
            )
            
            # If the user clicks "Cancel" on the dialog
            if not result:
                return json.dumps({"status": "cancelled", "message": "Export cancelled."})
                
            filepath = result if isinstance(result, str) else result[0]

            rows = self._write_snapshot_csv(filepath)
            self._last_exported_csv_path = filepath

            return json.dumps({"status": "ok", "path": filepath, "rows": rows})
            
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)})
   

    def get_summary(self) -> str:
      return json.dumps(self._build_summary())
    
# ─────────────────────────────────────────────
#  Protocol
# ─────────────────────────────────────────────   
    def _calculate_crc16(self, data: bytes | bytearray) -> int:
        """Helper to calculate CRC16 for the ACK validation."""
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
                crc &= 0xFFFF
        return crc
    
    def _validate_ack(self, rx: bytes | bytearray, expected_chunk: int) -> tuple[bool, str]:
        """Strict 12-byte ACK validation from the Flash Tool protocol."""
        if len(rx) != 12:
            return False, f"Invalid Length (Got {len(rx)} bytes)"
        if rx[:3]  != b"\xFE\xFE\xFE":
            return False, "[2] Error While Validating ACK (Start bytes)"
        if rx[9:]  != b"\xFE\xFE\xFE":
            return False, "[3] Error While Validating ACK (End bytes)"
        if rx[3] != 0x41:
            return False, "[4] Error While Validating ACK (Command byte)"
        if rx[6] != 0x00:
            return False, "NACK sent by Controller"

        rx_chunk = (rx[4] << 8) | rx[5]
        rx_crc   = (rx[7] << 8) | rx[8]
        calc_crc = self._calculate_crc16(rx[3:7])
        
        if rx_crc != calc_crc:
            return False, "[5] Error While Validating ACK (CRC Mismatch)"
        if rx_chunk != expected_chunk:
            return False, f"[6] Error While Validating ACK (Expected chunk {expected_chunk})"
            
        return True, "Valid"

# ─────────────────────────────────────────────
#  HTML front-end
# ─────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Throughput Analysis</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  /* Dark theme (default) */
  --bg-dark:  #0f1219;
  --bg-main:  #1a1f2e;
  --bg-card:  #252d3d;
  --surface:  #2a323f;
  --border:   #404857;
  --border-lt: #505870;
  --text-primary: #f5f7fa;
  --text-secondary: #b4b9c8;
  --text-muted: #8a8f9f;
  --blue:     #3b82f6;
  --blue-light: #60a5fa;
  --blue-dark: #1e40af;
  --green:    #10b981;
  --green-light: #34d399;
  --red:      #ef4444;
  --red-light: #f87171;
  --amber:    #f59e0b;
  --purple:   #8b5cf6;
  --cyan:     #06b6d4;
  --r:        12px;
}

body.light-theme {
  /* Light theme */
  --bg-dark:  #ffffff;
  --bg-main:  #ffffff;
  --bg-card:  #ffffff;
  --surface:  #ffffff;
  --border:   #d1d5db;
  --border-lt: #9ca3af;
  --text-primary: #111827;
  --text-secondary: #374151;
  --text-muted: #6b7280;
  --blue:     #2563eb;
  --blue-light: #3b82f6;
  --blue-dark: #1d4ed8;
  --green:    #059669;
  --green-light: #10b981;
  --red:      #dc2626;
  --red-light: #ef4444;
  --amber:    #d97706;
  --purple:   #7c3aed;
  --cyan:     #0891b2;
}
body {
  font-family: 'Inter', system-ui, sans-serif;
  background: linear-gradient(135deg, var(--bg-dark) 0%, var(--bg-main) 100%);
  color: var(--text-primary);
  font-size: 14px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  letter-spacing: 0.3px;
  transition: all 0.3s ease;
}

/* Topbar */
.topbar {
  height: 70px;
  background: linear-gradient(135deg, var(--surface) 0%, rgba(42, 50, 63, 0.6) 100%);
  border-bottom: 1px solid var(--border);
  padding: 0 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
}

body.light-theme .topbar {
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  backdrop-filter: none;
}
.brand { 
  display: flex; 
  align-items: center; 
  gap: 16px; 
}

.logo-mark {
  display: flex; 
  align-items: center; 
  justify-content: center;
  flex-shrink: 0;
  width: 50px;
  height: 50px;
  background: linear-gradient(135deg, var(--blue) 0%, var(--purple) 100%);
  border-radius: 14px;
  box-shadow: 0 8px 20px rgba(59, 130, 246, 0.25);
  transition: all 0.3s ease;
}
.logo-mark:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(59, 130, 246, 0.35);
}
.logo-mark svg { 
  width: 28px; 
  height: 28px; 
}

.brand-text { 
  display: flex; 
  flex-direction: column; 
  gap: 2px; 
}
.brand-name { 
  font-size: 16px; 
  font-weight: 700; 
  letter-spacing: -0.3px;
  background: linear-gradient(135deg, var(--text-primary) 0%, var(--blue-light) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.brand-sub  { 
  font-size: 11px; 
  color: var(--text-muted); 
  font-weight: 400; 
  letter-spacing: 0.5px;
}

.pill {
  display: inline-flex; 
  align-items: center; 
  gap: 8px;
  padding: 8px 16px; 
  border-radius: 999px;
  font-size: 12px; 
  font-weight: 600;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  background: rgba(42, 50, 63, 0.5);
  letter-spacing: 0.5px;
  transition: all 0.3s ease;
}
.pill-dot { 
  width: 8px; 
  height: 8px; 
  border-radius: 50%; 
  background: var(--text-muted);
}
.pill.connected  { 
  border-color: var(--green);
  color: var(--green-light); 
  background: rgba(16, 185, 129, 0.1);
}
.pill.connected .pill-dot { 
  background: var(--green-light);
  box-shadow: 0 0 8px var(--green);
}
.pill.running    { 
  border-color: var(--blue);
  color: var(--blue-light);  
  background: rgba(59, 130, 246, 0.1);
  animation: pulse-pill 2s ease-in-out infinite;
}
.pill.running .pill-dot  { 
  background: var(--blue-light);
  box-shadow: 0 0 12px var(--blue);
  animation: pulse-dot 2s ease-in-out infinite;
}
.pill.done       { 
  border-color: var(--amber);
  color: var(--amber); 
  background: rgba(245, 158, 11, 0.1);
}
.pill.done .pill-dot     { 
  background: var(--amber);
  box-shadow: 0 0 8px var(--amber);
}
@keyframes pulse-pill { 
  0%,100% { opacity: 1; } 
  50% { opacity: 0.7; } 
}
@keyframes pulse-dot { 
  0%,100% { box-shadow: 0 0 12px var(--blue); } 
  50% { box-shadow: 0 0 20px var(--blue); } 
}

/* Theme toggle button */
.theme-toggle {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid var(--border-lt);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.3s ease;
  position: relative;
}
.theme-toggle:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: var(--blue);
  color: var(--blue-light);
  transform: scale(1.05);
}
.theme-toggle:active {
  transform: scale(0.98);
}

body.light-theme .theme-toggle {
  background: #f3f4f6;
  border-color: #d1d5db;
  color: #6b7280;
}

body.light-theme .theme-toggle:hover {
  background: #e5e7eb;
  border-color: #3b82f6;
  color: #3b82f6;
}
.theme-icon {
  width: 18px;
  height: 18px;
  transition: all 0.3s ease;
}

.theme-toggle:hover .theme-icon:not([style*="display: none"]) {
  color: var(--blue-light);
}

.top-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.4px;
  white-space: nowrap;
}

.top-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--red);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
}

.top-status.connected {
  color: var(--green-light);
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.08);
}

.top-status.connected .top-status-dot {
  background: var(--green-light);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15);
}

.top-status.disconnected {
  color: #fca5a5;
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.08);
}

body.light-theme .top-status {
  background: #f9fafb;
}


/* Layout */
.layout { 
  display: flex; 
  flex: 1; 
  overflow: hidden; 
  # flex-direction: row-reverse;
}

/* Right Control Panel */
.control-panel {
  width: 300px;
  flex-shrink: 0;
  background: var(--surface);
  border-left: 1px solid var(--border);
  padding: 18px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

body.light-theme .control-panel {
  background: #ffffff;
  border-left-color: #d1d5db;
}

/* Control rows */
.ctrl-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 10px; 
}

.ctrl-row.full { 
  flex-wrap: nowrap; 
  gap:10px;
}
.ctrl-row select { flex: 1; min-width: 0; }
.ctrl-row.buttons {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 6px;
  margin-top: 4px;
}

/* Icon-only buttons */
.btn-icon {
  width: 38px;
  height: 38px;
  padding: 0;
  min-width: 38px;
  flex-shrink: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
  color: var(--blue-light);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  font-size: 0;
}
.btn-icon svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
.btn-icon:hover {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(139, 92, 246, 0.2) 100%);
  border-color: var(--blue);
  transform: translateY(-1px);
}
.btn-icon:active {
  transform: scale(0.95);
}
.btn-icon:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

body.light-theme .btn-icon {
  background: #f3f4f6;
  color: #3b82f6;
}
body.light-theme .btn-icon:hover {
  background: #e5e7eb;
  border-color: #3b82f6;
}

/* Action buttons row */
.btn-action {
  flex: 1;
  height: 36px;
  border: none;
  border-radius: 7px;
  font-family: 'Inter', sans-serif;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
  padding: 0 10px;
  white-space: nowrap;
}
.btn-action::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.1);
  transition: left 0.3s ease;
}
.btn-action:not(:disabled):hover::before {
  left: 100%;
}
.btn-action svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.btn-action:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-action:not(:disabled):active {
  transform: scale(0.96);
}

.btn-action.start {
  background: linear-gradient(135deg, var(--green) 0%, var(--green-light) 100%);
  color: #fff;
  box-shadow: 0 3px 12px rgba(16, 185, 129, 0.2);
}
.btn-action.start:not(:disabled):hover {
  box-shadow: 0 5px 18px rgba(16, 185, 129, 0.35);
  transform: translateY(-1px);
}

.btn-action.stop {
  background: linear-gradient(135deg, var(--red) 0%, var(--red-light) 100%);
  color: #fff;
  box-shadow: 0 3px 12px rgba(239, 68, 68, 0.2);
}
.btn-action.stop:not(:disabled):hover {
  box-shadow: 0 5px 18px rgba(239, 68, 68, 0.35);
  transform: translateY(-1px);
}

.btn-action.export {
  background: linear-gradient(135deg, var(--purple) 0%, var(--cyan) 100%);
  color: #fff;
  box-shadow: 0 3px 12px rgba(139, 92, 246, 0.2);
}
.btn-action.export:not(:disabled):hover {
  box-shadow: 0 5px 18px rgba(139, 92, 246, 0.35);
  transform: translateY(-1px);
}

.btn-action.analyze {
  background: linear-gradient(135deg, var(--amber) 0%, var(--blue) 100%);
  color: #fff;
  box-shadow: 0 3px 12px rgba(245, 158, 11, 0.2);
}
.btn-action.analyze:not(:disabled):hover {
  box-shadow: 0 5px 18px rgba(245, 158, 11, 0.35);
  transform: translateY(-1px);
}

.btn-action.download {
  background: linear-gradient(135deg, var(--green) 0%, var(--blue) 100%);
  color: #fff;
  box-shadow: 0 3px 12px rgba(16, 185, 129, 0.2);
}
.btn-action.download:not(:disabled):hover {
  box-shadow: 0 5px 18px rgba(16, 185, 129, 0.35);
  transform: translateY(-1px);
}

/* Control section label */
.ctrl-section {
  margin-top: 8px;
}
.ctrl-section-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 10px;
  display: block;
}

body.light-theme .ctrl-section-title {
  color: #6b7280;
}

/* Metrics display */
.metrics-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 7px;
  border: 1px solid var(--border);
  transition: all 0.2s ease;
}

body.light-theme .metric-row {
  background: #f9fafb;
  border-color: #e5e7eb;
}

.metric-row:hover {
  border-color: var(--border-lt);
}

.metric-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.metric-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-value.blown { color: var(--red-light); }
.metric-value.avg { color: var(--green-light); }
.metric-value.max { color: var(--amber); }
.metric-value.frame { color: var(--blue-light); }

body.light-theme .metric-value.blown { color: #dc2626; }
body.light-theme .metric-value.avg { color: #059669; }
body.light-theme .metric-value.max { color: #d97706; }
body.light-theme .metric-value.frame { color: #2563eb; }

/* Main content area */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Resizable log area */
.log-container {
  display: flex;
  flex-direction: column;
  height: 140px;
  min-height: 120px;
  flex-shrink: 0;
  border-top: 1px solid var(--border);
}

.log-resizer {
  width: 100%;
  height: 4px;
  background: var(--border);
  cursor: ns-resize;
  transition: background 0.2s ease;
  flex-shrink: 0;
}

.log-resizer:hover {
  background: var(--blue-light);
}

body.light-theme .log-resizer {
  background: #d1d5db;
}

body.light-theme .log-resizer:hover {
  background: #3b82f6;
}

select, input[type=text] {
  width: 100%;
  height: 38px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-lt);
  border-radius: 9px;
  color: var(--text-primary);
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  padding: 0 32px 0 12px;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%238a8f9f' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  transition: all .2s ease;
}
select:hover, input[type=text]:hover {
  border-color: var(--border);
  background-color: rgba(0, 0, 0, 0.3);
}
select:focus, input[type=text]:focus { 
  border-color: var(--blue); 
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
  outline: none;
}

body.light-theme select,
body.light-theme input[type=text] {
  background: #f3f4f6;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%234b5563' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  border-color: #d1d5db;
  color: #111827;
}

body.light-theme select:hover,
body.light-theme input[type=text]:hover {
  background-color: #e5e7eb;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%234b5563' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  border-color: #9ca3af;
}

body.light-theme select:focus,
body.light-theme input[type=text]:focus {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%234b5563' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.btn {
  width: 100%; 
  height: 38px;
  border: 1px solid transparent; 
  border-radius: 9px;
  font-family: 'Inter', sans-serif; 
  font-size: 13px; 
  font-weight: 600;
  cursor: pointer; 
  display: flex; 
  align-items: center; 
  justify-content: center; 
  gap: 8px;
  transition: all .2s ease; 
  margin-bottom: 6px; 
  white-space: nowrap;
  letter-spacing: 0.3px;
  position: relative;
  overflow: hidden;
}
.btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.1);
  transition: left 0.3s ease;
}
.btn:not(:disabled):hover::before {
  left: 100%;
}
.btn svg { 
  flex-shrink: 0; 
  position: relative;
  z-index: 1;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn:not(:disabled):active { transform: scale(.96); }
.btn-blue    { 
  background: linear-gradient(135deg, var(--blue) 0%, var(--blue-light) 100%);
  color: #fff;          
  border-color: var(--blue);
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2);
}
.btn-blue:not(:disabled):hover    { 
  box-shadow: 0 6px 25px rgba(59, 130, 246, 0.35);
  transform: translateY(-1px);
}
.btn-ghost   { 
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-secondary);  
  border-color: var(--border-lt);
}
.btn-ghost:not(:disabled):hover   { 
  background: rgba(255, 255, 255, 0.05);
  border-color: var(--border);
  color: var(--text-primary);
}
.btn-green   { 
  background: linear-gradient(135deg, var(--green) 0%, var(--green-light) 100%);
  color: #fff;  
  border-color: var(--green);
  box-shadow: 0 4px 15px rgba(16, 185, 129, 0.2);
}
.btn-green:not(:disabled):hover   { 
  box-shadow: 0 6px 25px rgba(16, 185, 129, 0.35);
  transform: translateY(-1px);
}
.btn-red     { 
  background: linear-gradient(135deg, var(--red) 0%, var(--red-light) 100%);
  color: #fff;  
  border-color: var(--red);
  box-shadow: 0 4px 15px rgba(239, 68, 68, 0.2);
}
.btn-red:not(:disabled):hover     { 
  box-shadow: 0 6px 25px rgba(239, 68, 68, 0.35);
  transform: translateY(-1px);
}
.btn-purple  { 
  background: linear-gradient(135deg, var(--purple) 0%, var(--cyan) 100%);
  color: #fff; 
  border-color: var(--purple);
  box-shadow: 0 4px 15px rgba(139, 92, 246, 0.2);
}
.btn-purple:not(:disabled):hover  { 
  box-shadow: 0 6px 25px rgba(139, 92, 246, 0.35);
  transform: translateY(-1px);
}
.hr { 
  height: 1px; 
  background: linear-gradient(90deg, transparent, var(--border), transparent);
  margin: 8px 0 4px; 
}

/* Main */
.main { 
  flex: 1; 
  min-width: 0; 
  display: flex; 
  flex-direction: column; 
  overflow: hidden; 
}

/* Stats row — 4 cards */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  padding: 16px 18px;
  background: linear-gradient(135deg, var(--bg-main) 0%, rgba(42, 50, 63, 0.8) 100%);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

body.light-theme .stats {
  background: #ffffff;
}
.scard {
  background: linear-gradient(135deg, var(--surface) 0%, rgba(42, 50, 63, 0.6) 100%);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 16px;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}
.scard::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
}

body.light-theme .scard {
  background: #f9fafb;
  border-color: #e5e7eb;
}

body.light-theme .scard::before {
  background: transparent;
}
.scard:hover {
  border-color: var(--border-lt);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  transform: translateY(-2px);
}
.scard-lbl {
  font-size: 11px; 
  font-weight: 700; 
  letter-spacing: .08em;
  text-transform: uppercase; 
  color: var(--text-muted); 
  margin-bottom: 8px;
}
.scard-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 24px; 
  font-weight: 700; 
  line-height: 1.1; 
  color: var(--text-primary);
}
.scard-val.c-blue   { color: var(--blue-light); }
.scard-val.c-green  { color: var(--green-light); }
.scard-val.c-amber  { color: var(--amber); }
.scard-val.c-red    { color: var(--red-light); }
.scard-val.c-purple { color: var(--purple); }
.scard-unit { 
  font-size: 10px; 
  color: var(--text-muted); 
  margin-top: 6px; 
  letter-spacing: 0.5px;
}
.scard-sub  { 
  font-size: 10px; 
  color: var(--text-muted); 
  margin-top: 4px; 
  font-family: 'JetBrains Mono', monospace; 
}

/* Chart area */
.chart-area {
  flex: 1; 
  min-height: 0;
  padding: 16px 18px 12px;
  display: flex; 
  flex-direction: column; 
  gap: 12px;
}
.chart-hdr {
  display: flex; 
  align-items: center; 
  justify-content: space-between; 
  flex-shrink: 0;
}
.chart-ttl { 
  font-size: 14px; 
  font-weight: 700;
  letter-spacing: 0.3px;
}
.legend { 
  display: flex; 
  gap: 18px; 
}
.leg-item { 
  display: flex; 
  align-items: center; 
  gap: 6px; 
  font-size: 11px; 
  color: var(--text-muted);
  letter-spacing: 0.3px;
}
.leg-sq { 
  width: 10px; 
  height: 10px; 
  border-radius: 4px;
}
.leg-sq.blown { 
  background: linear-gradient(135deg, var(--red) 0%, var(--red-light) 100%);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
}
.leg-sq.ok    { 
  background: linear-gradient(135deg, var(--blue) 0%, var(--blue-light) 100%);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}
.leg-ln { 
  width: 14px; 
  height: 2px; 
  border-top: 2px dashed var(--amber);
}

.chart-box {
  flex: 1; 
  min-height: 0; 
  position: relative;
  background: linear-gradient(135deg, var(--surface) 0%, rgba(42, 50, 63, 0.6) 100%);
  border: 1px solid var(--border);
  border-radius: var(--r); 
  overflow: hidden;
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.3);
}
canvas#chart { 
  position: absolute; 
  inset: 0; 
  width: 100%; 
  height: 100%; 
}

body.light-theme .chart-box {
  background: #f9fafb;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* Log */
.log {
  flex: 1;
  min-height: 0;
  border-top: 1px solid var(--border);
  background: linear-gradient(135deg, var(--surface) 0%, rgba(42, 50, 63, 0.6) 100%);
  display: flex; 
  flex-direction: column;
}

body.light-theme .log {
  background: #ffffff;
}
.log-hdr {
  padding: 10px 18px; 
  border-bottom: 1px solid var(--border);
  font-size: 11px; 
  font-weight: 700; 
  letter-spacing: .1em;
  text-transform: uppercase; 
  color: var(--text-muted); 
  flex-shrink: 0;
}
.log-body { 
  flex: 1; 
  overflow-y: auto; 
  padding: 8px 18px 10px;
}
.log-entry {
  font-family: 'JetBrains Mono', monospace; 
  font-size: 12px;
  line-height: 1.8; 
  color: var(--text-muted);
  padding-left: 12px; 
  border-left: 3px solid transparent;
  transition: all 0.2s ease;
  margin-bottom: 2px;
}
.log-entry:hover {
  color: var(--text-primary);
  # padding-left: 14px;
}
.log-entry.ok   { 
  color: var(--green-light); 
  border-color: var(--green);
}
.log-entry.err  { 
  color: var(--red-light);   
  border-color: var(--red);
}
.log-entry.info { 
  color: var(--blue-light);  
  border-color: var(--blue);
}
.log-entry.warn { 
  color: var(--amber); 
  border-color: var(--amber);
}

body.light-theme .log-entry {
  color: #6b7280;
}

body.light-theme .log-entry.ok { 
  color: #059669; 
  border-color: #10b981;
}

body.light-theme .log-entry.err { 
  color: #dc2626;   
  border-color: #dc2626;
}

body.light-theme .log-entry.info { 
  color: #2563eb;  
  border-color: #2563eb;
}

body.light-theme .log-entry.warn { 
  color: #d97706; 
  border-color: #d97706;
}

/* Toast */
#toast {
  position: fixed; 
  bottom: 24px; 
  right: 24px;
  background: linear-gradient(135deg, var(--bg-dark) 0%, var(--surface) 100%);
  color: var(--text-primary); 
  font-size: 13px; 
  font-weight: 600;
  padding: 14px 20px; 
  border-radius: var(--r);
  opacity: 0; 
  transform: translateY(8px) scale(0.95);
  transition: all .3s cubic-bezier(.16,1,.3,1);
  pointer-events: none; 
  z-index: 9999;
  max-width: 380px; 
  line-height: 1.5;
  border: 1px solid var(--border);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  letter-spacing: 0.3px;
}
#toast.success { 
  background: linear-gradient(135deg, var(--green) 0%, var(--green-light) 100%);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 8px 32px rgba(16, 185, 129, 0.25);
}
#toast.show    { 
  opacity: 1; 
  transform: translateY(0) scale(1); 
  pointer-events: auto;
}

body.light-theme #toast {
  background: #1f2937;
  color: #ffffff;
  border-color: #374151;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  background: rgba(7, 10, 18, 0.65);
  backdrop-filter: blur(8px);
  z-index: 10000;
  padding: 24px;
}
.modal-backdrop.show {
  display: flex;
}
.modal-card {
  width: min(420px, 100%);
  border-radius: 18px;
  border: 1px solid var(--border);
  background: linear-gradient(180deg, var(--surface) 0%, var(--bg-dark) 100%);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
  padding: 24px;
  text-align: center;
}
.modal-title {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 12px;
}
.modal-message {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.4;
  margin-bottom: 20px;
}
.modal-close {
  border: none;
  border-radius: 10px;
  height: 40px;
  padding: 0 18px;
  min-width: 96px;
  cursor: pointer;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--blue) 0%, var(--green) 100%);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.25);
}
.modal-close:hover {
  transform: translateY(-1px);
}

body.light-theme .modal-card {
  background: #ffffff;
  border-color: #d1d5db;
}

body.light-theme .modal-title {
  color: #6b7280;
}

body.light-theme .modal-message {
  color: #111827;
}

body.light-theme .modal-close {
  background: linear-gradient(135deg, #2563eb 0%, #059669 100%);
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
}

body.light-theme .modal-close:hover {
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.3);
}

/* Metric Detail Modal Styles */
.metric-modal-card {
  width: min(640px, 95%);
  border-radius: 18px;
  border: 1px solid var(--border);
  background: linear-gradient(180deg, var(--surface) 0%, var(--bg-dark) 100%);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
  padding: 28px;
  text-align: left;
  max-height: 80vh;
  overflow-y: auto;
  position: relative;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.metric-modal-card::-webkit-scrollbar {
  width: 8px;
}

.metric-modal-card::-webkit-scrollbar-track {
  background: transparent;
}

.metric-modal-card::-webkit-scrollbar-thumb {
  background: rgba(59, 130, 246, 0.3);
  border-radius: 4px;
}

.metric-modal-card::-webkit-scrollbar-thumb:hover {
  background: rgba(59, 130, 246, 0.5);
}

body.light-theme .metric-modal-card::-webkit-scrollbar-thumb {
  background: rgba(37, 99, 235, 0.2);
}

body.light-theme .metric-modal-card::-webkit-scrollbar-thumb:hover {
  background: rgba(37, 99, 235, 0.4);
}

body.light-theme .metric-modal-card {
  background: #ffffff;
  border-color: #d1d5db;
}

.metric-modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--border);
}

body.light-theme .metric-modal-header {
  border-bottom-color: #e5e7eb;
}

.metric-modal-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  background: rgba(59, 130, 246, 0.1);
  color: var(--blue-light);
}

.metric-modal-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

body.light-theme .metric-modal-title {
  color: #111827;
}

.metric-modal-subtitle {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  margin-top: 2px;
}

.metric-detail-section {
  margin-bottom: 18px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.15);
  border: 1px solid var(--border);
}

body.light-theme .metric-detail-section {
  background: #f9fafb;
  border-color: #e5e7eb;
}

.metric-detail-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 6px;
}

.metric-detail-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-all;
}

body.light-theme .metric-detail-value {
  color: #111827;
}

.metric-detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
}

body.light-theme .metric-detail-row {
  border-bottom-color: #e5e7eb;
}

.metric-detail-row:last-child {
  border-bottom: none;
}

.metric-detail-row-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
}

.metric-detail-row-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

body.light-theme .metric-detail-row-value {
  color: #111827;
}

.metric-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 8px;
}

.metric-table th {
  background: rgba(59, 130, 246, 0.08);
  padding: 8px 10px;
  text-align: left;
  font-size: 10px;
  font-weight: 700;
  color: var(--blue-light);
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

body.light-theme .metric-table th {
  background: #eff6ff;
  color: #2563eb;
  border-bottom-color: #dbeafe;
}

.metric-table td {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

body.light-theme .metric-table td {
  border-bottom-color: #f3f4f6;
  color: #374151;
}

.metric-table td:first-child {
  color: var(--text-primary);
  font-weight: 600;
}

body.light-theme .metric-table td:first-child {
  color: #111827;
}

.metric-formula {
  background: rgba(0, 0, 0, 0.2);
  padding: 10px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--green-light);
  margin-top: 8px;
  line-height: 1.4;
}

body.light-theme .metric-formula {
  background: #f0fdf4;
  color: #059669;
}

.metric-modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

body.light-theme .metric-modal-footer {
  border-top-color: #e5e7eb;
}

.modal-btn-close {
  border: none;
  border-radius: 10px;
  height: 38px;
  padding: 0 18px;
  min-width: 90px;
  cursor: pointer;
  font-weight: 700;
  font-size: 12px;
  color: #fff;
  background: linear-gradient(135deg, var(--blue) 0%, var(--blue-light) 100%);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
  transition: all 0.2s ease;
}

.modal-btn-close:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.35);
}

body.light-theme .modal-btn-close {
  background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.15);
}

body.light-theme .modal-btn-close:hover {
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.25);
}

/* Close button for metric modals */
.metric-modal-close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.1);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  padding: 0;
  line-height: 1;
}

.metric-modal-close-btn:hover {
  background: rgba(59, 130, 246, 0.2);
  transform: scale(1.05);
}

.metric-modal-close-btn:active {
  transform: scale(0.95);
}

body.light-theme .metric-modal-close-btn {
  background: rgba(37, 99, 235, 0.08);
  color: #111827;
}

body.light-theme .metric-modal-close-btn:hover {
  background: rgba(37, 99, 235, 0.15);
}

/* Make stat cards clickable */
.scard {
  cursor: pointer;
}

.scard.clickable {
  position: relative;
}

.scard.clickable::after {
  content: '';
  position: absolute;
  bottom: 6px;
  right: 6px;
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-top: 8px solid transparent;
  border-right: 8px solid var(--border-lt);
  border-bottom: 8px solid var(--border-lt);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.scard.clickable:hover::after {
  opacity: 0.5;
}

/* Light theme scrollbar for metric modal */
body.light-theme .metric-modal-card::-webkit-scrollbar {
  width: 6px;
}

body.light-theme .metric-modal-card::-webkit-scrollbar-track {
  background: transparent;
}

body.light-theme .metric-modal-card::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}

body.light-theme .metric-modal-card::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

/* Light theme button styles */
body.light-theme .btn-action {
  border: 1px solid transparent;
}

body.light-theme .btn-action.start {
  background: linear-gradient(135deg, #059669 0%, #10b981 100%);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(5, 150, 105, 0.2);
}

body.light-theme .btn-action.start:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(5, 150, 105, 0.3);
}

body.light-theme .btn-action.stop {
  background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(220, 38, 38, 0.2);
}

body.light-theme .btn-action.stop:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(220, 38, 38, 0.3);
}

body.light-theme .btn-action.export {
  background: linear-gradient(135deg, #7c3aed 0%, #0891b2 100%);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(124, 58, 237, 0.2);
}

body.light-theme .btn-action.export:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(124, 58, 237, 0.3);
}

body.light-theme .btn-action.analyze {
  background: linear-gradient(135deg, #d97706 0%, #2563eb 100%);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(217, 119, 6, 0.2);
}

body.light-theme .btn-action.analyze:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(217, 119, 6, 0.3);
}

body.light-theme .btn-action.download {
  background: linear-gradient(135deg, #059669 0%, #2563eb 100%);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(5, 150, 105, 0.2);
}

body.light-theme .btn-action.download:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(5, 150, 105, 0.3);
}

body.light-theme .btn {
  transition: all .2s ease;
}

body.light-theme .btn-blue {
  background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
  color: #ffffff;
  border-color: #2563eb;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.2);
}

body.light-theme .btn-blue:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.3);
}

body.light-theme .btn-ghost {
  background: #f3f4f6;
  color: #374151;
  border-color: #d1d5db;
}

body.light-theme .btn-ghost:not(:disabled):hover {
  background: #e5e7eb;
  border-color: #9ca3af;
  color: #111827;
}

body.light-theme .btn-green {
  background: linear-gradient(135deg, #059669 0%, #10b981 100%);
  color: #ffffff;
  border-color: #059669;
  box-shadow: 0 2px 8px rgba(5, 150, 105, 0.2);
}

body.light-theme .btn-green:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(5, 150, 105, 0.3);
}

body.light-theme .btn-red {
  background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
  color: #ffffff;
  border-color: #dc2626;
  box-shadow: 0 2px 8px rgba(220, 38, 38, 0.2);
}

body.light-theme .btn-red:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(220, 38, 38, 0.3);
}

body.light-theme .btn-purple {
  background: linear-gradient(135deg, #7c3aed 0%, #0891b2 100%);
  color: #ffffff;
  border-color: #7c3aed;
  box-shadow: 0 2px 8px rgba(124, 58, 237, 0.2);
}

body.light-theme .btn-purple:not(:disabled):hover {
  box-shadow: 0 4px 16px rgba(124, 58, 237, 0.3);
}

/* Light theme pill styles */
body.light-theme .pill {
  background: #f3f4f6;
  border-color: #d1d5db;
  color: #374151;
}

body.light-theme .pill.connected {
  border-color: #10b981;
  color: #059669;
  background: rgba(5, 150, 105, 0.08);
}

body.light-theme .pill.connected .pill-dot {
  background: #10b981;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.3);
}

body.light-theme .pill.running {
  border-color: #3b82f6;
  color: #2563eb;
  background: rgba(37, 99, 235, 0.08);
}

body.light-theme .pill.running .pill-dot {
  background: #3b82f6;
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.2);
}

body.light-theme .pill.done {
  border-color: #f59e0b;
  color: #d97706;
  background: rgba(217, 119, 6, 0.08);
}

body.light-theme .pill.done .pill-dot {
  background: #f59e0b;
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.2);
}

/* Light theme status styles */
body.light-theme .top-status.disconnected {
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(220, 38, 38, 0.08);
}

body.light-theme .top-status.disconnected .top-status-dot {
  background: #dc2626;
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1);
}

/* Light theme chart area */
body.light-theme .chart-hdr {
  color: #111827;
}

body.light-theme .chart-ttl {
  color: #111827;
  font-weight: 700;
}

body.light-theme .leg-item {
  color: #6b7280;
}

/* Light theme log area */
body.light-theme .log-hdr {
  color: #6b7280;
  border-bottom-color: #d1d5db;
}

body.light-theme .log-body {
  background: #ffffff;
}

/* Light theme for scard hover */
body.light-theme .scard:hover {
  border-color: #bfdbfe;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
}

/* Light theme scrollbar */
body.light-theme ::-webkit-scrollbar-track {
  background: transparent;
}

body.light-theme ::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 6px;
}

body.light-theme ::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

/* Light theme hr divider */
body.light-theme .hr {
  background: linear-gradient(90deg, transparent, #d1d5db, transparent);
}

/* Light theme modal backdrop */
body.light-theme .modal-backdrop {
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(8px);
}

::-webkit-scrollbar { 
  width: 6px; 
}
::-webkit-scrollbar-track { 
  background: transparent; 
}
::-webkit-scrollbar-thumb { 
  background: var(--border-lt); 
  border-radius: 6px;
  transition: all 0.2s ease;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--border);
}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <!-- Logo mark -->
    <div class="logo-mark">
      <svg viewBox="0 0 38 38" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="lg1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#3b6fe0"/>
            <stop offset="100%" stop-color="#6c3aed"/>
          </linearGradient>
        </defs>
        <!-- Background rounded rect -->
        <rect width="38" height="38" rx="9" fill="url(#lg1)"/>
        <!-- Waveform / throughput bars -->
        <rect x="5"  y="22" width="4" height="11" rx="1.5" fill="rgba(255,255,255,0.5)"/>
        <rect x="11" y="16" width="4" height="17" rx="1.5" fill="rgba(255,255,255,0.7)"/>
        <rect x="17" y="10" width="4" height="23" rx="1.5" fill="rgba(255,255,255,0.9)"/>
        <rect x="23" y="14" width="4" height="19" rx="1.5" fill="rgba(255,255,255,0.75)"/>
        <rect x="29" y="19" width="4" height="14" rx="1.5" fill="rgba(255,255,255,0.55)"/>
        <!-- Trend line over bars -->
        <polyline points="7,20 13,14 19,8 25,12 31,17"
                  fill="none" stroke="#fff" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
        <!-- Dot on peak -->
        <circle cx="19" cy="8" r="2.2" fill="#fff"/>
      </svg>
    </div>
    <div class="brand-text">
      <span class="brand-name">Throughput Analysis</span>
      <span class="brand-sub">Serial Monitor &amp; Frame Inspector</span>
    </div>
  </div>
  <div style="display: flex; align-items: center; gap: 12px;">
    <div class="top-status disconnected" id="usbStatus">
      <span class="top-status-dot" id="usbStatusDot"></span>
      <span id="usbStatusText">Disconnected</span>
    </div>
    <button class="theme-toggle" id="themeToggle" title="Toggle dark/light theme">
      <svg class="theme-icon" id="sunIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      </svg>
      <svg class="theme-icon" id="moonIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: none;">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
    </button>
  </div>
</div>

<div class="layout">

  <div class="main">
    <div class="stats">
      <div class="scard clickable" id="cardFrameBlown" onclick="app.openMetricModal('frameBlownModal')">
        <div class="scard-lbl">Frames Blown</div>
        <div class="scard-val c-red" id="svBlown">—</div>
      </div>
      <div class="scard clickable" id="cardAvgTime" onclick="app.openMetricModal('avgTimeModal')">
        <div class="scard-lbl">Average Time</div>
        <div class="scard-val c-green" id="svAvg">—</div>
        <div class="scard-unit">microseconds</div>
      </div>
      <div class="scard clickable" id="cardMaxTime" onclick="app.openMetricModal('maxTimeModal')">
        <div class="scard-lbl">Maximum Time</div>
        <div class="scard-val c-amber" id="svMaxTime">—</div>
        <div class="scard-unit">microseconds</div>
      </div>
      <div class="scard clickable" id="cardPeakFrame" onclick="app.openMetricModal('peakFrameModal')">
        <div class="scard-lbl">Peak Frame</div>
        <div class="scard-val c-blue" id="svMaxFrame">—</div>
      </div>
    </div>

    <!-- Chart area -->
    <div class="chart-area">
      <div class="chart-hdr">
        <span class="chart-ttl">Analysis Data View</span>
        <div class="legend">
          <div class="leg-item"><div class="leg-sq ok"></div>Normal (&le;2000µs)</div>
          <div class="leg-item"><div class="leg-sq blown"></div>Blown (&gt;2000µs)</div>
          <div class="leg-item"><div class="leg-ln"></div>2000µs threshold</div>
        </div>
      </div>
      <div class="chart-box"><canvas id="chart"></canvas></div>
    </div>
  </div>

  <!-- Right Control Panel -->
  <div class="control-panel">
    <!-- Connection Section -->
    <div class="ctrl-section">
      <span class="ctrl-section-title">Connection</span>
      
      <!-- Row 1: COM Port + Refresh -->
      <div class="ctrl-row full">
        <select id="portSel"><option value="">Select port…</option></select>
        <button class="btn-icon" id="btnRefresh" title="Refresh ports" onclick="app.refreshPorts()">
          <svg id="refreshIcon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 8a7 7 0 1 0 2-4.9"/>
            <polyline points="1,3 1,8 6,8"/>
          </svg>
        </button>
      </div>
      
      <!-- Row 2: Baud Rate + Connect -->
      <div class="ctrl-row full">
        <select id="baudSel">
          <option>9600</option><option>19200</option><option>38400</option>
          <option selected>57600</option><option>115200</option>
          <option>230400</option><option>460800</option><option>921600</option>
        </select>
        <button class="btn-icon" id="btnConn" onclick="app.toggleConnect()" title="Connect/Disconnect">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="5" cy="11" r="2"/><circle cx="11" cy="5" r="2"/><line x1="6.5" y1="9.5" x2="9.5" y2="6.5"/></svg>
        </button>
      </div>
    </div>

    <!-- Analysis Section -->
    <div class="ctrl-section">
      <span class="ctrl-section-title">Analysis</span>
      
      <div class="ctrl-row buttons">
        <button class="btn-action start" id="btnStart" onclick="app.startAnalysis()" title="Start Analysis" disabled>
          <svg viewBox="0 0 16 16" fill="currentColor"><polygon points="4,2 14,8 4,14"/></svg>
          Start
        </button>
        <button class="btn-action stop" id="btnStop" onclick="app.stopAnalysis()" title="Stop Analysis" disabled>
          <svg viewBox="0 0 16 16" fill="currentColor"><rect x="3" y="3" width="10" height="10" rx="2"/></svg>
          Stop
        </button>
        <button class="btn-action export" id="btnExport" onclick="app.exportCsv()" title="Export CSV" disabled>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v9M4 7l4 4 4-4"/><line x1="2" y1="14" x2="14" y2="14"/></svg>
          CSV
        </button>
      </div>
      <div class="hr"></div>
      <div class="ctrl-row buttons" style="grid-template-columns: 1fr 1fr 1fr;">
        <button class="btn-action analyze" id="btnAnalyze" onclick="app.analyze()" title="Run Analysis" disabled>
          <svg viewBox="0 0 16 16" fill="currentColor"><path d="M3 3h10v2H3zm0 4h10v2H3zm0 4h7v2H3z"/></svg>
          Analyze
        </button>
        <button class="btn-action download" id="btnDownloadExcel" onclick="app.downloadExcel()" title="Download Excel" disabled>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v9M4 7l4 4 4-4"/><path d="M3 14h10"/></svg>
          Excel
        </button>
        <button class="btn-action download" id="btnDownloadPdf" onclick="app.downloadPdf()" title="Download PDF" disabled>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v9M4 7l4 4 4-4"/><path d="M3 14h10"/></svg>
          PDF
        </button>
      </div>
    </div>
  </div>

</div>

<div id="toast"></div>
<div class="modal-backdrop" id="analysisModal">
  <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="analysisModalTitle">
    <div class="modal-title" id="analysisModalTitle">Analysis Complete</div>
    <div class="modal-message" id="analysisModalMessage">Patterns Analyzed Successfully</div>
    <button class="modal-close" type="button" onclick="app.closeAnalysisModal()">OK</button>
  </div>
</div>

<!-- Metric Detail Modals -->
<div class="modal-backdrop" id="frameBlownModal">
  <div class="metric-modal-card" role="dialog" aria-modal="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('frameBlownModal')" aria-label="Close">×</button>
    <div class="metric-modal-header">
      <div class="metric-modal-icon">⚠️</div>
      <div>
        <div class="metric-modal-title" id="blownModalTitle">Frames Blown</div>
        <div class="metric-modal-subtitle">Threshold Exceedance Analysis</div>
      </div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Percentage of Total Frames</div>
      <div class="metric-detail-value" id="blownPercent">—</div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Definition</div>
      <div class="metric-detail-value" style="font-size: 12px; font-weight: 400;">Frames with processing time exceeding 2000 microseconds</div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label" id="blownFramesCountLabel">All Blown Frames</div>
      <table class="metric-table">
        <thead>
          <tr><th>Rank</th><th>Frame #</th><th>Time (µs)</th></tr>
        </thead>
        <tbody id="blownFramesList"></tbody>
      </table>
    </div>
    <div class="metric-modal-footer">
      <button class="modal-btn-close" onclick="app.closeMetricModal('frameBlownModal')">Close</button>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="avgTimeModal">
  <div class="metric-modal-card" role="dialog" aria-modal="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('avgTimeModal')" aria-label="Close">×</button>
    <div class="metric-modal-header">
      <div class="metric-modal-icon">📊</div>
      <div>
        <div class="metric-modal-title">Average Time</div>
        <div class="metric-modal-subtitle">Mean Processing Latency</div>
      </div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Average Value</div>
      <div class="metric-detail-value" id="avgValue">—</div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Summary</div>
      <div class="metric-detail-row">
        <span class="metric-detail-row-label">Total Accumulated Time</span>
        <span class="metric-detail-row-value" id="avgTotalTime">—</span>
      </div>
      <div class="metric-detail-row">
        <span class="metric-detail-row-label">Number of Frames</span>
        <span class="metric-detail-row-value" id="avgFrameCount">—</span>
      </div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Interpretation</div>
      <div class="metric-detail-value" style="font-size: 12px; font-weight: 400;" id="avgInterpretation">—</div>
    </div>
    <div class="metric-modal-footer">
      <button class="modal-btn-close" onclick="app.closeMetricModal('avgTimeModal')">Close</button>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="maxTimeModal">
  <div class="metric-modal-card" role="dialog" aria-modal="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('maxTimeModal')" aria-label="Close">×</button>
    <div class="metric-modal-header">
      <div class="metric-modal-icon">⏱️</div>
      <div>
        <div class="metric-modal-title">Maximum Time</div>
        <div class="metric-modal-subtitle">Peak Processing Latency</div>
      </div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Peak Value</div>
      <div class="metric-detail-value" id="maxValue">—</div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Top 10 Highest Processing Times</div>
      <table class="metric-table">
        <thead>
          <tr><th>Rank</th><th>Frame #</th><th>Time (µs)</th><th>Timestamp (s)</th></tr>
        </thead>
        <tbody id="maxFramesList"></tbody>
      </table>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Analysis</div>
      <div class="metric-detail-row">
        <span class="metric-detail-row-label">Exceeds Threshold by</span>
        <span class="metric-detail-row-value" id="maxExceedance">—</span>
      </div>
      <div class="metric-detail-row">
        <span class="metric-detail-row-label">Peak Frame Index</span>
        <span class="metric-detail-row-value" id="maxFrameIndex">—</span>
      </div>
    </div>
    <div class="metric-modal-footer">
      <button class="modal-btn-close" onclick="app.closeMetricModal('maxTimeModal')">Close</button>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="peakFrameModal">
  <div class="metric-modal-card" role="dialog" aria-modal="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('peakFrameModal')" aria-label="Close">×</button>
    <div class="metric-modal-header">
      <div class="metric-modal-icon">🎯</div>
      <div>
        <div class="metric-modal-title">Peak Frame</div>
        <div class="metric-modal-subtitle">Maximum Latency Frame Details</div>
      </div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Peak Frame Index</div>
      <div class="metric-detail-value" id="peakFrameNum">—</div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Peak Processing Time</div>
      <div class="metric-detail-value" id="peakFrameTime">—</div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Status</div>
      <div class="metric-detail-row">
        <span class="metric-detail-row-label">Exceeds Threshold</span>
        <span class="metric-detail-row-value" id="peakFrameStatus">—</span>
      </div>
      <div class="metric-detail-row">
        <span class="metric-detail-row-label">Exceedance Margin</span>
        <span class="metric-detail-row-value" id="peakFrameExceed">—</span>
      </div>
    </div>
    <div class="metric-detail-section">
      <div class="metric-detail-label">Explanation</div>
      <div class="metric-detail-value" style="font-size: 12px; font-weight: 400;">This frame has the highest recorded processing latency in the entire session. It represents the worst-case scenario for system performance.</div>
    </div>
    <div class="metric-modal-footer">
      <button class="modal-btn-close" onclick="app.closeMetricModal('peakFrameModal')">Close</button>
    </div>
  </div>
</div>

<script>
// ── Chart ─────────────────────────────────────────────────────────────────────
const cvs = document.getElementById('chart');
const ctx = cvs.getContext('2d');
let latestChunk = null;   // array of 500 percent values (0-100)
function drawChart() {
  const cvs = document.getElementById('chart');
  const ctx = cvs.getContext('2d');
  const box = cvs.parentElement.getBoundingClientRect();
  const W = box.width, H = box.height;
  if (W === 0 || H === 0) return;
  const dpr = window.devicePixelRatio || 1;
  cvs.width = W * dpr; cvs.height = H * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  
  // Detect light theme
  const isLightTheme = document.body.classList.contains('light-theme');
  
  if (!latestChunk) {
    ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
    ctx.font = "14px 'Inter', sans-serif";
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('Start analysis to see live data', W / 2, H / 2);
    return;
  }

  // ── Axes dimensions ──
  const pad = { t: 24, r: 24, b: 48, l: 56 };
  const iW = W - pad.l - pad.r;
  const iH = H - pad.t - pad.b;

  // ── Y axis: 0-100% ──
  ctx.font = "10px 'JetBrains Mono', monospace";
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  
  for (let p = 0; p <= 100; p += 20) {
    const y = pad.t + iH - (p / 100) * iH;
    ctx.strokeStyle = isLightTheme ? 'rgba(200, 200, 200, 0.5)' : 'rgba(80, 88, 112, 0.3)'; 
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + iW, y); ctx.stroke();
    ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
    ctx.fillText(p + '%', pad.l - 10, y);
  }

  // Y axis title
  ctx.save();
  ctx.translate(14, pad.t + iH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.font = "10px 'Inter', sans-serif";
  ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
  ctx.fillText('Scheduler Load %', 0, 0);
  ctx.restore();

  // ── X axis: Frame 0-499 ──
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.font = "10px 'JetBrains Mono', monospace";

  const frameSteps = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 499];
  frameSteps.forEach(f => {
    const x = pad.l + (f / 499) * iW;
    ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
    ctx.fillText(f, x, pad.t + iH + 8);
  });

  // X axis title
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.font = "10px 'Inter', sans-serif";
  ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
  ctx.fillText('Frame Index', pad.l + iW / 2, H - 4);

  // ── Dynamic Threshold Line ──
  const THRESHOLD_US = 2000;
  const SCALE_FACTOR = 20;
  const threshPct = THRESHOLD_US / SCALE_FACTOR; 

  if (threshPct <= 100) {
    const threshY = pad.t + iH - (threshPct / 100) * iH;
    ctx.strokeStyle = isLightTheme ? '#d97706' : '#f59e0b'; 
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.beginPath(); 
    ctx.moveTo(pad.l, threshY); 
    ctx.lineTo(pad.l + iW, threshY); 
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ── Calculate Points ──
  const points = [];
  latestChunk.forEach((pct, frameIdx) => {
    const x = pad.l + (frameIdx / 499) * iW;
    const y = pad.t + iH - (pct / 100) * iH;
    points.push({ x, y, pct });
  });

  // ── Draw Area Gradient ──
  ctx.beginPath();
  ctx.moveTo(points[0].x, pad.t + iH); // Start at bottom-left
  points.forEach(pt => ctx.lineTo(pt.x, pt.y));
  ctx.lineTo(points[points.length - 1].x, pad.t + iH); // Drop to bottom-right
  ctx.closePath();

  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + iH);
  if (isLightTheme) {
    grad.addColorStop(0, 'rgba(37, 99, 235, 0.2)');
    grad.addColorStop(0.5, 'rgba(37, 99, 235, 0.08)');
    grad.addColorStop(1, 'rgba(37, 99, 235, 0.01)');
  } else {
    grad.addColorStop(0, 'rgba(59, 130, 246, 0.25)');
    grad.addColorStop(0.5, 'rgba(59, 130, 246, 0.08)');
    grad.addColorStop(1, 'rgba(59, 130, 246, 0.01)');
  }
  ctx.fillStyle = grad;
  ctx.fill();

  // ── Draw Crisp Top Line ──
  ctx.beginPath();
  points.forEach((pt, i) => {
    if (i === 0) ctx.moveTo(pt.x, pt.y);
    else ctx.lineTo(pt.x, pt.y);
  });
  ctx.strokeStyle = isLightTheme ? '#2563eb' : '#60a5fa';
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.stroke();

  // ── Draw Red Dots for "Blown" Frames ──
  ctx.fillStyle = isLightTheme ? '#dc2626' : '#ef4444';
  points.forEach(pt => {
    if ((pt.pct * SCALE_FACTOR) > THRESHOLD_US) {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 3, 0, Math.PI * 2);
      ctx.fill();
      // Add glow effect
      ctx.strokeStyle = isLightTheme ? 'rgba(220, 38, 38, 0.3)' : 'rgba(239, 68, 68, 0.4)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  });
}
new ResizeObserver(drawChart).observe(document.querySelector('.chart-box'));

// ── App controller ─────────────────────────────────────────────────────────────
const app = (() => {
  let connected = false, running = false, canExport = false, canAnalyze = false, canDownloadExcel = false, analysisRunning = false;
  let lastUsbConnected = null;
  
  // ── Metric Data Storage ──
  let metricData = {
    blown: 0,
    avgUs: 0,
    maxUs: 0,
    maxFrame: 0,
    totalTime: 0,
    frameCount: 0,
    blownFrames: [],
    allFrames: []
  };
  const THRESHOLD_US = 2000;
  const SCALE_FACTOR = 20;

  // ── Theme Management ──
  function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);
  }

  function setTheme(theme) {
    const isDark = theme === 'dark';
    if (isDark) {
      document.body.classList.remove('light-theme');
    } else {
      document.body.classList.add('light-theme');
    }
    localStorage.setItem('theme', theme);
    updateThemeIcons(isDark);
    drawChart(); // Redraw chart with new theme colors
  }

  function toggleTheme() {
    const currentTheme = document.body.classList.contains('light-theme') ? 'light' : 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
  }

  function updateThemeIcons(isDark) {
    const sunIcon = document.getElementById('sunIcon');
    const moonIcon = document.getElementById('moonIcon');

    sunIcon.style.display = isDark ? 'block' : 'none';
    moonIcon.style.display = isDark ? 'none' : 'block';
  }

  // Attach theme toggle listener
  document.getElementById('themeToggle').addEventListener('click', toggleTheme);

  function log(msg, cls = '') {
    toast(msg, cls);
  }

  function toast(msg, cls = '') {
    const t = document.getElementById('toast');
    t.textContent = msg; 
    t.className = cls + ' show';
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove('show'), 4500);
  }

  function setStatus(state, label) {
    const severity = state === 'done' ? 'success' : (state === 'connected' || state === 'running' ? 'info' : (state === 'error' ? 'err' : ''));
    if (label) {
      toast(label, severity);
    }
  }

  function updateUsbStatus(isConnected) {
    if (lastUsbConnected === isConnected) {
      return;
    }

    lastUsbConnected = isConnected;
    const status = document.getElementById('usbStatus');
    const text = document.getElementById('usbStatusText');
    text.textContent = isConnected ? 'Connected' : 'Disconnected';
    status.classList.toggle('connected', isConnected);
    status.classList.toggle('disconnected', !isConnected);
  }

  function sync() {
    const btn = document.getElementById('btnConn');
    btn.title = connected ? 'Disconnect from port' : 'Connect to port';
    document.getElementById('btnStart').disabled  = !connected || running;
    document.getElementById('btnStop').disabled   = !running;
    document.getElementById('btnExport').disabled = !canExport;
    document.getElementById('btnAnalyze').disabled = !canAnalyze || analysisRunning;
    document.getElementById('btnDownloadExcel').disabled = !canDownloadExcel;
  }

  function setStats(blown, avgUs, maxUs, maxFrame) {
    // Update UI
    document.getElementById('svBlown').textContent    = blown    != null ? Number(blown).toLocaleString()   : '—';
    document.getElementById('svAvg').textContent      = avgUs    != null ? Number(avgUs).toLocaleString()   : '—';
    document.getElementById('svMaxTime').textContent  = maxUs    != null ? Number(maxUs).toLocaleString()   : '—';
    document.getElementById('svMaxFrame').textContent = maxFrame != null ? Number(maxFrame).toLocaleString() : '—';
    
    // Store metric data
    metricData.blown = blown || 0;
    metricData.avgUs = avgUs || 0;
    metricData.maxUs = maxUs || 0;
    metricData.maxFrame = maxFrame || 0;
    
    // Calculate total time and frame count
    if (latestChunk && Array.isArray(latestChunk)) {
      metricData.frameCount = latestChunk.length;
      metricData.totalTime = (metricData.avgUs * metricData.frameCount);
      
      // Build frames array with actual times
      metricData.allFrames = latestChunk.map((pct, idx) => ({
        frameIndex: idx,
        percentValue: pct,
        timeUs: pct * SCALE_FACTOR,
        isBlown: (pct * SCALE_FACTOR) > THRESHOLD_US
      }));
      
      // Get blown frames sorted by time (descending)
      metricData.blownFrames = metricData.allFrames
        .filter(f => f.isBlown)
        .sort((a, b) => b.timeUs - a.timeUs);
    }
  }

  async function refreshPorts() {
    const icon = document.getElementById('refreshIcon');
    icon.classList.add('spin');
    const ports = JSON.parse(await window.pywebview.api.get_ports());
    icon.classList.remove('spin');
    const sel = document.getElementById('portSel');
    const prev = sel.value;
    sel.innerHTML = '<option value="">Select port…</option>';
    ports.forEach(p => {
      const o = document.createElement('option');
      o.value = o.textContent = p;
      if (p === prev) o.selected = true;
      sel.appendChild(o);
    });
    log(`Found ${ports.length} port(s)${ports.length ? ': ' + ports.join(', ') : '.'}`, ports.length ? 'info' : '');
  }

  async function toggleConnect() {
    if (connected) {
      await window.pywebview.api.disconnect();
      connected = false; running = false; canExport = false; canAnalyze = false; canDownloadExcel = false; analysisRunning = false;
      updateUsbStatus(false);
      setStatus('', 'Disconnected');
      log('Disconnected.', 'warn');
    } else {
      const port = document.getElementById('portSel').value;
      const baud = document.getElementById('baudSel').value;
      if (!port) { log('Select a COM port first.', 'err'); return; }
      const r = JSON.parse(await window.pywebview.api.connect(port, baud));
      if (r.status === 'ok') {
        connected = true;
        updateUsbStatus(true);
        setStatus('connected', 'Connected');
        log(r.message, 'ok');
      } else {
        updateUsbStatus(false);
        log('Failed: ' + r.message, 'err');
      }
    }
    sync();
  }

  async function startAnalysis() {
    const r = JSON.parse(await window.pywebview.api.start_analysis());
    if (r.status === 'ok') {
      running = true; canExport = false; canAnalyze = false; canDownloadExcel = false; analysisRunning = false;
      latestChunk = null;
      setStats(0, 0, 0, 0); drawChart();
      setStatus('running', 'Running');
      log('Analysis started — receiving chunks every second…', 'info');
    } else {
      log('Start failed: ' + r.message, 'err');
    }
    sync();
  }

  async function stopAnalysis() {
    const r = JSON.parse(await window.pywebview.api.stop_analysis());
    running = false;
    if (r.status === 'ok') {
      canExport = true;
      canAnalyze = true;
      canDownloadExcel = false;
      setStatus('done', 'Complete');
      toast(r.message, 'success');
      log(r.message + (r.ack_received ? ' (ACK received)' : ' (ACK timeout)'), 'ok');
      const s = JSON.parse(await window.pywebview.api.get_summary());
      setStats(s.blown, s.avg_us, s.max_us, s.max_frame);
    } else {
      log('Stop error: ' + r.message, 'err');
    }
    sync();
  }

  async function exportCsv() {
    // We now just call the python function without passing a filepath. 
    // Python handles the dialog natively.
    const r = JSON.parse(await window.pywebview.api.export_csv());
    
    if (r.status === 'ok') {
      toast(`Saved ${Number(r.rows).toLocaleString()} rows → ${r.path}`, 'success');
      log(`CSV exported (${Number(r.rows).toLocaleString()} rows) → ${r.path}`, 'ok');
    } else if (r.status === 'cancelled') {
      log(r.message, 'warn');
    } else {
      log('Export error: ' + r.message, 'err');
    }
  }

  function onChunk(data) {
    latestChunk = data.frame_data;   // 500 percent values
    setStats(data.blown, data.avg_us, data.max_us, data.max_frame);
    drawChart();
  }

  function onError(msg) {
    running = false; analysisRunning = false; setStatus('error', 'Error');
    log('Serial error: ' + msg, 'err'); sync();
  }

  async function analyze() {
    if (analysisRunning) return;
    const r = JSON.parse(await window.pywebview.api.analyze());
    if (r.status === 'ok') {
      analysisRunning = true;
      canDownloadExcel = false;
      toast(r.message, 'info');
      sync();
    } else {
      toast(r.message, 'err');
    }
  }

  async function downloadExcel() {
    const r = JSON.parse(await window.pywebview.api.download_excel());
    if (r.status === 'ok') {
      toast(`Excel downloaded → ${r.path}`, 'success');
    } else if (r.status === 'cancelled') {
      toast(r.message, 'warn');
    } else {
      toast(r.message, 'err');
    }
  }

  function onAnalysisComplete(payload) {
    analysisRunning = false;
    canDownloadExcel = true;
    sync();
    showAnalysisModal(payload && payload.message ? payload.message : 'Patterns Analyzed Successfully');
  }

  function onAnalysisError(msg) {
    analysisRunning = false;
    canDownloadExcel = false;
    toast(msg, 'err');
    sync();
  }

  function showAnalysisModal(message) {
    const modal = document.getElementById('analysisModal');
    const modalMessage = document.getElementById('analysisModalMessage');
    modalMessage.textContent = message;
    modal.classList.add('show');
  }

  function closeAnalysisModal() {
    document.getElementById('analysisModal').classList.remove('show');
  }

  // ── Metric Modal Functions ──
  function openMetricModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    // Populate modal content based on modal type
    if (modalId === 'frameBlownModal') {
      populateBlownFramesModal();
    } else if (modalId === 'avgTimeModal') {
      populateAvgTimeModal();
    } else if (modalId === 'maxTimeModal') {
      populateMaxTimeModal();
    } else if (modalId === 'peakFrameModal') {
      populatePeakFrameModal();
    }
    
    modal.classList.add('show');
  }

  function closeMetricModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('show');
    }
  }

  function populateBlownFramesModal() {
    // Update title dynamically based on count
    const totalBlown = metricData.blown;
    document.getElementById('blownModalTitle').textContent = `${totalBlown.toLocaleString()} Blown Frame${totalBlown !== 1 ? 's' : ''}`;
    
    const blownPercent = metricData.frameCount > 0 
      ? ((metricData.blown / metricData.frameCount) * 100).toFixed(2)
      : '0.00';
    document.getElementById('blownPercent').textContent = `${blownPercent}%`;
    
    // Update label to show total count
    document.getElementById('blownFramesCountLabel').textContent = `All ${totalBlown.toLocaleString()} Blown Frame${totalBlown !== 1 ? 's' : ''}`;
    
    // Generate ALL blown frames (sorted by time, descending)
    const tbody = document.getElementById('blownFramesList');
    tbody.innerHTML = '';
    
    const sortedBlown = metricData.blownFrames
      .sort((a, b) => b.timeUs - a.timeUs);
    
    sortedBlown.forEach((frame, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td>${frame.frameIndex}</td>
        <td>${frame.timeUs.toLocaleString()}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function populateAvgTimeModal() {
    document.getElementById('avgValue').textContent = metricData.avgUs.toLocaleString() + ' µs';
    document.getElementById('avgTotalTime').textContent = metricData.totalTime.toLocaleString() + ' µs';
    document.getElementById('avgFrameCount').textContent = metricData.frameCount.toLocaleString();
    
    // Interpretation
    let interpretation = '';
    if (metricData.avgUs < 500) {
      interpretation = 'Excellent: Average response time is very low, indicating optimal system performance.';
    } else if (metricData.avgUs < 1000) {
      interpretation = 'Good: Average response time is within acceptable range for normal operations.';
    } else if (metricData.avgUs < 1500) {
      interpretation = 'Acceptable: Average response time is moderate. Monitor for potential bottlenecks.';
    } else {
      interpretation = 'Concerning: Average response time is elevated. Consider optimizing system performance.';
    }
    document.getElementById('avgInterpretation').textContent = interpretation;
  }

  function populateMaxTimeModal() {
    document.getElementById('maxValue').textContent = metricData.maxUs.toLocaleString() + ' µs';
    
    const exceedance = metricData.maxUs - THRESHOLD_US;
    document.getElementById('maxExceedance').textContent = exceedance > 0 
      ? `+${exceedance.toLocaleString()} µs (${(exceedance / THRESHOLD_US * 100).toFixed(1)}% over)`
      : 'Within threshold';
    
    document.getElementById('maxFrameIndex').textContent = metricData.maxFrame;
    
    // Generate top 10 highest times
    const tbody = document.getElementById('maxFramesList');
    tbody.innerHTML = '';
    
    const topFrames = metricData.allFrames
      .sort((a, b) => b.timeUs - a.timeUs)
      .slice(0, 10);
    
    topFrames.forEach((frame, idx) => {
      const tr = document.createElement('tr');
      const timestamp = (frame.frameIndex / 500).toFixed(2); // Approximate timestamp
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td>${frame.frameIndex}</td>
        <td>${frame.timeUs.toLocaleString()}</td>
        <td>${timestamp}s</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function populatePeakFrameModal() {
    document.getElementById('peakFrameNum').textContent = `Frame ${metricData.maxFrame}`;
    document.getElementById('peakFrameTime').textContent = metricData.maxUs.toLocaleString() + ' µs';
    
    const exceeds = metricData.maxUs > THRESHOLD_US;
    document.getElementById('peakFrameStatus').textContent = exceeds ? '⚠️ Yes' : '✓ No';
    
    if (exceeds) {
      const exceedance = metricData.maxUs - THRESHOLD_US;
      document.getElementById('peakFrameExceed').textContent = `+${exceedance.toLocaleString()} µs`;
    } else {
      document.getElementById('peakFrameExceed').textContent = 'N/A';
    }
  }

  window.addEventListener('pywebviewready', () => {
    initTheme();
    refreshPorts();
    toast('Tool ready. Select a port and connect.', 'info');
    drawChart();
  });

  return { toggleTheme, toggleConnect, startAnalysis, stopAnalysis, exportCsv, refreshPorts, onChunk, onError, analyze, downloadExcel, onAnalysisComplete, onAnalysisError, closeAnalysisModal, openMetricModal, closeMetricModal };
})();

window._app = app;
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
api    = Api()
window = webview.create_window(
    title    = "Throughput Analysis Tool",
    html     = HTML,
    js_api   = api,
    width    = 1400,
    height   = 800,
    min_size = (1100, 600),
)

if __name__ == "__main__":
    webview.start(gui="edgechromium", debug=False)
