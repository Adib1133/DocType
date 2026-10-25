# DocType

A local desktop app for cropping document photos, cleaning text scans, exporting PDFs, and visually removing PDF pages. Files stay on your computer.

## Start

Install Python 3.10 or newer, run `python -m pip install -r requirements.txt`, then double-click **DocType.bat** or run `python app.py`. This repository contains source only. After building, the launcher uses `dist/DocType/DocType.exe`; keep its `_internal` folder beside the executable.

## Appearance and settings

Open **Settings / Output folder** or **File → Settings**.

- **Light:** cream surfaces with maroon accents.
- **Dark:** charcoal surfaces, muted rose buttons, and light text.
- **System:** follows the appearance reported by the operating system through CustomTkinter. Detection depends on platform support.
- **Saved output folder:** all image and PDF exports reuse this folder until changed. If none is saved, the first export prompts and remembers your choice. An unavailable folder produces an error rather than silently changing the destination.
- **Default page size and DPI:** used for image-to-PDF exports. These do not resample pages copied by the PDF page remover.
- **Save removed pages by default:** controls whether PDF removal also produces a separate file containing removed pages.

Click **Save settings** to apply and persist changes in `config/settings.json`. Theme changes retain loaded images, undo history, PDF removal selection, and current export options. Document image colours are not changed by the theme.

## Image workflow

1. Add images using **+ Add** or **Ctrl+O**.
2. Review the page in Preview or Before / After.
3. Use Manual Crop to drag the crop frame, corners, or edges; Apply commits the crop and Cancel discards it. Auto Detect starts with a detected boundary, or the full frame if no reliable outer edge exists.
4. Choose a profile and Apply Enhancement.
5. Export as a combined PDF, separate PDFs, or PNGs.

Profiles:

| Profile | Purpose |
| --- | --- |
| Clean scan | White-paper cleanup for text documents |
| Soft text | Gentler contrast for faint text |
| Keep colour | Text cleanup while retaining colour |
| Original (no filter) | Preserve the original cropped image |

Text cleanup can remove faint watermarks or photographic shading. Use Original for ID cards and photographs when preserving every detail is important. This app does not perform OCR, reconstruct missing details, or produce editable Word files.

Batch actions rotate, enhance, or auto-crop all loaded pages. Uncertain automatic crops are skipped. Undo and redo are tracked per image.

## Visual PDF page removal

1. Switch to the **PDF pages** tab and choose **Open PDF**.
2. Wait for the page thumbnails to render.
3. Click a page to mark it with a maroon **×** for removal. Click it again to keep it, or choose Clear selection.
4. Review the selected/remaining count. At least one page must remain.
5. Choose whether to save removed pages separately, then click **Save edited PDF**.

Outputs are `filename_edited.pdf` and, optionally, `filename_removed.pdf` in the saved output folder. The source remains unchanged. Existing output names receive numeric suffixes. Pages keep their source order and are copied without rasterizing their content. If the source file changes while open, reopen it before saving.

Document-level bookmarks, interactive form structures, and digital signatures are not reconstructed. PDFs requiring a password must be unlocked before opening in this app.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+O | Open images; open PDF in the PDF pages tab |
| Ctrl+E | Export images to PDF; save PDF removal selection in the PDF tab |
| Ctrl+Z / Ctrl+Y | Image undo / redo |
| Delete | Remove selected image; disabled in PDF tab |
| Ctrl+Q | Quit |

## Project layout

```text
app.py                 Main window, image workflow, settings
image_processor.py     Crop, enhancement, image/PDF export
document_tools.py      Preferences and PDF page extraction
pdf_pages_panel.py     Rendered PDF thumbnails and selection
theme.py               Shared light and dark palettes
DocType.bat            Launcher
doctype.spec           Build configuration
requirements.txt       Python runtime dependencies
tests/                 Processing, UI, settings, and theme tests
config/settings.json   Preferences (created when saved)
dist/DocType/          Generated application (not committed)
```

## Development and verification

```powershell
python -m pip install -r requirements.txt
python app.py
python -m unittest discover -s tests -v
python -m pip install pyinstaller
python -m PyInstaller --noconfirm doctype.spec
```

Close the packaged app before rebuilding so its files are not locked. `build/` and Python cache folders are disposable; retain `dist/DocType/_internal`. Tests cover crop interaction, enhancement, PDF page order and export, settings persistence, thumbnail selection, and theme switching without lost edits.

## Repository hygiene

Tests use synthetic documents, not personal photos. Do not commit private documents, saved settings, export folders, Python caches, or compiled distributions. These paths are excluded by `.gitignore`. Run tests from the repository root; UI tests need a desktop session.
