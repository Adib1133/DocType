import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import pikepdf
from app import DocTypeApp

class PdfTabTests(unittest.TestCase):
    def test_render_select_clear_and_export(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            source=Path(folder)/'pages.pdf'
            with pikepdf.Pdf.new() as pdf:
                for i in range(3):pdf.add_blank_page(page_size=(200+i*20,300))
                pdf.save(source)
            ui=DocTypeApp()
            try:
                ui._pdf_remover()
                self.assertEqual(ui._tab_var.get(),'pdf')
                panel=ui._frame_pdf
                panel.load(source)
                deadline=time.monotonic()+10
                while len(panel.cards)<3 and time.monotonic()<deadline:
                    ui.update();time.sleep(.01)
                self.assertEqual(len(panel.cards),3)
                self.assertEqual(len(panel.photos),3)
                panel.cards[1].event_generate('<Button-1>',x=100,y=100)
                ui.update()
                self.assertEqual(panel.selected,{1})
                self.assertTrue(panel.cards[1].find_withtag('remove_mark'))
                panel.clear_selection()
                self.assertFalse(panel.selected)
                panel.toggle(1)
                panel.output_folder=lambda:folder
                with patch('pdf_pages_panel.messagebox.showinfo'):
                    panel.save()
                with pikepdf.open(Path(folder)/'pages_edited.pdf') as pdf:self.assertEqual(len(pdf.pages),2)
                with pikepdf.open(Path(folder)/'pages_removed.pdf') as pdf:self.assertEqual(len(pdf.pages),1)
                panel.toggle(0);panel.toggle(2)
                self.assertEqual(panel.save_button.cget('state'),'disabled')
                panel.load(source)
                self.assertFalse(panel.selected)
            finally:
                panel._close_renderer()
                for callback in ui.tk.call('after','info'):ui.after_cancel(callback)
                ui.destroy()

if __name__=='__main__':unittest.main()
