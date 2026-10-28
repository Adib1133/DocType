import unittest
from unittest.mock import patch
import customtkinter as ctk
import tkinter as tk
from PIL import Image
from printing import preview_and_print

class PreviewTests(unittest.TestCase):
    def test_preview_renders_navigates_and_cancels_without_printing(self):
        root=ctk.CTk();root.withdraw()
        visited=[];failures=[]
        def page(i):visited.append(i);return Image.new('RGB',(200,300),['white','red'][i])
        def children(widget):
            result=[]
            for child in widget.winfo_children():result.append(child);result.extend(children(child))
            return result
        def exercise():
            window=next(w for w in root.winfo_children() if isinstance(w,ctk.CTkToplevel))
            try:
                widgets=children(window)
                self.assertTrue(any(isinstance(w,tk.Canvas) and any(w.type(i)=='image' for i in w.find_all()) for w in widgets))
                next(w for w in widgets if isinstance(w,ctk.CTkButton) and w.cget('text')=='Next').invoke()
                self.assertEqual(visited,[0,1])
                next(w for w in widgets if isinstance(w,ctk.CTkButton) and w.cget('text')=='Cancel').invoke()
            except Exception as ex:failures.append(ex);window.destroy()
        root.after(250,exercise)
        try:
            with patch('printing.print_pages') as native:
                self.assertFalse(preview_and_print(root,2,page))
                native.assert_not_called()
            if failures:raise failures[0]
        finally:
            for callback in root.tk.call('after','info'):root.after_cancel(callback)
            root.destroy()
if __name__=='__main__':unittest.main()
