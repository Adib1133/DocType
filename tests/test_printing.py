import unittest
from unittest.mock import patch
import ctypes as C
from PIL import Image
import printing

class Function:
    def __init__(self,fn):self.fn=fn
    def __call__(self,*args):return self.fn(*args)
class Api:
    def __init__(self,**functions):
        for key,fn in functions.items():setattr(self,key,Function(fn))

class PrintingTests(unittest.TestCase):
    def test_fit_and_range(self):
        self.assertEqual(printing.fit_rect((100,200),(1000,1000),(300,300)),(250,0,750,1000))
        self.assertEqual(printing.fit_rect((100,100),(600,300),(600,300)),(0,0,600,300))
        self.assertEqual(list(printing.page_indices(5,2,2,4)),[1,2,3])
        with self.assertRaises(ValueError):printing.page_indices(5,2,4,2)

    def fake_api(self,accepted=True,fail_page=False):
        self.events=[]
        def dialog(pointer):
            pd=C.cast(pointer,C.POINTER(printing.PRINTDLG)).contents
            if accepted:
                pd.hDC=99;pd.Flags|=2;pd.nFromPage=2;pd.nToPage=3
                pd.hDevMode=11;pd.hDevNames=12
            return accepted
        def event(name,result=1):
            def run(*args):self.events.append(name);return result
            return run
        self.apis={
            'comdlg32':Api(PrintDlgW=dialog,CommDlgExtendedError=lambda:0),
            'gdi32':Api(GetDeviceCaps=lambda dc,i:{8:1200,10:1600,88:300,90:300}[i],
                StartDocW=event('start'),StartPage=event('page',-1 if fail_page else 1),
                EndPage=event('endpage'),EndDoc=event('end'),AbortDoc=event('abort'),DeleteDC=event('delete')),
            'kernel32':Api(GlobalFree=event('free')),
            'user32':Api(GetAncestor=lambda *args:1)}
        return lambda name,**kwargs:self.apis[name]

    def test_cancel_does_not_spool(self):
        with patch('printing.C.WinDLL',self.fake_api(False)):
            self.assertFalse(printing.print_pages(1,3,lambda i:self.fail('Rendered on cancel')))
        self.assertEqual(self.events,[])

    def test_range_spools_once_and_releases_handles(self):
        seen=[]
        def page(i):seen.append(i);return Image.new('RGB',(100,200))
        with patch('printing.C.WinDLL',self.fake_api()),patch('printing.ImageWin.Dib'):
            self.assertTrue(printing.print_pages(1,4,page))
        self.assertEqual(seen,[1,2])
        self.assertEqual(self.events,['start','page','endpage','page','endpage','end','delete','free','free'])

    def test_print_failure_aborts_job(self):
        with patch('printing.C.WinDLL',self.fake_api(fail_page=True)),patch('printing.ImageWin.Dib'):
            with self.assertRaises(RuntimeError):printing.print_pages(1,4,lambda i:Image.new('RGB',(100,200)))
        self.assertIn('abort',self.events)
        self.assertEqual(self.events[-3:],['delete','free','free'])

if __name__=='__main__':unittest.main()
