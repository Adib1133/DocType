"""Shared cream/maroon and charcoal/rose appearance palettes."""
import customtkinter as ctk
LIGHT = dict(BG_MAIN='#FAF6EF',BG_PANEL='#F3ECE1',BG_CARD='#FFFFFF',BORDER_COLOR='#D8C9BA',
 MAROON='#7A1C28',MAROON_HOVER='#912332',MAROON_DARK='#5C131E',TEXT_MAIN='#2D1518',
 TEXT_MUTED='#75595C',BUTTON_ALT='#EBE0D2',BUTTON_ALT_HOV='#DECFC0')
DARK = dict(BG_MAIN='#19171B',BG_PANEL='#242127',BG_CARD='#302B32',BORDER_COLOR='#514650',
 MAROON='#963E53',MAROON_HOVER='#AD4D65',MAROON_DARK='#F0B8C5',TEXT_MAIN='#F4EAE6',
 TEXT_MUTED='#C4B2B7',BUTTON_ALT='#3B323A',BUTTON_ALT_HOV='#51414C')
PALETTE = LIGHT.copy()
def apply_theme(mode):
    ctk.set_appearance_mode(mode.lower())
    PALETTE.clear()
    PALETTE.update(DARK if ctk.get_appearance_mode()=='Dark' else LIGHT)
    return PALETTE
