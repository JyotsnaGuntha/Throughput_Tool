import os
import pandas as pd
from sklearn.ensemble import IsolationForest
from datetime import datetime  # <-- Added for the timestamp!

def analyze_all_csvs_in_folder():
    current_folder = os.path.dirname(os.path.abspath(__file__))
    files_in_folder = os.listdir(current_folder)
    
    csv_files = [
        f for f in files_in_folder 
        if f.endswith('.csv') and '_ML_Analyzed' not in f
    ]
    
    if not csv_files:
        print("No new CSV files found in this folder to analyze.")
        return

    print(f"Found {len(csv_files)} CSV file(s) to analyze.\n")

    for file_name in csv_files:
        input_path = os.path.join(current_folder, file_name)
        print(f"Loading -> {file_name}")
        
        try:
            df = pd.read_csv(input_path)
            
            if 'Time_Second' not in df.columns:
                print(f"Skipping {file_name}\n")
                continue
                
            X = df.drop(columns=['Time_Second'], errors='ignore')
            df = df.copy()
            
            # Train the ML model
            clf = IsolationForest(contamination=0.05, random_state=42)
            df['Anomaly_Score'] = clf.fit_predict(X)
            df['Status'] = df['Anomaly_Score'].map({1: 'Normal', -1: 'Anomaly'})
            
            # =========================================================
            # GENERATE THE TEXT REASONS
            # =========================================================
            frame_cols = [col for col in df.columns if col.startswith('Frame_')]
            
            normal_data = df[df['Status'] == 'Normal'][frame_cols]
            normal_means = normal_data.mean() if len(normal_data) > 0 else df[frame_cols].mean()
            
            reasons = []
            for idx, row in df.iterrows():
                if row['Status'] == 'Anomaly':
                    diff = row[frame_cols] - normal_means
                    abs_diff = diff.abs()
                    
                    anomalous_frames = abs_diff[abs_diff > 75].index
                    if len(anomalous_frames) == 0:
                        anomalous_frames = [abs_diff.idxmax()]
                    
                    row_reasons = []
                    for col in anomalous_frames:
                        actual_val = int(row[col])
                        normal_val = int(normal_means[col])
                        deviation = actual_val - normal_val
                        direction = "SPIKED" if deviation > 0 else "DROPPED"
                        row_reasons.append(f"{col} {direction} to {actual_val}µs (Normal avg: {normal_val}µs)")
                    
                    reasons.append(" | ".join(row_reasons))
                else:
                    reasons.append("")
            
            df['Anomaly_Reason'] = reasons
            cols = ['Time_Second', 'Status', 'Anomaly_Reason'] + frame_cols
            df = df[cols]
            
            # =========================================================
            # HIGHLIGHTING THE CELLS
            # =========================================================
            def highlight_exact_cells(data):
                styles = pd.DataFrame('', index=data.index, columns=data.columns)
                
                for idx, row in data.iterrows():
                    if row['Status'] == 'Anomaly':
                        styles.loc[idx, 'Time_Second'] = 'background-color: #ffe6e6;'
                        styles.loc[idx, 'Status'] = 'background-color: #ffe6e6; font-weight: bold; color: darkred;'
                        styles.loc[idx, 'Anomaly_Reason'] = 'background-color: #fff3cd; color: #856404;'
                        
                        abs_diff = abs(row[frame_cols] - normal_means)
                        bad_frames = abs_diff[abs_diff > 75].index
                        if len(bad_frames) == 0:
                            bad_frames = [abs_diff.idxmax()]
                            
                        for col in bad_frames:
                            styles.loc[idx, col] = 'background-color: #ff0000; color: white; font-weight: bold;'
                            
                return styles

            styled_df = df.style.apply(highlight_exact_cells, axis=None)
            
            # =========================================================
            # NEW: SAVE WITH TIMESTAMP IN FILENAME
            # =========================================================
            filename_without_ext, _ = os.path.splitext(file_name)
            
            # Get the exact time right now (e.g., 20260427_143005)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Add the timestamp to the end of the file name
            output_name = f"{filename_without_ext}_ML_Analyzed_{timestamp}.xlsx"
            output_path = os.path.join(current_folder, output_name)
            
            styled_df.to_excel(output_path, index=False, engine='openpyxl')
            
            anomalies = len(df[df['Status'] == 'Anomaly'])
            print(f"✅ Success! Analyzed {len(df)} seconds. Found {anomalies} anomalies.")
            print(f"💾 Saved Excel file as -> {output_name}\n")
            
        except Exception as e:
            print(f"❌ Error processing {file_name}: {e}\n")

if __name__ == "__main__":
    print("=== Throughput ML Analyzer ===")
    analyze_all_csvs_in_folder()
    input("Press Enter to exit...")