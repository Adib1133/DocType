import unittest
from types import SimpleNamespace
from PIL import Image
import customtkinter as ctk
from app import DocTypeApp, ImageRecord, CropCanvas

class CropInteractionTests(unittest.TestCase):
    def setUp(self):
        self.ui=DocTypeApp()
        self.ui._records=[ImageRecord('one.png',Image.new('RGB',(600,800),'grey')),
                          ImageRecord('two.png',Image.new('RGB',(600,800),'white'))]
        self.ui._select_image(0)
        self.ui.update()
    def tearDown(self):
        for callback in self.ui.tk.call("after", "info"):
            self.ui.after_cancel(callback)
        self.ui.destroy()
    def editor(self):
        self.ui._manual_crop()
        self.ui.update()
        dialog=next(w for w in self.ui.winfo_children() if isinstance(w,ctk.CTkToplevel))
        canvas=next(w for w in dialog.winfo_children() if isinstance(w,CropCanvas))
        return dialog,canvas
    def buttons(self,widget):
        result=[]
        for child in widget.winfo_children():
            if isinstance(child,ctk.CTkButton): result.append(child)
            else: result.extend(self.buttons(child))
        return result
    def test_drag_resize_cancel_and_apply(self):
        dialog,canvas=self.editor()
        x1,y1,x2,y2=canvas._rect
        canvas._press(SimpleNamespace(x=x1,y=y1))
        canvas._drag(SimpleNamespace(x=x1+60,y=y1+80))
        canvas._release(None)
        crop=canvas.get_rect_original()
        self.assertGreater(crop[0],0)
        self.assertGreater(crop[1],0)
        dialog.geometry('750x600')
        self.ui.update()
        resized=canvas.get_rect_original()
        for a,b in zip(crop,resized): self.assertLessEqual(abs(a-b),2)
        next(b for b in self.buttons(dialog) if b.cget('text')=='Cancel').invoke()
        self.assertEqual(self.ui._records[0].cropped.size,(600,800))
        dialog,canvas=self.editor()
        canvas.set_rect_normalized(.1,.1,.9,.9)
        next(b for b in self.buttons(dialog) if b.cget('text')=='Apply crop').invoke()
        w,h=self.ui._records[0].cropped.size
        self.assertAlmostEqual(w,480,delta=2)
        self.assertAlmostEqual(h,640,delta=2)
        self.ui._undo()
        self.assertEqual(self.ui._records[0].cropped.size,(600,800))
    def test_auto_crop_opens_selected_box_without_changing_image(self):
        from unittest.mock import patch
        import numpy as np
        points=np.array([[50,60],[550,60],[550,740],[50,740]],dtype=np.float32)
        with patch('app.detect_document',return_value=(Image.new('RGB',(500,680)),points)):
            self.ui._auto_detect()
        self.ui.update()
        dialog=next(w for w in self.ui.winfo_children() if isinstance(w,ctk.CTkToplevel))
        canvas=next(w for w in dialog.winfo_children() if isinstance(w,CropCanvas))
        rect=canvas.get_rect_original()
        self.assertAlmostEqual(rect[0],50,delta=1)
        self.assertAlmostEqual(rect[1],60,delta=1)
        self.assertEqual(self.ui._records[0].cropped.size,(600,800))
        dialog.destroy()
        with patch('app.detect_document',return_value=(None,None)):
            self.ui._auto_detect()
        self.ui.update()
        dialog=next(w for w in self.ui.winfo_children() if isinstance(w,ctk.CTkToplevel))
        canvas=next(w for w in dialog.winfo_children() if isinstance(w,CropCanvas))
        rect=canvas.get_rect_original()
        self.assertEqual(rect[:2],(0,0))
        self.assertAlmostEqual(rect[2],600,delta=1)
        dialog.destroy()

    def test_move_is_bounded_and_batch_edits(self):
        dialog,canvas=self.editor()
        canvas.set_rect_normalized(.2,.2,.8,.8)
        x1,y1,x2,y2=canvas._rect
        canvas._press(SimpleNamespace(x=(x1+x2)/2,y=(y1+y2)/2))
        canvas._drag(SimpleNamespace(x=-100,y=-100))
        canvas._release(None)
        self.assertEqual(canvas.get_rect_original()[:2],(0,0))
        dialog.destroy()
        self.ui._batch_edit('Rotate')
        self.assertTrue(all(r.cropped.size==(800,600) for r in self.ui._records))
        self.ui._batch_edit('Enhance')
        self.assertTrue(all(len(r.history)==2 for r in self.ui._records))

if __name__=='__main__': unittest.main()
