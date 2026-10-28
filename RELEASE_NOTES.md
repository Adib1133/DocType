# DocType — Initial Release

DocType is a local Windows desktop utility for preparing document images, exporting PDFs, and removing selected PDF pages through a visual interface.

## Workplace use

This application is intended for use at my current workplace to automate repetitive document-processing tasks, including preparing scanned paperwork, applying batch edits, exporting files to a saved directory, and separating unwanted pages from PDFs. It is designed to reduce manual steps in day-to-day office workflows. This statement describes intended use, not an endorsement by my employer.

## Features

- Cream/maroon light mode, charcoal dark mode, and a System appearance option.
- Image preview and side-by-side before/after comparison.
- Manual crop review with resize handles, plus automatic document-boundary suggestions.
- Clean scan, Soft text, Keep colour, and Original (no filter) profiles.
- Batch rotation, enhancement, and confident automatic cropping.
- Combined PDF, individual PDF, and PNG exports.
- Saved output directory, default paper size, DPI, and PDF-removal preferences.
- Dedicated PDF pages tab with rendered thumbnails; click a page to mark it with a cross for removal.
- Optional separate PDF containing removed pages, alongside the edited PDF.
- Source PDFs remain unchanged; exported pages retain their original order.
- Unique export filenames to avoid overwriting existing output files.

## Refinements

- Theme changes retain loaded image edits, undo history, PDF selections, and current export choices.
- PDF export waits for previews to finish and rejects removal of every page.
- A changed source PDF must be reopened before exporting its page selection.
- Processing and preferences stay local; no cloud account is required.

## Getting started

Install Python 3.10 or newer, then run:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Alternatively, use `DocType.bat`. If you build the Windows executable, keep the complete `dist/DocType/` folder together, including `_internal`.

Open Settings to choose your output folder and appearance. See [README.md](README.md) for workflows, shortcuts, and build instructions.

## Validation

The GitHub-ready source snapshot passed all 15 automated tests, covering image processing, crop interactions, preferences, PDF selection/export, and theme switching. UI tests require a desktop session.

## Known limitations

- Text-cleanup filters may suppress faint watermarks or photographic shading. Use Original (no filter) when retaining all source detail is essential.
- Automatic crop suggestions may need adjustment, particularly when paper boundaries are unclear.
- The app does not perform OCR or generate editable Word documents.
- Password-required PDFs must be unlocked before use. Document-level bookmarks, form structures, and digital signatures are not reconstructed during page extraction.
- System-theme detection depends on operating-system support.

## License

Released under the GNU General Public License, version 3 (GPL-3.0-only). See [LICENSE](LICENSE) for the complete terms. Third-party dependencies retain their own licenses.

## Direct printing update

Added native Windows print dialogs for enhanced images, remaining PDF pages, and removed PDF pages. Includes printer properties, copy handling, page ranges, proportional fitting, cancellation, and cleanup of failed jobs. Ctrl+P prints the active workspace. Physical printer output has not been verified; automated tests cover page ranges, sizing, cancellation, and job cleanup.

## Print preview update

Added an in-app preview before the Windows print dialog for enhanced images and remaining/removed PDF pages. Includes page navigation and safe cancellation. The Windows GDI pane itself does not receive a preview.
