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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:       #f5f6f8;
  --surface:  #ffffff;
  --border:   #e4e6eb;
  --border2:  #d0d3dc;
  --text:     #111827;
  --muted:    #6b7280;
  --hint:     #9ca3af;
  --blue:     #3b6fe0;
  --blue-bg:  #eff3fd;
  --blue-bd:  #c7d6f8;
  --green:    #16a34a;
  --green-bg: #f0fdf4;
  --green-bd: #bbf7d0;
  --red:      #dc2626;
  --red-bg:   #fef2f2;
  --amber:    #d97706;
  --amber-bg: #fffbeb;
  --purple:   #7c3aed;
  --purple-bg:#f5f3ff;
  --purple-bd:#ddd6fe;
  --r:        10px;
}
body {
  font-family: 'Inter', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Topbar */
.topbar {
  height: 56px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.brand { display: flex; align-items: center; gap: 12px; }

/* Logo SVG area */
.logo-mark {
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.logo-mark svg { width: 38px; height: 38px; }

.brand-text { display: flex; flex-direction: column; gap: 1px; }
.brand-name { font-size: 15px; font-weight: 700; letter-spacing: -0.02em; color: var(--text); }
.brand-sub  { font-size: 11px; color: var(--muted); font-weight: 400; }

.pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 999px;
  font-size: 12px; font-weight: 500;
  border: 1px solid var(--border2);
  color: var(--muted);
}
.pill-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--hint); }
.pill.connected  { border-color: var(--green-bd); color: var(--green); background: var(--green-bg); }
.pill.connected .pill-dot { background: var(--green); }
.pill.running    { border-color: var(--blue-bd);  color: var(--blue);  background: var(--blue-bg); animation: blink 1.4s ease-in-out infinite; }
.pill.running .pill-dot  { background: var(--blue); }
.pill.done       { border-color: #fde68a; color: var(--amber); background: var(--amber-bg); }
.pill.done .pill-dot     { background: var(--amber); }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.45} }

/* Layout */
.layout { display: flex; flex: 1; overflow: hidden; }

/* Sidebar */
.sidebar {
  width: 230px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 10px 12px 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.sec-label {
  font-size: 10px; font-weight: 600; letter-spacing: .09em;
  text-transform: uppercase; color: var(--hint);
  padding: 14px 2px 6px;
}
.field { margin-bottom: 8px; }
.field > label {
  display: block; font-size: 11px; font-weight: 500;
  color: var(--muted); margin-bottom: 4px;
}

/* Port row: select + refresh icon button side by side */
.port-row { display: flex; gap: 5px; align-items: center; }
.port-row select { flex: 1; }
.icon-btn {
  flex-shrink: 0;
  width: 34px; height: 34px;
  background: var(--bg);
  border: 1px solid var(--border2);
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all .15s;
  color: var(--muted);
}
.icon-btn:hover { background: #eaecf1; color: var(--blue); border-color: var(--blue-bd); }
.icon-btn:active { transform: scale(.95); }
.icon-btn svg { width: 14px; height: 14px; flex-shrink: 0; }
.spin { animation: spin .6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

select, input[type=text] {
  width: 100%;
  height: 34px;
  background: var(--bg);
  border: 1px solid var(--border2);
  border-radius: 7px;
  color: var(--text);
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  padding: 0 30px 0 10px;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%239ca3af' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  transition: border-color .15s, box-shadow .15s;
}
select:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(59,111,224,.1); outline: none; }

.btn {
  width: 100%; height: 34px;
  border: 1px solid transparent; border-radius: 7px;
  font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 500;
  cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 7px;
  transition: all .15s; margin-bottom: 5px; white-space: nowrap;
}
.btn svg { flex-shrink: 0; }
.btn:disabled { opacity: .38; cursor: not-allowed; }
.btn:not(:disabled):active { transform: scale(.98); }
.btn-blue    { background: var(--blue);       color: #fff;          border-color: var(--blue); }
.btn-blue:not(:disabled):hover    { background: #2d5dc7; border-color: #2d5dc7; }
.btn-ghost   { background: var(--bg);         color: var(--muted);  border-color: var(--border2); }
.btn-ghost:not(:disabled):hover   { background: #eaecf1; }
.btn-green   { background: var(--green-bg);   color: var(--green);  border-color: var(--green-bd); }
.btn-green:not(:disabled):hover   { background: #dcfce7; }
.btn-red     { background: var(--red-bg);     color: var(--red);    border-color: #fecaca; }
.btn-red:not(:disabled):hover     { background: #fee2e2; }
.btn-purple  { background: var(--purple-bg);  color: var(--purple); border-color: var(--purple-bd); }
.btn-purple:not(:disabled):hover  { background: #ede9fe; }
.hr { height: 1px; background: var(--border); margin: 6px 0 2px; }

/* Main */
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }

/* Stats row — 4 cards */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 12px 14px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.scard {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 10px 13px 11px;
}
.scard-lbl {
  font-size: 10px; font-weight: 600; letter-spacing: .06em;
  text-transform: uppercase; color: var(--hint); margin-bottom: 4px;
}
.scard-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 19px; font-weight: 500; line-height: 1.1; color: var(--text);
}
.scard-val.c-blue   { color: var(--blue); }
.scard-val.c-green  { color: var(--green); }
.scard-val.c-amber  { color: var(--amber); }
.scard-val.c-red    { color: var(--red); }
.scard-val.c-purple { color: var(--purple); }
.scard-unit { font-size: 10px; color: var(--hint); margin-top: 4px; }
.scard-sub  { font-size: 10px; color: var(--muted); margin-top: 2px; font-family: 'JetBrains Mono', monospace; }

/* Chart area */
.chart-area {
  flex: 1; min-height: 0;
  padding: 12px 14px 8px;
  display: flex; flex-direction: column; gap: 8px;
}
.chart-hdr {
  display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
}
.chart-ttl { font-size: 13px; font-weight: 600; }
.legend { display: flex; gap: 14px; }
.leg-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--muted); }
.leg-sq { width: 10px; height: 10px; border-radius: 3px; }
.leg-sq.blown { background: #ef4444; }
.leg-sq.ok    { background: #3b6fe0; }
.leg-ln { width: 14px; height: 2px; border-top: 2px dashed #e8922a; }

.chart-box {
  flex: 1; min-height: 0; position: relative;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r); overflow: hidden;
}
canvas#chart { position: absolute; inset: 0; width: 100%; height: 100%; }

/* Log */
.log {
  flex-shrink: 0; height: 100px; border-top: 1px solid var(--border);
  background: var(--surface); display: flex; flex-direction: column;
}
.log-hdr {
  padding: 5px 14px; border-bottom: 1px solid var(--border);
  font-size: 10px; font-weight: 600; letter-spacing: .08em;
  text-transform: uppercase; color: var(--hint); flex-shrink: 0;
}
.log-body { flex: 1; overflow-y: auto; padding: 4px 14px 6px; }
.log-entry {
  font-family: 'JetBrains Mono', monospace; font-size: 11.5px;
  line-height: 1.9; color: var(--muted);
  padding-left: 10px; border-left: 2px solid transparent;
}
.log-entry.ok   { color: var(--green); border-color: var(--green); }
.log-entry.err  { color: var(--red);   border-color: var(--red);  }
.log-entry.info { color: var(--blue);  border-color: var(--blue); }
.log-entry.warn { color: var(--amber); border-color: var(--amber);}

/* Toast */
#toast {
  position: fixed; bottom: 20px; right: 20px;
  background: #111827; color: #fff; font-size: 13px; font-weight: 500;
  padding: 12px 18px; border-radius: var(--r);
  opacity: 0; transform: translateY(8px);
  transition: all .3s cubic-bezier(.16,1,.3,1);
  pointer-events: none; z-index: 9999;
  max-width: 360px; line-height: 1.4;
}
#toast.success { background: var(--green); }
#toast.show    { opacity: 1; transform: translateY(0); }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }
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
  <div class="pill" id="statusPill">
    <span class="pill-dot"></span>
    <span id="statusTxt">Disconnected</span>
  </div>
</div>

<div class="layout">

  <div class="sidebar">

    <div class="sec-label">Connection</div>
    <div class="field">
      <label>COM Port</label>
      <div class="port-row">
        <select id="portSel"><option value="">Select port…</option></select>
        <button class="icon-btn" id="btnRefresh" title="Refresh ports" onclick="app.refreshPorts()">
          <svg id="refreshIcon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 8a7 7 0 1 0 2-4.9"/>
            <polyline points="1,3 1,8 6,8"/>
          </svg>
        </button>
      </div>
    </div>
    <div class="field">
      <label>Baud Rate</label>
      <select id="baudSel">
        <option>9600</option><option>19200</option><option>38400</option>
        <option selected>57600</option><option>115200</option>
        <option>230400</option><option>460800</option><option>921600</option>
      </select>
    </div>
    <button class="btn btn-blue" id="btnConn" onclick="app.toggleConnect()">
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="5" cy="11" r="2"/><circle cx="11" cy="5" r="2"/><line x1="6.5" y1="9.5" x2="9.5" y2="6.5"/></svg>
      Connect
    </button>

    <div class="hr"></div>
    <div class="sec-label">Analysis</div>
    <button class="btn btn-green" id="btnStart" onclick="app.startAnalysis()" disabled>
      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><polygon points="4,2 14,8 4,14"/></svg>
      Start Analysis
    </button>
    <button class="btn btn-red" id="btnStop" onclick="app.stopAnalysis()" disabled>
      <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><rect x="3" y="3" width="10" height="10" rx="2"/></svg>
      Stop Analysis
    </button>

    <div class="hr"></div>
    <div class="sec-label">Export</div>
    <button class="btn btn-purple" id="btnExport" onclick="app.exportCsv()" disabled>
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v9M4 7l4 4 4-4"/><line x1="2" y1="14" x2="14" y2="14"/></svg>
      Export CSV
    </button>

  </div>

  <div class="main">

    <!-- 4 stat cards -->
    <div class="stats">
      <div class="scard">
        <div class="scard-lbl">Frames Blown</div>
        <div class="scard-val c-red" id="svBlown">—</div>
        <div class="scard-unit">frames &gt; 2000µs threshold</div>
      </div>
      <div class="scard">
        <div class="scard-lbl">Average Time</div>
        <div class="scard-val c-green" id="svAvg">—</div>
        <div class="scard-unit">µs per frame</div>
      </div>
      <div class="scard">
        <div class="scard-lbl">Maximum Time</div>
        <div class="scard-val c-amber" id="svMaxTime">—</div>
        <div class="scard-unit">µs (peak)</div>
      </div>
      <div class="scard">
        <div class="scard-lbl">Peak Frame</div>
        <div class="scard-val c-purple" id="svMaxFrame">—</div>
        <div class="scard-unit">frame index (0–499)</div>
      </div>
    </div>

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

    <div class="log">
      <div class="log-hdr">Activity Log</div>
      <div class="log-body" id="logBody"></div>
    </div>

  </div>
</div>

<div id="toast"></div>

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
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, W, H);

  if (!latestChunk) {
    ctx.fillStyle = '#9ca3af';
    ctx.font = "13px 'Inter', sans-serif";
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('Start analysis to see live data', W / 2, H / 2);
    return;
  }

  // ── Axes dimensions ──
  const pad = { t: 20, r: 20, b: 40, l: 50 };
  const iW = W - pad.l - pad.r;
  const iH = H - pad.t - pad.b;

  // ── Y axis: 0-100% ──
  ctx.font = "9px 'JetBrains Mono', monospace";
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  
  for (let p = 0; p <= 100; p += 20) {
    const y = pad.t + iH - (p / 100) * iH;
    ctx.strokeStyle = '#f0f1f4'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + iW, y); ctx.stroke();
    ctx.fillStyle = '#9ca3af';
    ctx.fillText(p + '%', pad.l - 8, y);
  }

  // Y axis title
  ctx.save();
  ctx.translate(14, pad.t + iH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.font = "9px 'Inter', sans-serif";
  ctx.fillStyle = '#9ca3af';
  ctx.fillText('Scheduler Load %', 0, 0);
  ctx.restore();

  // ── X axis: Frame 0-499 ──
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.font = "9px 'JetBrains Mono', monospace";

  const frameSteps = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 499];
  frameSteps.forEach(f => {
    const x = pad.l + (f / 499) * iW;
    ctx.fillStyle = '#9ca3af';
    ctx.fillText(f, x, pad.t + iH + 6);
  });

  // X axis title
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.font = "9px 'Inter', sans-serif";
  ctx.fillStyle = '#9ca3af';
  ctx.fillText('Frame Index', pad.l + iW / 2, H - 2);

  // ── Dynamic Threshold Line ──
  const THRESHOLD_US = 2000;
  const SCALE_FACTOR = 20;
  const threshPct = THRESHOLD_US / SCALE_FACTOR; 

  if (threshPct <= 100) {
    const threshY = pad.t + iH - (threshPct / 100) * iH;
    ctx.strokeStyle = '#e8922a'; ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(pad.l, threshY); ctx.lineTo(pad.l + iW, threshY); ctx.stroke();
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
  ctx.moveTo(points[0].x, pad.t + iH); // Start at bottom-left of the graph
  points.forEach(pt => ctx.lineTo(pt.x, pt.y)); // Trace the peaks
  ctx.lineTo(points[points.length - 1].x, pad.t + iH); // Drop to bottom-right
  ctx.closePath();

  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + iH);
  grad.addColorStop(0, 'rgba(59,111,224,0.35)'); // Solid blue near the peaks
  grad.addColorStop(1, 'rgba(59,111,224,0.01)'); // Fade to almost nothing at the bottom
  ctx.fillStyle = grad;
  ctx.fill();

  // ── Draw Crisp Top Line ──
  ctx.beginPath();
  points.forEach((pt, i) => {
    if (i === 0) ctx.moveTo(pt.x, pt.y);
    else ctx.lineTo(pt.x, pt.y);
  });
  ctx.strokeStyle = '#3b6fe0';
  ctx.lineWidth = 1.2;          // A thin, sharp line prevents it from looking messy
  ctx.lineJoin = 'round';       // Smooths out the jagged peaks slightly
  ctx.stroke();

  // ── Draw Red Dots for "Blown" Frames ──
  ctx.fillStyle = '#ef4444';
  points.forEach(pt => {
    if ((pt.pct * SCALE_FACTOR) > THRESHOLD_US) {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
  });
}
new ResizeObserver(drawChart).observe(document.querySelector('.chart-box'));

// ── App controller ─────────────────────────────────────────────────────────────
const app = (() => {
  let connected = false, running = false, canExport = false;

  function log(msg, cls = '') {
    const b = document.getElementById('logBody');
    const e = document.createElement('div');
    e.className = 'log-entry ' + cls;
    const t = new Date().toLocaleTimeString('en', { hour12: false });
    e.textContent = t + '  ' + msg;
    b.appendChild(e);
    b.scrollTop = b.scrollHeight;
  }

  function toast(msg, cls = '') {
    const t = document.getElementById('toast');
    t.textContent = msg; t.className = cls + ' show';
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove('show'), 4500);
  }

  function setStatus(state, label) {
    document.getElementById('statusPill').className = 'pill ' + state;
    document.getElementById('statusTxt').textContent = label;
  }

  function sync() {
    const btn = document.getElementById('btnConn');
    if (connected) {
      btn.className = 'btn btn-ghost';
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><line x1="3" y1="3" x2="13" y2="13"/><line x1="13" y1="3" x2="3" y2="13"/></svg> Disconnect`;
    } else {
      btn.className = 'btn btn-blue';
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="5" cy="11" r="2"/><circle cx="11" cy="5" r="2"/><line x1="6.5" y1="9.5" x2="9.5" y2="6.5"/></svg> Connect`;
    }
    document.getElementById('btnStart').disabled  = !connected || running;
    document.getElementById('btnStop').disabled   = !running;
    document.getElementById('btnExport').disabled = !canExport;
  }

  function setStats(blown, avgUs, maxUs, maxFrame) {
    document.getElementById('svBlown').textContent    = blown    != null ? Number(blown).toLocaleString()   : '—';
    document.getElementById('svAvg').textContent      = avgUs    != null ? Number(avgUs).toLocaleString()   : '—';
    document.getElementById('svMaxTime').textContent  = maxUs    != null ? Number(maxUs).toLocaleString()   : '—';
    document.getElementById('svMaxFrame').textContent = maxFrame != null ? maxFrame                         : '—';
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
    refreshPorts();
    log('Tool ready. Select a port and connect.', 'info');
    drawChart();
  });

  return { toggleConnect, startAnalysis, stopAnalysis, exportCsv, refreshPorts, onChunk, onError };
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
    width    = 1200,
    height   = 720,
    min_size = (900, 560),
)

if __name__ == "__main__":
    webview.start(gui='edgechromium', debug=False)
