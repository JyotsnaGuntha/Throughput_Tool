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
import threading
import time
from datetime import datetime

import serial
import serial.tools.list_ports
import webview

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
        self._lock = threading.Lock()
        self._data: list[tuple[int, int, int]] = []   # (second, frame_idx, raw_percent)
        self._thread: threading.Thread | None = None

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
            with self._lock:
                self._data = []
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
            for i, raw in enumerate(chunk):
                rows.append((second, i, raw))   # store raw percent (0-100)
            with self._lock:
                self._data.extend(rows)

            # Compute stats for this chunk
            blown = sum(1 for r in chunk if (r * SCALE_FACTOR) > BLOWN_THRESHOLD)
            avg_us = sum(r * SCALE_FACTOR for r in chunk) // CHUNK_SIZE
            max_val = max(chunk)
            max_frame = chunk.index(max_val)   # 0-based frame index
            max_us = max_val * SCALE_FACTOR

            # Pass raw percent values for the scatter plot (frame index → percent)
            frame_data = list(chunk)   # list of 500 percent values

            window.evaluate_js(
                f"window._app && window._app.onChunk({json.dumps({'second': second, 'blown': blown, 'avg_us': avg_us, 'max_us': max_us, 'max_frame': max_frame, 'frame_data': frame_data})})"
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

            # 3. Group the flat data by the 'second' timestamp
            chunked_data = {}
            for sec, frame, pct in snapshot:
                if sec not in chunked_data:
                    chunked_data[sec] = [0] * CHUNK_SIZE 
                
                if 0 <= frame < CHUNK_SIZE:
                    chunked_data[sec][frame] = pct * SCALE_FACTOR

            # 4. Write to the CSV
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                header = ["Time_Second"] + [f"Frame_{i}" for i in range(CHUNK_SIZE)]
                writer.writerow(header)
                
                for sec in sorted(chunked_data.keys()):
                    row_data = [sec] + chunked_data[sec]
                    writer.writerow(row_data)
                    
            return json.dumps({"status": "ok", "path": filepath, "rows": len(chunked_data)})
            
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)})
   

    def get_summary(self) -> str:
        with self._lock:
            snapshot = list(self._data)
        if not snapshot:
            return json.dumps({"rows": 0, "seconds": 0, "blown": 0, "avg_us": 0, "max_us": 0, "max_frame": 0})
        total_rows = len(snapshot)
        seconds    = snapshot[-1][0] if snapshot else 0
        
        # Updated to check against microsecond threshold
        blown      = sum(1 for (_, _, pct) in snapshot if (pct * SCALE_FACTOR) > BLOWN_THRESHOLD)
        
        avg_us     = sum(pct * SCALE_FACTOR for (_, _, pct) in snapshot) // total_rows
        max_row    = max(snapshot, key=lambda r: r[2])
        max_us     = max_row[2] * SCALE_FACTOR
        max_frame  = max_row[1]
        return json.dumps({"rows": total_rows, "seconds": seconds, "blown": blown,
                           "avg_us": avg_us, "max_us": max_us, "max_frame": max_frame})
    
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
.theme-icon[style*="display: none"] {
  opacity: 0;
  transform: rotate(-180deg);
}
.theme-toggle:hover .theme-icon:not([style*="display: none"]) {
  color: var(--blue-light);
}


/* Layout */
.layout { 
  display: flex; 
  flex: 1; 
  overflow: hidden; 
  flex-direction: row-reverse;
}

/* Right Control Panel */
.control-panel {
  width: 320px;
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
}

.ctrl-row.full { flex-wrap: nowrap; }
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
  min-height: 100px;
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
  border-color: #d1d5db;
  color: #111827;
}

body.light-theme select:hover,
body.light-theme input[type=text]:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

body.light-theme select:focus,
body.light-theme input[type=text]:focus {
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
  padding-left: 14px;
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
  <div style="display: flex; align-items: center; gap: 16px;">
    <div class="pill" id="statusPill">
      <span class="pill-dot"></span>
      <span id="statusTxt">Disconnected</span>
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
    <!-- Chart area -->
    <div class="chart-area">
      <div class="chart-hdr">
        <span class="chart-ttl">Frame vs. Scheduler Load % (latest chunk)</span>
        <div class="legend">
          <div class="leg-item"><div class="leg-sq ok"></div>Normal (&le;2000µs)</div>
          <div class="leg-item"><div class="leg-sq blown"></div>Blown (&gt;2000µs)</div>
          <div class="leg-item"><div class="leg-ln"></div>2000µs threshold</div>
        </div>
      </div>
      <div class="chart-box"><canvas id="chart"></canvas></div>
    </div>

    <!-- Log container with resizable handle -->
    <div class="log-container">
      <div class="log-resizer" id="logResizer"></div>
      <div class="log">
        <div class="log-hdr">Activity Log</div>
        <div class="log-body" id="logBody"></div>
      </div>
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
      
      <!-- Row 3: Action Buttons -->
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
    </div>

    <!-- Metrics Section -->
    <div class="ctrl-section">
      <span class="ctrl-section-title">Metrics</span>
      <div class="metrics-panel">
        <div class="metric-row">
          <span class="metric-label">Frames Blown</span>
          <span class="metric-value blown" id="svBlown">—</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Avg Time</span>
          <span class="metric-value avg" id="svAvg">—</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Max Time</span>
          <span class="metric-value max" id="svMaxTime">—</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Peak Frame</span>
          <span class="metric-value frame" id="svMaxFrame">—</span>
        </div>
      </div>
    </div>
  </div>

</div>

<div id="toast"></div>

<script>
// ── Resizable Log Area ────────────────────────────────────────────────────────
const logResizer = document.getElementById('logResizer');
const logContainer = document.querySelector('.log-container');
let isResizing = false;

logResizer.addEventListener('mousedown', () => {
  isResizing = true;
  document.addEventListener('mousemove', handleResize);
  document.addEventListener('mouseup', stopResize);
});

function handleResize(e) {
  if (!isResizing) return;
  const mainRect = document.querySelector('.main').getBoundingClientRect();
  const newHeight = mainRect.bottom - e.clientY;
  if (newHeight > 60 && newHeight < mainRect.height - 100) {
    logContainer.style.height = newHeight + 'px';
    drawChart();
  }
}

function stopResize() {
  isResizing = false;
  document.removeEventListener('mousemove', handleResize);
  document.removeEventListener('mouseup', stopResize);
}

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
  let connected = false, running = false, canExport = false;

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
    if (isDark) {
      sunIcon.style.display = 'block';
      moonIcon.style.display = 'none';
    } else {
      sunIcon.style.display = 'none';
      moonIcon.style.display = 'block';
    }
  }

  // Attach theme toggle listener
  document.getElementById('themeToggle').addEventListener('click', toggleTheme);

  function log(msg, cls = '') {
    const b = document.getElementById('logBody');
    const e = document.createElement('div');
    e.className = 'log-entry ' + cls;
    const t = new Date().toLocaleTimeString('en', { hour12: false });
    e.textContent = t + '  ' + msg;
    b.appendChild(e);
    b.scrollTop = b.scrollHeight;
    // Animate in
    e.style.opacity = '0';
    e.style.transform = 'translateX(-10px)';
    setTimeout(() => {
      e.style.transition = 'all 0.3s ease';
      e.style.opacity = '1';
      e.style.transform = 'translateX(0)';
    }, 10);
  }

  function toast(msg, cls = '') {
    const t = document.getElementById('toast');
    t.textContent = msg; 
    t.className = cls + ' show';
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove('show'), 4500);
  }

  function setStatus(state, label) {
    document.getElementById('statusPill').className = 'pill ' + state;
    document.getElementById('statusTxt').textContent = label;
  }

  function sync() {
    const btn = document.getElementById('btnConn');
    btn.title = connected ? 'Disconnect from port' : 'Connect to port';
    document.getElementById('btnStart').disabled  = !connected || running;
    document.getElementById('btnStop').disabled   = !running;
    document.getElementById('btnExport').disabled = !canExport;
  }

  function setStats(blown, avgUs, maxUs, maxFrame) {
    document.getElementById('svBlown').textContent    = blown    != null ? Number(blown).toLocaleString()   : '—';
    document.getElementById('svAvg').textContent      = avgUs    != null ? Number(avgUs).toLocaleString()   : '—';
    document.getElementById('svMaxTime').textContent  = maxUs    != null ? Number(maxUs).toLocaleString()   : '—';
    document.getElementById('svMaxFrame').textContent = maxFrame != null ? Number(maxFrame).toLocaleString() : '—';
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
      connected = false; running = false; canExport = false;
      setStatus('', 'Disconnected');
      log('Disconnected.', 'warn');
    } else {
      const port = document.getElementById('portSel').value;
      const baud = document.getElementById('baudSel').value;
      if (!port) { log('Select a COM port first.', 'err'); return; }
      const r = JSON.parse(await window.pywebview.api.connect(port, baud));
      if (r.status === 'ok') {
        connected = true;
        setStatus('connected', 'Connected');
        log(r.message, 'ok');
      } else {
        log('Failed: ' + r.message, 'err');
      }
    }
    sync();
  }

  async function startAnalysis() {
    const r = JSON.parse(await window.pywebview.api.start_analysis());
    if (r.status === 'ok') {
      running = true; canExport = false;
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
    log(`s${data.second}: blown=${data.blown}, avg=${data.avg_us}µs, max=${data.max_us}µs @ frame ${data.max_frame}`, 'info');
  }

  function onError(msg) {
    running = false; setStatus('', 'Error');
    log('Serial error: ' + msg, 'err'); sync();
  }

  window.addEventListener('pywebviewready', () => {
    initTheme();
    refreshPorts();
    log('Tool ready. Select a port and connect.', 'info');
    drawChart();
  });

  return { toggleTheme, toggleConnect, startAnalysis, stopAnalysis, exportCsv, refreshPorts, onChunk, onError };
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
