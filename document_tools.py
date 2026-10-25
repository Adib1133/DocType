"""Persistent preferences and non-destructive PDF page operations."""
import json
import os
import re
import sys
from pathlib import Path
import pikepdf

DEFAULTS = {"output_dir": "", "page_size": "A4", "dpi": "150", "save_removed": True, "theme": "Light"}

def settings_path():
    root = Path(sys.executable).resolve().parents[2] if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    return root / 'config' / 'settings.json'

def load_settings(path=None):
    result = DEFAULTS.copy()
    try:
        data = json.loads(Path(path or settings_path()).read_text(encoding='utf-8'))
        if isinstance(data, dict):
            if data.get('theme') in ('Light','Dark','System'): result['theme'] = data['theme']
            if isinstance(data.get('output_dir'), str): result['output_dir'] = data['output_dir']
            if data.get('page_size') in ('A4','A3','Letter','Auto'): result['page_size'] = data['page_size']
            if str(data.get('dpi')) in ('72','96','150','200','300'): result['dpi'] = str(data['dpi'])
            if isinstance(data.get('save_removed'), bool): result['save_removed'] = data['save_removed']
    except (OSError, ValueError):
        pass
    return result

def save_settings(values, path=None):
    path = Path(path or settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(values, indent=2), encoding='utf-8')
    temporary.replace(path)

def unique_path(folder, name):
    path = Path(folder) / name
    index = 2
    while path.exists():
        path = Path(folder) / f'{Path(name).stem}_{index}{Path(name).suffix}'
        index += 1
    return path

def parse_pages(text, count):
    selected = set()
    for token in text.split(','):
        match = re.fullmatch(r'\s*(\d+)\s*(?:-\s*(\d+)\s*)?', token)
        if not match: raise ValueError('Enter page numbers or ranges, for example: 2, 4-6, 9.')
        first, last = int(match[1]), int(match[2] or match[1])
        if first < 1 or last > count or first > last:
            raise ValueError(f'Page numbers must be between 1 and {count}, with ranges in ascending order.')
        selected.update(range(first-1,last))
    if len(selected) == count:
        raise ValueError('Keep at least one page in the edited PDF.')
    return selected

def remove_pdf_pages(source, selection, folder, save_removed=True):
    """Keep source untouched; copy original page objects without rasterizing them."""
    source = Path(source)
    folder = Path(folder)
    if not folder.is_dir(): raise ValueError('The saved output folder is unavailable. Change it in Settings.')
    written = []
    try:
        with pikepdf.open(source) as original:
            selected = parse_pages(selection, len(original.pages))
            groups = [('edited', [i for i in range(len(original.pages)) if i not in selected])]
            if save_removed: groups.append(('removed', sorted(selected)))
            for label, indices in groups:
                destination = unique_path(folder, f'{source.stem}_{label}.pdf')
                with pikepdf.Pdf.new() as output:
                    output.pages.extend(original.pages[i] for i in indices)
                    written.append(destination)
                    output.save(destination)
        return written
    except Exception:
        for path in written: path.unlink(missing_ok=True)
        raise
