"""Windows system print dialog and GDI printing; no PDF-reader dependency."""
import ctypes as C
from ctypes import wintypes as W
import os
from PIL import ImageWin

class PRINTDLG(C.Structure):
    _fields_=[('lStructSize',W.DWORD),('hwndOwner',W.HWND),('hDevMode',W.HGLOBAL),
      ('hDevNames',W.HGLOBAL),('hDC',W.HDC),('Flags',W.DWORD),
      ('nFromPage',W.WORD),('nToPage',W.WORD),('nMinPage',W.WORD),('nMaxPage',W.WORD),
      ('nCopies',W.WORD),('hInstance',W.HINSTANCE),('lCustData',W.LPARAM),
      ('lpfnPrintHook',C.c_void_p),('lpfnSetupHook',C.c_void_p),
      ('lpPrintTemplateName',W.LPCWSTR),('lpSetupTemplateName',W.LPCWSTR),
      ('hPrintTemplate',W.HGLOBAL),('hSetupTemplate',W.HGLOBAL)]
class DOCINFO(C.Structure):
    _fields_=[('cbSize',C.c_int),('lpszDocName',W.LPCWSTR),('lpszOutput',W.LPCWSTR),
              ('lpszDatatype',W.LPCWSTR),('fwType',W.DWORD)]

def fit_rect(size, printable, dpi):
    """Center and fit, including printers with unequal X/Y resolution."""
    w,h=size;pw,ph=printable;dx,dy=dpi
    if min(w,h,pw,ph,dx,dy)<=0:raise ValueError('Invalid page or printer dimensions.')
    scale=min(pw/(w*dx),ph/(h*dy))
    rw,rh=max(1,round(w*dx*scale)),max(1,round(h*dy*scale))
    x,y=(pw-rw)//2,(ph-rh)//2
    return x,y,x+rw,y+rh

def page_indices(count,flags,first,last):
    if not 1<=count<=65535:raise ValueError('Print between 1 and 65535 pages per job.')
    if flags & 2:
        if not 1<=first<=last<=count:raise ValueError('Invalid print page range.')
        return range(first-1,last)
    return range(count)

def print_pages(owner,count,get_page,title='DocType'):
    """Show native dialog, then spool only after Print. Return False on Cancel."""
    if os.name!='nt':raise RuntimeError('Direct printing is supported on Windows only.')
    page_indices(count,0,1,count)
    dialog=C.WinDLL('comdlg32',use_last_error=True)
    gdi=C.WinDLL('gdi32',use_last_error=True)
    kernel=C.WinDLL('kernel32',use_last_error=True)
    user=C.WinDLL('user32',use_last_error=True)
    dialog.PrintDlgW.argtypes=[C.POINTER(PRINTDLG)];dialog.PrintDlgW.restype=W.BOOL
    dialog.CommDlgExtendedError.restype=W.DWORD
    kernel.GlobalFree.argtypes=[W.HGLOBAL];kernel.GlobalFree.restype=W.HGLOBAL
    user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
    gdi.GetDeviceCaps.argtypes=[W.HDC,C.c_int];gdi.GetDeviceCaps.restype=C.c_int
    for name in ('StartPage','EndPage','EndDoc','AbortDoc','DeleteDC'):
        fn=getattr(gdi,name);fn.argtypes=[W.HDC];fn.restype=C.c_int
    gdi.StartDocW.argtypes=[W.HDC,C.POINTER(DOCINFO)];gdi.StartDocW.restype=C.c_int
    pd=PRINTDLG();pd.lStructSize=C.sizeof(pd)
    pd.hwndOwner=user.GetAncestor(owner,2) or owner
    # Driver handles copies/collation. Hide legacy FILE: checkbox; virtual PDF
    # printers remain selectable and provide their own destination prompt.
    pd.Flags=0x100|0x4|0x40000|0x100000
    pd.nMinPage=pd.nFromPage=1;pd.nMaxPage=pd.nToPage=count;pd.nCopies=1
    started=False
    try:
        if not dialog.PrintDlgW(C.byref(pd)):
            error=dialog.CommDlgExtendedError()
            if error:raise RuntimeError(f'Windows print dialog failed (0x{error:04X}). Check installed printers.')
            return False
        pages=page_indices(count,pd.Flags,pd.nFromPage,pd.nToPage)
        width,height=(gdi.GetDeviceCaps(pd.hDC,i) for i in (8,10))
        dpi=tuple(gdi.GetDeviceCaps(pd.hDC,i) for i in (88,90))
        info=DOCINFO(C.sizeof(DOCINFO),title,None,None,0)
        if gdi.StartDocW(pd.hDC,C.byref(info))<=0:raise RuntimeError('Windows could not start the print job.')
        started=True
        for index in pages:
            img=get_page(index).convert('RGB')
            rect=fit_rect(img.size,(width,height),dpi)
            if gdi.StartPage(pd.hDC)<=0:raise RuntimeError('Printer could not start a page.')
            ImageWin.Dib(img).draw(pd.hDC,rect)
            if gdi.EndPage(pd.hDC)<=0:raise RuntimeError('Printer could not finish a page.')
        if gdi.EndDoc(pd.hDC)<=0:raise RuntimeError('Windows could not finish the print job.')
        started=False
        return True
    finally:
        if pd.hDC:
            if started:gdi.AbortDoc(pd.hDC)
            gdi.DeleteDC(pd.hDC)
        for handle in (pd.hDevMode,pd.hDevNames):
            if handle:kernel.GlobalFree(handle)

def print_pdf(owner,path,indices,title):
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(path) as doc:
        def render(index):
            page=doc[indices[index]]
            try:
                w,h=page.get_size()
                bitmap=page.render(scale=min(300/72,4500/max(w,h)))
                try:return bitmap.to_pil().convert('RGB').copy()
                finally:bitmap.close()
            finally:page.close()
        return preview_and_print(owner,len(indices),render,title)

def preview_and_print(parent,count,get_page,title='DocType'):
    """Review the actual print set before opening the Windows printer dialog."""
    import tkinter as tk
    from tkinter import messagebox
    import customtkinter as ctk
    from PIL import ImageTk
    from theme import PALETTE
    if count<1:raise ValueError('There are no pages to preview.')
    window=ctk.CTkToplevel(parent)
    window.title('Print preview — '+title)
    window.geometry('900x760')
    window.minsize(580,460)
    window.configure(fg_color=PALETTE['BG_MAIN'])
    window.transient(parent)
    state={'index':0,'result':False,'image':None,'photo':None,'resize':None}
    header=ctk.CTkFrame(window,fg_color='transparent')
    header.pack(fill='x',padx=16,pady=10)
    counter=ctk.CTkLabel(header,text='')
    counter.pack(side='left')
    ctk.CTkLabel(window,text='Content preview · Paper, orientation and margins are set in the next Windows dialog.',
        text_color=PALETTE['TEXT_MUTED'],wraplength=700).pack(padx=16,pady=(0,8))
    footer=ctk.CTkFrame(window,fg_color=PALETTE['BG_PANEL'])
    footer.pack(side='bottom',fill='x',padx=12,pady=12)
    canvas=tk.Canvas(window,bg='#484448',highlightthickness=0)
    canvas.pack(fill='both',expand=True,padx=16,pady=4)
    def redraw():
        state['resize']=None
        if state['image'] is None:return
        img=state['image'].copy()
        img.thumbnail((max(1,canvas.winfo_width()-32),max(1,canvas.winfo_height()-32)))
        state['photo']=ImageTk.PhotoImage(img)
        canvas.delete('all')
        canvas.create_image(canvas.winfo_width()/2,canvas.winfo_height()/2,image=state['photo'])
    def show(index):
        try:
            state['image']=get_page(index).convert('RGB').copy()
            state['index']=index
            counter.configure(text=f'Page {index+1} of {count}')
            previous.configure(state='normal' if index else 'disabled')
            following.configure(state='normal' if index<count-1 else 'disabled')
            print_button.configure(state='normal')
            redraw()
        except Exception as ex:
            print_button.configure(state='disabled')
            messagebox.showerror('Print preview',str(ex),parent=window)
    def resize(event):
        if state['resize']:window.after_cancel(state['resize'])
        state['resize']=window.after(80,redraw)
    def close():
        if state['resize']:window.after_cancel(state['resize'])
        window.destroy()
    def submit():
        try:
            sent=print_pages(window.winfo_id(),count,get_page,title)
            if sent:
                state['result']=True
                close()
        except Exception as ex:messagebox.showerror('Print',str(ex),parent=window)
    previous=ctk.CTkButton(header,text='Previous',width=95,command=lambda:show(state['index']-1),fg_color=PALETTE['MAROON'])
    previous.pack(side='right',padx=4)
    following=ctk.CTkButton(header,text='Next',width=95,command=lambda:show(state['index']+1),fg_color=PALETTE['MAROON'])
    following.pack(side='right',padx=4)
    ctk.CTkButton(footer,text='Cancel',command=close,fg_color=PALETTE['MAROON']).pack(side='left',padx=12,pady=10)
    print_button=ctk.CTkButton(footer,text='Choose printer / Print…',command=submit,fg_color=PALETTE['MAROON'])
    print_button.pack(side='right',padx=12,pady=10)
    window.protocol('WM_DELETE_WINDOW',close)
    window.bind('<Escape>',lambda e:close())
    canvas.bind('<Configure>',resize)
    window.update_idletasks()
    show(0)
    window.grab_set()
    parent.wait_window(window)
    return state['result']
