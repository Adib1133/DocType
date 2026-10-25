import unittest
import tkinter as tk
from PIL import Image
import customtkinter as ctk
from app import DocTypeApp,ImageRecord
from theme import DARK,LIGHT
class ThemeTests(unittest.TestCase):
    def test_theme_switch_keeps_edits_and_export_choices(self):
        ui=DocTypeApp()
        try:
            rec=ImageRecord('sample',Image.new('RGB',(200,300),'white'))
            rec.push_history()
            ui._records.append(rec);ui._select_image(0)
            ui._dpi_var.set('300');ui._tab_var.set('pdf')
            for mode,palette in [('Dark',DARK),('Light',LIGHT),('Dark',DARK)]:
                ui._settings['theme']=mode
                ui._apply_appearance();ui.update()
                self.assertEqual(ui.cget('fg_color'),palette['BG_MAIN'])
                self.assertEqual(ui._frame_pdf.cget('fg_color'),palette['BG_MAIN'])
                self.assertIs(ui._records[0],rec)
                self.assertEqual(len(rec.history),1)
                self.assertEqual(ui._dpi_var.get(),'300')
                self.assertEqual(ui._tab_var.get(),'pdf')
            ui._open_settings();ui.update()
        finally:
            for child in list(ui.winfo_children()):
                if isinstance(child, ctk.CTkToplevel):child.destroy()
            for callback in ui.tk.call('after','info'):ui.after_cancel(callback)
            ui.destroy()
            ctk.set_appearance_mode('light')
if __name__=='__main__':unittest.main()
