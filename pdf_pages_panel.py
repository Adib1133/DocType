"""Embedded, thumbnail-based PDF page removal workspace."""
from theme import PALETTE
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import ImageTk
import pypdfium2 as pdfium
from document_tools import remove_pdf_pages

class PdfPagesPanel(ctk.CTkFrame):
    def __init__(self, parent, output_folder, settings, status):
        super().__init__(parent, fg_color=PALETTE["BG_MAIN"], corner_radius=0)
        self.output_folder, self.settings, self.status = output_folder, settings, status
        self.path = None
        self.selected = set()
        self.cards = []
        self.photos = []
        self.document = None
        self.pending = None
        self.count = 0
        self.restore_selection = set()
        self.failed = False
        toolbar = ctk.CTkFrame(self, fg_color='transparent')
        toolbar.pack(fill='x', padx=12, pady=12)
        ctk.CTkButton(toolbar, text='Open PDF…', width=110, fg_color=PALETTE["MAROON"], command=self.choose).pack(side='left')
        ctk.CTkButton(toolbar, text='Clear selection', width=120, fg_color=PALETTE["MAROON"], command=self.clear_selection).pack(side='right')
        self.name = ctk.CTkLabel(self, text='Open a PDF to see its pages.', wraplength=500)
        self.name.pack(padx=12)
        ctk.CTkLabel(self, text='Click a page to mark it × for removal. Click again to keep it.',
                     text_color=PALETTE["TEXT_MUTED"], wraplength=500).pack(padx=12,pady=(2,8))
        footer=ctk.CTkFrame(self,fg_color=PALETTE["BG_PANEL"])
        footer.pack(side='bottom',fill='x',padx=12,pady=12)
        self.summary=ctk.CTkLabel(footer,text='No PDF loaded')
        self.summary.pack(pady=4)
        self.save_removed=tk.BooleanVar(value=settings()['save_removed'])
        ctk.CTkCheckBox(footer,text='Also save removed pages as a separate PDF',
            variable=self.save_removed,fg_color=PALETTE["MAROON"]).pack(padx=12,pady=6)
        self.save_button=ctk.CTkButton(footer,text='Save edited PDF',command=self.save,
            fg_color=PALETTE["MAROON"],state='disabled')
        self.save_button.pack(pady=(4,12))
        self.grid_area=ctk.CTkScrollableFrame(self,fg_color='transparent')
        self.grid_area.pack(fill='both',expand=True,padx=8)
        for col in range(2): self.grid_area.grid_columnconfigure(col,weight=1)
        self.bind('<Destroy>',self._destroyed,add='+')

    def _close_renderer(self):
        if self.pending:
            self.after_cancel(self.pending)
            self.pending=None
        if self.document:
            self.document.close()
            self.document=None

    def _destroyed(self,event):
        if event.widget is self: self._close_renderer()

    def choose(self):
        path=filedialog.askopenfilename(parent=self,title='Open PDF',filetypes=[('PDF','*.pdf')])
        if path:
            try:self.load(path)
            except Exception as ex:messagebox.showerror('Open PDF',str(ex),parent=self)

    def load(self,path):
        document=pdfium.PdfDocument(path)
        count=len(document)
        if not count:
            document.close()
            raise ValueError('This PDF has no pages.')
        self._close_renderer()
        for child in self.grid_area.winfo_children():child.destroy()
        self.document=document
        self.path=str(path)
        stat=Path(path).stat()
        self.source_stamp=(stat.st_size,stat.st_mtime_ns)
        self.count=count
        self.failed=False
        self.restore_selection.clear()
        self.selected.clear();self.cards.clear();self.photos.clear()
        self.name.configure(text=f'{os.path.basename(path)} · {count} pages')
        self._update_summary()
        self.pending=self.after(1,lambda:self._render_next(0))

    def _render_next(self,index):
        self.pending=None
        if self.document is None:return
        try:
            page=self.document[index]
            try:
                width,height=page.get_size()
                bitmap=page.render(scale=min(210/max(width,1),260/max(height,1)))
                try:img=bitmap.to_pil().convert('RGB').copy()
                finally:bitmap.close()
            finally:page.close()
            photo=ImageTk.PhotoImage(img)
            self.photos.append(photo)
            card=tk.Canvas(self.grid_area,width=230,height=300,bg='white',highlightthickness=2,
                           highlightbackground='#D8C9BA',cursor='hand2')
            card.create_image(115,140,image=photo)
            card.create_text(115,285,text=f'Page {index+1}',fill='#2D1518',tags='caption')
            card.bind('<Button-1>',lambda event,i=index:self.toggle(i))
            card.grid(row=index//2,column=index%2,padx=8,pady=8)
            self.cards.append(card)
            if index in self.restore_selection:
                self.toggle(index)
                self.restore_selection.discard(index)
            self._update_summary()
            if index+1<self.count:
                self.pending=self.after(5,lambda:self._render_next(index+1))
            else:
                self._close_renderer()
                self._update_summary()
        except Exception as ex:
            self.failed=True
            self._close_renderer()
            self._update_summary()
            messagebox.showerror('PDF preview',f'Could not render page {index+1}: {ex}',parent=self)

    def toggle(self,index):
        if index>=len(self.cards):return
        if index in self.selected:self.selected.remove(index)
        else:self.selected.add(index)
        card=self.cards[index]
        card.delete('remove_mark')
        marked=index in self.selected
        card.configure(highlightbackground='#A42535' if marked else '#D8C9BA',highlightthickness=2)
        if marked:
            card.create_rectangle(3,3,227,274,fill='#A42535',stipple='gray12',outline='',tags='remove_mark')
            card.create_oval(184,9,222,47,fill='#A42535',outline='white',tags='remove_mark')
            card.create_text(203,27,text='×',fill='white',font=('Segoe UI',26,'bold'),tags='remove_mark')
        card.itemconfigure('caption',text=f'Page {index+1}'+(' · Remove' if marked else ''))
        self._update_summary()

    def clear_selection(self):
        for index in list(self.selected):self.toggle(index)

    def _update_summary(self):
        n=len(self.selected)
        loading=len(self.cards)<self.count
        text=f'{n} selected for removal · {self.count-n} kept'
        if loading:text+=f' · Preview {len(self.cards)}/{self.count}'
        if self.failed:text='Preview failed. Reopen the PDF to try again.'
        elif n==self.count and self.count:text+=' · Keep at least one page'
        self.summary.configure(text=text)
        self.save_button.configure(state='normal' if 0<n<self.count and not loading and not self.failed else 'disabled')

    def save(self):
        if not self.path or not 0<len(self.selected)<self.count or self.failed or len(self.cards)!=self.count:return
        try:
            stat=Path(self.path).stat()
            if (stat.st_size,stat.st_mtime_ns)!=self.source_stamp:
                raise ValueError('The source PDF has changed. Reopen it before exporting.')
            folder=self.output_folder()
            if not folder:return
            selection=','.join(str(i+1) for i in sorted(self.selected))
            paths=remove_pdf_pages(self.path,selection,folder,self.save_removed.get())
            self.status(f'Saved {len(paths)} PDF file(s). Original unchanged.')
            messagebox.showinfo('PDF saved','\n'.join(map(str,paths)),parent=self)
        except Exception as ex:messagebox.showerror('PDF export',str(ex),parent=self)
