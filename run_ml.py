import argparse
import json
import os
import tempfile
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROW_THRESHOLD_US = 2000.0
CRIT_Z = 3.0
CRIT_ABS_DIFF = 200.0
CRIT_DELTA = 250.0
MIN_STD = 25.0
MAX_REASON_FRAMES = 8
ROLLING_WINDOW = 10

STATUS_NORMAL = "Normal"
STATUS_SPIKE = "Spike"

COLOR_WARNING = "#ffe8cc"
COLOR_CRITICAL = "#ff4d4f"


def validate_and_prepare_csv(input_path: str) -> tuple[pd.DataFrame, list[str], dict]:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    df = pd.read_csv(input_path)

    if "Time_Second" not in df.columns:
        raise ValueError("Missing required column: Time_Second")

    required_frames = [f"Frame_{i}" for i in range(500)]
    missing = [c for c in required_frames if c not in df.columns]
    if missing:
        raise ValueError(f"Missing frame columns: {missing[:10]}{' ...' if len(missing) > 10 else ''}")

    keep_cols = ["Time_Second"] + required_frames
    base_df = df[keep_cols].copy()

    base_df["Time_Second"] = pd.to_numeric(base_df["Time_Second"], errors="coerce")
    frame_df = base_df[required_frames].apply(pd.to_numeric, errors="coerce")

    null_cells_before = int(frame_df.isnull().sum().sum())
    frame_df = frame_df.interpolate(axis=0, limit_direction="both").fillna(0)
    null_cells_after = int(frame_df.isnull().sum().sum())

    base_df[required_frames] = frame_df
    base_df = base_df.dropna(subset=["Time_Second"]).reset_index(drop=True)

    validation = {
        "rows": len(base_df),
        "missing_frame_columns": len(missing),
        "null_cells_before_fix": null_cells_before,
        "null_cells_after_fix": null_cells_after,
    }
    return base_df, required_frames, validation


def _build_reason_text(
    row_idx,
    df,
    frame_cols,
    means,
    stds,
    deltas,
    row_threshold_flag,
    critical_mask,
):
    reasons = []

    if row_threshold_flag[row_idx]:
        exceeded_cols = [col for col in frame_cols if float(df.loc[row_idx, col]) > ROW_THRESHOLD_US]
        if exceeded_cols:
            top_exceeded = sorted(exceeded_cols, key=lambda col: float(df.loc[row_idx, col]), reverse=True)[:3]
            top_text = ", ".join(f"{col}={int(df.loc[row_idx, col])}us" for col in top_exceeded)
            reasons.append(
                f"Row-wise anomaly: value exceeded {int(ROW_THRESHOLD_US)}us threshold ({top_text})"
            )

    critical_frames = [col for col in frame_cols if critical_mask.loc[row_idx, col]]

    def frame_reason(col, level):
        actual_val = float(df.loc[row_idx, col])
        mean_val = float(means[col])
        std_val = float(stds[col])
        delta = actual_val - mean_val
        jump = float(deltas.loc[row_idx, col])
        movement = f"jump {int(jump)}us"
        direction = "SPIKED" if delta >= 0 else "DROPPED"
        z_score = abs(delta) / (std_val if std_val > 0 else MIN_STD)
        return (
            f"{col} {level} {direction} to {int(actual_val)}us "
            f"(avg {int(mean_val)}us, delta {int(delta)}us, {movement}, z={z_score:.2f})"
        )

    for col in critical_frames[:MAX_REASON_FRAMES]:
        reasons.append(frame_reason(col, "CRITICAL"))

    extra_count = max(0, len(critical_frames) - MAX_REASON_FRAMES)
    if extra_count > 0:
        reasons.append(f"{extra_count} additional frame anomalies not shown")

    return " | ".join(reasons)


def analyze_dataframe(base_df: pd.DataFrame, frame_cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    work_df = base_df.copy()

    row_isolation_flag = (work_df[frame_cols] > ROW_THRESHOLD_US).any(axis=1)

    means = work_df[frame_cols].mean()
    stds = work_df[frame_cols].std(ddof=0).clip(lower=MIN_STD)

    diff = work_df[frame_cols].subtract(means, axis=1)
    abs_diff = diff.abs()
    z_scores = abs_diff.divide(stds, axis=1)
    deltas = work_df[frame_cols].diff().fillna(0.0)

    rolling_mean = work_df[frame_cols].rolling(window=ROLLING_WINDOW, min_periods=1).mean()
    rolling_var = work_df[frame_cols].rolling(window=ROLLING_WINDOW, min_periods=1).var().fillna(0.0)
    ma_instability = (work_df[frame_cols] - rolling_mean).abs() > CRIT_ABS_DIFF
    var_instability = rolling_var > (rolling_var.mean() + rolling_var.std(ddof=0)).fillna(0)
    unstable_mask = (ma_instability | var_instability).any(axis=1)

    critical_spike = (diff > 0) & ((z_scores >= CRIT_Z) | (abs_diff >= CRIT_ABS_DIFF) | (deltas >= CRIT_DELTA))
    critical_drop = (diff < 0) & ((z_scores >= CRIT_Z) | (abs_diff >= CRIT_ABS_DIFF) | (deltas <= -CRIT_DELTA))

    critical_mask = critical_spike | critical_drop

    has_critical = critical_mask.any(axis=1)

    status = pd.Series(STATUS_NORMAL, index=work_df.index)
    status.loc[row_isolation_flag | has_critical] = STATUS_SPIKE

    detection_type = pd.Series("None", index=work_df.index)
    detection_type.loc[row_isolation_flag & ~has_critical] = "RowWise"
    detection_type.loc[has_critical & ~row_isolation_flag] = "ColumnWise"
    detection_type.loc[has_critical & row_isolation_flag] = "RowWise+ColumnWise"

    reasons = []
    critical_frames_col = []
    highlight_color_col = []
    severity_scores = []
    health_scores = []

    severity_matrix = (z_scores * 0.5) + (abs_diff.divide(means.replace(0, 1), axis=1) * 0.3) + (
        rolling_var.divide(stds, axis=1) * 0.2
    )
    severity_matrix = severity_matrix.fillna(0)

    for idx in work_df.index:
        critical_frames = [col for col in frame_cols if critical_mask.loc[idx, col]]

        critical_frames_col.append(",".join(critical_frames))

        row_severity = float(severity_matrix.loc[idx].mean())
        severity_scores.append(row_severity)
        health_scores.append(max(0.0, 100.0 - min(100.0, row_severity * 20.0)))

        if status.loc[idx] == STATUS_SPIKE:
            highlight_color_col.append(COLOR_CRITICAL)
        else:
            highlight_color_col.append("")

        if status.loc[idx] == STATUS_NORMAL:
            reasons.append("")
        else:
            reasons.append(
                _build_reason_text(
                    idx,
                    work_df,
                    frame_cols,
                    means,
                    stds,
                    deltas,
                    row_isolation_flag,
                    # warning_mask,
                    critical_mask,
                    # unstable_mask,
                )
            )

    out_df = work_df.copy()
    out_df["Status"] = status
    out_df["Detection_Type"] = detection_type
    out_df["Anomaly_Reason"] = reasons
    out_df["Critical_Frames"] = critical_frames_col
    out_df["Highlight_Color"] = highlight_color_col
    out_df["Row_Anomaly_Score"] = work_df[frame_cols].max(axis=1)
    out_df["Severity_Score"] = severity_scores
    out_df["Frame_Health_Score"] = health_scores

    critical_count = int((out_df["Status"] == STATUS_SPIKE).sum())
    anomalies = int((out_df["Status"] != STATUS_NORMAL).sum())
    
    # Count RowWise and ColumnWise detections for metrics
    frames_blown = int((out_df["Detection_Type"].str.contains("RowWise", na=False)).sum())
    spikes_detected = int((out_df["Detection_Type"].str.contains("ColumnWise", na=False)).sum())

    meta = {
        "rows": len(out_df),
        "anomalies": anomalies,
        "critical": critical_count,
        "frames_blown": frames_blown,
        "spikes_detected": spikes_detected,
        "avg_latency": float(work_df[frame_cols].mean().mean()),
        "max_latency": float(work_df[frame_cols].max().max()),
        "health_score": float(pd.Series(health_scores).mean() if health_scores else 100.0),
    }

    return out_df, critical_mask, meta


def save_excel_and_csv(analyzed_df: pd.DataFrame, frame_cols: list[str], base_name: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    excel_path = os.path.join(output_dir, "analyzed_data.xlsx")
    anomaly_csv_path = os.path.join(output_dir, "anomalies.csv")

    ordered_cols = [
        "Time_Second",
        "Status",
        "Detection_Type",
        "Anomaly_Reason",
        "Critical_Frames",
        "Highlight_Color",
        "Row_Anomaly_Score",
        "Severity_Score",
        "Frame_Health_Score",
    ] + frame_cols

    final_df = analyzed_df[ordered_cols]
    final_df.to_excel(excel_path, index=False, engine="openpyxl")

    anomalies_only = final_df[final_df["Status"] != STATUS_NORMAL].copy()
    anomalies_only.to_csv(anomaly_csv_path, index=False)

    return excel_path, anomaly_csv_path, len(anomalies_only)


def generate_visualizations(analyzed_df: pd.DataFrame, frame_cols: list[str], charts_dir: str) -> dict:
    os.makedirs(charts_dir, exist_ok=True)
    sns.set(style="whitegrid")

    chart_paths = {}

    # 2. Anomaly frequency graph
    plt.figure(figsize=(8, 4))
    counts = analyzed_df["Status"].value_counts().reindex([STATUS_NORMAL, STATUS_SPIKE], fill_value=0)
    sns.barplot(x=counts.index, y=counts.values, palette=["#10b981", "#ef4444"])
    plt.title("Anomaly Frequency")
    plt.ylabel("Rows")
    plt.tight_layout()
    p2 = os.path.join(charts_dir, "anomaly_frequency.png")
    plt.savefig(p2, dpi=160)
    plt.close()
    chart_paths["anomaly_frequency"] = p2

    # 3. Spike timeline
    row_peak = analyzed_df[frame_cols].max(axis=1)
    plt.figure(figsize=(12, 4))
    plt.plot(analyzed_df["Time_Second"], row_peak, color="#7c3aed", linewidth=1.2)
    plt.axhline(y=ROW_THRESHOLD_US, color="#ef4444", linestyle="--", linewidth=1)
    plt.title("Spike Timeline (Peak Frame Latency per Second)")
    plt.xlabel("Time_Second")
    plt.ylabel("Latency (us)")
    plt.tight_layout()
    p3 = os.path.join(charts_dir, "spike_timeline.png")
    plt.savefig(p3, dpi=160)
    plt.close()
    chart_paths["spike_timeline"] = p3


    # 5. Top critical frame chart
    top_crit = analyzed_df[analyzed_df["Status"] == STATUS_SPIKE]
    if top_crit.empty:
        top_vals = analyzed_df[frame_cols].max().sort_values(ascending=False).head(10)
    else:
        top_vals = top_crit[frame_cols].max().sort_values(ascending=False).head(10)
    plt.figure(figsize=(11, 4))
    sns.barplot(x=top_vals.index, y=top_vals.values, color="#ef4444")
    plt.xticks(rotation=45, ha="right")
    plt.title("Top Critical Frames")
    plt.ylabel("Max Latency (us)")
    plt.tight_layout()
    p5 = os.path.join(charts_dir, "top_critical_frames.png")
    plt.savefig(p5, dpi=160)
    plt.close()
    chart_paths["top_critical_frames"] = p5

    return chart_paths


def _table(data, col_widths=None, header_bg="#2563eb"):
    t = Table(data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def generate_pdf_report(
    pdf_path: str,
    analyzed_df: pd.DataFrame,
    meta: dict,
    chart_paths: dict,
    input_csv: str,
):
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1d4ed8"),
        alignment=1,
        spaceAfter=12,
    )
    sub_style = ParagraphStyle("SubStyle", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#374151"), alignment=1)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=14, textColor=colors.HexColor("#111827"), spaceBefore=8, spaceAfter=8)

    # Cover page
    story.append(Paragraph("Throughput Analysis Report", title_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        _table(
            [
                ["Metric", "Value"],
                ["Active Time (seconds)", f"{meta['rows']:,}"],
                ["Frames Blown", f"{meta['frames_blown']:,}"],
                ["Spikes Detected", f"{meta['spikes_detected']:,}"],
                ["Maximum Time", f"{meta['max_latency']:.2f} us"],
                ["Average Time", f"{meta['avg_latency']:.2f} us"],
                ["Overall Throughput %", ]
            ],
            col_widths=[2.5 * inch, 3.3 * inch],
            header_bg="#1d4ed8",
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    # Add Anomaly Frequency chart to first page
    if "anomaly_frequency" in chart_paths and os.path.exists(chart_paths["anomaly_frequency"]):
        story.append(Paragraph("Anomaly Frequency", h2))
        story.append(Image(chart_paths["anomaly_frequency"], width=3.5 * inch, height=2.0 * inch))
        story.append(Spacer(1, 0.1 * inch))

    # Add Top Critical Frames chart to first page
    if "top_critical_frames" in chart_paths and os.path.exists(chart_paths["top_critical_frames"]):
        story.append(Paragraph("Top 10 Maximum Frames Graph", h2))
        story.append(Image(chart_paths["top_critical_frames"], width=5.5 * inch, height=2.0 * inch))

    story.append(PageBreak())

    # Critical frame ranking
    story.append(Paragraph("Top 10 Maximum Frame Times", h2))
    frame_cols = [c for c in analyzed_df.columns if c.startswith("Frame_")]
    top_critical = analyzed_df[analyzed_df["Status"] == STATUS_SPIKE]
    if top_critical.empty:
        top_vals = analyzed_df[frame_cols].max().sort_values(ascending=False).head(10)
    else:
        top_vals = top_critical[frame_cols].max().sort_values(ascending=False).head(10)
    ranking_table = [["Rank", "Frame", "Peak Time (us)"]]
    for i, (f, v) in enumerate(top_vals.items(), start=1):
        ranking_table.append([i, f, f"{float(v):.2f}"])
    story.append(_table(ranking_table, col_widths=[0.8 * inch, 2.2 * inch, 2.8 * inch], header_bg="#dc2626"))

    # # ML explanations
    # story.append(Paragraph("ML-generated Explanations", h2))
    # explanations = analyzed_df[analyzed_df["Status"] != STATUS_NORMAL][["Time_Second", "Status", "Anomaly_Reason"]].head(12)
    # if explanations.empty:
    #     story.append(Paragraph("No anomalies detected.", styles["Normal"]))
    # else:
    #     for _, row in explanations.iterrows():
    #         story.append(
    #             Paragraph(
    #                 f"<b>T={int(row['Time_Second'])}</b> [{row['Status']}] {row['Anomaly_Reason'][:360]}",
    #                 styles["Normal"],
    #             )
    #         )
    #         story.append(Spacer(1, 0.05 * inch))

    # Build and save the PDF document
    doc.build(story)



def run_pipeline(input_csv: str, output_dir: str):
    base_name = os.path.splitext(os.path.basename(input_csv))[0]

    base_df, frame_cols, validation = validate_and_prepare_csv(input_csv)
    analyzed_df, critical_mask, meta = analyze_dataframe(base_df, frame_cols)

    excel_path, anomaly_csv_path, anomaly_count = save_excel_and_csv(analyzed_df, frame_cols, base_name, output_dir)

    with tempfile.TemporaryDirectory(prefix="throughput_charts_") as charts_dir:
        chart_paths = generate_visualizations(analyzed_df, frame_cols, charts_dir)

        pdf_path = os.path.join(output_dir, "analysis_report.pdf")
        generate_pdf_report(pdf_path, analyzed_df, meta, chart_paths, input_csv)
    
    # Temp directory is now cleaned up, but PDF has been generated with images embedded

    result = {
        "status": "success",
        "rows": meta["rows"],
        "anomalies": anomaly_count,
        "critical": meta["critical"],
        "avg_latency": round(meta["avg_latency"], 3),
        "max_latency": round(meta["max_latency"], 3),
        "health_score": round(meta["health_score"], 3),
        "validation": validation,
        "excel_path": excel_path,
        "anomaly_csv_path": anomaly_csv_path,
        "pdf_path": pdf_path,
        "charts": chart_paths,
        "execution_status": "completed",
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Throughput diagnostics ML + reporting pipeline")
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--output-dir", required=True, help="Output folder path")
    args = parser.parse_args()

    try:
        result = run_pipeline(args.input, args.output_dir)
        print(json.dumps(result))
    except Exception as exc:
        error_payload = {"status": "error", "message": str(exc), "execution_status": "failed"}
        print(json.dumps(error_payload))
        raise


if __name__ == "__main__":
    main()
