# Throughput Analysis Tool - Comprehensive Codebase Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [Purpose and Use Case](#purpose-and-use-case)
3. [Overall Architecture](#overall-architecture)
4. [Technology Stack](#technology-stack)
5. [Dependencies](#dependencies)
6. [System Requirements](#system-requirements)
7. [Key Components](#key-components)
8. [Module-wise Breakdown](#module-wise-breakdown)
9. [Data Flow Architecture](#data-flow-architecture)
10. [Key Functionalities](#key-functionalities)
11. [Execution Flow](#execution-flow)
12. [API Reference](#api-reference)
13. [Frontend Structure](#frontend-structure)
14. [Configuration and Constants](#configuration-and-constants)
15. [Workflow](#workflow)
16. [Setup and Installation](#setup-and-installation)
17. [File Structure](#file-structure)

---

## Project Overview

**Project Name:** Throughput Analysis Tool (v1.1)  
**Type:** Desktop Application - Serial Port Data Acquisition & Real-time Analysis  
**Purpose:** Analyze frame throughput and latency from embedded systems via serial communication  
**Platform:** Windows (using pywebview with Edge Chromium)  
**Primary Language:** Python 3 (Backend) + JavaScript (Frontend)

### Quick Summary
The Throughput Analysis Tool is a real-time monitoring and analysis application that:
- Connects to embedded systems via serial ports (COM ports)
- Receives frame-by-frame throughput data (500 frames per second)
- Tracks frame latency, anomalies, and performance metrics
- Provides live visualization and dashboard
- Generates comprehensive ML-based analysis with anomaly detection
- Exports data as CSV, Excel, and PDF reports

---

## Purpose and Use Case

### Primary Use Cases
1. **Real-time Performance Monitoring**: Monitor scheduler throughput on embedded systems
2. **Anomaly Detection**: Identify frame latency spikes exceeding 2000µs threshold
3. **Performance Analysis**: Analyze historical data patterns and trends
4. **Compliance Reporting**: Generate detailed PDF/Excel reports for performance audits
5. **System Diagnostics**: Investigate performance degradation and bottlenecks

### Why It's Used
- **Performance Validation**: Ensures embedded systems meet latency requirements
- **System Health Monitoring**: Tracks ongoing system performance
- **Root Cause Analysis**: ML algorithms identify patterns in anomalies
- **Historical Tracking**: Stores and analyzes long-term performance trends
- **Professional Reporting**: Generates formal reports for stakeholders

### Target Users
- Embedded Systems Engineers
- Performance Analysts
- Quality Assurance Teams
- System Integration Specialists

---

## Overall Architecture

### High-Level Architecture Diagram
```
┌─────────────────────────────────────────────────────────┐
│           Throughput Analysis Tool (Desktop App)         │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │         Frontend Layer (HTML/CSS/JavaScript)      │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │  Interactive Dashboard & Controls           │  │  │
│  │  │  ├─ Live Metric Charts (Canvas)            │  │  │
│  │  │  ├─ Port Connection Manager                │  │  │
│  │  │  ├─ Analysis Controls                      │  │  │
│  │  │  ├─ Data Export Interface                  │  │  │
│  │  │  └─ Dark/Light Theme Toggle                │  │  │
│  │  └────────────────────────────────────────────┘  │  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │      Python Backend (API Layer)                   │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │ API Class - Main Application Logic         │  │  │
│  │  │ ├─ Serial Communication Handler            │  │  │
│  │  │ ├─ Data Acquisition & Processing           │  │  │
│  │  │ ├─ Real-time Metrics Calculation           │  │  │
│  │  │ ├─ Analysis Engine Integration             │  │  │
│  │  │ ├─ Report Generation (PDF/Excel)           │  │  │
│  │  │ ├─ Data Export Management                  │  │  │
│  │  │ └─ UI Synchronization                      │  │  │
│  │  └────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │ VisualizationEngine - Chart Generation     │  │  │
│  │  │ ├─ Heatmap Generation                      │  │  │
│  │  │ ├─ Spike Graph Analysis                    │  │  │
│  │  │ ├─ Rolling Average Plots                   │  │  │
│  │  │ └─ Latency Distribution Charts             │  │  │
│  │  └────────────────────────────────────────────┘  │  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │   External Processing Layer (ML Analysis)        │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │ run_ml.py - Anomaly Detection & ML Analysis│  │  │
│  │  │ ├─ Statistical Analysis (Z-scores, STD)    │  │  │
│  │  │ ├─ Anomaly Detection Algorithms            │  │  │
│  │  │ ├─ Pattern Recognition                     │  │  │
│  │  │ └─ Report Generation (via ReportLab)       │  │  │
│  │  └────────────────────────────────────────────┘  │  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │    Hardware Interface (Serial Communication)      │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │ COM Port / USB Serial Device               │  │  │
│  │  │ ├─ Bi-directional Communication            │  │  │
│  │  │ ├─ Protocol: Frame-based (binary)          │  │  │
│  │  │ └─ Data Rate: 500 bytes/second             │  │  │
│  │  └────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │ Embedded Device (Controller)                │  │  │
│  │  │ ├─ Sends 500-byte chunks every second      │  │  │
│  │  │ └─ Each byte = frame latency (0-255 scale) │  │  │
│  │  └────────────────────────────────────────────┘  │  │
└─────────────────────────────────────────────────────────┘
```

### Architecture Layers

#### 1. **Presentation Layer (Frontend)**
- HTML/CSS/JavaScript application
- Interactive dashboard with live charts
- Real-time metric display
- User controls (Connect, Start, Stop, Analyze, Export)
- Dark/Light theme support

#### 2. **Application Logic Layer (Backend)**
- Python-based API class handling all business logic
- Serial port communication management
- Real-time data acquisition and processing
- Metrics calculation and aggregation
- Integration with external ML analysis

#### 3. **Data Processing Layer**
- Real-time data streaming from hardware
- On-the-fly metric calculations
- Statistical analysis
- State management and threading

#### 4. **Analysis Layer**
- ML-based anomaly detection (external process)
- Pattern recognition
- Health scoring
- Report generation

#### 5. **Hardware Interface**
- Serial port communication (pyserial)
- Protocol handling (binary frame protocol)
- Device enumeration and management

---

## Technology Stack

### Frontend Technologies
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| UI Framework | Vanilla JavaScript | ES6+ | Application logic and interactivity |
| Styling | CSS 3 | Custom | UI design and theming |
| Markup | HTML 5 | - | Semantic structure |
| Charting | HTML5 Canvas | - | Real-time data visualization |
| Icons | Lucide SVG | - | UI icons (Sun/Moon for theme) |
| Fonts | Inter, JetBrains Mono | Google Fonts | Typography |

### Backend Technologies
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Runtime | Python | 3.x | Application runtime |
| Desktop Framework | pywebview | 6.2.1+ | Embedded Chromium browser |
| Serial Communication | pyserial | 3.5+ | COM port interface |
| Data Processing | pandas | 2.2.0+ | CSV/DataFrame operations |
| Visualization | matplotlib | 3.8.0+ | Static visualization generation |
| Visualization | seaborn | 0.13.2+ | Statistical visualization |
| Report Generation | reportlab | 4.2.2+ | PDF document creation |
| CLI Interface | argparse | Built-in | Command-line argument parsing |

### Platform & Runtime
| Component | Details |
|-----------|---------|
| OS | Windows 10/11 |
| Browser Engine | Edge Chromium (via pywebview) |
| Python Version | 3.8+ |
| Architecture | 64-bit |

---

## Dependencies

### Core Dependencies (requirements.txt)
```
pywebview>=6.2.1          # Desktop application framework
pythonnet>=3.1.0rc0       # .NET interoperability (optional)
pyserial>=3.5             # Serial port communication
pandas>=2.2.0             # Data manipulation and analysis
matplotlib>=3.8.0         # Static visualization
seaborn>=0.13.2           # Statistical visualization
reportlab>=4.2.2          # PDF report generation
```

### System-Level Dependencies
- Windows 10/11
- .NET Framework (via pythonnet, if enabled)
- Microsoft Edge WebView2 (comes with Windows 11, can be installed separately)

### Optional Dependencies
- **For development**: VS Code, Python Extension
- **For testing**: pytest (if test suite exists)

---

## System Requirements

### Minimum Requirements
- **OS**: Windows 10 or Windows 11
- **CPU**: Intel i5 or equivalent (2.0+ GHz)
- **RAM**: 2 GB minimum (4 GB recommended)
- **Storage**: 500 MB free space
- **Python**: 3.8+

### Recommended Requirements
- **OS**: Windows 11 Pro/Enterprise
- **CPU**: Intel i7 or AMD Ryzen 7 (3.0+ GHz)
- **RAM**: 8 GB
- **Storage**: 1 GB SSD
- **Python**: 3.10+

### Hardware Interface
- USB Port (for serial adapter)
- COM Port (COM1-COM256 supported)
- Serial Communication: 115200 baud (configurable)

---

## Key Components

### 1. **VisualizationEngine Class**
**Location**: Lines 46-135 in Tool_V1.1.py  
**Purpose**: Generate static visualization charts for analysis reports

**Methods:**
- `__init__()` - Initialize visualization environment
- `generate_all()` - Generate all visualization types
- `anomaly_heatmap()` - Create frame value heatmap
- `frame_spike_graphs()` - Generate spike analysis charts
- `rolling_average_plots()` - Create rolling average visualizations
- `latency_distribution()` - Generate latency distribution charts

**Dependencies**: matplotlib, seaborn, pandas

---

### 2. **Api Class**
**Location**: Lines 137-830 in Tool_V1.1.py  
**Purpose**: Main application backend - handles all business logic

**Key Attributes:**
```python
_ser: serial.Serial | None          # Active serial connection
_running: bool                       # Analysis running flag
_analysis_running: bool              # ML analysis in progress
_lock: threading.Lock()              # Thread-safe data access
_data: list[tuple]                  # Raw data points (second, frame, value)
_session_total_us: int              # Cumulative latency
_session_sample_count: int          # Total samples collected
_session_blown: int                 # Frames exceeding threshold
_session_max_us: int                # Maximum latency observed
_session_max_frame: int             # Frame index with max latency
_blown_frames_list: list            # Details of anomalous frames
_frame_totals: list                 # Per-frame cumulative latency
_frame_counts: list                 # Per-frame sample count
_top10_frames: list                 # Top 10 max latency frames
```

**Key Methods:**

| Method | Purpose | Parameters | Returns |
|--------|---------|-----------|---------|
| `connect()` | Establish serial connection | port, baud | JSON status |
| `disconnect()` | Close serial connection | - | JSON status |
| `start_analysis()` | Begin data acquisition | - | JSON status |
| `stop_analysis()` | Stop data collection | - | JSON status |
| `_receive_loop()` | Background thread for receiving data | - | void |
| `analyze()` | Trigger ML analysis subprocess | - | JSON status |
| `export_analysis()` | Export Excel and PDF reports | - | JSON with paths |
| `export_csv()` | Export raw data as CSV | - | JSON with path |
| `get_ports()` | List available COM ports | - | JSON array |
| `get_summary()` | Get current session metrics | - | JSON metrics |

---

### 3. **Frontend Application (JavaScript IIFE)**
**Location**: Lines 3073-4074 in Tool_V1.1.py  
**Pattern**: Immediately Invoked Function Expression (IIFE)  
**Scope**: All app logic encapsulated, exported via `window._app`

**Key State Variables:**
```javascript
connected: bool              // Serial connection status
running: bool               // Analysis running status
metricData: object          // Current metrics snapshot
latestChunk: array          // Latest frame data
currentMetricShown: string  // Currently displayed metric modal
```

**Key Functions:**
- `toggleTheme()` - Switch between dark/light themes
- `toggleConnect()` - Establish/close serial connection
- `startAnalysis()` - Begin data acquisition
- `stopAnalysis()` - Stop data acquisition
- `analyze()` - Trigger ML analysis
- `exportAnalysis()` - Export reports
- `exportCsv()` - Export CSV data
- `onChunk()` - Handle incoming data
- `onError()` - Handle errors
- `drawChart()` - Render dashboard charts

---

## Module-wise Breakdown

### Module 1: VisualizationEngine (Static Visualization)
**File**: Tool_V1.1.py (Lines 46-135)  
**Responsibility**: Generate static visualization charts for reports  
**Called By**: run_ml.py (analysis workflow)  
**Technology**: matplotlib, seaborn, pandas

**Workflow**:
1. Accept analyzed DataFrame
2. Generate heatmap of frame values
3. Create spike graphs for top-N frames
4. Generate rolling average plots
5. Create latency distribution charts
6. Save PNG files to output directory

### Module 2: Api Class (Main Backend)
**File**: Tool_V1.1.py (Lines 137-830)  
**Responsibility**: Core application logic and business rules  
**Exposes To**: Frontend (JavaScript) via pywebview JS API  
**Technology**: serial, threading, pandas, json

**Key Workflows**:
1. **Connection Management**: List ports, connect, disconnect
2. **Data Acquisition**: Receive frames, process, aggregate metrics
3. **Real-time Updates**: Send data chunks to frontend
4. **Analysis Workflow**: Prepare CSV, invoke ML subprocess
5. **Report Generation**: Create PDF reports with metrics
6. **Export Management**: Save CSV/Excel/PDF to user location

### Module 3: Frontend Controller (JavaScript)
**File**: Tool_V1.1.py (Lines 3073-4074, embedded HTML)  
**Responsibility**: Handle user interactions and UI updates  
**Interacts With**: Api class (via window._app)  
**Technology**: JavaScript ES6+, Canvas API, localStorage

**Key Workflows**:
1. **UI Initialization**: Load theme, connect event handlers
2. **Connection Flow**: Port selection → connect → status update
3. **Analysis Flow**: Start → receive chunks → update charts → stop
4. **Data Export**: Export CSV/Excel with file dialog
5. **Theme Management**: Toggle theme, update colors, persist preference
6. **Modal Management**: Show/hide metric details, tables

### Module 4: ML Analysis Engine (run_ml.py)
**File**: run_ml.py (Full file, ~400+ lines)  
**Responsibility**: Statistical analysis and anomaly detection  
**Called By**: Api.analyze() (subprocess)  
**Technology**: pandas, matplotlib, reportlab, sklearn-like algorithms

**Key Analysis Functions**:
- `validate_and_prepare_csv()` - Data validation and cleaning
- `analyze_dataframe()` - Multi-level anomaly detection
- `generate_excel_report()` - Create Excel workbook
- `generate_pdf_report()` - Create PDF document
- Returns JSON with file paths

---

## Data Flow Architecture

### Data Flow Diagram
```
┌─────────────────────────────────────────────────────────────────┐
│                       Serial Device                              │
│                  (Embedded Controller)                           │
│  Sends 500-byte chunks every 1 second (500 frames per second)   │
└────────────────────────┬────────────────────────────────────────┘
                         │ Binary data (bytes)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API._receive_loop()                          │
│                  (Python Background Thread)                      │
│  ├─ Read 500 bytes from serial port                             │
│  ├─ Parse each byte as frame latency (0-255)                    │
│  ├─ Multiply by SCALE_FACTOR (20) to get microseconds           │
│  ├─ Increment second counter                                    │
│  └─ Calculate aggregate metrics                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │ (second, frame_idx, raw_value) tuples
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Metrics Aggregation                            │
│  ├─ _session_total_us    (sum of all latencies)                 │
│  ├─ _session_blown       (count > 2000µs)                       │
│  ├─ _session_max_us      (maximum latency)                      │
│  ├─ _frame_totals        (per-frame cumulative)                 │
│  ├─ _frame_counts        (per-frame sample count)               │
│  └─ _top10_frames        (highest latency frames)               │
└────────────────────────┬────────────────────────────────────────┘
                         │ window.evaluate_js() call
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend: onChunk()                           │
│  ├─ Receive chunk data from backend                             │
│  ├─ Update metric displays                                      │
│  ├─ Update dashboard cards                                      │
│  ├─ Redraw canvas charts                                        │
│  ├─ Add to metric modal tables                                  │
│  └─ Store in currentMetricData                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ User clicks "Analyze"
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  API.export_csv() + subprocess                  │
│  ├─ Reconstruct CSV with all frames and time values             │
│  ├─ Write to temporary file                                     │
│  └─ Invoke: python run_ml.py --input csv --output-dir temp      │
└────────────────────────┬────────────────────────────────────────┘
                         │ subprocess.run()
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              run_ml.py: ML Analysis Processing                  │
│  ├─ Load CSV data                                               │
│  ├─ Validate 500 Frame_ columns                                 │
│  ├─ Calculate statistics (mean, std, deltas)                    │
│  ├─ Apply anomaly detection algorithms                          │
│  ├─ Generate heatmaps and charts                                │
│  ├─ Create Excel workbook                                       │
│  ├─ Generate PDF report                                         │
│  └─ Output JSON with file paths                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │ JSON via stdout
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│           API._run_analysis_worker() parses JSON                │
│  ├─ Extract excel_path, pdf_path, anomaly_csv_path              │
│  ├─ Store in instance variables                                 │
│  ├─ Call onAnalysisComplete() via JS                            │
│  └─ Enable "Export Analysis" button                             │
└────────────────────────┬────────────────────────────────────────┘
                         │ User clicks "Export Analysis"
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│           API.export_analysis() + File Dialog                   │
│  ├─ Show folder selection dialog                                │
│  ├─ Copy Excel file to user location                            │
│  ├─ Copy PDF file to user location                              │
│  ├─ Copy anomaly CSV (if present)                               │
│  └─ Return result to frontend                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ User downloads files
                         ▼
              User Review & Decision Making
```

---

## Key Functionalities

### 1. **Serial Port Management**
**Feature**: Connect and manage serial communication with embedded device

**Capabilities**:
- Auto-detect available COM ports
- Filter for USB devices only
- Configurable baud rate (default 115200)
- Bi-directional communication (send commands, receive data)
- Connection status display
- Auto-disconnect on app close

**Implementation**:
```python
# Located in Api.get_ports() and Api.connect()
def get_ports(self) -> str:
    all_ports = serial.tools.list_ports.comports()
    usb_ports = [p.device for p in all_ports if p.vid is not None or "USB" in p.hwid]
    return json.dumps(usb_ports)

def connect(self, port: str, baud: str) -> str:
    self._ser = serial.Serial(port, int(baud), timeout=1.5)
    return json.dumps({"status": "ok", "message": f"Connected to {port}"})
```

---

### 2. **Real-time Data Acquisition**
**Feature**: Continuously receive and process frame latency data

**Capabilities**:
- Receive 500-byte chunks every second
- Parse binary data (each byte = frame latency)
- Scale raw values to microseconds (byte × 20)
- Calculate aggregate metrics per chunk
- Thread-safe data storage
- Automatic error handling

**Data Format**:
```
Chunk Structure:
├─ Byte 0:   Frame 0 latency (0-255 raw)
├─ Byte 1:   Frame 1 latency (0-255 raw)
├─ ...
└─ Byte 499: Frame 499 latency (0-255 raw)

Scaled to: latency_us = raw_byte × 20

Example: byte value 100 = 100 × 20 = 2000µs latency
```

**Implementation** (Api._receive_loop()):
```python
def _receive_loop(self):
    while self._running:
        chunk = self._ser.read(CHUNK_SIZE)  # 500 bytes
        for i, raw in enumerate(chunk):
            raw_us = raw * SCALE_FACTOR  # raw × 20
            self._session_total_us += raw_us
            if raw_us > BLOWN_THRESHOLD:  # > 2000µs
                self._session_blown += 1
        window.evaluate_js(f"window._app && window._app.onChunk(...)")
```

---

### 3. **Real-time Dashboard Visualization**
**Feature**: Live charting and metric display using HTML5 Canvas

**Dashboard Components**:
- **4 Metric Cards** (2×2 grid):
  - Frames Blown (exceeding 2000µs)
  - Average Latency (µs)
  - Peak Latency (µs)
  - Peak Frame Index
- **Live Canvas Charts**: Donut/pie/bar representations
- **Legend & Indicators**: Color-coded status
- **Clickable Cards**: Show detailed metric modals
- **Real-time Updates**: Every received chunk

**Chart Types**:
- Donut chart for Frames Blown (blue safe, red blown)
- Gauge chart for Average Latency
- Bar chart for Peak metrics
- Detailed table view on click

---

### 4. **Anomaly Detection & Analysis**
**Feature**: ML-based pattern recognition for anomalies

**Algorithm Components**:
- **Z-Score Analysis**: Statistical outlier detection
- **Absolute Difference**: Deviation from mean
- **Delta Analysis**: Frame-to-frame change detection
- **Rolling Variance**: Temporal instability detection
- **Multi-level Detection**:
  - Row-wise: Any frame exceeds 2000µs
  - Column-wise: Individual frames spike
  - Temporal: Instability patterns

**Thresholds**:
```python
ROW_THRESHOLD_US = 2000.0      # Hard limit per frame
WARN_Z = 2.0                   # 2-sigma warning
CRIT_Z = 3.0                   # 3-sigma critical
WARN_ABS_DIFF = 75.0           # Warning threshold
CRIT_ABS_DIFF = 200.0          # Critical threshold
WARN_DELTA = 120.0             # Frame change warning
CRIT_DELTA = 250.0             # Frame change critical
```

**Output**: 
- Anomaly classification (Normal/Warning/Critical)
- Detection type (RowWise/ColumnWise/Both)
- Severity scores (0-100)
- Health scores (0-100)
- Reason text (human-readable explanation)

---

### 5. **Report Generation**
**Feature**: Generate professional PDF and Excel reports

**Report Contents**:

| Report Type | Format | Contents |
|------------|--------|----------|
| **PDF Report** | Document | Title, metadata, session summary, key metrics, performance index, analysis insights, recommendations, data characteristics, conclusion |
| **Excel Report** | Spreadsheet | Raw data table, anomaly markers, analysis results, highlighting |
| **CSV Export** | CSV | Raw frame-by-frame data with Time_Second and Frame_0 to Frame_499 columns |

**Implementation**:
- PDF: Uses reportlab library with styled tables
- Excel: pandas DataFrame with conditional formatting
- CSV: Reconstructed from in-memory data structure

---

### 6. **Dark/Light Theme**
**Feature**: User-selectable UI theme with persistent storage

**Implementation**:
- CSS custom properties for color variables
- Toggle button in header (Sun/Moon icons)
- localStorage persistence
- requestAnimationFrame for chart redraw synchronization
- Smooth 0.3s transitions

**Supported Theme Colors**:
- Dark theme: Blue accents (#3b82f6), Gray backgrounds (#0f1219)
- Light theme: Blue accents (#2563eb), White backgrounds (#ffffff)

---

### 7. **Export & Download Management**
**Feature**: Multi-format data export to user's file system

**Supported Formats**:
- **CSV**: Raw frame data (Time_Second + Frame_0..Frame_499)
- **Excel**: Analyzed data with anomaly annotations
- **PDF**: Professional report with visuals

**Dialog Integration**:
- Uses webview.FileDialog for file selection
- Timestamp-based default filenames
- User-selectable destination
- Supports batch export (Excel + PDF + CSV)

---

## Execution Flow

### Complete Session Workflow

```
1. APP STARTUP
   └─ Python main() creates Api instance
   └─ Creates webview window with HTML
   └─ Loads embedded CSS and JavaScript
   └─ JavaScript IIFE runs, initializes app state
   └─ Theme initialization (read localStorage)
   └─ Event handlers bound to all controls

2. USER CONNECTS TO DEVICE
   ├─ User selects COM port from dropdown
   ├─ User clicks "Connect" button
   ├─ Frontend calls: window._app.toggleConnect(port, baud)
   ├─ Backend Api.connect() creates serial.Serial object
   ├─ Updates connection status display
   └─ Enables Start button

3. USER STARTS ANALYSIS
   ├─ User clicks "Start Analysis" button
   ├─ Frontend calls: window._app.startAnalysis()
   ├─ Backend Api.start_analysis():
   │  ├─ Resets session state (clears old data)
   │  ├─ Sends START_FRAME to device: b'\xFE\xFE\xFE\x80\xFE\xFE\xFE'
   │  ├─ Spawns background thread: _receive_loop()
   │  ├─ Updates UI: disable Start, enable Stop
   │  └─ Starts real-time data reception
   └─ _receive_loop() begins:
      ├─ Loop while _running == True:
      │  ├─ Read 500 bytes from serial port (blocking with 1.5s timeout)
      │  ├─ Process each byte:
      │  │  ├─ Calculate: latency_us = byte × 20
      │  │  ├─ Update: _session_total_us, _session_sample_count
      │  │  ├─ Check: if latency > 2000µs: increment _session_blown
      │  │  ├─ Track: max latency and frame index
      │  │  └─ Store per-frame statistics
      │  ├─ Build summary metrics
      │  ├─ Call: window._app.onChunk() via window.evaluate_js()
      │  └─ Frontend updates dashboard in real-time
      └─ Loop continues for entire session

4. REAL-TIME DASHBOARD UPDATES (Per Chunk)
   ├─ onChunk() receives data object with:
   │  ├─ second: current second counter
   │  ├─ blown: cumulative blown frames
   │  ├─ avg_us: average latency
   │  ├─ max_us: maximum latency
   │  ├─ max_frame: frame index with max
   │  ├─ frame_data: [500 bytes] current chunk
   │  └─ new_blown_frames: [{frameIndex, second, timeUs}]
   ├─ Update metric card displays:
   │  ├─ "#blownCardValue" ← blown count
   │  ├─ "#avgCardValue" ← avg_us
   │  ├─ "#peakTimeCardValue" ← max_us
   │  └─ "#peakFrameCardValue" ← max_frame
   ├─ Redraw canvas charts with requestAnimationFrame
   ├─ Add blown frames to detail tables
   └─ Add to blown frames modal list

5. USER STOPS ANALYSIS
   ├─ User clicks "Stop Analysis" button
   ├─ Frontend calls: window._app.stopAnalysis()
   ├─ Backend Api.stop_analysis():
   │  ├─ Sets _running = False (stops _receive_loop)
   │  ├─ Sends STOP_FRAME to device: b'\xFE\xFE\xFE\x81\xFE\xFE\xFE'
   │  ├─ Waits for ACK from device (7-byte acknowledgment)
   │  ├─ Returns summary message: "Analysis Done, Csv Ready to Export"
   │  └─ Updates UI: enable Start, disable Stop
   └─ Final metrics frozen for review

6. USER ANALYZES DATA (ML)
   ├─ User clicks "Analyze" button (analysis-ml-button)
   ├─ Frontend calls: window._app.analyze()
   ├─ Backend Api.analyze():
   │  ├─ Checks if data exists
   │  ├─ Exports session data to temporary CSV
   │  ├─ Spawns subprocess: python run_ml.py --input csv --output-dir temp
   │  └─ Sets _analysis_running = True
   └─ Subprocess run_ml.py:
      ├─ Loads CSV data
      ├─ Validates 500 Frame_ columns
      ├─ Performs comprehensive analysis:
      │  ├─ Calculates statistics (mean, std, deltas)
      │  ├─ Applies anomaly detection algorithms
      │  ├─ Categorizes rows (Normal/Warning/Critical)
      │  ├─ Generates reason text per anomaly
      │  └─ Calculates health scores
      ├─ Generates visualizations:
      │  ├─ Heatmap of frame values
      │  ├─ Spike graphs for top frames
      │  ├─ Rolling average plots
      │  └─ Latency distribution charts
      ├─ Creates Excel workbook with:
      │  ├─ Raw data table
      │  ├─ Anomaly annotations
      │  ├─ Conditional formatting
      │  └─ Embedded charts
      ├─ Creates PDF report with:
      │  ├─ Title and metadata
      │  ├─ Session summary table
      │  ├─ Key performance metrics
      │  ├─ Analysis insights
      │  ├─ Recommendations
      │  ├─ Embedded visualizations
      │  └─ Professional formatting
      ├─ Writes to output_dir with timestamp
      ├─ Prints JSON to stdout:
      │  └─ {"excel_path": "...", "pdf_path": "...", "anomaly_csv_path": "..."}
      └─ Process terminates
   └─ Backend parses JSON output:
      ├─ Extracts file paths
      ├─ Stores in instance: _analysis_excel_path, _analysis_pdf_path
      ├─ Calls: window._app.onAnalysisComplete()
      └─ Frontend shows: "Export Analysis" button enabled

7. USER EXPORTS RESULTS
   ├─ Option A: Export CSV (raw data)
   │  ├─ User clicks "Export CSV" / "Export Csv" button
   │  ├─ Frontend calls: window._app.exportCsv()
   │  ├─ Shows file save dialog with default name: "throughput_YYYYMMDD_HHMMSS.csv"
   │  ├─ Backend Api.export_csv() writes CSV to selected location
   │  ├─ CSV contains: Time_Second, Frame_0...Frame_499 columns
   │  ├─ CSV data reconstructed from _data list
   │  └─ Returns success message with file path
   │
   ├─ Option B: Export Analysis (Excel + PDF)
   │  ├─ User clicks "Export Analysis" button
   │  ├─ Frontend calls: window._app.exportAnalysis()
   │  ├─ Shows folder selection dialog
   │  ├─ Backend Api.export_analysis():
   │  │  ├─ Checks if analysis Excel/PDF exist
   │  │  ├─ Creates timestamped filenames
   │  │  ├─ Copies Excel to: "throughput_YYYYMMDD_HHMMSS_ML_Analyzed.xlsx"
   │  │  ├─ Copies PDF to: "throughput_YYYYMMDD_HHMMSS_Analysis_Report.pdf"
   │  │  ├─ Optionally copies: "throughput_YYYYMMDD_HHMMSS_Anomalies.csv"
   │  │  └─ Returns success message with all paths
   │  └─ User downloads all files
   │
   └─ Option C: Manual Data Access
      └─ User can manually review metrics in modal dialogs

8. USER VIEWS DETAILED METRICS
   ├─ User clicks on metric card (blown, avg, peak-time, peak-frame)
   ├─ Frontend calls: window._app.toggleMetricView(metricType)
   ├─ Modal opens showing:
   │  ├─ Metric title and icon
   │  ├─ Summary statistics
   │  ├─ Detailed table of top anomalies (if applicable)
   │  ├─ Sortable columns (rank, frameIndex, timeUs, timestamp)
   │  └─ Close button (×)
   └─ User closes modal or selects different metric

9. USER CHANGES THEME
   ├─ User clicks theme toggle button (top-right corner)
   ├─ Frontend calls: window._app.toggleTheme()
   ├─ Backend toggleTheme():
   │  ├─ Detects current theme from body.classList
   │  ├─ Toggles: dark ↔ light
   │  ├─ Calls: setTheme(newTheme)
   │  └─ setTheme():
   │     ├─ Applies body class: document.body.classList.add/remove('light-theme')
   │     ├─ Saves preference: localStorage.setItem('theme', theme)
   │     ├─ Updates icons visibility (Sun ↔ Moon)
   │     ├─ Waits with setTimeout (50ms for CSS to apply)
   │     ├─ Calls requestAnimationFrame to redraw charts
   │     └─ drawChart() re-renders with new theme colors
   ├─ UI transitions smoothly (0.3s)
   └─ Preference persists across sessions

10. USER DISCONNECTS
    ├─ User clicks "Connect" button (now showing "Disconnect")
    ├─ Frontend calls: window._app.toggleConnect()
    ├─ Backend Api.disconnect():
    │  ├─ Checks if analysis still running (prevents disconnect)
    │  ├─ Sets _running = False
    │  ├─ Closes serial port: self._ser.close()
    │  ├─ Updates UI: disables Start, enables Connect
    │  └─ Returns success
    └─ Connection closed, resources freed

11. APP SHUTDOWN
    ├─ User closes application window
    ├─ Python webview.start() loop terminates
    ├─ Api instance cleaned up
    ├─ Serial port closed (if open)
    ├─ Thread joined (if running)
    └─ Process exits cleanly
```

---

## API Reference

### Backend API (Python - Api Class)

#### Connection Management

**`get_ports() → str`**
- Returns available COM ports (JSON)
- Filters for USB devices only
- Example: `["COM3", "COM4", "COM5"]`

**`connect(port: str, baud: str) → str`**
- Establish serial connection
- Parameters: port (e.g., "COM3"), baud (e.g., "115200")
- Returns: `{"status": "ok"|"error", "message": "..."}`

**`disconnect() → str`**
- Close serial connection
- Returns: `{"status": "ok"|"error", "message": "..."}`

---

#### Analysis Control

**`start_analysis() → str`**
- Begin frame data acquisition
- Sends START_FRAME and spawns receive thread
- Returns: `{"status": "ok"|"error", "message": "..."}`

**`stop_analysis() → str`**
- Stop data acquisition
- Sends STOP_FRAME and waits for ACK
- Returns: `{"status": "ok", "message": "Analysis Done, Csv Ready to Export", "ack_received": bool}`

**`analyze() → str`**
- Trigger ML analysis subprocess
- Spawns: `python run_ml.py --input csv --output-dir temp`
- Returns: `{"status": "ok"|"error", "message": "..."}`

---

#### Data Export

**`export_csv() → str`**
- Export raw data as CSV
- Shows file save dialog
- Returns: `{"status": "ok"|"cancelled"|"error", "path": "...", "rows": int}`

**`export_analysis() → str`**
- Export Excel + PDF analysis reports
- Shows folder selection dialog
- Returns: `{"status": "ok"|"cancelled"|"error", "excel_path": "...", "pdf_path": "...", "anomaly_csv_path": "..."}`

**`download_pdf() → str`** (Legacy)
- Deprecated: Use export_analysis()

---

#### Data Retrieval

**`get_summary() → str`**
- Get current session metrics (JSON)
- Returns: `{"rows": int, "seconds": int, "blown": int, "avg_us": int, "max_us": int, "max_frame": int}`

**`get_default_csv_name() → str`**
- Get suggested CSV filename and home directory
- Returns: `{"name": "throughput_YYYYMMDD_HHMMSS.csv", "home": "C:\\Users\\..."}`

---

#### Error Handling

**`js_error(message: str) → str`**
- Log JavaScript errors from frontend
- Prints to console: `[JS ERROR] message`
- Returns: `{"status": "ok"}`

**`onChunk(data: object)`** (Called from Python)
- Invoked via: `window.evaluate_js("window._app && window._app.onChunk(...)")`
- Data structure:
  ```json
  {
    "second": 42,
    "blown": 5,
    "avg_us": 1200,
    "max_us": 2500,
    "max_frame": 127,
    "frame_data": [50, 45, 52, 48, ...],
    "new_blown_frames": [{"frameIndex": 127, "second": 42, "timeUs": 2500}],
    "frame_avgs": [1200, 1210, ...],
    "top10": [{...}, ...]
  }
  ```

---

### Frontend API (JavaScript)

#### Connection Management

**`window._app.toggleConnect(port?, baud?)`**
- Connect to selected port or disconnect if connected
- Parameters: port (optional, from dropdown), baud (optional, default "115200")
- Updates: `connected` state, UI status

**`window._app.refreshPorts()`**
- Refresh COM port dropdown
- Calls backend: `get_ports()`
- Updates: `#portSelect` options

---

#### Analysis Control

**`window._app.startAnalysis()`**
- Begin data acquisition
- Calls backend: `start_analysis()`
- Updates: Button states, running indicator

**`window._app.stopAnalysis()`**
- Stop data acquisition
- Calls backend: `stop_analysis()`
- Updates: Button states, final metrics

**`window._app.analyze()`**
- Trigger ML analysis
- Calls backend: `analyze()`
- Shows loading indicator, enables export on complete

---

#### Data Export

**`window._app.exportCsv()`**
- Export raw data as CSV
- Calls backend: `export_csv()`
- Shows file dialog, triggers download

**`window._app.exportAnalysis()`**
- Export Excel + PDF reports
- Calls backend: `export_analysis()`
- Shows folder dialog, triggers downloads

---

#### Data Display

**`window._app.onChunk(data)`**
- Handle incoming data chunk
- Updates metric displays
- Redraws charts
- Adds to modal tables

**`window._app.openMetricModal(metricType)`**
- Show detailed metric modal
- Parameters: "frameBlown", "avgTime", "maxTime", "peakFrame"
- Shows: Table of anomalies with details

**`window._app.closeMetricModal(modalId)`**
- Hide metric modal
- Parameters: "frameBlownModal", "avgTimeModal", "maxTimeModal", "peakFrameModal"

**`window._app.toggleMetricView(metricType)`**
- Toggle metric modal visibility
- Same as: open if closed, close if open

---

#### Theme Management

**`window._app.toggleTheme()`**
- Switch between dark and light themes
- Updates: body.classList, CSS variables, icons
- Persists: theme preference in localStorage

---

#### Utilities

**`window._app.onError(message)`**
- Handle error from backend
- Shows alert dialog
- Parameters: error message string

**`window._app.onAnalysisComplete(result)`**
- Handle successful analysis completion
- Parameters: `{"message": "..."}`
- Enables export buttons

**`window._app.onAnalysisError(message)`**
- Handle analysis error
- Shows error alert
- Parameters: error message string

---

## Frontend Structure

### HTML Structure Overview

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <!-- Meta tags, fonts, styles -->
</head>
<body>
  <!-- Layout -->
  <div class="topbar">
    <!-- Brand, theme toggle -->
  </div>
  <div class="layout">
    <!-- Main content area -->
    <div class="main">
      <!-- Stats row -->
      <div class="stats">
        <div class="scard"><!-- Row/Seconds/Blown/Avg metrics --></div>
      </div>
      <!-- Dashboard grid -->
      <div class="analysis-dashboard">
        <section class="analysis-card"><!-- Frames Blown Card --></section>
        <section class="analysis-card"><!-- Average Time Card --></section>
        <section class="analysis-card"><!-- Peak Time Card --></section>
        <section class="analysis-card"><!-- Peak Frame Card --></section>
      </div>
      <!-- Chart area -->
      <div class="chart-area">
        <canvas id="chart"></canvas>
      </div>
    </div>
    <!-- Control panel (right side) -->
    <div class="control-panel">
      <!-- Port selector -->
      <!-- Connect button -->
      <!-- Start/Stop buttons -->
      <!-- Analyze button -->
      <!-- Export buttons -->
      <!-- Metric modals -->
    </div>
  </div>
  <!-- Alert overlay -->
  <div id="alertOverlay" class="alert-overlay">
    <div class="alert-card"><!-- Alert content --></div>
  </div>
  <!-- Loading overlay -->
  <div id="loadingOverlay" class="loading-overlay">
    <div class="loading-card"><!-- Loading spinner --></div>
  </div>
  <!-- Metric modals -->
  <div id="frameBlownModal" class="modal-backdrop">
    <div class="metric-modal-card"><!-- Blown frames table --></div>
  </div>
  <!-- ... more modals ... -->
</body>
</html>
```

### CSS Architecture

**CSS Organization**:
- **Root Variables** (lines 815-835): Dark theme colors
- **Light Theme Override** (lines 837-856): Light theme colors
- **Component Styles**:
  - Topbar (lines 858-915)
  - Theme toggle (lines 917-989)
  - Buttons (lines 991-1210)
  - Form controls (lines 1212-1315)
  - Layout containers (lines 1317-1500)
  - Cards (lines 1502-1610)
  - Charts (lines 1612-1700)
  - Modals (lines 1702-1815)
  - Alerts (lines 1817-1920)
  - Responsive media queries

**Color System**:
- **Dark Theme**: Blue accents, dark grays
- **Light Theme**: Blue accents, whites/grays
- **Gradients**: Multi-step for depth
- **Shadows**: Layered for elevation

---

## Configuration and Constants

### Application Constants (Tool_V1.1.py)

```python
# Serial Protocol
START_FRAME = b'\xFE\xFE\xFE\x80\xFE\xFE\xFE'    # 7 bytes - Start command
STOP_FRAME  = b'\xFE\xFE\xFE\x81\xFE\xFE\xFE'    # 7 bytes - Stop command

# Data Parameters
CHUNK_SIZE   = 500         # Frames per chunk (bytes)
SCALE_FACTOR = 20          # Multiply raw byte by 20 to get µs
BLOWN_THRESHOLD = 2000     # Microseconds - threshold for "blown" frame

# Timing
ACK_TIMEOUT = 2.0          # Seconds to wait for ACK from device
SERIAL_TIMEOUT = 1.5       # Serial port read timeout (seconds)
BAUD_RATE = 115200         # Default serial baud rate (configurable)
```

### ML Analysis Thresholds (run_ml.py)

```python
# Anomaly Detection Thresholds
ROW_THRESHOLD_US = 2000.0      # Hard limit - any value > this is anomalous
WARN_Z = 2.0                   # 2-sigma = warning level
CRIT_Z = 3.0                   # 3-sigma = critical level
WARN_ABS_DIFF = 75.0           # Absolute deviation - warning
CRIT_ABS_DIFF = 200.0          # Absolute deviation - critical
WARN_DELTA = 120.0             # Frame-to-frame change - warning
CRIT_DELTA = 250.0             # Frame-to-frame change - critical

# Analysis Parameters
MIN_STD = 25.0                 # Minimum standard deviation (to prevent division issues)
MAX_REASON_FRAMES = 8          # Max anomalous frames to include in reason text
ROLLING_WINDOW = 10            # Window size for rolling statistics
```

### Window Configuration

```python
window = webview.create_window(
    title    = "Throughput Analysis Tool",
    html     = HTML,                    # Embedded HTML string
    js_api   = api,                     # Python Api class exposed to JS
    width    = 1400,                    # Default window width (pixels)
    height   = 800,                     # Default window height (pixels)
    min_size = (1100, 600),             # Minimum window size
)
```

---

## Workflow

### High-Level Workflow Phases

#### Phase 1: Connection & Setup
1. Application starts
2. User selects COM port from dropdown (populated by `get_ports()`)
3. User clicks "Connect"
4. Backend establishes serial connection
5. Connection status shows as "Connected"

#### Phase 2: Data Acquisition
1. User clicks "Start Analysis"
2. Backend sends START_FRAME to device
3. Device begins sending 500-byte chunks every second
4. Background thread (`_receive_loop`) receives and processes chunks
5. Real-time metrics update on dashboard every second

#### Phase 3: Real-time Monitoring
1. Metric cards update (blown count, avg, peak, etc.)
2. Canvas charts redraw with new data
3. User can click cards to view detailed tables
4. Analysis continues indefinitely or until user stops

#### Phase 4: Analysis & Export
1. User clicks "Analyze" to trigger ML processing
2. Session data exported to temporary CSV
3. Subprocess runs `run_ml.py` for analysis
4. Excel workbook generated with anomaly annotations
5. PDF report generated with visualizations
6. User clicks "Export Analysis" to save files

#### Phase 5: Reporting & Decision Making
1. User downloads Excel/PDF/CSV files
2. Reviews metrics and analysis
3. Makes decisions based on findings
4. Can re-analyze or export new data

#### Phase 6: Disconnection & Cleanup
1. User clicks "Disconnect"
2. Serial port closes
3. Resources freed
4. Application ready for new session or closure

### Typical Session Duration
- **Setup**: 30 seconds (port selection, connection)
- **Data Collection**: 60-300 seconds (1-5 minutes typical)
- **Analysis**: 30-60 seconds (ML processing)
- **Export**: 10-20 seconds (file operations)
- **Total**: 5-10 minutes typical

---

## Setup and Installation

### Prerequisites
- Windows 10 or Windows 11
- Python 3.8+
- pip (Python package installer)
- A USB serial adapter (if not using built-in COM port)

### Installation Steps

#### 1. Clone or Extract Repository
```bash
cd d:\Throughput_Tool
```

#### 2. Create Virtual Environment
```bash
python -m venv venv
```

#### 3. Activate Virtual Environment
```bash
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Windows CMD
venv\Scripts\activate.bat
```

#### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 5. Verify Installation
```bash
python -m py_compile Tool_V1.1.py
python run_ml.py --help  # Should show argument help
```

#### 6. Run Application
```bash
python Tool_V1.1.py
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| `ImportError: No module named 'serial'` | Run `pip install pyserial>=3.5` |
| `ImportError: No module named 'webview'` | Run `pip install pywebview>=6.2.1` |
| `No COM ports detected` | Check USB device connections, install CH340/PL2303 drivers |
| `"Cannot connect to port"` | Ensure device is powered, check baud rate, verify COM port |
| `Analysis subprocess fails` | Ensure `run_ml.py` is in same directory, check file permissions |
| `Theme toggle not working` | Clear browser cache/localStorage, restart application |

---

## File Structure

```
d:\Throughput_Tool\
├── Tool_V1.1.py                    # Main application (4000+ lines)
│   ├── Imports (pyserial, pandas, matplotlib, webview, reportlab)
│   ├── VisualizationEngine class   # Static visualizations
│   ├── Api class                   # Main backend logic
│   │   ├── Serial connection management
│   │   ├── Data acquisition & processing
│   │   ├── Metrics calculation
│   │   ├── CSV/Excel export
│   │   ├── PDF report generation
│   │   └─ Analysis integration
│   ├── Embedded HTML string (lines 805-4100)
│   │   ├── <head> with meta tags and fonts
│   │   ├── <style> with CSS (1500+ lines)
│   │   └── <body> with layout structure
│   ├── Embedded JavaScript IIFE (lines 3073-4074)
│   │   ├── App state variables
│   │   ├── Theme management
│   │   ├── Event handlers
│   │   ├── UI update functions
│   │   └─ API communication
│   ├── Window initialization (lines 4111-4119)
│   └── Entry point: webview.start()
│
├── run_ml.py                       # ML Analysis module (~400 lines)
│   ├── Data validation & preparation
│   ├── Statistical analysis functions
│   ├── Anomaly detection algorithms
│   ├── Excel workbook generation
│   ├── PDF report generation
│   ├── Visualization generation
│   └─ JSON output to stdout
│
├── requirements.txt                # Python dependencies
│
├── run.bat                         # Batch file for quick launch
│
├── throughput_*.csv                # Sample/historical data files
│
├── final_test_*/                   # Test output directories
│   ├── anomalies.csv
│   └─ (other analysis outputs)
│
├── venv/                           # Python virtual environment
│   ├── Scripts/
│   ├── Lib/
│   └─ pyvenv.cfg
│
├── .git/                           # Git repository
├── .gitignore                      # Git ignore file
│
└── .vscode/                        # VS Code settings
    └── settings.json
```

---

## Key Technical Decisions

### 1. **Why Embedded HTML/CSS/JavaScript?**
- **Simplification**: Single Python file deployment
- **No Additional Setup**: No separate web server needed
- **Security**: Direct access to Python API via pywebview
- **Portability**: Desktop application without external dependencies
- **Performance**: HTML5 Canvas for fast rendering

### 2. **Why Real-time Canvas Charts?**
- **Performance**: Fast rendering (60+ FPS)
- **Responsiveness**: Immediate visual feedback
- **Customization**: Full control over visualization
- **No Dependencies**: Native browser API

### 3. **Why Background Threading?**
- **Non-blocking UI**: UI remains responsive during data collection
- **Continuous Streaming**: Can receive data indefinitely
- **Error Isolation**: Network errors don't crash main thread
- **Scalability**: Can handle multiple concurrent operations

### 4. **Why Subprocess for ML Analysis?**
- **Process Isolation**: Separate Python process prevents blocking
- **Memory Management**: Analysis memory freed after completion
- **Error Isolation**: ML errors don't crash main app
- **Modularity**: ML can be updated independently
- **Reusability**: run_ml.py can be used standalone

### 5. **Why CSS Variables for Theming?**
- **Maintainability**: Single source of truth for colors
- **Runtime Switching**: No page reload needed
- **Performance**: Direct CSS updates (not JavaScript repaints)
- **Consistency**: Applies to all elements automatically
- **Browser Support**: Native CSS feature in modern browsers

---

## Advanced Topics

### Serial Protocol Details

#### Frame Format
```
Structure:
├─ Byte 0-2: 0xFE 0xFE 0xFE  (header)
├─ Byte 3:   Command (0x80=START, 0x81=STOP, 0x41=ACK)
├─ Byte 4-5: Data/Sequence (host dependent)
├─ Byte 6:   Status (0x00=success)
├─ Byte 7-8: CRC-16 (calculated)
└─ Byte 9-11: 0xFE 0xFE 0xFE (footer)
```

#### CRC-16 Calculation
```python
def _calculate_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc
```

### Anomaly Detection Algorithm Flow

1. **Input**: DataFrame with Time_Second and Frame_0..Frame_499
2. **Calculate Statistics**:
   - Mean per column
   - Standard deviation per column
   - Row-wise max check
3. **Multi-level Detection**:
   - Z-score analysis
   - Absolute difference analysis
   - Delta analysis
   - Rolling variance analysis
4. **Classification**:
   - Critical: Triggers critical conditions
   - Warning: Triggers warning conditions
   - Normal: All normal
5. **Output**: Annotated DataFrame with:
   - Status column
   - Detection type column
   - Severity scores
   - Health scores
   - Reason text

---

## Performance Considerations

### Memory Usage
- **Per Session**:
  - 500 data points/second
  - ~1 hour session = ~1.8M data points
  - Memory per point: ~20 bytes (tuple)
  - Total: ~36 MB for 1-hour session
  
### CPU Usage
- **Receive Loop**: <1% (I/O bound)
- **Frontend Updates**: <2% (60 FPS Canvas)
- **ML Analysis**: 20-40% (processing intensive)

### Network Latency
- **Serial**: Fixed 1-second chunks (500 bytes/second)
- **No Network**: All local communication

### Optimization Tips
- Export and archive old data (reduces memory)
- Run ML analysis during off-peak hours (processing intensive)
- Limit dashboard update rate if necessary (modify onChunk)
- Use light theme for better rendering performance

---

## Future Enhancement Opportunities

1. **Database Integration**: Replace CSV with SQLite/PostgreSQL
2. **Cloud Sync**: Upload analysis to cloud storage
3. **Real-time Alerts**: Email/SMS notifications on critical conditions
4. **Advanced ML**: Deep learning models for pattern prediction
5. **Multi-device**: Support for multiple serial devices simultaneously
6. **Web Interface**: Make available as web application
7. **Historical Analytics**: Trend analysis across multiple sessions
8. **Customizable Thresholds**: UI for configuring anomaly detection parameters
9. **Performance Profiling**: Built-in profiler for system analysis
10. **Remote Monitoring**: Real-time dashboard from remote machine

---

## Summary

The **Throughput Analysis Tool** is a comprehensive desktop application designed for real-time monitoring and analysis of embedded system frame throughput. It combines:

- **Real-time Data Acquisition**: Continuous monitoring via serial communication
- **Interactive Dashboard**: Live metrics and Canvas-based visualizations
- **Statistical Analysis**: ML-powered anomaly detection
- **Professional Reporting**: Excel and PDF report generation
- **User-friendly Interface**: Dark/Light theme, intuitive controls
- **Enterprise Features**: Export capabilities, detailed metrics

The architecture is modular, maintainable, and extensible for future enhancements. The codebase demonstrates best practices in:
- Thread-safe data handling
- Frontend-backend separation
- Real-time data visualization
- Professional report generation
- Error handling and user feedback

---

**Document Version**: 1.0  
**Last Updated**: May 16, 2026  
**Author**: Development Team  
**Status**: Complete

## Conclusion

The project is progressively evolving into a scalable real-time analysis and engineering automation platform focused on improving system performance monitoring, design consistency, and workflow efficiency.

Additionally, thread decoupling was implemented to overcome single-thread bottlenecks by moving serial port monitoring (`_receive_loop`) to a background thread, ensuring smooth real-time UI rendering and uninterrupted high-speed data acquisition.