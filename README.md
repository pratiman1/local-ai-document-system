# Local AI Multilingual Document Processing System

A professional, offline-first desktop document processing application built with **Python**, **PySide6 (Qt6)**, and **PyMuPDF**.

Engineered for native, cross-platform performance across **macOS (Apple Silicon & Intel)**, **Windows 10/11**, and **Linux**.

---

## 🌟 Core Features (Current)

- **100% Offline & Private:** Zero background telemetry, zero cloud AI calls, complete local document isolation.
- **Cross-Platform Desktop UI:** Built on Qt6 (PySide6) with native font rendering, compact layout, and responsive controls.
- **Local PDF Text Extraction:** Fast digital text layer extraction via PyMuPDF.
- **Dynamic Hardware Detection:** Automatically inspects host operating system, processor architecture, and physical RAM without hardcoded values.
- **Drag-and-Drop Ingestion:** Space-efficient file drop zone supporting `.pdf` documents.
- **File Management:** Quick "Remove File" (✕) button and "Open Another File" (Replace) option with unsaved-edits protection.
- **Editable Document Preview:** Full-text editing mode allowing manual cleanup and in-place correction.
- **Page-by-Page Inspector:** Individual page viewer with page-specific word counts and stats.
- **Multilingual Language Selector:** Pre-configured for scheduled Indian languages (Hindi, Tamil, Telugu, Marathi, Bengali, Gujarati, Punjabi, Kannada, Malayalam, Odia, Assamese, Urdu) and English.
- **One-Click Local TXT Export:** Non-destructive UTF-8 text export with overwrite protection.

---

## 🔮 Planned Features (Upcoming)

The following capabilities are currently under development and planned for future releases:

- **Local OCR Engine (Planned):** Scanned PDF and image text recognition using local OCR models (PaddleOCR / Tesseract) without cloud dependency.
- **DOCX Document Export (Planned):** Exporting extracted and formatted documents to Microsoft Word (`.docx`) format.
- **Formatted PDF Export (Planned):** Multilingual formatted PDF document export preserving Indian language scripts and layouts.
- **Optional Cloud AI Enhancement (Planned):** Optional, user-authorized text cleanup and grammar enhancement via OpenAI ChatGPT or Google Gemini APIs with strict privacy disclosures and keychain credential storage.
- **Offline Machine Translation (Planned):** Local translation models for scheduled Indian languages.

---

## 🌐 Offline Translation Models & Engines

The application supports 100% offline neural translation with two pluggable offline engines: **Argos Translate** and **AI4Bharat IndicTrans2**, complete with automatic engine choice and optional **Compare Mode**.

---

### 🇮🇳 AI4Bharat IndicTrans2 Engine (`models/indictrans2/`)

AI4Bharat IndicTrans2 provides state-of-the-art neural machine translation across 22 scheduled Indian languages and English. It supports **direct Indian language to Indian language translation** (e.g., Hindi to Tamil, Marathi to Bengali) without pivoting through English.

#### Folder Layout for IndicTrans2 Models
Place the downloaded model folders directly into `models/indictrans2/`:
```text
Local_AI_Document_System/
└── models/
    └── indictrans2/
        ├── en-indic/       # English to Indic (22 languages)
        │   ├── model.safetensors (or pytorch_model.bin)
        │   ├── config.json
        │   └── tokenizer files
        ├── indic-en/       # Indic to English (22 languages)
        │   ├── model.safetensors (or pytorch_model.bin)
        │   ├── config.json
        │   └── tokenizer files
        └── indic-indic/    # Direct Indic to Indic (320M distilled model)
            ├── model.safetensors (or pytorch_model.bin)
            ├── config.json
            └── tokenizer files
```

#### Download Sizes & Hugging Face Repositories (Distilled Models)
- **English to Indic (`en-indic`):** ~200M params | Download: **~800 MB - 1 GB** | Disk: ~850 MB
  - Repo: `ai4bharat/indictrans2-en-indic-dist-200M`
- **Indic to English (`indic-en`):** ~200M params | Download: **~800 MB - 1 GB** | Disk: ~850 MB
  - Repo: `ai4bharat/indictrans2-indic-en-dist-200M`
- **Indic to Indic (`indic-indic`):** ~320M params | Download: **~1.2 GB - 1.5 GB** | Disk: ~1.4 GB
  - Repo: `ai4bharat/indictrans2-indic-indic-dist-320M`

#### Toolkit Installation Across Platforms
To enable IndicTrans2 in your local environment, install the required packages:
```bash
pip install IndicTransToolkit transformers torch sentencepiece
```
- **macOS (Apple Silicon M1/M2/M3/M4):** Automatically utilizes Metal Performance Shaders (`mps`) hardware acceleration with strict memory management (< 1.5 GB RAM).
- **Windows 10/11 & Linux:** Runs on CPU or NVIDIA CUDA GPU automatically.
- **8 GB RAM Friendly:** Lazy-loads only the requested direction; unloads previous models and runs garbage collection before loading another direction.

---

### 🌐 Argos Translate Models (`models/argos/`)

Place all downloaded `.argosmodel` files directly into the **`models/argos/`** folder:
```text
Local_AI_Document_System/
└── models/
    └── argos/
        ├── translate-en_hi-1_0.argosmodel    # English to Hindi (direct)
        ├── translate-hi_en-1_0.argosmodel    # Hindi to English (direct)
        ├── translate-en_ta-1_0.argosmodel    # English to Tamil (direct)
        └── translate-en_te-1_0.argosmodel    # English to Telugu (direct)
```

---

### ⚡ Automatic Engine Routing & Compare Mode

- **Automatic Engine Priority:**
  1. **IndicTrans2 Direct:** Selected whenever an installed IndicTrans2 model covers the pair (e.g., direct Hindi ➔ Tamil with `indic-indic`).
  2. **Argos Direct:** Selected when an Argos model is installed directly for the pair.
  3. **Argos English Pivot:** Applied when no direct pair exists (e.g., Hindi ➔ English ➔ Tamil).
  4. **Missing Model Guidance:** Specifies exact model files and target folders.
- **User Preference Override:** In Settings (⚙️), you can force `Argos Translate Only`, `IndicTrans2 Only`, or keep `Automatic`.
- **Sequential Compare Mode:**
  - When both engines cover a language pair, Compare Mode translates each page sequentially (never parallel, safeguarding 8 GB RAM).
  - Calculates lexical consensus using token F1 score and character n-gram overlap (chrF).
  - Flags pages below the configured threshold (default 60%).
  - Provides a side-by-side review dialog allowing the user to select the preferred translation per page.
  - *Disclosure: "Agreement indicator, not an accuracy score; two models can agree and still be wrong."*

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
│   ├── upload_panel.py        # Compact horizontal file drop zone & remove/replace controls
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
│   └── icons/                 # Portable SVG vector icons (chevron, close)
│
├── uploads/                   # Staged input files
├── exports/                   # Exported output documents
│
└── tests/                     # Automated test suites
    ├── test_indictrans2_and_routing.py   # IndicTrans2, router & compare mode tests
    ├── test_argos_model_management.py    # Argos offline model management tests
    ├── test_translation.py               # Language detection & translation pipeline tests
    ├── test_ocr.py                       # OCR engine & recovery tests
    ├── test_ai_enhance.py                # Optional AI enhancement tests
    ├── test_security_remediations.py     # Privacy & security audit tests
    ├── test_export_dialog.py             # Export dialog & folder tests
    ├── test_extractor.py                 # PDF extraction tests
    ├── test_txt_exporter.py              # TXT exporter tests
    ├── test_system_info.py               # Hardware detection tests
    └── test_ui_launch.py                 # Cross-platform UI integration tests
```

---

## 🧪 Running the Automated Test Suites & Benchmark

To verify all components locally:
```bash
# Run all 11 test suites
for t in tests/test_*.py; do python "$t"; done

# Run the cross-engine translation benchmark
python tools/translation_benchmark.py
```

---

## 📦 Future Standalone Distribution Strategy (Packaging Roadmap)

When ready to distribute standalone binaries without requiring users to install Python:

- **macOS:** Build native `.app` and `.dmg` bundles with PyInstaller using the `--windowed` flag.
- **Windows:** Build native `.exe` installer or portable executable using Inno Setup or PyInstaller `--onefile`.
- **Linux:** Package as an `AppImage` or native `.deb` package for universal compatibility across distributions.
