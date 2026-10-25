"""
image_processor.py
------------------
Core image processing engine (no GUI dependencies).

Handles:
  - Automatic document detection via Canny + contour + perspective transform
  - Document scan enhancement (photocopy/scanner look)
  - PDF export via img2pdf / Pillow fallback
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance
import img2pdf
import os
import io
from typing import Optional, Tuple, List


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def pil_to_cv(pil_img: Image.Image) -> np.ndarray:
    """Convert a PIL Image (RGB) → OpenCV ndarray (BGR)."""
    return cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)


def cv_to_pil(cv_img: np.ndarray) -> Image.Image:
    """Convert an OpenCV ndarray (BGR or gray) → PIL Image (RGB)."""
    if cv_img.ndim == 2:
        return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGB))
    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))


def resize_for_preview(img: Image.Image, max_side: int = 900) -> Image.Image:
    """Downscale *img* so the longest side ≤ *max_side* (preserves aspect)."""
    w, h = img.size
    ratio = min(max_side / w, max_side / h, 1.0)
    if ratio < 1.0:
        return img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    return img.copy()


# ---------------------------------------------------------------------------
# Automatic document / paper detection
# ---------------------------------------------------------------------------

def _order_points(pts: np.ndarray) -> np.ndarray:
    """
    Return (top-left, top-right, bottom-right, bottom-left) ordering
    for a quadrilateral given as 4 (x, y) pairs.
    """
    rect = np.zeros((4, 2), dtype="float32")
    s    = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]    # top-left  has smallest sum
    rect[2] = pts[np.argmax(s)]    # bot-right has largest  sum
    diff     = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # top-right has smallest diff
    rect[3] = pts[np.argmax(diff)] # bot-left  has largest  diff
    return rect


def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Warp *image* so the quadrilateral *pts* fills a rectangular output."""
    rect = _order_points(pts)
    tl, tr, br, bl = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w   = max(int(width_a), int(width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h    = max(int(height_a), int(height_b))

    dst = np.array([
        [0,         0        ],
        [max_w - 1, 0        ],
        [max_w - 1, max_h - 1],
        [0,         max_h - 1],
    ], dtype="float32")

    M      = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (max_w, max_h))
    return warped


def detect_document(
    pil_img: Image.Image,
) -> Tuple[Optional[Image.Image], Optional[np.ndarray]]:
    """
    Detect the largest document/paper quad in *pil_img* and return a
    perspective-corrected crop.

    Returns
    -------
    (warped_pil, quad_pts)
      warped_pil : PIL Image (perspective-corrected)  or None on failure
      quad_pts   : (4, 2) float32 array in original image coords  or None
    """
    orig = pil_to_cv(pil_img)
    h, w = orig.shape[:2]
    scale = min(1.0, 1200.0 / max(h, w))
    small = cv2.resize(orig, (max(1, round(w * scale)), max(1, round(h * scale))))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    threshold, paper = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edges = cv2.Canny(blurred, 30, 100)
    kernel = np.ones((5, 5), np.uint8)
    masks = [cv2.morphologyEx(paper, cv2.MORPH_CLOSE, kernel),
             cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)]
    # Different exposures can split the paper at Otsu's threshold. Try nearby
    # levels too, then require evidence along the actual outer edges.
    for factor in (0.8, 1.15):
        _, mask = cv2.threshold(blurred, min(250, threshold*factor), 255, cv2.THRESH_BINARY)
        masks.append(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel))
    for low, high in ((10,90),(25,75),(5,95)):
        level = (float(np.percentile(blurred,low)) + float(np.percentile(blurred,high))) / 2
        _, mask = cv2.threshold(blurred,level,255,cv2.THRESH_BINARY)
        masks.append(cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel))
    sh, sw = gray.shape
    candidates = []
    for mask in masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
            hull = cv2.convexHull(contour)
            for epsilon in (0.015, 0.025, 0.04):
                quad = cv2.approxPolyDP(hull, epsilon * cv2.arcLength(hull, True), True)
                if len(quad) != 4 or not cv2.isContourConvex(quad):
                    continue
                area = cv2.contourArea(quad) / (sw * sh)
                if not 0.12 < area < 0.995:
                    continue
                # A paper boundary must separate lighter paper from its surroundings.
                inside = np.zeros_like(gray)
                cv2.fillConvexPoly(inside, quad, 255)
                inner = cv2.erode(inside, np.ones((13, 13), np.uint8))
                outer = cv2.dilate(inside, np.ones((13, 13), np.uint8))
                inner_ring = (inside > 0) & (inner == 0)
                outer_ring = (outer > 0) & (inside == 0)
                if outer_ring.sum() < 30:
                    continue
                contrast = float(np.median(gray[inner_ring])) - float(np.median(gray[outer_ring]))
                if contrast < 6:
                    continue
                # Reject an internal table: its outside is still the same paper.
                points = quad.reshape(4,2).astype(float)
                center = points.mean(axis=0)
                supported = 0
                for a,b in zip(points, np.roll(points,-1,axis=0)):
                    mid = (a+b)/2
                    inward = center-mid
                    inward /= max(np.linalg.norm(inward),1)
                    positions = a[None,:] + np.linspace(.15,.85,20)[:,None]*(b-a)
                    inner_pts = np.rint(positions+inward*8).astype(int)
                    outer_pts = np.rint(positions-inward*8).astype(int)
                    valid = ((outer_pts[:,0]>=0)&(outer_pts[:,0]<sw)&
                             (outer_pts[:,1]>=0)&(outer_pts[:,1]<sh))
                    if valid.sum()<8:
                        continue
                    ip,op = inner_pts[valid],outer_pts[valid]
                    ip[:,0]=np.clip(ip[:,0],0,sw-1)
                    ip[:,1]=np.clip(ip[:,1],0,sh-1)
                    delta = np.median(gray[ip[:,1],ip[:,0]].astype(float)-gray[op[:,1],op[:,0]])
                    supported += delta > 6
                if supported < 3:
                    continue
                candidates.append((area + min(contrast, 100) / 300, quad))
    if not candidates:
        # No trustworthy boundary: preserve the full page, never crop to a table.
        return None, None
    quad = max(candidates, key=lambda item: item[0])[1].reshape(4, 2).astype(np.float32)
    # Preserve a small safety margin for marks near the paper edge.
    center = quad.mean(axis=0)
    quad = center + (quad - center) * 1.008
    quad[:, 0] = np.clip(quad[:, 0] / scale, 0, w - 1)
    quad[:, 1] = np.clip(quad[:, 1] / scale, 0, h - 1)
    return cv_to_pil(four_point_transform(orig, quad)), quad


# ---------------------------------------------------------------------------
# Document scan / photocopy enhancement
# ---------------------------------------------------------------------------

def _build_gamma_lut(gamma: float) -> np.ndarray:
    """Pre-compute a 256-entry uint8 LUT for gamma correction."""
    table = np.array(
        [((i / 255.0) ** gamma) * 255 for i in range(256)],
        dtype=np.uint8,
    )
    return table


def _estimate_background(gray: np.ndarray, kernel_size: int = 25) -> np.ndarray:
    """
    Estimate the illumination / paper background using morphological dilation.

    A large dilation kernel "fills in" dark text pixels with the surrounding
    bright background value, producing a smooth background map.

    Parameters
    ----------
    gray        : uint8 single-channel image.
    kernel_size : Size of the rectangular dilation kernel.  Use larger values
                  for images with coarser lighting gradients.

    Returns
    -------
    Smoothed background image (uint8, same size as *gray*).
    """
    ks     = kernel_size | 1            # ensure odd
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ks, ks))
    # Closing fills dark strokes without spreading bright paper into shadows.
    # A dilation followed by a wide blur produced grey fringes around dense text.
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    bg = cv2.GaussianBlur(closed, (5, 5), 0)
    return bg


def apply_color_grade(
    src_pil: Image.Image,
    ref_pil: Optional[Image.Image] = None,   # kept for API compatibility
    intensity: float = 1.0,
    apply_clahe: bool = False,
    # Fine-tune knobs exposed in the UI
    bg_kernel: int = 25,          # background-estimation kernel size
    black_point: float = 2.0,     # percentile to clip as black (0–10)
    white_point: float = 98.0,    # percentile to clip as white (90–100)
    gamma: float = 1.15,          # > 1 darkens mid-tones; 1 = linear
    desaturate: float = 1.0,      # 1.0 = fully grayscale, 0 = keep color
    profile: str = "Clean scan",
) -> Image.Image:
    """
    Transform *src_pil* into a clean document-scan look:

    Pipeline
    --------
    1. Convert to grayscale (weighted luminance).
    2. Estimate the paper background via morphological dilation + blur.
    3. Divide the image by the background map → removes uneven lighting,
       makes the paper pure white.
    4. Stretch the histogram so the darkest pixels clip to black and the
       brightest to white.
    5. Apply gamma correction to push mid-tones darker (crisper text).
    6. Apply CLAHE for local contrast if requested.
    7. Reconstruct an RGB image.
    8. Blend the result with the original using *intensity*.

    Parameters
    ----------
    src_pil     : Source PIL image.
    ref_pil     : Unused (kept for backward compatibility).
    intensity   : 0.0 = no change, 1.0 = full scan effect.
    apply_clahe : Enable local contrast enhancement.
    bg_kernel   : Dilation kernel size for background estimation.
    black_point : Lower histogram clip percentile.
    white_point : Upper histogram clip percentile.
    gamma       : Gamma value (<1 lightens, >1 darkens mid-tones).
    desaturate  : 1.0 = full grayscale output, 0.0 = keep original color.

    Returns
    -------
    Enhanced PIL Image (RGB).
    """
    if profile == "Original (no filter)":
        return src_pil.convert("RGB").copy()
    src_rgb  = np.array(src_pil.convert("RGB"))
    original = src_rgb.astype(np.float32)

    # ── Step 1: Weighted grayscale ────────────────────────────────────────
    gray = (0.299 * src_rgb[:, :, 0].astype(np.float32)
            + 0.587 * src_rgb[:, :, 1].astype(np.float32)
            + 0.114 * src_rgb[:, :, 2].astype(np.float32)).astype(np.uint8)

    # ── Step 2: Background estimation ────────────────────────────────────
    # Scale the background window with resolution; text must not enter the lighting map.
    work_scale = min(1.0, 1400.0 / max(gray.shape))
    work = cv2.resize(gray, None, fx=work_scale, fy=work_scale) if work_scale < 1 else gray
    kernel = max(9, int(bg_kernel * min(work.shape) / 750)) | 1
    bg = _estimate_background(work, kernel_size=kernel)
    bg = cv2.resize(bg, (gray.shape[1], gray.shape[0]))
    bg_f  = bg.astype(np.float32)
    gray_f = gray.astype(np.float32)

    # ── Step 3: Normalize by background → white paper ────────────────────
    # Dividing by bg makes the local background ≈ 1.0 → ≈ 255 after scaling
    normalized = np.clip((gray_f / np.maximum(bg_f, 1.0)) * 255.0, 0, 255).astype(np.uint8)

    # ── Step 4: Histogram stretch ─────────────────────────────────────────
    p_lo = min(float(np.percentile(normalized, black_point)), 100.0)
    # Map near-paper tones to white before they can become grey halos.
    # The soft preset keeps more low-contrast pencil detail.
    paper_ceiling = 247.0 if gamma < 1.0 else 237.0
    p_hi = min(max(float(np.percentile(normalized, white_point)), 220.0), paper_ceiling)
    span = max(p_hi - p_lo, 1.0)
    stretched = np.clip((normalized.astype(np.float32) - p_lo) / span * 255.0,
                        0, 255).astype(np.uint8)

    # ── Step 5: Gamma correction (darken mid-tones) ───────────────────────
    tone = stretched.astype(np.float32) / 255.0
    if gamma >= 1.0:
        # Smooth contrast curve: crisp ink and white paper, with antialiased edges.
        tone = tone * tone * (3.0 - 2.0 * tone)
    sharpened = np.clip(255.0 * np.power(tone, gamma), 0, 255).astype(np.uint8)

    # ── Step 6: CLAHE for local contrast ──────────────────────────────────
    if apply_clahe:
        clahe     = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        sharpened = clahe.apply(sharpened)
    # Remove residual paper texture without thresholding away light pencil strokes.
    sharpened = np.clip(sharpened.astype(np.float32) * (255.0 / 248.0), 0, 255).astype(np.uint8)

    # ── Step 7: Reconstruct RGB ───────────────────────────────────────────
    # Full grayscale → stack into three identical channels
    scan_rgb = np.stack([sharpened, sharpened, sharpened], axis=2).astype(np.float32)

    # Blend grayscale scan with a version that keeps the original color
    # (desaturate=1.0 → pure gray; desaturate=0.0 → keep original hue)
    if desaturate < 1.0:
        # Scale original color channels by the same brightness ratio
        gray_ratio = sharpened.astype(np.float32) / np.maximum(
            gray.astype(np.float32), 1.0
        )
        colored = np.stack([
            np.clip(src_rgb[:, :, ch].astype(np.float32) * gray_ratio, 0, 255)
            for ch in range(3)
        ], axis=2)
        scan_rgb = desaturate * scan_rgb + (1.0 - desaturate) * colored

    # ── Step 8: Blend with original using intensity slider ────────────────
    result = (intensity * scan_rgb + (1.0 - intensity) * original)
    result = result.clip(0, 255).astype(np.uint8)

    return Image.fromarray(result, "RGB")


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

PAGE_SIZES = {
    "A4":     (595, 842),   # pts at 72 dpi
    "Letter": (612, 792),
    "A3":     (842, 1191),
    "Auto":   None,
}


def export_pdf(
    images: List[Image.Image],
    output_path: str,
    page_size: str = "A4",
    dpi: int = 150,
) -> None:
    """
    Save *images* as a multi-page PDF to *output_path*.

    Parameters
    ----------
    images      : List of PIL Images (RGB).
    output_path : Destination .pdf file path.
    page_size   : One of 'A4', 'Letter', 'A3', 'Auto'.
    dpi         : Resolution for the output pages.
    """
    if not images:
        raise ValueError("Add at least one image before exporting.")
    if dpi <= 0:
        raise ValueError("DPI must be positive.")
    jpeg_buffers = []
    for img in images:
        if img.mode != "RGB":
            img = img.convert("RGB")
        if page_size != "Auto" and page_size in PAGE_SIZES:
            pt_w, pt_h = PAGE_SIZES[page_size]
            px_w = int(pt_w / 72.0 * dpi)
            px_h = int(pt_h / 72.0 * dpi)
            img  = _fit_image_to_page(img, px_w, px_h)

        buf = io.BytesIO()
        img.save(buf, format="PNG", dpi=(dpi, dpi))
        jpeg_buffers.append(buf.getvalue())

    try:
        if page_size != "Auto" and page_size in PAGE_SIZES:
            pt_w, pt_h = PAGE_SIZES[page_size]
            layout     = img2pdf.get_layout_fun(
                (img2pdf.mm_to_pt(pt_w * 25.4 / 72),
                 img2pdf.mm_to_pt(pt_h * 25.4 / 72))
            )
            pdf_bytes = img2pdf.convert(jpeg_buffers, layout_fun=layout)
        else:
            pdf_bytes = img2pdf.convert(jpeg_buffers)

        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    except Exception:
        pil_images = [Image.open(io.BytesIO(b)) for b in jpeg_buffers]
        first = pil_images[0]
        rest  = pil_images[1:] if len(pil_images) > 1 else []
        first.save(
            output_path,
            format="PDF",
            save_all=True,
            append_images=rest,
            resolution=dpi,
        )


def _fit_image_to_page(img: Image.Image, page_w: int, page_h: int) -> Image.Image:
    """
    Resize *img* to fit inside (page_w × page_h) with white padding.
    Fills the page as far as the aspect ratio allows.
    """
    w, h    = img.size
    scale   = min(page_w / w, page_h / h)
    new_w   = int(w * scale)
    new_h   = int(h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas  = Image.new("RGB", (page_w, page_h), (255, 255, 255))
    canvas.paste(resized, ((page_w - new_w) // 2, (page_h - new_h) // 2))
    return canvas


def export_images(
    images: List[Image.Image],
    output_dir: str,
    fmt: str = "PNG",
    base_name: str = "output",
    dpi: int = 150,
) -> List[str]:
    """
    Save each image as an individual file.  Returns list of saved paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    ext   = fmt.lower()
    paths = []
    for i, img in enumerate(images, start=1):
        if img.mode != "RGB":
            img = img.convert("RGB")
        fpath = os.path.join(output_dir, f"{base_name}_{i:03d}.{ext}")
        suffix = 2
        while os.path.exists(fpath):
            fpath = os.path.join(output_dir, f"{base_name}_{i:03d}_{suffix}.{ext}")
            suffix += 1
        img.save(fpath, format=fmt, dpi=(dpi, dpi))
        paths.append(fpath)
    return paths
