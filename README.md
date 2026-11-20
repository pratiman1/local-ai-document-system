# Local AI Multilingual Document Processing System

A professional, offline-first desktop document processing application built with **Python**, **PySide6 (Qt6)**, and **PyMuPDF**.

Engineered for native, cross-platform performance across **macOS (Apple Silicon & Intel)**, **Windows 10/11**, and **Linux**.

---

## 🌟 Core Features

- **100% Offline & Private:** Zero background telemetry, zero cloud AI calls, complete local document isolation.
- **Cross-Platform Desktop UI:** Built on Qt6 (PySide6) with native font rendering and responsive layouts.
- **High-Performance PDF Text Extraction:** Local extraction via PyMuPDF reading digital text layers in milliseconds.
- **Dynamic Hardware Detection:** Automatically inspects the host operating system, processor architecture, and physical RAM without hardcoded values.
- **Drag-and-Drop Ingestion:** Compact, space-efficient file drop zone supporting `.pdf` documents.
- **Editable Document Preview:** Full-text editing mode allowing manual cleanup and in-place correction.
- **Page-by-Page Inspector:** Individual page viewer with page-specific word counts and stats.
- **Multilingual Language Selector:** Pre-configured for scheduled Indian languages (Hindi, Tamil, Telugu, Marathi, Bengali, Gujarati, Punjabi, Kannada, Malayalam, Odia, Assamese, Urdu) and English.
- **One-Click Local TXT Export:** Non-destructive UTF-8 text export with overwrite protection.

---

## 💻 Cross-Platform Installation & Setup

### Prerequisites
- **Python:** 3.10, 3.11, 3.12, or 3.14 (64-bit recommended)
- **Pip:** Package installer for Python

---

### 🍎 macOS Setup (Apple Silicon & Intel)

1. **Clone or Download the Repository:**
   ```bash
   git clone https://github.com/your-username/Local_AI_Document_System.git
   cd Local_AI_Document_System
   ```

2. **Create and Activate Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the Application:**
   ```bash
   python main.py
   ```

---

### 🪟 Windows 10 / 11 Setup

1. **Open PowerShell or Command Prompt:**
   ```powershell
   cd Local_AI_Document_System
   ```

2. **Create and Activate Virtual Environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Launch the Application:**
   ```powershell
   python main.py
   ```

---

### 🐧 Linux Setup (Ubuntu / Debian / Fedora)

1. **Install System Qt Dependencies (if not already installed):**
   *Ubuntu / Debian:*
   ```bash
   sudo apt update
   sudo apt install -y python3-venv python3-pip libgl1-mesa-glx libxkbcommon-x11-0
   ```
   *Fedora:*
   ```bash
   sudo dnf install -y python3-pip mesa-libGL libxkbcommon-x11
   ```

2. **Create and Activate Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the Application:**
   ```bash
   python main.py
   ```

---

## 📁 Project Architecture

```text
Local_AI_Document_System/
│
├── main.py                     # Desktop application entry point (QApplication)
├── requirements.txt           # Core cross-platform dependencies
├── .gitignore                 # Portable Git ignore rules
├── README.md                  # System documentation
│
├── config/                    # Configuration and UI themes
│   ├── settings.py            # Cross-platform paths, fonts, window sizes
│   └── languages.py           # Indian language registry
│
├── ui/                        # Modular PySide6 GUI components
│   ├── main_window.py         # Main application coordinator window
│   ├── upload_panel.py        # Compact horizontal file drop zone
│   ├── language_selector.py   # Target language selector with chevron arrow
│   ├── preview_panel.py       # Metrics ribbon, full text editor, page breakdown
│   ├── export_panel.py        # Export controls with tooltip guidance
│   └── system_info_panel.py   # Dynamic host hardware & OS detection card
│
├── utils/                     # Cross-platform utility modules
│   └── system_info.py         # Stdlib OS, CPU arch, and RAM probe
│
├── extractors/
│   └── pdf_extractor.py       # Local PyMuPDF text extraction engine
│
├── exporters/
│   └── txt_exporter.py        # UTF-8 text export engine
│
├── assets/                    # Application icons & visual resources
│   └── icons/                 # Portable SVG vector icons
│
├── uploads/                   # Staged input files
├── exports/                   # Exported output documents
│
└── tests/                     # Automated test suites
    ├── test_extractor.py      # PDF extraction tests
    ├── test_txt_exporter.py   # TXT exporter tests
    ├── test_system_info.py    # Hardware detection tests
    └── test_ui_launch.py      # Cross-platform UI integration tests
```

---

## 🧪 Running the Automated Test Suites

To verify all components locally:
```bash
python tests/test_system_info.py
python tests/test_txt_exporter.py
python tests/test_extractor.py
python tests/test_ui_launch.py
```

---

## 📦 Future Standalone Distribution Strategy (Packaging Roadmap)

When ready to distribute standalone binaries without requiring users to install Python:

- **macOS:** Build native `.app` and `.dmg` bundles with PyInstaller using the `--windowed` flag.
- **Windows:** Build native `.exe` installer or portable executable using Inno Setup or PyInstaller `--onefile`.
- **Linux:** Package as an `AppImage` or native `.deb` package for universal compatibility across distributions.
