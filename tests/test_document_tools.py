import tempfile
import unittest
from pathlib import Path
import pikepdf
from document_tools import load_settings,save_settings,parse_pages,remove_pdf_pages

class DocumentToolsTests(unittest.TestCase):
    def test_settings_roundtrip(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path=Path(folder)/'settings.json'
            values=load_settings(path)
            values.update(output_dir=folder,dpi='300',save_removed=False)
            save_settings(values,path)
            self.assertEqual(load_settings(path),values)
            path.write_text('broken')
            self.assertEqual(load_settings(path)['output_dir'],'')

    def test_page_ranges(self):
        self.assertEqual(parse_pages('2, 4-6, 4',8),{1,3,4,5})
        for bad in ('','0','9','5-2','1-8','abc','2,'):
            with self.assertRaises(ValueError):parse_pages(bad,8)

    def test_split_order_original_and_collisions(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            source=Path(folder)/'input.pdf'
            with pikepdf.Pdf.new() as pdf:
                for i in range(5):
                    page=pdf.add_blank_page(page_size=(200+i*10,300))
                    page.Contents=pdf.make_stream(f'% unique page {i}'.encode())
                pdf.save(source)
            original=source.read_bytes()
            paths=remove_pdf_pages(source,'2,4',folder,True)
            for path,indices in zip(paths,([0,2,4],[1,3])):
                with pikepdf.open(path) as pdf:
                    self.assertEqual([int(p.MediaBox[2]) for p in pdf.pages],[200+i*10 for i in indices])
                    self.assertEqual([p.Contents.read_bytes() for p in pdf.pages],[f'% unique page {i}'.encode() for i in indices])
            self.assertEqual(source.read_bytes(),original)
            newer=remove_pdf_pages(source,'2',folder,False)
            self.assertEqual(len(newer),1)
            self.assertNotEqual(newer[0],paths[0])
            self.assertTrue(all(p.exists() for p in paths))

if __name__=='__main__':unittest.main()
