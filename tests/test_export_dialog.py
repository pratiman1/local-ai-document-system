"""
tests/test_export_dialog.py
---------------------------
Automated test suite validating the export save dialog behaviors:
1. Default folder defaults to the user's Documents folder (portable across OSes).
2. The last chosen folder is remembered and used for subsequent exports.
3. Cancelling the Save File dialog does nothing and displays no error.
4. Full file path is included in the confirmation and Open Folder capability is provided.
5. Overwrite protection prompts before replacing existing files.
"""

import os
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set Qt to run in headless offscreen mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import QStandardPaths

from ui.export_panel import (
    ExportPanel,
    get_default_documents_folder,
    open_file_folder,
)
from config.settings import EXPORTS_DIR


class DummyMainWindow:
    """Mock main window provider for export tests."""
    def __init__(self, text: str = "Extracted multilingual content: हिन्दी, Tamil தமிழ்."):
        self._text = text

    def get_document_text(self) -> str:
        return self._text


def run_tests():
    print("\n" + "=" * 65)
    print("🧪 EXPORT SAVE DIALOG & LOCATION PERSISTENCE TEST SUITE")
    print("=" * 65 + "\n")

    app = QApplication.instance()
    if not app:
        app = QApplication(["-platform", "offscreen"])

    # --------------------------------------------------------------------------
    # Test 1: Default Folder is Documents Folder
    # --------------------------------------------------------------------------
    print("Test 1: Verifying default folder is user's Documents folder...")
    docs_folder = get_default_documents_folder()
    print(f"  • Detected Documents Folder: {docs_folder}")
    assert docs_folder is not None, "Documents folder resolution returned None"
    assert "Documents" in str(docs_folder) or docs_folder == Path.home(), "Expected Documents or Home directory"
    assert docs_folder != EXPORTS_DIR, "Default export directory must not be project's exports directory"

    panel = ExportPanel()
    assert panel.get_export_dir() == docs_folder, "ExportPanel did not default to Documents folder"
    print("  ✅ Passed: Default save directory accurately resolves to user's Documents folder.")

    # --------------------------------------------------------------------------
    # Test 2: Remember Last Chosen Folder
    # --------------------------------------------------------------------------
    print("\nTest 2: Verifying last chosen export folder is remembered...")
    custom_dir = PROJECT_ROOT / "uploads" / "custom_user_folder"
    custom_dir.mkdir(parents=True, exist_ok=True)
    custom_target_file = custom_dir / "sample_extracted.txt"

    try:
        # Simulate successful export to custom_dir
        panel.set_document_name("sample.pdf")
        dummy_parent = DummyMainWindow()
        panel.window = lambda: dummy_parent

        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(custom_target_file), "Text Files (*.txt)")):
            with patch.object(QMessageBox, "exec", return_value=QMessageBox.Ok):
                panel._on_export_txt_clicked()

        assert custom_target_file.exists(), "Exported file was not created"
        assert panel._last_export_dir == custom_dir, "Last export directory was not saved"
        assert panel.get_export_dir() == custom_dir, "Subsequent get_export_dir() did not return remembered folder"
        print("  ✅ Passed: Last chosen directory is remembered for subsequent dialogs.")
    finally:
        if custom_target_file.exists():
            custom_target_file.unlink()
        if custom_dir.exists():
            shutil.rmtree(custom_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # Test 3: Cancel Does Nothing and Shows No Error
    # --------------------------------------------------------------------------
    print("\nTest 3: Verifying cancellation does nothing and shows no error...")
    panel_cancel = ExportPanel()
    panel_cancel.set_document_name("sample.pdf")
    panel_cancel.window = lambda: DummyMainWindow()

    with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
        with patch.object(QMessageBox, "critical") as mock_crit, \
             patch.object(QMessageBox, "warning") as mock_warn:
            panel_cancel._on_export_txt_clicked()
            assert not mock_crit.called, "Critical error shown on cancel!"
            assert not mock_warn.called, "Warning shown on cancel!"

    assert panel_cancel.export_status.text() == "", "Status text should remain empty on cancel"
    assert panel_cancel.btn_open_folder.isHidden(), "Open Folder button should not appear on cancel"
    print("  ✅ Passed: Dialog cancellation handled cleanly with zero errors.")

    # --------------------------------------------------------------------------
    # Test 4: Full Path in Confirmation & Open Folder Action
    # --------------------------------------------------------------------------
    print("\nTest 4: Verifying full path in confirmation and Open Folder button...")
    test_out = PROJECT_ROOT / "uploads" / "full_path_test_extracted.txt"
    try:
        panel_confirm = ExportPanel()
        panel_confirm.set_document_name("test_doc.pdf")
        panel_confirm.window = lambda: DummyMainWindow("Hindi text: नमस्कार")

        captured_msg_text = []
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(test_out), "Text Files (*.txt)")):
            with patch.object(QMessageBox, "exec") as mock_exec:
                def fake_exec(msg_self):
                    captured_msg_text.append(msg_self.text())
                    return QMessageBox.Ok
                with patch.object(QMessageBox, "exec", side_effect=lambda: fake_exec(QMessageBox())):
                    # Check that QMessageBox contains the full path
                    with patch("PySide6.QtWidgets.QMessageBox.setText") as mock_set_text:
                        panel_confirm._on_export_txt_clicked()
                        # Inspect called arguments on setText
                        called_texts = [str(call_arg[0][0]) for call_arg in mock_set_text.call_args_list]
                        assert any(str(test_out) in txt for txt in called_texts), "Full path missing from confirmation text!"

        assert test_out.exists(), "File should be created"
        assert not panel_confirm.btn_open_folder.isHidden(), "Open Folder button should be visible"
        assert panel_confirm._last_saved_file == str(test_out), "Last saved file path missing"
        print("  ✅ Passed: Full file path displayed in confirmation and Open Folder button enabled.")
    finally:
        if test_out.exists():
            test_out.unlink()

    # --------------------------------------------------------------------------
    # Test 5: Overwrite Protection Prompt
    # --------------------------------------------------------------------------
    print("\nTest 5: Verifying overwrite protection prompts before replacing...")
    existing_file = PROJECT_ROOT / "uploads" / "_overwrite_test.txt"
    try:
        existing_file.write_text("Original text before export", encoding="utf-8")
        panel_ow = ExportPanel()
        panel_ow.set_document_name("overwrite_doc.pdf")
        panel_ow.window = lambda: DummyMainWindow("Brand new text")

        # Case A: User clicks 'No' (Rejects overwrite)
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(existing_file), "Text Files (*.txt)")):
            with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as mock_q:
                panel_ow._on_export_txt_clicked()
                assert mock_q.called, "Overwrite confirmation was not prompted!"
                assert existing_file.read_text(encoding="utf-8") == "Original text before export", "File was overwritten despite user saying No!"

        # Case B: User clicks 'Yes' (Accepts overwrite)
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(existing_file), "Text Files (*.txt)")):
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as mock_q:
                with patch.object(QMessageBox, "exec", return_value=QMessageBox.Ok):
                    panel_ow._on_export_txt_clicked()
                    assert existing_file.read_text(encoding="utf-8") == "Brand new text", "File was not replaced after user confirmed Yes!"

        print("  ✅ Passed: Overwrite protection prompt verified (rejects on No, replaces on Yes).")
    finally:
        if existing_file.exists():
            existing_file.unlink()

    print("\n" + "=" * 65)
    print("🎉 ALL EXPORT SAVE DIALOG TESTS PASSED SUCCESSFULLY!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_tests()
