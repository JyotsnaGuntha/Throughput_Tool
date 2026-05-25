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

# ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#  Protocol constants
#  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
START_FRAME = b'\xFE\xFE\xFE\x80\xFE\xFE\xFE'
STOP_FRAME  = b'\xFE\xFE\xFE\x81\xFE\xFE\xFE'
CHUNK_SIZE   = 500
SCALE_FACTOR = 20
ACK_TIMEOUT  = 3.0
BLOWN_THRESHOLD = 2000   # time

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#  Backend API
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
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

        # Extended analytics state
        self._blown_frames_list: list = []          # [{frameIndex, second, timeUs}]
        self._frame_totals: list = [0] * CHUNK_SIZE # running µs sum per frame index
        self._frame_counts: list = [0] * CHUNK_SIZE # sample count per frame index
        self._top10_frames: list = []               # top-10 [{frameIndex, second, timeUs}]

        self._last_exported_csv_path: str | None = None
        self._analysis_excel_path: str | None = None
        self._analysis_pdf_path: str | None = None
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
            self._blown_frames_list = []
            self._frame_totals = [0] * CHUNK_SIZE
            self._frame_counts = [0] * CHUNK_SIZE
            self._top10_frames = []
        self._analysis_excel_path = None
        self._analysis_pdf_path = None
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
                # Extract JSON from output (in case there are debug prints)
                output_text = completed.stdout.strip()
                json_start = output_text.find('{')
                if json_start == -1:
                    raise json.JSONDecodeError("No JSON object found", output_text, 0)
                result = json.loads(output_text[json_start:])
            except (json.JSONDecodeError, ValueError) as e:
                error_msg = f"Analysis completed but the model returned an invalid response: {str(e)}"
                window.evaluate_js(
                    f"window._app && window._app.onAnalysisError({json.dumps(error_msg)})"
                )
                return

            pdf_path = result.get("pdf_path")  # PDF report from ML analysis
            if not pdf_path or not os.path.exists(pdf_path):
                window.evaluate_js(
                    f"window._app && window._app.onAnalysisError({json.dumps('Analysis completed but no PDF report was generated.')})"
                )
                return

            self._analysis_pdf_path = pdf_path
            self._analysis_excel_path = result.get("excel_path")  # Store Excel path as well for reference
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
        if not self._analysis_pdf_path or not os.path.exists(self._analysis_pdf_path):
            return json.dumps({"status": "error", "message": "No analyzed PDF report is available."})

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

            filepath = result if isinstance(result, str) else result[0]
            shutil.copyfile(self._analysis_pdf_path, filepath)
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
        doc = SimpleDocTemplate(output_path, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        story = []

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

        story.append(Paragraph("Throughput Analysis Report", title_style))
        story.append(Spacer(1, 0.2*inch))

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

        story.append(Paragraph("Analysis Insights & Observations", heading_style))
        insights = self._generate_insights(summary)
        for insight in insights:
            story.append(Paragraph(f"• {insight}", ParagraphStyle('Insight', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#374151'), spaceAfter=6, leftIndent=20)))
        story.append(Spacer(1, 0.2*inch))

        story.append(Paragraph("Recommendations", heading_style))
        recommendations = self._generate_recommendations(summary)
        for rec in recommendations:
            story.append(Paragraph(f"• {rec}", ParagraphStyle('Rec', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#374151'), spaceAfter=6, leftIndent=20)))
        story.append(Spacer(1, 0.2*inch))

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

        story.append(Paragraph("Conclusion", heading_style))
        conclusion = self._generate_conclusion(summary)
        story.append(Paragraph(conclusion, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))

        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#9ca3af'), alignment=TA_CENTER)
        story.append(Paragraph("This report was automatically generated by the Throughput Analysis Tool.", footer_style))

        doc.build(story)

    def _calculate_performance_index(self, summary: dict) -> int:
        if summary['rows'] == 0:
            return 0
        blown_ratio = summary['blown'] / max(summary['rows'], 1)
        performance = int(max(0, 100 - (blown_ratio * 100)))
        return performance

    def _generate_insights(self, summary: dict) -> list[str]:
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
        # Get all ports and filter only those that are USB devices
        all_ports = serial.tools.list_ports.comports()
        usb_ports = [
            p.device for p in all_ports 
            if p.vid is not None or "USB" in (p.hwid or "").upper()
        ]
        return json.dumps(usb_ports)

    def connect(self, port: str, baud: str) -> str:
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = serial.Serial(port, int(baud), timeout=1.5)
            return json.dumps({"status": "ok", "message": f"Connected to Com Port {port}"})
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"Unable to Connect To Com Port {port}"})

    def disconnect(self) -> str:
        
        if self._running or self._analysis_running:
            return json.dumps({"status": "error", "message": "Cannot disconnect while an analysis process is running. Please stop it first."})
            
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
                        f"window._app && window._app.onError({json.dumps(str(exc))})"
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
            chunk_blown_frames: list = []          # new blown frames this chunk
            chunk_frame_us: list = []              # µs value per frame in this chunk

            for i, raw in enumerate(chunk):
                rows.append((second, i, raw))
                raw_us = raw * SCALE_FACTOR
                chunk_total_us += raw_us
                chunk_frame_us.append(raw_us)
                if raw_us > BLOWN_THRESHOLD:
                    chunk_blown += 1
                    chunk_blown_frames.append({'frameIndex': i, 'second': second, 'timeUs': raw_us})
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

                # Extended analytics
                self._blown_frames_list.extend(chunk_blown_frames)

                for i, us in enumerate(chunk_frame_us):
                    self._frame_totals[i] += us
                    self._frame_counts[i] += 1

                # Maintain top-10 across all frames seen so far
                candidates = list(self._top10_frames)
                for i, us in enumerate(chunk_frame_us):
                    candidates.append({'frameIndex': i, 'second': second, 'timeUs': us})
                candidates.sort(key=lambda x: x['timeUs'], reverse=True)
                self._top10_frames = candidates[:10]

                # Build snapshot for JS (do this inside the lock for consistency)
                frame_avgs = [
                    self._frame_totals[i] // self._frame_counts[i]
                    if self._frame_counts[i] > 0 else 0
                    for i in range(CHUNK_SIZE)
                ]
                top10_snapshot = list(self._top10_frames)

            frame_data = list(chunk)
            stats = self._build_summary()

            window.evaluate_js(
                f"window._app && window._app.onChunk({json.dumps({'second': second, 'blown': stats['blown'], 'avg_us': stats['avg_us'], 'max_us': stats['max_us'], 'max_frame': stats['max_frame'], 'frame_data': frame_data, 'new_blown_frames': chunk_blown_frames, 'frame_avgs': frame_avgs, 'top10': top10_snapshot})})"
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
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"throughput_{ts}.csv"
            
            result = window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=default_name,
                file_types=["CSV Files (*.csv)", "All files (*.*)"]
            )
            
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

    def js_error(self, message: str) -> str:
      try:
        print("[JS ERROR]", message)
      except Exception:
        pass
      return json.dumps({"status": "ok"})
    
    def _calculate_crc16(self, data: bytes | bytearray) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
                crc &= 0xFFFF
        return crc
    
    def _validate_ack(self, rx: bytes | bytearray, expected_chunk: int) -> tuple[bool, str]:
        if len(rx) != 12:
            return False, f"Invalid Frame Length"
        if rx[:3]  != b"\xFE\xFE\xFE":
            return False, "[1] Error While Validating ACK"
        if rx[9:]  != b"\xFE\xFE\xFE":
            return False, "[2] Error While Validating ACK"
        if rx[3] != 0x41:
            return False, "[3] Error While Validating ACK"
        if rx[6] != 0x00:
            return False, "Failed to Stop the Analysis Process"

        rx_chunk = (rx[4] << 8) | rx[5]
        rx_crc   = (rx[7] << 8) | rx[8]
        calc_crc = self._calculate_crc16(rx[3:7])
        
        if rx_crc != calc_crc:
            return False, "[4] Error While Validating ACK"
        if rx_chunk != expected_chunk:
            return False, f"[5] Error While Validating ACK"
            
        return True, "Valid"

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

.layout { 
  display: flex; 
  flex: 1; 
  overflow: hidden; 
}

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

/* ── Connection panel field labels ─────────────────── */
.conn-field {
  margin-bottom: 12px;
}
.conn-field-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 6px;
  display: block;
}
body.light-theme .conn-field-label {
  color: #6b7280;
}

/* ── Full-width Connect button ─────────────────────── */
.btn-connect {
  width: 100%;
  height: 42px;
  border: none;
  border-radius: 9px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: #fff;
  font-family: 'Inter', sans-serif;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s ease;
  box-shadow: 0 3px 12px rgba(16, 185, 129, 0.25);
  margin-bottom: 10px;
  letter-spacing: 0.01em;
  position: relative;
  overflow: hidden;
}
.btn-connect::before {
  content: '';
  position: absolute;
  top: 0; left: -100%;
  width: 100%; height: 100%;
  background: rgba(255,255,255,0.12);
  transition: left 0.3s ease;
}
.btn-connect:hover::before { left: 100%; }
.btn-connect:hover {
  box-shadow: 0 5px 18px rgba(16, 185, 129, 0.4);
  transform: translateY(-1px);
}
.btn-connect:active { transform: scale(0.98); }
.btn-connect.disconnect-mode {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  box-shadow: 0 3px 12px rgba(239, 68, 68, 0.25);
}
.btn-connect.disconnect-mode:hover {
  box-shadow: 0 5px 18px rgba(239, 68, 68, 0.4);
}
body.light-theme .btn-connect {
  background: linear-gradient(135deg, #059669 0%, #10b981 100%);
  box-shadow: 0 3px 12px rgba(5, 150, 105, 0.25);
}
body.light-theme .btn-connect.disconnect-mode {
  background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
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

.hr { 
  height: 1px; 
  background: linear-gradient(90deg, transparent, var(--border), transparent);
  margin: 8px 0 4px; 
}

.main { 
  flex: 1; 
  min-width: 0; 
  display: flex; 
  flex-direction: column; 
  overflow: hidden; 
}

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

/* Alert overlay */
.alert-overlay {
  position: fixed; inset: 0; z-index: 20000;
  background: rgba(0, 0, 0, 0.45); backdrop-filter: blur(4px);
  display: none; align-items: center; justify-content: center;
}
.alert-overlay.show { display: flex; }
.alert-card {
  background: linear-gradient(180deg, var(--surface) 0%, var(--bg-dark) 100%);
  border: 1px solid var(--border); border-radius: 16px;
  padding: 30px 34px; min-width: 320px; max-width: 460px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.45); animation: slideUp 0.22s ease;
}
body.light-theme .alert-card {
  background: #ffffff; border-color: #d1d5db;
}
.alert-hdr { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.alert-ico {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700; flex-shrink: 0;
}
.alert-ico.error { background: rgba(239, 68, 68, 0.15); color: var(--red-light); }
.alert-ico.warning { background: rgba(245, 158, 11, 0.15); color: var(--amber); }
.alert-ico.success { background: rgba(16, 185, 129, 0.15); color: var(--green-light); }
.alert-ico.info { background: rgba(59, 130, 246, 0.15); color: var(--blue-light); }

body.light-theme .alert-ico.error { background: rgba(220, 38, 38, 0.1); color: #dc2626; }
body.light-theme .alert-ico.warning { background: rgba(217, 119, 6, 0.1); color: #d97706; }
body.light-theme .alert-ico.success { background: rgba(5, 150, 105, 0.1); color: #059669; }
body.light-theme .alert-ico.info { background: rgba(37, 99, 235, 0.1); color: #2563eb; }

.alert-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
body.light-theme .alert-title { color: #111827; }
.alert-body {
  font-size: 13px; color: var(--text-secondary); line-height: 1.65;
  margin-bottom: 22px; padding-left: 48px; word-break: break-word;
}
body.light-theme .alert-body { color: #4b5563; }
.alert-ok {
  width: 100%; padding: 11px; border: none; border-radius: 8px;
  font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 700;
  cursor: pointer; transition: background 0.2s ease; color: #fff;
}
.alert-ok.error { background: linear-gradient(135deg, var(--red) 0%, var(--red-light) 100%); }
.alert-ok.warning { background: linear-gradient(135deg, var(--amber) 0%, #fcd34d 100%); }
.alert-ok.success { background: linear-gradient(135deg, var(--green) 0%, var(--green-light) 100%); }
.alert-ok.info { background: linear-gradient(135deg, var(--blue) 0%, var(--blue-light) 100%); }

body.light-theme .alert-ok.error { background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%); }
body.light-theme .alert-ok.warning { background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%); }
body.light-theme .alert-ok.success { background: linear-gradient(135deg, #059669 0%, #10b981 100%); }
body.light-theme .alert-ok.info { background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%); }

@keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

/* Loading Overlay */
.loading-overlay {
  position: fixed; inset: 0; z-index: 30000;
  background: rgba(7, 10, 18, 0.75); backdrop-filter: blur(6px);
  display: none; align-items: center; justify-content: center;
}
.loading-overlay.show { display: flex; }

.loading-card {
  background: linear-gradient(180deg, var(--surface) 0%, var(--bg-dark) 100%);
  border: 1px solid var(--border); border-radius: 16px;
  padding: 36px 48px; display: flex; flex-direction: column; align-items: center; gap: 20px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.6); animation: slideUp 0.2s ease;
}
body.light-theme .loading-card {
  background: #ffffff; border-color: #d1d5db;
}

.spinner {
  width: 44px; height: 44px;
  border: 4px solid rgba(59, 130, 246, 0.15);
  border-top-color: var(--blue-light);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
body.light-theme .spinner {
  border-color: rgba(37, 99, 235, 0.15); border-top-color: #3b82f6;
}
.loading-text {
  font-size: 15px; font-weight: 600; color: var(--text-primary); letter-spacing: 0.3px;
}
body.light-theme .loading-text { color: #111827; }

@keyframes spin { to { transform: rotate(360deg); } }

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

.sort-header {
  cursor: pointer;
  user-select: none;
  padding: 8px 10px;
  border-radius: 4px;
  transition: background 0.2s ease;
  white-space: nowrap;
}

.sort-header:hover {
  background: rgba(59, 130, 246, 0.15);
}

body.light-theme .sort-header:hover {
  background: rgba(37, 99, 235, 0.12);
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

.metric-modal-close-btn:focus {
  outline: 2px solid var(--blue-light);
  outline-offset: 2px;
  border-radius: 8px;
}

body.light-theme .metric-modal-close-btn:focus {
  outline: 2px solid #2563eb;
}

.metric-modal-card:focus-within {
  box-shadow: inset 0 0 0 1px var(--blue-light);
}

body.light-theme .metric-modal-card:focus-within {
  box-shadow: inset 0 0 0 1px #2563eb;
}

button:focus-visible {
  outline: 2px solid var(--blue-light);
  outline-offset: 2px;
  border-radius: 8px;
}

body.light-theme button:focus-visible {
  outline: 2px solid #2563eb;
}

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

body.light-theme .top-status.disconnected {
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(220, 38, 38, 0.08);
}

body.light-theme .top-status.disconnected .top-status-dot {
  background: #dc2626;
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1);
}

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

body.light-theme .scard:hover {
  border-color: #bfdbfe;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
}

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

body.light-theme .hr {
  background: linear-gradient(90deg, transparent, #d1d5db, transparent);
}

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

/* ── Dashboard Panel Styles ──────────────────────────────────── */
.dash-hero-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 2px;
}
.dash-kpi {
  background: rgba(0,0,0,0.18);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.3s ease;
}
.dash-kpi::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  border-radius: 10px 10px 0 0;
}
.dash-kpi.c-red::before    { background: linear-gradient(90deg, var(--red), var(--red-light)); }
.dash-kpi.c-green::before  { background: linear-gradient(90deg, var(--green), var(--green-light)); }
.dash-kpi.c-amber::before  { background: linear-gradient(90deg, var(--amber), #fcd34d); }
.dash-kpi.c-blue::before   { background: linear-gradient(90deg, var(--blue), var(--blue-light)); }
.dash-kpi.c-purple::before { background: linear-gradient(90deg, var(--purple), var(--cyan)); }

body.light-theme .dash-kpi {
  background: #f9fafb;
  border-color: #e5e7eb;
}
.dash-kpi-lbl {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}
body.light-theme .dash-kpi-lbl { color: #6b7280; }
.dash-kpi-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.1;
}
body.light-theme .dash-kpi-val { color: #111827; }
.dash-kpi-val.c-red    { color: var(--red-light); }
.dash-kpi-val.c-green  { color: var(--green-light); }
.dash-kpi-val.c-amber  { color: var(--amber); }
.dash-kpi-val.c-blue   { color: var(--blue-light); }
.dash-kpi-val.c-purple { color: var(--purple); }
.dash-kpi-sub {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
}
body.light-theme .dash-kpi-sub { color: #9ca3af; }

.dash-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  margin-top: 4px;
}
.dash-badge.excellent { background: rgba(16,185,129,0.15); color: var(--green-light); }
.dash-badge.good      { background: rgba(59,130,246,0.15); color: var(--blue-light); }
.dash-badge.moderate  { background: rgba(245,158,11,0.15); color: var(--amber); }
.dash-badge.critical  { background: rgba(239,68,68,0.15);  color: var(--red-light); }

body.light-theme .dash-badge.excellent { background: rgba(5,150,105,0.12);  color: #059669; }
body.light-theme .dash-badge.good      { background: rgba(37,99,235,0.12);  color: #2563eb; }
body.light-theme .dash-badge.moderate  { background: rgba(217,119,6,0.12);  color: #d97706; }
body.light-theme .dash-badge.critical  { background: rgba(220,38,38,0.12);  color: #dc2626; }

.dash-section {
  background: rgba(0,0,0,0.12);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
}
body.light-theme .dash-section {
  background: #f9fafb;
  border-color: #e5e7eb;
}
.dash-section-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
body.light-theme .dash-section-title { color: #6b7280; }
.dash-section-title .live-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--green-light);
  box-shadow: 0 0 0 2px rgba(52,211,153,0.2);
  animation: livePulse 1.4s ease-in-out infinite;
}
@keyframes livePulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(52,211,153,0.2); }
  50%       { box-shadow: 0 0 0 5px rgba(52,211,153,0.08); }
}

.dash-table {
  width: 100%;
  border-collapse: collapse;
}
.dash-table th {
  background: rgba(59,130,246,0.07);
  padding: 7px 10px;
  text-align: left;
  font-size: 10px;
  font-weight: 700;
  color: var(--blue-light);
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  white-space: nowrap;
}
body.light-theme .dash-table th {
  background: #eff6ff;
  color: #2563eb;
  border-bottom-color: #dbeafe;
}
.dash-table th.sortable {
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.dash-table th.sortable:hover { background: rgba(59,130,246,0.14); }
body.light-theme .dash-table th.sortable:hover { background: #dbeafe; }
.dash-table td {
  padding: 7px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
  vertical-align: middle;
}
body.light-theme .dash-table td {
  border-bottom-color: #f3f4f6;
  color: #374151;
}
.dash-table tr:last-child td { border-bottom: none; }
.dash-table tr:hover td { background: rgba(59,130,246,0.04); }
body.light-theme .dash-table tr:hover td { background: #f0f9ff; }

.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px; height: 22px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}
.rank-badge.r1 { background: rgba(245,158,11,0.25); color: #fcd34d; }
.rank-badge.r2 { background: rgba(148,163,184,0.18); color: #cbd5e1; }
.rank-badge.r3 { background: rgba(180,125,90,0.2); color: #c4956a; }
.rank-badge.rn { background: rgba(59,130,246,0.12); color: var(--blue-light); }

body.light-theme .rank-badge.r1 { background: rgba(245,158,11,0.18); color: #d97706; }
body.light-theme .rank-badge.r2 { background: rgba(100,116,139,0.15); color: #475569; }
body.light-theme .rank-badge.r3 { background: rgba(120,80,50,0.12);  color: #78502a; }
body.light-theme .rank-badge.rn { background: rgba(37,99,235,0.1);   color: #2563eb; }

.time-bar-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 90px;
}
.time-bar-bg {
  flex: 1;
  height: 5px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
  overflow: hidden;
}
body.light-theme .time-bar-bg { background: #e5e7eb; }
.time-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}
.time-bar-fill.blown { background: linear-gradient(90deg, var(--red), var(--red-light)); }
.time-bar-fill.ok    { background: linear-gradient(90deg, var(--blue), var(--blue-light)); }
.time-bar-fill.peak  { background: linear-gradient(90deg, var(--amber), #fcd34d); }

.blown-status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.blown-status-dot.blown { background: var(--red-light); }
.blown-status-dot.ok    { background: var(--green-light); }

.avg-canvas-wrap {
  width: 100%;
  height: 90px;
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0,0,0,0.15);
}
body.light-theme .avg-canvas-wrap { background: #f3f4f6; }
canvas.avg-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.dash-hero-frame {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  background: rgba(59,130,246,0.07);
  border: 1px solid rgba(59,130,246,0.2);
  border-radius: 12px;
  margin-bottom: 2px;
}
body.light-theme .dash-hero-frame {
  background: #eff6ff;
  border-color: #bfdbfe;
}
.dash-hero-frame-icon {
  font-size: 28px;
  flex-shrink: 0;
}
.dash-hero-frame-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 32px;
  font-weight: 700;
  color: var(--blue-light);
  line-height: 1;
}
body.light-theme .dash-hero-frame-num { color: #2563eb; }
.dash-hero-frame-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
body.light-theme .dash-hero-frame-label { color: #6b7280; }

#analysisDetail {
  display: none;
  flex: 1;
  min-height: 0;
  width: 100%;
  box-sizing: border-box;
}

#analysisDetail .metric-modal-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 22px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--r);
  background: linear-gradient(135deg, var(--surface) 0%, rgba(42, 50, 63, 0.75) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 12px 30px rgba(0, 0, 0, 0.18);
}

#analysisDetail .metric-modal-header {
  margin-bottom: 0;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

body.light-theme #analysisDetail .metric-modal-card {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-color: #dbe2ea;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8), 0 12px 30px rgba(15, 23, 42, 0.08);
}

body.light-theme #analysisDetail .metric-modal-header {
  border-bottom-color: #e5e7eb;
}

#analysisDetail .metric-detail-section {
  margin-bottom: 0;
  padding: 16px;
  border-radius: 14px;
  background: rgba(0, 0, 0, 0.12);
}

body.light-theme #analysisDetail .metric-detail-section {
  background: #f8fafc;
  border-color: #e5e7eb;
}

#analysisDetail .metric-detail-value {
  line-height: 1.45;
}

#analysisDetail .metric-table {
  width: 100%;
}

#analysisDetail .metric-table td,
#analysisDetail .metric-table th {
  padding-top: 10px;
  padding-bottom: 10px;
}

#analysisDetail .metric-modal-title {
  font-size: 20px;
}

#analysisDetail .metric-modal-subtitle {
  font-size: 12px;
}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <div class="logo-mark">
      <svg viewBox="0 0 38 38" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="lg1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#3b6fe0"/>
            <stop offset="100%" stop-color="#6c3aed"/>
          </linearGradient>
        </defs>
        <rect width="38" height="38" rx="9" fill="url(#lg1)"/>
        <rect x="5"  y="22" width="4" height="11" rx="1.5" fill="rgba(255,255,255,0.5)"/>
        <rect x="11" y="16" width="4" height="17" rx="1.5" fill="rgba(255,255,255,0.7)"/>
        <rect x="17" y="10" width="4" height="23" rx="1.5" fill="rgba(255,255,255,0.9)"/>
        <rect x="23" y="14" width="4" height="19" rx="1.5" fill="rgba(255,255,255,0.75)"/>
        <rect x="29" y="19" width="4" height="14" rx="1.5" fill="rgba(255,255,255,0.55)"/>
        <polyline points="7,20 13,14 19,8 25,12 31,17"
                  fill="none" stroke="#fff" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
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
      <div class="scard clickable" id="cardFrameBlown" onclick="app.toggleMetricView('frameBlown')">
        <div class="scard-lbl">Frames Blown</div>
        <div class="scard-val c-red" id="svBlown">—</div>
      </div>
      <div class="scard clickable" id="cardAvgTime" onclick="app.toggleMetricView('avgTime')">
        <div class="scard-lbl">Average Time</div>
        <div class="scard-val c-green" id="svAvg">—</div>
        <div class="scard-unit">microseconds</div>
      </div>
      <div class="scard clickable" id="cardMaxTime" onclick="app.toggleMetricView('maxTime')">
        <div class="scard-lbl">Maximum Time</div>
        <div class="scard-val c-amber" id="svMaxTime">—</div>
        <div class="scard-unit">microseconds</div>
      </div>
      <div class="scard clickable" id="cardPeakFrame" onclick="app.toggleMetricView('peakFrame')">
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
      <div id="chartView" class="chart-box"><canvas id="chart"></canvas></div>
      <div id="analysisDetail" style="display: none;">

        <!-- ══ 1. FRAMES BLOWN DASHBOARD ══════════════════════════════ -->
        <div class="metric-modal-card" id="inline_frameBlown" style="display:none;">
          <div class="metric-modal-header">
            <div class="metric-modal-icon">⚠️</div>
            <div style="flex:1;">
              <div class="metric-modal-title" id="inline_blownModalTitle">Frames Blown</div>
              <div class="metric-modal-subtitle">Real-time Threshold Exceedance Monitor</div>
            </div>
          </div>

          <!-- KPI strip -->
          <div class="dash-hero-grid">
            <div class="dash-kpi c-red">
              <div class="dash-kpi-lbl">Total Blown</div>
              <div class="dash-kpi-val c-red" id="ib_totalBlown">—</div>
              <div class="dash-kpi-sub">frames > 2000 µs</div>
            </div>
            <div class="dash-kpi c-amber">
              <div class="dash-kpi-lbl">% of Frames</div>
              <div class="dash-kpi-val c-amber" id="ib_blownPct">—</div>
              <div class="dash-kpi-sub">exceedance rate</div>
            </div>
            <div class="dash-kpi c-purple">
              <div class="dash-kpi-lbl">Last Blown</div>
              <div class="dash-kpi-val c-purple" id="ib_lastBlownSec">—</div>
              <div class="dash-kpi-sub">second of session</div>
            </div>
          </div>

          <!-- Live table -->
          <div class="dash-section">
            <div class="dash-section-title">
              <span class="live-dot"></span>
              All Blown Frames — <span id="ib_blownCount">0</span> total
              <span style="margin-left:auto; display:flex; gap:6px;">
                <button onclick="app.sortBlownInline('frameIndex')" id="ib_sortFrameBtn"
                  style="background:rgba(59,130,246,0.1);border:1px solid var(--border);border-radius:5px;padding:2px 8px;font-size:10px;color:var(--text-secondary);cursor:pointer;">Frame #</button>
                <button onclick="app.sortBlownInline('second')" id="ib_sortSecBtn"
                  style="background:rgba(59,130,246,0.1);border:1px solid var(--border);border-radius:5px;padding:2px 8px;font-size:10px;color:var(--text-secondary);cursor:pointer;">Second</button>
                <button onclick="app.sortBlownInline('timeUs')" id="ib_sortTimeBtn"
                  style="background:rgba(59,130,246,0.15);border:1px solid var(--blue);border-radius:5px;padding:2px 8px;font-size:10px;color:var(--blue-light);cursor:pointer;">Time ▼</button>
              </span>
            </div>
            <table class="dash-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Frame #</th>
                  <th>Second</th>
                  <th>Time (µs)</th>
                  <th>Severity</th>
                </tr>
              </thead>
              <tbody id="ib_blownBody"></tbody>
            </table>
          </div>
        </div>

        <!-- ══ 2. AVERAGE TIME DASHBOARD ═══════════════════════════════ -->
        <div class="metric-modal-card" id="inline_avgTime" style="display:none;">
          <div class="metric-modal-header">
            <div class="metric-modal-icon">📊</div>
            <div style="flex:1;">
              <div class="metric-modal-title">Average Time</div>
              <div class="metric-modal-subtitle">Mean Processing Latency — Live per-Frame Analysis</div>
            </div>
          </div>

          <!-- KPI strip -->
          <div class="dash-hero-grid">
            <div class="dash-kpi c-green">
              <div class="dash-kpi-lbl">Overall Average</div>
              <div class="dash-kpi-val c-green" id="ib_avgOverall">—</div>
              <div class="dash-kpi-sub">µs across all frames</div>
            </div>
            <div class="dash-kpi c-blue">
              <div class="dash-kpi-lbl">Frame Count</div>
              <div class="dash-kpi-val c-blue" id="ib_avgFrameCount">—</div>
              <div class="dash-kpi-sub">total samples seen</div>
            </div>
            <div class="dash-kpi c-purple">
              <div class="dash-kpi-lbl">Status</div>
              <div id="ib_avgBadge" class="dash-badge excellent" style="margin-top:6px;">Excellent</div>
            </div>
          </div>

          <!-- Per-frame sparkline -->
          <div class="dash-section">
            <div class="dash-section-title">
              <span class="live-dot"></span>
              Per-Frame Average (0 → 499)
            </div>
            <div class="avg-canvas-wrap">
              <canvas class="avg-canvas" id="ib_avgCanvas"></canvas>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:4px;">
              <span style="font-size:9px;color:var(--text-muted);">Frame 0</span>
              <span style="font-size:9px;color:var(--text-muted);text-align:center;">--- 2000 µs threshold ---</span>
              <span style="font-size:9px;color:var(--text-muted);">Frame 499</span>
            </div>
          </div>

          <!-- Top 10 highest average frames -->
          <div class="dash-section">
            <div class="dash-section-title">Top 10 Highest-Average Frames</div>
            <table class="dash-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Frame #</th>
                  <th>Avg Time (µs)</th>
                  <th>vs Overall</th>
                  <th>Bar</th>
                </tr>
              </thead>
              <tbody id="ib_avgTopBody"></tbody>
            </table>
          </div>
        </div>

        <!-- ══ 3. MAX TIME DASHBOARD ════════════════════════════════════ -->
        <div class="metric-modal-card" id="inline_maxTime" style="display:none;">
          <div class="metric-modal-header">
            <div class="metric-modal-icon">⏱️</div>
            <div style="flex:1;">
              <div class="metric-modal-title">Maximum Time</div>
              <div class="metric-modal-subtitle">Peak Latency Tracker — Top 10 All-Time Highs</div>
            </div>
          </div>

          <!-- KPI strip -->
          <div class="dash-hero-grid">
            <div class="dash-kpi c-amber">
              <div class="dash-kpi-lbl">Session Max</div>
              <div class="dash-kpi-val c-amber" id="ib_maxValue">—</div>
              <div class="dash-kpi-sub">µs — all-time peak</div>
            </div>
            <div class="dash-kpi c-red">
              <div class="dash-kpi-lbl">Over Threshold</div>
              <div class="dash-kpi-val c-red" id="ib_maxExceed">—</div>
              <div class="dash-kpi-sub">µs above 2000</div>
            </div>
            <div class="dash-kpi c-blue">
              <div class="dash-kpi-lbl">Reached at Second</div>
              <div class="dash-kpi-val c-blue" id="ib_maxSecond">—</div>
              <div class="dash-kpi-sub">session timestamp</div>
            </div>
          </div>

          <!-- Top 10 table -->
          <div class="dash-section">
            <div class="dash-section-title">
              <span class="live-dot"></span>
              Top 10 Highest Processing Times
            </div>
            <table class="dash-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Frame #</th>
                  <th>Second</th>
                  <th>Time (µs)</th>
                  <th>Severity Bar</th>
                </tr>
              </thead>
              <tbody id="ib_maxBody"></tbody>
            </table>
          </div>
        </div>

        <!-- ══ 4. PEAK FRAME DASHBOARD ══════════════════════════════════ -->
        <div class="metric-modal-card" id="inline_peakFrame" style="display:none;">
          <div class="metric-modal-header">
            <div class="metric-modal-icon">🎯</div>
            <div style="flex:1;">
              <div class="metric-modal-title">Peak Frame</div>
              <div class="metric-modal-subtitle">Top 10 Frames by Maximum Processing Time</div>
            </div>
          </div>

          <!-- Hero frame card -->
          <div class="dash-hero-frame">
            <div class="dash-hero-frame-icon">🏆</div>
            <div>
              <div class="dash-hero-frame-num" id="ib_peakHeroNum">Frame —</div>
              <div class="dash-hero-frame-label" id="ib_peakHeroTime">— µs — absolute session peak</div>
            </div>
            <div style="margin-left:auto;" id="ib_peakHeroBadge"></div>
          </div>

          <!-- KPI strip -->
          <div class="dash-hero-grid">
            <div class="dash-kpi c-blue">
              <div class="dash-kpi-lbl">Peak Frame #</div>
              <div class="dash-kpi-val c-blue" id="ib_peakFrameNum">—</div>
              <div class="dash-kpi-sub">index 0–499</div>
            </div>
            <div class="dash-kpi c-amber">
              <div class="dash-kpi-lbl">Peak Time</div>
              <div class="dash-kpi-val c-amber" id="ib_peakFrameTime">—</div>
              <div class="dash-kpi-sub">µs maximum</div>
            </div>
            <div class="dash-kpi c-red">
              <div class="dash-kpi-lbl">Threshold Status</div>
              <div id="ib_peakStatus" class="dash-badge critical" style="margin-top:6px;">⚠️ Blown</div>
            </div>
          </div>

          <!-- Top 10 peak frames table -->
          <div class="dash-section">
            <div class="dash-section-title">
              <span class="live-dot"></span>
              Top 10 Peak Frames
            </div>
            <table class="dash-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Frame #</th>
                  <th>Second</th>
                  <th>Time (µs)</th>
                  <th>Threshold</th>
                </tr>
              </thead>
              <tbody id="ib_peakBody"></tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  </div>

  <!-- Right Control Panel -->
  <div class="control-panel">
    <!-- Connection Section -->
    <div class="ctrl-section">
      <span class="ctrl-section-title">Connection</span>

      <!-- COM Port field -->
      <div class="conn-field">
        <span class="conn-field-label">COM Port</span>
        <div class="ctrl-row full">
          <select id="portSel"><option value="">No ports found</option></select>
          <button class="btn-icon" id="btnRefresh" title="Refresh ports" onclick="app.refreshPorts()">
            <svg id="refreshIcon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 8a7 7 0 1 0 2-4.9"/>
              <polyline points="1,3 1,8 6,8"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Baud Rate field -->
      <div class="conn-field">
        <span class="conn-field-label">Baud Rate</span>
        <select id="baudSel">
          <option>9600</option><option>19200</option><option>38400</option>
          <option selected>57600</option><option>115200</option>
          <option>230400</option><option>460800</option><option>921600</option>
        </select>
      </div>

      <!-- Full-width Connect / Disconnect button -->
      <button class="btn-connect" id="btnConn" onclick="app.toggleConnect()">Connect</button>
    </div>

    <!-- Analysis Section -->
    <div class="ctrl-section">
      <span class="ctrl-section-title">Analysis</span>
      
      <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 8px;">
        <button class="btn-action start" id="btnStart" onclick="app.startAnalysis()" title="Start Analysis" style="flex: none; height: 40px; font-size: 13px;" disabled>
          <svg viewBox="0 0 16 16" fill="currentColor"><polygon points="4,2 14,8 4,14"/></svg>
          Start
        </button>
        
        <button class="btn-action stop" id="btnStop" onclick="app.stopAnalysis()" title="Stop Analysis" style="flex: none; height: 40px; font-size: 13px;" disabled>
          <svg viewBox="0 0 16 16" fill="currentColor"><rect x="3" y="3" width="10" height="10" rx="2"/></svg>
          Stop
        </button>
        
        <div class="hr" style="margin: 4px 0; flex: none;"></div>
        
        <button class="btn-action analyze" id="btnAnalyze" onclick="app.analyze()" title="Run ML Analysis" style="flex: none; height: 40px; font-size: 13px;" disabled>
          <svg viewBox="0 0 16 16" fill="currentColor"><path d="M3 3h10v2H3zm0 4h10v2H3zm0 4h7v2H3z"/></svg>
          Analyze
        </button>
        
        <button class="btn-action download" id="btnDownloadExcel" onclick="app.downloadExcel()" title="Export Analysis Report" style="flex: none; height: 40px; font-size: 13px;" disabled>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 2v9M4 7l4 4 4-4"/><line x1="2" y1="14" x2="14" y2="14"/>
          </svg>
          Export Analysis
        </button>
      </div>
    </div>
  </div>

</div>

<!-- Alert overlay -->
<div class="alert-overlay" id="alertOverlay" role="presentation">
    <div class="alert-card" role="dialog" aria-modal="true" aria-labelledby="alertTitle" aria-hidden="true">
        <div class="alert-hdr">
            <div class="alert-ico error" id="alertIco">!</div>
            <div class="alert-title" id="alertTitle">Error</div>
        </div>
        <div class="alert-body" id="alertBody"></div>
        <button class="alert-ok error" id="alertOk" onclick="app.closeAlert()">OK</button>
    </div>
</div>

<div class="loading-overlay" id="loadingOverlay" role="presentation">
    <div class="loading-card">
        <div class="spinner"></div>
        <div class="loading-text" id="loadingText">Analyzing Data...</div>
    </div>
</div>

<!-- Metric Detail Modals -->
<div class="modal-backdrop" id="frameBlownModal" role="presentation">
  <div class="metric-modal-card" role="dialog" aria-modal="true" aria-labelledby="blownModalTitle" aria-hidden="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('frameBlownModal')" aria-label="Close Frames Blown details">×</button>
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
      <div class="metric-detail-label" id="blownFramesCountLabel">All Blown Frames</div>
      <table class="metric-table">
        <thead>
          <tr>
            <th class="sort-header" id="blownSortRankHeader" onclick="app.sortBlownFrames('rank')">Rank</th>
            <th class="sort-header" id="blownSortFrameHeader" onclick="app.sortBlownFrames('frameIndex')">Frame #</th>
            <th class="sort-header" id="blownSortTimeHeader" onclick="app.sortBlownFrames('timeUs')">Time (µs)</th>
          </tr>
        </thead>
        <tbody id="blownFramesList"></tbody>
      </table>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="avgTimeModal" role="presentation">
  <div class="metric-modal-card" role="dialog" aria-modal="true" aria-labelledby="avgTimeModalTitle" aria-hidden="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('avgTimeModal')" aria-label="Close Average Time details">×</button>
    <div class="metric-modal-header">
      <div class="metric-modal-icon">📊</div>
      <div>
        <div class="metric-modal-title" id="avgTimeModalTitle">Average Time</div>
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
  </div>
</div>

<div class="modal-backdrop" id="maxTimeModal" role="presentation">
  <div class="metric-modal-card" role="dialog" aria-modal="true" aria-labelledby="maxTimeModalTitle" aria-hidden="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('maxTimeModal')" aria-label="Close Maximum Time details">×</button>
    <div class="metric-modal-header">
      <div class="metric-modal-icon">⏱️</div>
      <div>
        <div class="metric-modal-title" id="maxTimeModalTitle">Maximum Time</div>
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
          <tr>
            <th class="sort-header" id="maxSortRankHeader" onclick="app.sortMaxFrames('rank')">Rank</th>
            <th class="sort-header" id="maxSortFrameHeader" onclick="app.sortMaxFrames('frameIndex')">Frame #</th>
            <th class="sort-header" id="maxSortTimeHeader" onclick="app.sortMaxFrames('timeUs')">Time (µs)</th>
            <th class="sort-header" id="maxSortTimestampHeader" onclick="app.sortMaxFrames('timestamp')">Timestamp (s)</th>
          </tr>
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
  </div>
</div>

<div class="modal-backdrop" id="peakFrameModal" role="presentation">
  <div class="metric-modal-card" role="dialog" aria-modal="true" aria-labelledby="peakFrameModalTitle" aria-hidden="true">
    <button class="metric-modal-close-btn" onclick="app.closeMetricModal('peakFrameModal')" aria-label="Close Peak Frame details">×</button>
    <div class="metric-modal-header">
      <div class="metric-modal-icon">🎯</div>
      <div>
        <div class="metric-modal-title" id="peakFrameModalTitle">Peak Frame</div>
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
      <div class="metric-detail-value" style="font-size: 12px; font-weight: 400;">
        This frame has the highest recorded processing latency in the entire session. 
        It represents the worst-case scenario for system performance.
      </div>
    </div>
  </div>
</div>

<script>
// ── Chart ─────────────────────────────────────────────────────────────────────
const cvs = document.getElementById('chart');
const ctx = cvs.getContext('2d');
let latestChunk = null;
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
  
  const isLightTheme = document.body.classList.contains('light-theme');
  
  if (!latestChunk) {
    ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
    ctx.font = "14px 'Inter', sans-serif";
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('Start analysis to see live data', W / 2, H / 2);
    return;
  }

  const pad = { t: 24, r: 24, b: 48, l: 56 };
  const iW = W - pad.l - pad.r;
  const iH = H - pad.t - pad.b;

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

  ctx.save();
  ctx.translate(14, pad.t + iH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.font = "10px 'Inter', sans-serif";
  ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
  ctx.fillText('Scheduler Load %', 0, 0);
  ctx.restore();

  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.font = "10px 'JetBrains Mono', monospace";

  const frameSteps = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 499];
  frameSteps.forEach(f => {
    const x = pad.l + (f / 499) * iW;
    ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
    ctx.fillText(f, x, pad.t + iH + 8);
  });

  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.font = "10px 'Inter', sans-serif";
  ctx.fillStyle = isLightTheme ? '#6b7280' : '#8a8f9f';
  ctx.fillText('Frame Index', pad.l + iW / 2, H - 4);

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

  const points = [];
  latestChunk.forEach((pct, frameIdx) => {
    const x = pad.l + (frameIdx / 499) * iW;
    const y = pad.t + iH - (pct / 100) * iH;
    points.push({ x, y, pct });
  });

  ctx.beginPath();
  ctx.moveTo(points[0].x, pad.t + iH);
  points.forEach(pt => ctx.lineTo(pt.x, pt.y));
  ctx.lineTo(points[points.length - 1].x, pad.t + iH);
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

  ctx.fillStyle = isLightTheme ? '#dc2626' : '#ef4444';
  points.forEach(pt => {
    if ((pt.pct * SCALE_FACTOR) > THRESHOLD_US) {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 3, 0, Math.PI * 2);
      ctx.fill();
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
  let currentMetricShown = null;
  let lastUsbConnected = null;
  
  let metricData = {
    blown: 0,
    avgUs: 0,
    maxUs: 0,
    maxFrame: 0,
    totalTime: 0,
    frameCount: 0,
    blownFrames: [],       // current-chunk blown frames (for chart coloring)
    blownFramesList: [],   // accumulated all-session blown frames
    maxFrames: [],
    allFrames: [],
    frameAvgs: [],         // per-frame running averages (500 entries)
    top10: []              // top-10 frames by timeUs across whole session
  };
  const THRESHOLD_US = 2000;
  const SCALE_FACTOR = 20;

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
    drawChart();
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

  document.getElementById('themeToggle').addEventListener('click', toggleTheme);

  function showAlert(title, body, type) {
    const overlay = document.getElementById("alertOverlay");
    if (!overlay) return;
    document.getElementById("alertTitle").textContent = title;
    document.getElementById("alertBody").textContent = body;
    const ico = document.getElementById("alertIco");
    const ok = document.getElementById("alertOk");
    type = type || "error";
    if (type === 'err') type = 'error';
    if (type === 'ok') type = 'success';
    if (type === 'warn') type = 'warning';

    ico.className = "alert-ico " + type;
    ok.className = "alert-ok " + type;
    ico.textContent = (type === "success") ? "✓" : (type === "warning") ? "⚠" : (type === "info") ? "i" : "!";
    overlay.classList.add("show");
    overlay.setAttribute('aria-hidden', 'false');
    setTimeout(() => ok.focus(), 50);
  }

  function closeAlert() {
    const overlay = document.getElementById("alertOverlay");
    if (overlay) {
        overlay.classList.remove("show");
        overlay.setAttribute('aria-hidden', 'true');
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
    btn.textContent = connected ? 'Disconnect' : 'Connect';
    btn.classList.toggle('disconnect-mode', connected);
    
    // FIX: Disable the Disconnect button if data gathering OR ML analysis is currently running
    btn.disabled = running || analysisRunning;

    document.getElementById('btnStart').disabled  = !connected || running;
    document.getElementById('btnStop').disabled   = !running;
    
    // Control ML flow buttons
    document.getElementById('btnAnalyze').disabled = !canAnalyze || analysisRunning;
    document.getElementById('btnDownloadExcel').disabled = !canDownloadExcel;
  }

  function showChartView() {
    const chartView = document.getElementById('chartView');
    const analysisDetail = document.getElementById('analysisDetail');
    chartView.style.display = 'block';
    analysisDetail.style.display = 'none';
    ['frameBlown','avgTime','maxTime','peakFrame','generic'].forEach(k => {
      const el = document.getElementById(k === 'generic' ? 'inline_generic' : 'inline_' + k);
      if (el) el.style.display = 'none';
    });
    currentMetricShown = null;
  }

  function setStats(blown, avgUs, maxUs, maxFrame) {
    document.getElementById('svBlown').textContent    = blown    != null ? Number(blown).toLocaleString()   : '—';
    document.getElementById('svAvg').textContent      = avgUs    != null ? Number(avgUs).toLocaleString()   : '—';
    document.getElementById('svMaxTime').textContent  = maxUs    != null ? Number(maxUs).toLocaleString()   : '—';
    document.getElementById('svMaxFrame').textContent = maxFrame != null ? Number(maxFrame).toLocaleString() : '—';
    
    metricData.blown = blown || 0;
    metricData.avgUs = avgUs || 0;
    metricData.maxUs = maxUs || 0;
    metricData.maxFrame = maxFrame || 0;
    
    if (latestChunk && Array.isArray(latestChunk)) {
      metricData.frameCount = latestChunk.length;
      metricData.totalTime = (metricData.avgUs * metricData.frameCount);
      
      metricData.allFrames = latestChunk.map((pct, idx) => ({
        frameIndex: idx,
        percentValue: pct,
        timeUs: pct * SCALE_FACTOR,
        isBlown: (pct * SCALE_FACTOR) > THRESHOLD_US
      }));
      metricData.maxFrames = [];
      
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
    
    if (ports.length === 0) {
      sel.innerHTML = '<option value="">No USB ports found</option>';
    } else {
      sel.innerHTML = ''; // Clear existing options
      
      // Populate the dropdown with USB ports
      ports.forEach(p => {
        const o = document.createElement('option');
        o.value = o.textContent = p;
        sel.appendChild(o);
      });
      
      // Auto-select logic: 
      // Keep the previous selection if it's still plugged in, 
      // otherwise default to the first USB port in the list.
      if (ports.includes(prev)) {
        sel.value = prev;
      } else {
        sel.value = ports[0];
      }
    }
  }

  async function toggleConnect() {
    if (connected) {
      // FIX: Check backend response before aggressively tearing down the UI state
      const r = JSON.parse(await window.pywebview.api.disconnect());
      if (r.status === 'error') {
        showAlert("Action Denied", r.message, "warning");
        return;
      }
      
      connected = false; running = false; canExport = false; canAnalyze = false; canDownloadExcel = false; analysisRunning = false;
      updateUsbStatus(false);
      showAlert("Disconnected", "Successfully disconnected from the port.", "warning");
    } else {
      const port = document.getElementById('portSel').value;
      const baud = document.getElementById('baudSel').value;
      if (!port) { showAlert("Warning", "Select a COM port first.", "warning"); return; }
      const r = JSON.parse(await window.pywebview.api.connect(port, baud));
      if (r.status === 'ok') {
        connected = true;
        updateUsbStatus(true);
      } else {
        updateUsbStatus(false);
        showAlert("Connection Failed", r.message, "error");
      }
    }
    sync();
  }

  async function startAnalysis() {
    const r = JSON.parse(await window.pywebview.api.start_analysis());
    if (r.status === 'ok') {
      running = true; canExport = false; canAnalyze = false; canDownloadExcel = false; analysisRunning = false;
      latestChunk = null;
      metricData.blownFramesList = [];
      metricData.frameAvgs = [];
      metricData.top10 = [];
      showChartView();
      setStats(0, 0, 0, 0); drawChart();
      showAlert("Analysis Started", "Receiving chunks every second...", "info");
    } else {
      showAlert("Start Failed", r.message, "error");
    }
    sync();
  }

  async function stopAnalysis() {
    const r = JSON.parse(await window.pywebview.api.stop_analysis());
    running = false;
    if (r.status === 'ok') {
      showChartView();
      canExport = true;
      canAnalyze = true;
      canDownloadExcel = false;
      showAlert("Analysis Complete", r.message + (r.ack_received ? ' (ACK received)' : ' (ACK timeout)'), "success");
      const s = JSON.parse(await window.pywebview.api.get_summary());
      setStats(s.blown, s.avg_us, s.max_us, s.max_frame);
    } else {
      showAlert("Stop Error", r.message, "error");
    }
    sync();
  }

  async function exportCsv() {
    const r = JSON.parse(await window.pywebview.api.export_csv());
    
    if (r.status === 'ok') {
      showAlert("Export Successful", `Saved ${Number(r.rows).toLocaleString()} rows → ${r.path}`, "success");
    } else if (r.status === 'cancelled') {
    } else {
      showAlert("Export Error", r.message, "error");
    }
  }

  function onChunk(data) {
    latestChunk = data.frame_data;

    // Accumulate blown frames (delta from this chunk only)
    if (data.new_blown_frames && data.new_blown_frames.length > 0) {
      metricData.blownFramesList = metricData.blownFramesList.concat(data.new_blown_frames);
    }
    // Update per-frame averages and top-10 sent by backend
    if (data.frame_avgs) metricData.frameAvgs = data.frame_avgs;
    if (data.top10)       metricData.top10      = data.top10;

    setStats(data.blown, data.avg_us, data.max_us, data.max_frame);
    drawChart();

    // Live-refresh whichever panel is open
    if (currentMetricShown) _refreshCurrentPanel();
  }

  async function onError(msg) {
    // 1. Stop all active operational flags
    running = false; 
    analysisRunning = false; 
    
    // 2. Force the UI connection state to false
    connected = false;
    
    // 3. Allow the user to export whatever data was captured before the yank
    canExport = true; 
    
    // 4. Tell the Python backend to close the dead port and clean up
    await window.pywebview.api.disconnect();
    
    // 5. Update the top UI status indicator
    updateUsbStatus(false);
    
    // 6. Show a clear alert to the user
    showAlert("Connection Lost", "The USB device was disconnected unexpectedly - " + msg, "error");
    
    // 7. Sync the buttons to reflect the new disconnected state
    sync();
  }

  function showLoading(msg) {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay) {
      document.getElementById("loadingText").textContent = msg || 'Processing...';
      overlay.classList.add("show");
    }
  }

  function hideLoading() {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay) {
      overlay.classList.remove("show");
    }
  }

  async function analyze() {
    if (analysisRunning) return;
    const r = JSON.parse(await window.pywebview.api.analyze());
    if (r.status === 'ok') {
      analysisRunning = true;
      canDownloadExcel = false;
      
      // SHOW the loading screen instead of the success alert
      showLoading("Running Machine Learning Analysis... Please wait.");
      
      sync();
    } else {
      showAlert("Analysis Error", r.message, "error");
    }
  }

  async function downloadExcel() {
    const r = JSON.parse(await window.pywebview.api.download_excel());
    if (r.status === 'ok') {
      showAlert("Download Successful", `Excel downloaded → ${r.path}`, "success");
    } else if (r.status === 'cancelled') {
    } else {
      showAlert("Download Error", r.message, "error");
    }
  }

  function onAnalysisComplete(payload) {
    analysisRunning = false;
    canDownloadExcel = true;
    
    // HIDE the loading screen
    hideLoading();
    
    sync();
    showChartView();
    showAlert("Analysis Complete", payload && payload.message ? payload.message : 'Patterns Analyzed Successfully', "success");
  }

  function onAnalysisError(msg) {
    analysisRunning = false;
    canDownloadExcel = false;
    
    // HIDE the loading screen
    hideLoading();
    
    showAlert("Analysis Error", msg, "error");
    sync();
  }

  let currentOpenModal = null;
  let previousFocusedElement = null;

  function getFocusableElements(container) {
    const focusableSelectors = [
      'button',
      '[href]',
      'input',
      'select',
      'textarea',
      '[tabindex]:not([tabindex="-1"])'
    ];
    return Array.from(container.querySelectorAll(focusableSelectors.join(',')))
      .filter(el => !el.hasAttribute('disabled') && el.offsetParent !== null);
  }

  function trapFocus(modalBackdrop) {
    const focusableElements = getFocusableElements(modalBackdrop);
    if (focusableElements.length === 0) return;

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    modalBackdrop._handleKeydown = (e) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    modalBackdrop.addEventListener('keydown', modalBackdrop._handleKeydown);
    setTimeout(() => firstElement.focus(), 50);
  }

  function releaseFocus(modalBackdrop) {
    if (modalBackdrop._handleKeydown) {
      modalBackdrop.removeEventListener('keydown', modalBackdrop._handleKeydown);
    }
  }

  function handleGlobalKeyboard(e) {
    if (e.key === 'Escape') {
      closeAlert();
      if (currentOpenModal && currentOpenModal.id.endsWith('Modal')) {
        closeMetricModal(currentOpenModal.id);
      }
    }
  }

  function openMetricModal(modalId) {
    if (modalId === 'frameBlownModal') return toggleMetricView('frameBlown');
    if (modalId === 'avgTimeModal') return toggleMetricView('avgTime');
    if (modalId === 'maxTimeModal') return toggleMetricView('maxTime');
    if (modalId === 'peakFrameModal') return toggleMetricView('peakFrame');
  }

  function closeMetricModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('show');
      modal.setAttribute('aria-hidden', 'true');
      releaseFocus(modal);
      currentOpenModal = null;
      
      if (previousFocusedElement && document.body.contains(previousFocusedElement)) {
        setTimeout(() => previousFocusedElement.focus(), 100);
      }
    }
  }

  function toggleMetricView(metricKey) {
    const chartView = document.getElementById('chartView');
    const analysisDetail = document.getElementById('analysisDetail');

    if (currentMetricShown === metricKey) {
      currentMetricShown = null;
      ['frameBlown','avgTime','maxTime','peakFrame'].forEach(k => {
        const el = document.getElementById('inline_' + k);
        if (el) el.style.display = 'none';
      });
      analysisDetail.style.display = 'none';
      chartView.style.display = 'block';
      return;
    }

    currentMetricShown = metricKey;
    chartView.style.display = 'none';
    analysisDetail.style.display = 'flex';
    ['frameBlown','avgTime','maxTime','peakFrame'].forEach(k => {
      const el = document.getElementById('inline_' + k);
      if (el) el.style.display = (k === metricKey) ? 'flex' : 'none';
    });

    _refreshCurrentPanel();
  }

  // ── Internal helpers ─────────────────────────────────────────
  let _blownSort = { by: 'timeUs', asc: false };

  function _refreshCurrentPanel() {
    if (currentMetricShown === 'frameBlown') _renderBlown();
    else if (currentMetricShown === 'avgTime')   _renderAvg();
    else if (currentMetricShown === 'maxTime')   _renderMax();
    else if (currentMetricShown === 'peakFrame') _renderPeak();
  }

  function _rankBadge(rank) {
    const cls = rank === 1 ? 'r1' : rank === 2 ? 'r2' : rank === 3 ? 'r3' : 'rn';
    return `<span class="rank-badge ${cls}">${rank}</span>`;
  }

  function _timebar(us, maxUs, cls) {
    const pct = maxUs > 0 ? Math.min(100, (us / maxUs) * 100).toFixed(1) : 0;
    return `<div class="time-bar-wrap">
      <div class="time-bar-bg"><div class="time-bar-fill ${cls}" style="width:${pct}%"></div></div>
    </div>`;
  }

  // ── 1. Frames Blown ────────────────────────────────────────────
  function _renderBlown() {
    const total = metricData.blown;
    const frameCount = metricData.frameCount || 500;
    const pct = frameCount > 0 ? ((total / frameCount) * 100).toFixed(2) : '0.00';

    _setText('ib_totalBlown', total.toLocaleString());
    _setText('ib_blownPct', pct + '%');

    const list = metricData.blownFramesList;
    const last = list.length > 0 ? 's' + list[list.length - 1].second : '—';
    _setText('ib_lastBlownSec', last);
    _setText('ib_blownCount', list.length.toLocaleString());

    // Sort
    let sorted = [...list];
    sorted.sort((a, b) => {
      const v = _blownSort.by === 'frameIndex' ? 'frameIndex'
              : _blownSort.by === 'second'     ? 'second' : 'timeUs';
      return _blownSort.asc ? a[v] - b[v] : b[v] - a[v];
    });

    const maxUs = sorted.length > 0 ? sorted[0].timeUs : THRESHOLD_US;
    const tbody = document.getElementById('ib_blownBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    sorted.forEach((f, idx) => {
      const barCls = f.timeUs > THRESHOLD_US * 1.5 ? 'blown' : 'peak';
      const over = f.timeUs - THRESHOLD_US;
      const severity = over > 1000 ? '<span class="dash-badge critical">Critical</span>'
                     : over > 500  ? '<span class="dash-badge moderate">High</span>'
                     :               '<span class="dash-badge good">Over</span>';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${_rankBadge(idx + 1)}</td>
        <td style="color:var(--text-primary);font-weight:600;">${f.frameIndex}</td>
        <td>s${f.second}</td>
        <td style="color:var(--red-light);">${f.timeUs.toLocaleString()}</td>
        <td>${severity}</td>
      `;
      tbody.appendChild(tr);
    });

    // highlight active sort button
    ['Frame','Sec','Time'].forEach(k => {
      const btn = document.getElementById('ib_sort' + k + 'Btn');
      if (!btn) return;
      const key = k === 'Frame' ? 'frameIndex' : k === 'Sec' ? 'second' : 'timeUs';
      const active = _blownSort.by === key;
      btn.style.background = active ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.08)';
      btn.style.borderColor = active ? 'var(--blue)' : 'var(--border)';
      btn.style.color = active ? 'var(--blue-light)' : 'var(--text-secondary)';
    });
  }

  function sortBlownInline(col) {
    if (_blownSort.by === col) _blownSort.asc = !_blownSort.asc;
    else { _blownSort.by = col; _blownSort.asc = false; }
    _renderBlown();
  }

  // ── 2. Average Time ────────────────────────────────────────────
  function _renderAvg() {
    const avg = metricData.avgUs;
    _setText('ib_avgOverall', avg.toLocaleString() + ' µs');
    _setText('ib_avgFrameCount', metricData.frameCount.toLocaleString());

    const badge = document.getElementById('ib_avgBadge');
    if (badge) {
      let cls, label;
      if (avg < 500)       { cls='excellent'; label='✓ Excellent'; }
      else if (avg < 1000) { cls='good';      label='✓ Good'; }
      else if (avg < 1500) { cls='moderate';  label='⚠ Moderate'; }
      else                 { cls='critical';  label='⚠ Concerning'; }
      badge.className = 'dash-badge ' + cls;
      badge.textContent = label;
    }

    // Draw sparkline
    _drawAvgCanvas();

    // Top 10 highest average frames
    const avgs = metricData.frameAvgs;
    if (!avgs || avgs.length === 0) return;

    const indexed = avgs.map((v, i) => ({ frameIndex: i, avgUs: v }));
    indexed.sort((a, b) => b.avgUs - a.avgUs);
    const top10 = indexed.slice(0, 10);
    const maxAvg = top10.length > 0 ? top10[0].avgUs : 1;

    const tbody = document.getElementById('ib_avgTopBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    top10.forEach((f, idx) => {
      const diff = f.avgUs - avg;
      const diffStr = diff >= 0 ? `+${diff.toLocaleString()}` : diff.toLocaleString();
      const barCls = f.avgUs > THRESHOLD_US ? 'blown' : 'ok';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${_rankBadge(idx + 1)}</td>
        <td style="color:var(--text-primary);font-weight:600;">${f.frameIndex}</td>
        <td style="color:${f.avgUs > THRESHOLD_US ? 'var(--red-light)' : 'var(--green-light)'};">${f.avgUs.toLocaleString()}</td>
        <td style="color:var(--text-muted);font-size:10px;">${diffStr} µs</td>
        <td>${_timebar(f.avgUs, maxAvg, barCls)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function _drawAvgCanvas() {
    const canvas = document.getElementById('ib_avgCanvas');
    if (!canvas) return;
    const avgs = metricData.frameAvgs;
    if (!avgs || avgs.length === 0) return;

    const wrap = canvas.parentElement;
    const W = wrap.clientWidth || 400;
    const H = wrap.clientHeight || 90;
    const dpr = window.devicePixelRatio || 1;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    const isLight = document.body.classList.contains('light-theme');
    const maxVal = Math.max(...avgs, THRESHOLD_US + 200);
    const pad = { t: 6, r: 6, b: 6, l: 6 };
    const iW = W - pad.l - pad.r;
    const iH = H - pad.t - pad.b;

    // Threshold line
    const thY = pad.t + iH - (THRESHOLD_US / maxVal) * iH;
    ctx.strokeStyle = isLight ? '#d97706' : '#f59e0b';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(pad.l, thY); ctx.lineTo(pad.l + iW, thY); ctx.stroke();
    ctx.setLineDash([]);

    // Area fill
    const pts = avgs.map((v, i) => ({
      x: pad.l + (i / (avgs.length - 1)) * iW,
      y: pad.t + iH - (v / maxVal) * iH
    }));

    ctx.beginPath();
    ctx.moveTo(pts[0].x, pad.t + iH);
    pts.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(pts[pts.length - 1].x, pad.t + iH);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + iH);
    grad.addColorStop(0, isLight ? 'rgba(37,99,235,0.22)' : 'rgba(59,130,246,0.28)');
    grad.addColorStop(1, isLight ? 'rgba(37,99,235,0.02)' : 'rgba(59,130,246,0.02)');
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    pts.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
    ctx.strokeStyle = isLight ? '#2563eb' : '#60a5fa';
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // Mark blown points
    ctx.fillStyle = isLight ? '#dc2626' : '#ef4444';
    pts.forEach((p, i) => {
      if (avgs[i] > THRESHOLD_US) {
        ctx.beginPath(); ctx.arc(p.x, p.y, 2.5, 0, Math.PI * 2); ctx.fill();
      }
    });
  }

  // ── 3. Maximum Time ────────────────────────────────────────────
  function _renderMax() {
    const top10 = metricData.top10;
    const sessionMax = metricData.maxUs;
    const exceed = sessionMax - THRESHOLD_US;
    _setText('ib_maxValue',  sessionMax.toLocaleString() + ' µs');
    _setText('ib_maxExceed', exceed > 0 ? '+' + exceed.toLocaleString() + ' µs' : 'Within');

    // second of the session-max entry
    const topEntry = top10.length > 0 ? top10[0] : null;
    _setText('ib_maxSecond', topEntry ? 's' + topEntry.second : '—');

    const tbody = document.getElementById('ib_maxBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    const maxUs = top10.length > 0 ? top10[0].timeUs : 1;
    top10.forEach((f, idx) => {
      const barCls = f.timeUs > THRESHOLD_US ? 'blown' : 'ok';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${_rankBadge(idx + 1)}</td>
        <td style="color:var(--text-primary);font-weight:600;">${f.frameIndex}</td>
        <td>s${f.second}</td>
        <td style="color:${f.timeUs > THRESHOLD_US ? 'var(--red-light)' : 'var(--green-light)'};">${f.timeUs.toLocaleString()}</td>
        <td>${_timebar(f.timeUs, maxUs, barCls)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // ── 4. Peak Frame ──────────────────────────────────────────────
  function _renderPeak() {
    const top10 = metricData.top10;
    const peakFrame = metricData.maxFrame;
    const peakTime  = metricData.maxUs;

    _setText('ib_peakHeroNum',  'Frame ' + peakFrame);
    _setText('ib_peakHeroTime', peakTime.toLocaleString() + ' µs — absolute session peak');
    _setText('ib_peakFrameNum',  peakFrame.toLocaleString());
    _setText('ib_peakFrameTime', peakTime.toLocaleString() + ' µs');

    const heroBadge = document.getElementById('ib_peakHeroBadge');
    if (heroBadge) {
      const blown = peakTime > THRESHOLD_US;
      heroBadge.innerHTML = blown
        ? '<span class="dash-badge critical">⚠️ Blown</span>'
        : '<span class="dash-badge excellent">✓ OK</span>';
    }
    const statusEl = document.getElementById('ib_peakStatus');
    if (statusEl) {
      const blown = peakTime > THRESHOLD_US;
      statusEl.className = 'dash-badge ' + (blown ? 'critical' : 'excellent');
      statusEl.textContent = blown ? '⚠️ Blown' : '✓ OK';
    }

    const tbody = document.getElementById('ib_peakBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    const maxUs = top10.length > 0 ? top10[0].timeUs : 1;
    top10.forEach((f, idx) => {
      const blown = f.timeUs > THRESHOLD_US;
      const statusBadge = blown
        ? '<span class="dash-badge critical" style="padding:2px 6px;font-size:9px;">⚠ Blown</span>'
        : '<span class="dash-badge excellent" style="padding:2px 6px;font-size:9px;">✓ OK</span>';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${_rankBadge(idx + 1)}</td>
        <td style="color:var(--blue-light);font-weight:700;font-size:13px;">${f.frameIndex}</td>
        <td>s${f.second}</td>
        <td style="color:${blown ? 'var(--red-light)' : 'var(--green-light)'};">${f.timeUs.toLocaleString()}</td>
        <td>${statusBadge}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function _setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // ── Legacy compat stubs (old modal populate fns no longer used inline) ───
  function populateBlownFramesModal() { _renderBlown(); }
  function populateAvgTimeModal()     { _renderAvg(); }
  function populateMaxTimeModal()     { _renderMax(); }
  function populatePeakFrameModal()   { _renderPeak(); }
  function renderBlownFramesTable()   {}
  function renderMaxFramesTable()     {}
  function sortBlownFrames(col)       { sortBlownInline(col); }
  function sortMaxFrames(col)         {}

  window.addEventListener('pywebviewready', () => {
    initTheme();
    refreshPorts();
    showAlert("Tool Ready", "Select a port and connect to begin.", "info");
    drawChart();
    
    document.addEventListener('keydown', handleGlobalKeyboard);
  });

  return { toggleTheme, toggleConnect, startAnalysis, stopAnalysis, exportCsv, refreshPorts, onChunk, onError, analyze, downloadExcel, onAnalysisComplete, onAnalysisError, showAlert, closeAlert, showLoading, hideLoading, openMetricModal, closeMetricModal, toggleMetricView, sortBlownInline };
})();

window._app = app;

// Disable Enter and Space keys from triggering buttons
  document.addEventListener('keydown', function(event) {
    if (document.activeElement && document.activeElement.tagName === 'BUTTON') {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault(); // Stops the button from being clicked
      }
    }
  });

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