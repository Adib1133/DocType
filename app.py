"""
app.py  –  DocType
==================
Desktop image-to-PDF processor with cream & maroon styling,
interactive crop review dialog, batch editing, and document enhancement.
"""

import os
from printing import preview_and_print
from theme import apply_theme
from pdf_pages_panel import PdfPagesPanel
import pikepdf
from document_tools import load_settings, save_settings, unique_path, parse_pages, remove_pdf_pages
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import customtkinter as ctk

from image_processor import (
    detect_document,
    apply_color_grade,
    export_pdf,
    export_images,
    resize_for_preview,
    PAGE_SIZES,
)

# ── Appearance & Cream / Maroon Palette ─────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

BG_MAIN        = "#FAF6EF"   # warm cream background
BG_PANEL       = "#F3ECE1"   # slightly deeper cream for panels
BG_CARD        = "#FFFFFF"   # clean card white
BORDER_COLOR   = "#D8C9BA"   # soft warm taupe border
MAROON         = "#7A1C28"   # deep maroon primary
MAROON_HOVER   = "#912332"   # lighter maroon on hover
MAROON_DARK    = "#5C131E"   # rich dark maroon
TEXT_MAIN      = "#2D1518"   # dark maroon-charcoal
TEXT_MUTED     = "#75595C"   # muted warm taupe-maroon
BUTTON_ALT     = "#EBE0D2"   # secondary button fill
BUTTON_ALT_HOV = "#DECFC0"   # secondary button hover

THUMB_W, THUMB_H = 130, 95


# ═══════════════════════════════════════════════════════════════════════════
# ImageRecord
# ═══════════════════════════════════════════════════════════════════════════

class ImageRecord:
    def __init__(self, path: str, pil_img: Image.Image):
        self.path        = path
        self.original    = pil_img.copy()
        self.cropped     = pil_img.copy()
        self.graded      = pil_img.copy()
        self.crop_rect   = None
        self.quad_pts    = None
        self.history     = []
        self.redo_stack  = []

    def push_history(self):
        self.history.append((self.cropped.copy(), self.graded.copy()))
        self.redo_stack.clear()

    def undo(self):
        if self.history:
            self.redo_stack.append((self.cropped.copy(), self.graded.copy()))
            self.cropped, self.graded = self.history.pop()
            return True
        return False

    def redo(self):
        if self.redo_stack:
            self.history.append((self.cropped.copy(), self.graded.copy()))
            self.cropped, self.graded = self.redo_stack.pop()
            return True
        return False

    @property
    def display_name(self):
        return os.path.basename(self.path)

    @property
    def info_str(self):
        w, h = self.cropped.size
        return f"{w} × {h} px"


# ═══════════════════════════════════════════════════════════════════════════
# CropCanvas – interactive drag-to-crop with corner resize handles
# ═══════════════════════════════════════════════════════════════════════════

class CropCanvas(tk.Canvas):
    HANDLE_R = 7

    def __init__(self, parent, on_rect_change=None, **kw):
        super().__init__(parent, bg="#1E1E1E", highlightthickness=0, **kw)
        self._photo       = None
        self._img_pil     = None
        self._scale       = 1.0
        self._ox = self._oy = 0

        self._rect        = None   # [x1, y1, x2, y2]
        self._dragging    = None
        self._drag_start  = None
        self._on_change   = on_rect_change

        self._rect_item   = None
        self._dim_items   = []
        self._handles     = []

        self.bind("<ButtonPress-1>",   self._press)
        self.bind("<B1-Motion>",       self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>",       self._resize)

    def set_image(self, pil_img: Image.Image):
        self._img_pil = pil_img
        self._rect    = None
        self._redraw_image()
        if self._img_pil:
            self.set_rect_normalized(0.0, 0.0, 1.0, 1.0)

    def set_rect_normalized(self, nx1, ny1, nx2, ny2):
        if not self._img_pil:
            return
        iw, ih = self._img_pil.size
        s = self._scale
        self._rect = [
            self._ox + nx1 * iw * s,
            self._oy + ny1 * ih * s,
            self._ox + nx2 * iw * s,
            self._oy + ny2 * ih * s,
        ]
        self._redraw_overlay()

    def get_rect_original(self):
        if not self._rect or not self._img_pil:
            return None
        x1, y1, x2, y2 = self._rect
        ox, oy, s = self._ox, self._oy, self._scale
        iw, ih    = self._img_pil.size

        rx1 = min(x1, x2)
        ry1 = min(y1, y2)
        rx2 = max(x1, x2)
        ry2 = max(y1, y2)

        ox1 = max(0, min(iw, round((rx1 - ox) / s)))
        oy1 = max(0, min(ih, round((ry1 - oy) / s)))
        ox2 = max(0, min(iw, round((rx2 - ox) / s)))
        oy2 = max(0, min(ih, round((ry2 - oy) / s)))

        if ox2 <= ox1:
            ox2 = min(iw, ox1 + 1)
        if oy2 <= oy1:
            oy2 = min(ih, oy1 + 1)
        return (ox1, oy1, ox2, oy2)

    def clear_rect(self):
        self._rect = None
        self._redraw_overlay()

    def _redraw_image(self):
        if not self._img_pil:
            return
        cw = max(self.winfo_width(), 100)
        ch = max(self.winfo_height(), 100)
        preview      = resize_for_preview(self._img_pil, max(cw, ch, 1))
        pw, ph       = preview.size
        self._scale  = pw / max(self._img_pil.width, 1)
        self._ox     = (cw - pw) // 2
        self._oy     = (ch - ph) // 2
        self._photo  = ImageTk.PhotoImage(preview)
        self.delete("all")
        self._rect_item = None
        self._handles   = []
        self._dim_items = []
        self.create_image(self._ox, self._oy, anchor="nw",
                          image=self._photo, tags="img")

    def _redraw_overlay(self):
        for item in self._dim_items + self._handles:
            self.delete(item)
        if self._rect_item:
            self.delete(self._rect_item)
        self._dim_items = []
        self._handles   = []
        self._rect_item = None

        if not self._rect or not self._img_pil:
            return

        x1, y1, x2, y2 = (min(self._rect[0], self._rect[2]),
                          min(self._rect[1], self._rect[3]),
                          max(self._rect[0], self._rect[2]),
                          max(self._rect[1], self._rect[3]))
        cw = max(self.winfo_width(), 100)
        ch = max(self.winfo_height(), 100)

        for rx1, ry1, rx2, ry2 in [(0, 0, cw, y1), (0, y2, cw, ch), (0, y1, x1, y2), (x2, y1, cw, y2)]:
            if rx2 > rx1 and ry2 > ry1:
                item = self.create_rectangle(
                    rx1, ry1, rx2, ry2,
                    fill="#000000", stipple="gray50",
                    outline="", tags="overlay"
                )
                self._dim_items.append(item)

        self._rect_item = self.create_rectangle(
            x1, y1, x2, y2,
            outline=MAROON, width=2, dash=(6, 3), tags="cropborder"
        )

        r = self.HANDLE_R
        for cx, cy in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
            h = self.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=MAROON, outline="white", width=1.5, tags="handle"
            )
            self._handles.append(h)

    def _resize(self, _=None):
        if self._img_pil:
            old_rect = self.get_rect_original()
            self._redraw_image()
            if old_rect:
                iw, ih = self._img_pil.size
                self.set_rect_normalized(
                    old_rect[0] / iw, old_rect[1] / ih,
                    old_rect[2] / iw, old_rect[3] / ih
                )
        else:
            self._redraw_overlay()

    def _hit_handle(self, x, y):
        if not self._rect:
            return None
        x1, y1, x2, y2 = (min(self._rect[0], self._rect[2]),
                          min(self._rect[1], self._rect[3]),
                          max(self._rect[0], self._rect[2]),
                          max(self._rect[1], self._rect[3]))
        r = self.HANDLE_R + 6
        for tag, (cx, cy) in [("tl",(x1,y1)), ("tr",(x2,y1)), ("br",(x2,y2)), ("bl",(x1,y2))]:
            if abs(x - cx) <= r and abs(y - cy) <= r:
                return tag
        return None

    def _inside(self, x, y):
        if not self._rect:
            return False
        x1, y1, x2, y2 = self._rect
        return min(x1,x2) < x < max(x1,x2) and min(y1,y2) < y < max(y1,y2)

    def _press(self, e):
        h = self._hit_handle(e.x, e.y)
        if h:
            self._dragging, self._drag_start = h, (e.x, e.y)
        elif self._inside(e.x, e.y):
            self._dragging, self._drag_start = "move", (e.x, e.y)
        else:
            self._dragging = "new"
            self._rect     = [e.x, e.y, e.x, e.y]
            self._redraw_overlay()

    def _drag(self, e):
        if not self._dragging or not self._rect or not self._img_pil:
            return
        x1, y1, x2, y2 = self._rect
        dx = e.x - self._drag_start[0]
        dy = e.y - self._drag_start[1]

        iw, ih = self._img_pil.size
        min_x = self._ox
        max_x = self._ox + iw * self._scale
        min_y = self._oy
        max_y = self._oy + ih * self._scale

        if self._dragging == "move":
            rw = abs(x2 - x1)
            rh = abs(y2 - y1)
            nx1 = min(x1, x2) + dx
            ny1 = min(y1, y2) + dy
            # Bound movement to image bounds
            nx1 = max(min_x, min(nx1, max_x - rw))
            ny1 = max(min_y, min(ny1, max_y - rh))
            self._rect = [nx1, ny1, nx1 + rw, ny1 + rh]
        elif self._dragging == "new":
            self._rect = [x1, y1, max(min_x, min(e.x, max_x)), max(min_y, min(e.y, max_y))]
        elif self._dragging == "tl":
            self._rect = [max(min_x, min(e.x, max_x)), max(min_y, min(e.y, max_y)), x2, y2]
        elif self._dragging == "tr":
            self._rect = [x1, max(min_y, min(e.y, max_y)), max(min_x, min(e.x, max_x)), y2]
        elif self._dragging == "br":
            self._rect = [x1, y1, max(min_x, min(e.x, max_x)), max(min_y, min(e.y, max_y))]
        elif self._dragging == "bl":
            self._rect = [max(min_x, min(e.x, max_x)), y1, x2, max(min_y, min(e.y, max_y))]

        self._drag_start = (e.x, e.y)
        self._redraw_overlay()

    def _release(self, _):
        self._dragging = self._drag_start = None
        if self._on_change:
            self._on_change(self.get_rect_original())


# ═══════════════════════════════════════════════════════════════════════════
# Card helper
# ═══════════════════════════════════════════════════════════════════════════

def make_card(parent, title: str, icon: str = "") -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8,
                        border_width=1, border_color=BORDER_COLOR)
    card.pack(fill="x", padx=10, pady=(0, 10))

    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill="x", padx=12, pady=(10, 4))
    ctk.CTkLabel(header, text=f"{icon}  {title}" if icon else title,
                 font=ctk.CTkFont("Segoe UI", 11, "bold"),
                 text_color=TEXT_MAIN).pack(anchor="w")
    return card


# ═══════════════════════════════════════════════════════════════════════════
# Main Application
# ═══════════════════════════════════════════════════════════════════════════

class DocTypeApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("DocType")
        self.geometry("1300x800")
        self.minsize(1000, 620)
        self.configure(fg_color=BG_MAIN)

        self._records         : list[ImageRecord] = []
        self._sel_idx         : int               = -1
        self._thumb_photos    = []
        self._current_profile : str               = "Clean scan"

        self._settings = load_settings()
        globals().update(apply_theme(self._settings["theme"]))
        self.configure(fg_color=BG_MAIN)
        self._build_menu()
        self._build_layout()
        self._bind_keys()
        self._set_status("Ready  ·  Load documents to begin")
        self.after(1500,self._watch_system_theme)

    def _build_menu(self):
        bar = tk.Menu(self, tearoff=0, bg=BG_PANEL, fg=TEXT_MAIN,
                      activebackground=MAROON, activeforeground="white")
        self.configure(menu=bar)

        def _m(lbl):
            m = tk.Menu(bar, tearoff=0, bg=BG_CARD, fg=TEXT_MAIN,
                        activebackground=MAROON, activeforeground="white")
            bar.add_cascade(label=lbl, menu=m)
            return m

        f = _m("File")
        f.add_command(label="Open Images…",     command=self._load_images, accelerator="Ctrl+O")
        f.add_separator()
        f.add_command(label="Export as PDF…",   command=self._export_pdf,  accelerator="Ctrl+E")
        f.add_command(label="Export as PNGs…",  command=self._export_images)
        f.add_separator()
        f.add_command(label="Print…", command=self._print_current, accelerator="Ctrl+P")
        f.add_command(label="Settings…", command=self._open_settings)
        f.add_command(label="PDF page remover…", command=self._pdf_remover)
        f.add_command(label="Quit",             command=self.quit,         accelerator="Ctrl+Q")

        e = _m("Edit")
        e.add_command(label="Undo",             command=self._undo,        accelerator="Ctrl+Z")
        e.add_command(label="Redo",             command=self._redo,        accelerator="Ctrl+Y")
        e.add_separator()
        e.add_command(label="Manual Crop…",     command=self._manual_crop)
        e.add_command(label="Auto Detect Crop…",command=self._auto_detect)
        e.add_separator()
        e.add_command(label="Remove Page",      command=self._remove_selected, accelerator="Del")

        b = _m("Batch")
        b.add_command(label="Rotate All Pages", command=lambda: self._batch_edit("Rotate"))
        b.add_command(label="Enhance All Pages",command=lambda: self._batch_edit("Enhance"))
        b.add_command(label="Auto Crop All Confident", command=lambda: self._batch_edit("Auto crop"))

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=0, minsize=165)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0, minsize=290)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self._build_left_panel()
        self._build_center()
        self._build_right_panel()
        self._build_statusbar()

    # ── Left Thumbnail Panel ───────────────────────────────────────────────
    def _build_left_panel(self):
        lp = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, width=165,
                          border_width=1, border_color=BORDER_COLOR)
        lp.grid(row=0, column=0, sticky="nsew")
        lp.grid_propagate(False)

        hdr = ctk.CTkFrame(lp, fg_color="transparent", height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Pages",
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=MAROON_DARK).pack(side="left", padx=14, pady=10)

        ctk.CTkButton(hdr, text="+ Add", width=52, height=26,
                      font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      fg_color=MAROON, hover_color=MAROON_HOVER,
                      text_color="white", corner_radius=5,
                      command=self._load_images).pack(side="right", padx=8, pady=10)

        sf = ctk.CTkFrame(lp, fg_color="transparent", corner_radius=0)
        sf.pack(fill="both", expand=True)

        self._thumb_canvas = tk.Canvas(sf, bg=BG_PANEL, highlightthickness=0, width=160)
        vsb = tk.Scrollbar(sf, orient="vertical", command=self._thumb_canvas.yview)
        self._thumb_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._thumb_canvas.pack(side="left", fill="both", expand=True)
        self._thumb_canvas.bind("<MouseWheel>",
            lambda e: self._thumb_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._thumb_inner = tk.Frame(self._thumb_canvas, bg=BG_PANEL)
        self._thumb_canvas.create_window((0, 0), window=self._thumb_inner, anchor="nw")
        self._thumb_inner.bind("<Configure>", lambda e:
            self._thumb_canvas.configure(scrollregion=self._thumb_canvas.bbox("all")))

        self._empty_hint = ctk.CTkLabel(
            sf, text="Click  + Add\nto open images",
            font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT_MUTED, justify="center")
        self._empty_hint.place(relx=0.5, rely=0.45, anchor="center")

    # ── Center Preview ─────────────────────────────────────────────────────
    def _build_center(self):
        center = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        center.grid(row=0, column=1, sticky="nsew", padx=1)
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        tab_bar = ctk.CTkFrame(center, fg_color=BG_PANEL, corner_radius=0, height=44,
                               border_width=1, border_color=BORDER_COLOR)
        tab_bar.grid(row=0, column=0, sticky="ew")
        tab_bar.grid_propagate(False)

        self._tab_var = tk.StringVar(value="preview")
        tab_inner = ctk.CTkFrame(tab_bar, fg_color="transparent")
        tab_inner.pack(side="left", padx=8, pady=6)

        for label, val in [("Preview", "preview"), ("Before / After", "compare"), ("PDF pages", "pdf")]:
            tk.Radiobutton(
                tab_inner, text=label, variable=self._tab_var, value=val,
                command=self._switch_tab, bg=BG_PANEL, fg=TEXT_MAIN,
                selectcolor=BG_CARD, activebackground=BG_CARD,
                activeforeground=MAROON_DARK, indicatoron=False, relief="flat",
                padx=14, pady=5, font=("Segoe UI", 10, "bold"), bd=0
            ).pack(side="left", padx=2)

        self._info_lbl = ctk.CTkLabel(tab_bar, text="",
                                      font=ctk.CTkFont("Consolas", 10),
                                      text_color=TEXT_MUTED)
        self._info_lbl.pack(side="right", padx=16)

        self._frame_single  = ctk.CTkFrame(center, fg_color=BG_MAIN, corner_radius=0)
        self._frame_compare = ctk.CTkFrame(center, fg_color=BG_MAIN, corner_radius=0)

        for f in (self._frame_single, self._frame_compare):
            f.grid(row=1, column=0, sticky="nsew")

        # Single preview
        self._frame_single.grid_rowconfigure(0, weight=1)
        self._frame_single.grid_columnconfigure(0, weight=1)
        self._preview_lbl = tk.Label(self._frame_single, bg="#2A2A2A")
        self._preview_lbl.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        self._dropzone = ctk.CTkFrame(
            self._frame_single, fg_color=BG_CARD, corner_radius=12,
            border_width=2, border_color=BORDER_COLOR, width=320, height=200)
        self._dropzone.place(relx=0.5, rely=0.5, anchor="center")
        self._dropzone.pack_propagate(False)

        ctk.CTkLabel(self._dropzone, text="📄",
                     font=ctk.CTkFont("Segoe UI", 40)).pack(pady=(22, 2))
        ctk.CTkLabel(self._dropzone, text="No images loaded",
                     font=ctk.CTkFont("Segoe UI", 13, "bold"),
                     text_color=TEXT_MAIN).pack()
        ctk.CTkLabel(self._dropzone, text="Click below or press Ctrl+O",
                     font=ctk.CTkFont("Segoe UI", 9),
                     text_color=TEXT_MUTED).pack(pady=(2, 0))
        ctk.CTkButton(self._dropzone, text="Open Images", width=130, height=30,
                      fg_color=MAROON, hover_color=MAROON_HOVER,
                      text_color="white", font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      command=self._load_images).pack(pady=10)

        # Before / After compare
        self._frame_compare.grid_columnconfigure(0, weight=1)
        self._frame_compare.grid_columnconfigure(1, weight=1)
        self._frame_compare.grid_rowconfigure(1, weight=1)

        for col, lbl in enumerate(["ORIGINAL", "ENHANCED"]):
            ctk.CTkLabel(self._frame_compare, text=lbl,
                         font=ctk.CTkFont("Segoe UI", 9, "bold"),
                         text_color=MAROON_DARK).grid(row=0, column=col, pady=(8, 2))

        self._before_lbl = tk.Label(self._frame_compare, bg="#2A2A2A")
        self._after_lbl  = tk.Label(self._frame_compare, bg="#2A2A2A")
        self._before_lbl.grid(row=1, column=0, sticky="nsew", padx=(10, 4), pady=(0, 10))
        self._after_lbl.grid(row=1, column=1, sticky="nsew", padx=(4, 10), pady=(0, 10))

        self._frame_pdf = PdfPagesPanel(center, self._output_folder, lambda: self._settings, self._set_status)
        self._frame_pdf.grid(row=1,column=0,sticky="nsew")
        self._switch_tab()

    # ── Right Controls Sidebar ─────────────────────────────────────────────
    def _build_right_panel(self):
        rp = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, width=290,
                          border_width=1, border_color=BORDER_COLOR)
        rp.grid(row=0, column=2, sticky="nsew")
        rp.grid_propagate(False)

        hdr = ctk.CTkFrame(rp, fg_color="transparent", height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Controls",
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=MAROON_DARK).pack(side="left", padx=14, pady=10)

        sb = ctk.CTkScrollableFrame(rp, fg_color="transparent", corner_radius=0)
        sb.pack(fill="both", expand=True)

        c = make_card(sb, "Tools & Settings", "")
        for label, action in [("Settings / Output folder…", self._open_settings),
                              ("PDF page remover…", self._pdf_remover)]:
            ctk.CTkButton(c, text=label, command=action, fg_color=MAROON,
                          hover_color=MAROON_HOVER).pack(fill="x", padx=10, pady=6)

        # ── Crop Section ──────────────────────────────────────────────────
        c = make_card(sb, "Crop Review", "✂")
        ctk.CTkButton(c, text="Review / Manual Crop…", height=32,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=MAROON_DARK, font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      border_width=1, border_color=BORDER_COLOR,
                      command=self._manual_crop).pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkButton(c, text="Auto Detect Document…", height=32,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=MAROON_DARK, font=ctk.CTkFont("Segoe UI", 10),
                      border_width=1, border_color=BORDER_COLOR,
                      command=self._auto_detect).pack(fill="x", padx=10, pady=(0, 8))

        # ── Enhancement Section ───────────────────────────────────────────
        c = make_card(sb, "Enhancement", "🎨")
        ctk.CTkLabel(c, text="Filter Profile:",
                     font=ctk.CTkFont("Segoe UI", 9, "bold"),
                     text_color=TEXT_MUTED).pack(anchor="w", padx=10, pady=(2, 2))

        self._profile_var = tk.StringVar(value=self._current_profile)
        cb = ctk.CTkComboBox(
            c, values=["Clean scan", "Soft text", "Keep colour", "Original (no filter)"],
            variable=self._profile_var, state="readonly", height=30,
            border_color=BORDER_COLOR, button_color=MAROON,
            dropdown_fg_color=BG_CARD, dropdown_text_color=TEXT_MAIN,
            font=ctk.CTkFont("Segoe UI", 10),
            command=self._on_profile_change,
        )
        cb.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(c, text="Apply Enhancement", height=34,
                      fg_color=MAROON, hover_color=MAROON_HOVER,
                      text_color="white", font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      command=self._apply_current_enhance).pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkButton(c, text="Reset to Original", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=MAROON_DARK, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=self._reset_current_page).pack(fill="x", padx=10, pady=(0, 8))

        # ── Batch Edits ───────────────────────────────────────────────────
        c = make_card(sb, "Batch Actions", "⚡")
        br = ctk.CTkFrame(c, fg_color="transparent")
        br.pack(fill="x", padx=10, pady=(2, 6))
        br.columnconfigure(0, weight=1)
        br.columnconfigure(1, weight=1)

        ctk.CTkButton(br, text="Rotate All", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=lambda: self._batch_edit("Rotate")
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(br, text="Enhance All", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=lambda: self._batch_edit("Enhance")
                      ).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        ctk.CTkButton(c, text="Batch Auto Crop (Confident Only)", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=lambda: self._batch_edit("Auto crop")
                      ).pack(fill="x", padx=10, pady=(0, 8))

        # ── History ───────────────────────────────────────────────────────
        c = make_card(sb, "History", "↩")
        hr = ctk.CTkFrame(c, fg_color="transparent")
        hr.pack(fill="x", padx=10, pady=(2, 8))
        hr.columnconfigure(0, weight=1)
        hr.columnconfigure(1, weight=1)

        ctk.CTkButton(hr, text="⟵ Undo", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=self._undo).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(hr, text="Redo ⟶", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=self._redo).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        # ── Export ────────────────────────────────────────────────────────
        c = make_card(sb, "Export", "📄")
        er = ctk.CTkFrame(c, fg_color="transparent")
        er.pack(fill="x", padx=10, pady=(2, 6))
        er.columnconfigure(0, weight=1)
        er.columnconfigure(1, weight=1)

        self._page_var = tk.StringVar(value=self._settings["page_size"])
        ctk.CTkComboBox(er, values=list(PAGE_SIZES.keys()), variable=self._page_var,
                        state="readonly", width=85, height=28, border_color=BORDER_COLOR,
                        button_color=MAROON, dropdown_fg_color=BG_CARD,
                        font=ctk.CTkFont("Segoe UI", 9)).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self._dpi_var = tk.StringVar(value=self._settings["dpi"])
        ctk.CTkComboBox(er, values=["72", "96", "150", "200", "300"], variable=self._dpi_var,
                        state="readonly", width=75, height=28, border_color=BORDER_COLOR,
                        button_color=MAROON, dropdown_fg_color=BG_CARD,
                        font=ctk.CTkFont("Segoe UI", 9)).grid(row=0, column=1, sticky="ew")

        ctk.CTkButton(c, text="Export Combined PDF…", height=34,
                      fg_color=MAROON, hover_color=MAROON_HOVER,
                      text_color="white", font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      command=self._export_pdf).pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkButton(c, text="Export Separate PDFs…", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=MAROON_DARK, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=self._export_separate_pdfs).pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkButton(c, text="Export PNGs…", height=28,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=MAROON_DARK, font=ctk.CTkFont("Segoe UI", 9),
                      border_width=1, border_color=BORDER_COLOR,
                      command=self._export_images).pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(c,text="Print enhanced pages…",height=30,fg_color=MAROON,
            hover_color=MAROON_HOVER,command=self._print_current).pack(fill="x",padx=10,pady=(0,10))

    # ── Status Bar ─────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=28,
                           border_width=1, border_color=BORDER_COLOR)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        bar.grid_propagate(False)

        self._status_var = tk.StringVar()
        ctk.CTkLabel(bar, textvariable=self._status_var, font=ctk.CTkFont("Segoe UI", 9),
                     text_color=TEXT_MUTED, anchor="w").pack(side="left", padx=14)

        self._count_lbl = ctk.CTkLabel(bar, text="0 pages", font=ctk.CTkFont("Segoe UI", 9),
                                       text_color=TEXT_MUTED)
        self._count_lbl.pack(side="right", padx=14)

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    # ── Tab Control ────────────────────────────────────────────────────────
    def _switch_tab(self):
        val = self._tab_var.get()
        if val == "pdf":
            self._frame_pdf.tkraise()
            return
        if val == "preview":
            self._frame_single.tkraise()
            self._refresh_preview()
        else:
            self._frame_compare.tkraise()
            self._refresh_before_after()

    # ── Thumbnails ─────────────────────────────────────────────────────────
    def _rebuild_thumbs(self):
        for w in self._thumb_inner.winfo_children():
            w.destroy()
        self._thumb_photos.clear()

        if self._records:
            self._empty_hint.place_forget()
        else:
            self._empty_hint.place(relx=0.5, rely=0.45, anchor="center")

        for i, rec in enumerate(self._records):
            thumb = rec.graded.copy()
            thumb.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            self._thumb_photos.append(photo)

            sel = (i == self._sel_idx)
            bg_color = MAROON if sel else BG_CARD
            text_col = "white" if sel else TEXT_MAIN
            sub_col  = "#F2D5DA" if sel else TEXT_MUTED

            card = tk.Frame(self._thumb_inner, bg=bg_color, cursor="hand2",
                            bd=1, relief="solid")
            card.pack(fill="x", pady=2, padx=4)

            img_lbl = tk.Label(card, image=photo, bg=bg_color)
            img_lbl.pack(pady=(6, 2))

            name_lbl = tk.Label(card, text=rec.display_name, bg=bg_color,
                                fg=text_col, font=("Segoe UI", 8, "bold"), wraplength=130)
            name_lbl.pack()

            dim_lbl = tk.Label(card, text=rec.info_str, bg=bg_color,
                               fg=sub_col, font=("Segoe UI", 7))
            dim_lbl.pack(pady=(0, 6))

            for w in (card, img_lbl, name_lbl, dim_lbl):
                w.bind("<Button-1>", lambda e, idx=i: self._select_image(idx))

        n = len(self._records)
        self._count_lbl.configure(text=f"{n} page{'s' if n != 1 else ''}")

    def _select_image(self, idx: int):
        if 0 <= idx < len(self._records):
            self._sel_idx = idx
            self._dropzone.place_forget()
            self._rebuild_thumbs()
            self._refresh_preview()
            self._refresh_before_after()
            rec = self._records[idx]
            self._info_lbl.configure(text=rec.info_str)
            self._set_status(f"Page {idx+1}/{len(self._records)}: {rec.display_name}")

    def _refresh_preview(self):
        if self._sel_idx < 0:
            return
        rec = self._records[self._sel_idx]
        cw = max(self._preview_lbl.winfo_width(), 200)
        ch = max(self._preview_lbl.winfo_height(), 200)
        preview = resize_for_preview(rec.graded, max(cw, ch, 1))
        self._main_photo = ImageTk.PhotoImage(preview)
        self._preview_lbl.configure(image=self._main_photo)

    def _refresh_before_after(self):
        if self._sel_idx < 0:
            return
        rec = self._records[self._sel_idx]
        fw = max(self._frame_compare.winfo_width(), 200)
        fh = max(self._frame_compare.winfo_height(), 200)
        half = max(100, fw // 2 - 24)

        before = resize_for_preview(rec.cropped, min(half, fh - 50))
        after  = resize_for_preview(rec.graded,  min(half, fh - 50))

        self._before_photo = ImageTk.PhotoImage(before)
        self._after_photo  = ImageTk.PhotoImage(after)
        self._before_lbl.configure(image=self._before_photo)
        self._after_lbl.configure(image=self._after_photo)

    # ── File Loading ───────────────────────────────────────────────────────
    def _load_images(self):
        paths = filedialog.askopenfilenames(
            title="Open Document Images",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp"),
                       ("All Files", "*.*")],
        )
        if not paths:
            return
        loaded = 0
        for p in paths:
            try:
                img = Image.open(p).convert("RGB")
                rec = ImageRecord(p, img)
                rec.graded = apply_color_grade(rec.cropped, profile=self._current_profile)
                self._records.append(rec)
                loaded += 1
            except Exception as ex:
                messagebox.showerror("Error", f"Failed to open {p}:\n{ex}")

        if loaded:
            self._select_image(len(self._records) - loaded)
            self._set_status(f"Loaded {loaded} images.")

    # ── Crop Dialog ────────────────────────────────────────────────────────
    def _open_crop_dialog(self, initial_rect=None):
        if self._sel_idx < 0:
            return None, None
        rec = self._records[self._sel_idx]

        dialog = ctk.CTkToplevel(self)
        dialog.title("Crop Review")
        dialog.geometry("800x650")
        dialog.minsize(600, 480)
        dialog.configure(fg_color=BG_MAIN)
        dialog.transient(self)

        top_bar = ctk.CTkFrame(dialog, fg_color=BG_PANEL, height=44, corner_radius=0)
        top_bar.pack(fill="x")
        ctk.CTkLabel(top_bar, text="Adjust crop boundary then click 'Apply crop'",
                     font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT_MUTED).pack(side="left", padx=14, pady=10)

        canvas = CropCanvas(dialog)
        canvas.pack(fill="both", expand=True, padx=10, pady=10)
        canvas.set_image(rec.cropped)

        if initial_rect is not None:
            iw, ih = rec.cropped.size
            canvas.set_rect_normalized(
                initial_rect[0] / iw, initial_rect[1] / ih,
                initial_rect[2] / iw, initial_rect[3] / ih
            )

        btn_bar = ctk.CTkFrame(dialog, fg_color=BG_PANEL, height=50, corner_radius=0)
        btn_bar.pack(fill="x", side="bottom")

        def _apply():
            crop = canvas.get_rect_original()
            if crop:
                rec.push_history()
                rec.cropped = rec.cropped.crop(crop)
                rec.graded  = apply_color_grade(rec.cropped, profile=self._current_profile)
                dialog.destroy()
                self._select_image(self._sel_idx)
                self._set_status(f"Cropped to {rec.info_str}")

        def _cancel():
            dialog.destroy()

        ctk.CTkButton(btn_bar, text="Cancel", width=90, height=32,
                      fg_color=BUTTON_ALT, hover_color=BUTTON_ALT_HOV,
                      text_color=TEXT_MAIN, font=ctk.CTkFont("Segoe UI", 10),
                      border_width=1, border_color=BORDER_COLOR,
                      command=_cancel).pack(side="right", padx=(4, 14), pady=9)

        ctk.CTkButton(btn_bar, text="Apply crop", width=110, height=32,
                      fg_color=MAROON, hover_color=MAROON_HOVER,
                      text_color="white", font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      command=_apply).pack(side="right", padx=4, pady=9)

        dialog.update()
        return dialog, canvas

    def _manual_crop(self):
        if self._sel_idx < 0:
            self._set_status("Select an image first.")
            return
        rec = self._records[self._sel_idx]
        return self._open_crop_dialog(initial_rect=(0, 0, rec.cropped.width, rec.cropped.height))

    def _auto_detect(self):
        if self._sel_idx < 0:
            self._set_status("Select an image first.")
            return
        rec = self._records[self._sel_idx]
        self._set_status("Detecting document boundary…")
        self.update_idletasks()

        warped, quad = detect_document(rec.original)
        if quad is not None:
            xs = quad[:, 0]
            ys = quad[:, 1]
            x1, y1 = max(0, int(xs.min())), max(0, int(ys.min()))
            x2, y2 = min(rec.cropped.width, int(xs.max())), min(rec.cropped.height, int(ys.max()))
            rect = (x1, y1, x2, y2)
        else:
            rect = (0, 0, rec.cropped.width, rec.cropped.height)

        return self._open_crop_dialog(initial_rect=rect)

    # ── Enhancement ────────────────────────────────────────────────────────
    def _on_profile_change(self, choice):
        self._current_profile = choice
        self._apply_current_enhance()

    def _apply_current_enhance(self):
        if self._sel_idx < 0:
            return
        rec = self._records[self._sel_idx]
        rec.push_history()
        rec.graded = apply_color_grade(rec.cropped, profile=self._current_profile)
        self._rebuild_thumbs()
        self._refresh_preview()
        self._refresh_before_after()
        self._set_status(f"Applied profile: {self._current_profile}")

    def _reset_current_page(self):
        if self._sel_idx < 0:
            return
        rec = self._records[self._sel_idx]
        rec.push_history()
        rec.cropped = rec.original.copy()
        rec.graded  = rec.original.copy()
        self._rebuild_thumbs()
        self._refresh_preview()
        self._refresh_before_after()
        self._set_status("Reset page to original.")

    # ── Batch Edits ────────────────────────────────────────────────────────
    def _batch_edit(self, action: str):
        if not self._records:
            return
        if action == "Rotate":
            for r in self._records:
                r.push_history()
                r.cropped = r.cropped.transpose(Image.Transpose.ROTATE_270)
                r.graded  = apply_color_grade(r.cropped, profile=self._current_profile)
            self._rebuild_thumbs()
            self._refresh_preview()
            self._refresh_before_after()
            self._set_status("Rotated all pages 90°.")
        elif action == "Enhance":
            for r in self._records:
                r.push_history()
                r.graded = apply_color_grade(r.cropped, profile=self._current_profile)
            self._rebuild_thumbs()
            self._refresh_preview()
            self._refresh_before_after()
            self._set_status(f"Enhanced all pages with '{self._current_profile}'.")
        elif action == "Auto crop":
            count = 0
            for r in self._records:
                warped, quad = detect_document(r.original)
                if quad is not None:
                    r.push_history()
                    xs, ys = quad[:, 0], quad[:, 1]
                    x1, y1 = max(0, int(xs.min())), max(0, int(ys.min()))
                    x2, y2 = min(r.original.width, int(xs.max())), min(r.original.height, int(ys.max()))
                    r.cropped = r.original.crop((x1, y1, x2, y2))
                    r.graded  = apply_color_grade(r.cropped, profile=self._current_profile)
                    count += 1
            self._rebuild_thumbs()
            self._refresh_preview()
            self._refresh_before_after()
            self._set_status(f"Auto-cropped {count} confident pages.")

    # ── Undo / Redo / Remove ───────────────────────────────────────────────
    def _undo(self):
        if self._sel_idx < 0:
            return
        if self._records[self._sel_idx].undo():
            self._rebuild_thumbs()
            self._refresh_preview()
            self._refresh_before_after()
            self._set_status("Undo.")

    def _redo(self):
        if self._sel_idx < 0:
            return
        if self._records[self._sel_idx].redo():
            self._rebuild_thumbs()
            self._refresh_preview()
            self._refresh_before_after()
            self._set_status("Redo.")

    def _remove_selected(self):
        if self._sel_idx < 0:
            return
        self._records.pop(self._sel_idx)
        self._sel_idx = min(self._sel_idx, len(self._records) - 1)
        if self._sel_idx >= 0:
            self._select_image(self._sel_idx)
        else:
            self._preview_lbl.configure(image="")
            self._before_lbl.configure(image="")
            self._after_lbl.configure(image="")
            self._dropzone.place(relx=0.5, rely=0.5, anchor="center")
            self._info_lbl.configure(text="")
        self._rebuild_thumbs()
        self._set_status("Page removed.")

    # ── Export ─────────────────────────────────────────────────────────────
    def _output_folder(self):
        folder = self._settings["output_dir"]
        if folder:
            if os.path.isdir(folder): return folder
            messagebox.showerror("Output folder unavailable", "The saved folder is unavailable. Change it in Settings.")
            return None
        folder = filedialog.askdirectory(title="Choose output folder (remembered for all exports)")
        if folder:
            try:
                updated = dict(self._settings, output_dir=folder)
                save_settings(updated)
                self._settings = updated
            except OSError as ex:
                messagebox.showerror("Settings", f"Could not save output folder: {ex}")
                return None
        return folder

    def _watch_system_theme(self):
        from theme import DARK, LIGHT
        expected=DARK if ctk.get_appearance_mode()=="Dark" else LIGHT
        if self._settings['theme']=="System" and BG_MAIN!=expected['BG_MAIN'] and not self.grab_current():
            self._apply_appearance()
        self.after(1500,self._watch_system_theme)

    def _apply_appearance(self):
        # Rebuild theme-dependent native Tk widgets too, retaining editing state.
        tab=self._tab_var.get()
        page,dpi=self._page_var.get(),self._dpi_var.get()
        pdf_path=self._frame_pdf.path
        selected=set(self._frame_pdf.selected)
        save_removed=self._frame_pdf.save_removed.get()
        self._frame_pdf._close_renderer()
        globals().update(apply_theme(self._settings['theme']))
        for widget in self.winfo_children(): widget.destroy()
        self.configure(fg_color=BG_MAIN)
        self._build_menu()
        self._build_layout()
        self.update_idletasks()
        if self._sel_idx>=0:self._select_image(self._sel_idx)
        self._page_var.set(page);self._dpi_var.set(dpi)
        self._tab_var.set(tab);self._switch_tab()
        if pdf_path:
            try:
                self._frame_pdf.load(pdf_path)
                self._frame_pdf.restore_selection=selected
                self._frame_pdf.save_removed.set(save_removed)
            except Exception as ex:messagebox.showerror("PDF preview",str(ex))

    def _open_settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("600x540")
        dialog.configure(fg_color=BG_MAIN)
        dialog.transient(self)
        appearance=tk.StringVar(value=self._settings['theme'])
        ctk.CTkLabel(dialog,text="Appearance").pack(pady=(12,4))
        ctk.CTkSegmentedButton(dialog,values=["Light","Dark","System"],variable=appearance,
            selected_color=MAROON,selected_hover_color=MAROON_HOVER).pack()
        folder = tk.StringVar(value=self._settings["output_dir"])
        ctk.CTkLabel(dialog,text="Saved output folder",text_color=TEXT_MAIN).pack(pady=(18,4))
        ctk.CTkEntry(dialog,textvariable=folder,width=510).pack(padx=20)
        def browse():
            chosen=filedialog.askdirectory(parent=dialog,title="Choose saved output folder")
            if chosen: folder.set(chosen)
        ctk.CTkButton(dialog,text="Browse…",command=browse,fg_color=MAROON).pack(pady=8)
        ctk.CTkLabel(dialog,text="All exports and edited PDFs use this folder.\nLeave blank to choose and remember a folder on the next export.",text_color=TEXT_MUTED).pack()
        page=tk.StringVar(value=self._page_var.get())
        dpi=tk.StringVar(value=self._dpi_var.get())
        for label,var,values in [("Default PDF page size",page,list(PAGE_SIZES)),("Default image export DPI",dpi,["72","96","150","200","300"])]:
            row=ctk.CTkFrame(dialog,fg_color="transparent"); row.pack(fill="x",padx=24,pady=6)
            ctk.CTkLabel(row,text=label).pack(side="left")
            ctk.CTkOptionMenu(row,variable=var,values=values,fg_color=MAROON).pack(side="right")
        removed=tk.BooleanVar(value=self._settings['save_removed'])
        ctk.CTkCheckBox(dialog,text="Also save removed PDF pages by default",variable=removed,fg_color=MAROON).pack(pady=8)
        def save():
            value=folder.get().strip()
            if value and not os.path.isdir(value):
                messagebox.showerror("Settings","Choose an existing output folder.",parent=dialog); return
            updated=dict(output_dir=os.path.abspath(value) if value else "",page_size=page.get(),dpi=dpi.get(),save_removed=removed.get(),theme=appearance.get())
            try: save_settings(updated)
            except OSError as ex:
                messagebox.showerror("Settings",str(ex),parent=dialog); return
            self._settings=updated
            self._frame_pdf.save_removed.set(removed.get())
            self._page_var.set(page.get()); self._dpi_var.set(dpi.get())
            dialog.destroy()
            self._apply_appearance()
            self._set_status("Settings saved.")
        ctk.CTkButton(dialog,text="Save settings",command=save,fg_color=MAROON).pack(pady=8)
        dialog.grab_set()

    def _pdf_remover(self):
        self._tab_var.set("pdf")
        self._switch_tab()

    def _print_current(self):
        if self._tab_var.get()=="pdf":
            self._frame_pdf.print_document()
            return
        if not self._records:
            messagebox.showwarning("Print","Add images to print first.");return
        try:
            pages=[r.graded for r in self._records]
            self.update_idletasks()
            sent=preview_and_print(self,len(pages),lambda i:pages[i],"DocType — enhanced pages")
            self._set_status("Print job sent to Windows." if sent else "Printing cancelled.")
        except Exception as ex:messagebox.showerror("Print",str(ex))

    def _export_pdf(self):
        if not self._records:
            messagebox.showwarning("Export", "No pages to export.")
            return
        folder = self._output_folder()
        if not folder: return
        path = str(unique_path(folder, "document.pdf"))
        try:
            dpi = int(self._dpi_var.get())
            ps  = self._page_var.get()
            export_pdf([r.graded for r in self._records], path, page_size=ps, dpi=dpi)
            self._set_status(f"Exported PDF: {os.path.basename(path)}")
            messagebox.showinfo("Export Complete", f"PDF exported successfully:\n{path}")
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex))

    def _export_separate_pdfs(self):
        if not self._records:
            messagebox.showwarning("Export", "No pages to export.")
            return
        folder = self._output_folder()
        if not folder:
            return
        try:
            dpi = int(self._dpi_var.get())
            ps  = self._page_var.get()
            for i, r in enumerate(self._records, start=1):
                stem = os.path.splitext(r.display_name)[0]
                p = os.path.join(folder, f"{stem}_page_{i}.pdf")
                suffix = 2
                while os.path.exists(p):
                    p = os.path.join(folder, f"{stem}_page_{i}_{suffix}.pdf")
                    suffix += 1
                export_pdf([r.graded], p, page_size=ps, dpi=dpi)
            self._set_status(f"Exported {len(self._records)} separate PDFs.")
            messagebox.showinfo("Export Complete", f"Exported {len(self._records)} PDFs to:\n{folder}")
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex))

    def _export_images(self):
        if not self._records:
            messagebox.showwarning("Export", "No pages to export.")
            return
        folder = self._output_folder()
        if not folder:
            return
        try:
            dpi   = int(self._dpi_var.get())
            paths = export_images([r.graded for r in self._records], output_dir=folder, fmt="PNG", dpi=dpi)
            self._set_status(f"Exported {len(paths)} PNGs.")
            messagebox.showinfo("Export Complete", f"Exported {len(paths)} PNGs to:\n{folder}")
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex))

    def _bind_keys(self):
        self.bind_all("<Control-p>",lambda e:self._print_current())
        self.bind_all("<Control-o>", lambda e: self._frame_pdf.choose() if self._tab_var.get() == "pdf" else self._load_images())
        self.bind_all("<Control-e>", lambda e: self._frame_pdf.save() if self._tab_var.get() == "pdf" else self._export_pdf())
        self.bind_all("<Control-q>", lambda e: self.quit())
        self.bind_all("<Control-z>", lambda e: self._undo())
        self.bind_all("<Control-y>", lambda e: self._redo())
        self.bind_all("<Delete>",    lambda e: None if self._tab_var.get() == "pdf" else self._remove_selected())


# ═══════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = DocTypeApp()
    app.mainloop()
