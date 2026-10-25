import unittest
import tempfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import pikepdf
from image_processor import detect_document, apply_color_grade, export_pdf

class ProcessingTests(unittest.TestCase):
    def test_skewed_paper(self):
        image = np.full((700, 900, 3), 35, np.uint8)
        quad = np.array([[140,80],[780,130],[730,620],[90,560]], np.int32)
        cv2.fillConvexPoly(image, quad, (210,210,210))
        cv2.putText(image, 'Document', (240,300), cv2.FONT_HERSHEY_SIMPLEX, 2, (30,30,30), 3)
        cropped, points = detect_document(Image.fromarray(image))
        self.assertIsNotNone(cropped)
        for corner in quad:
            self.assertLess(np.linalg.norm(points-corner, axis=1).min(), 20)

    def test_blank_and_full_page_preserved(self):
        self.assertEqual(detect_document(Image.new('RGB', (600,800), 'white')), (None,None))
        # Synthetic full-page form avoids shipping private document photos.
        paper = np.full((800,600,3),210,np.uint8)
        cv2.rectangle(paper,(55,60),(545,740),(30,30,30),2)
        for y in range(110,740,45):
            cv2.line(paper,(55,y),(545,y),(30,30,30),1)
        for x in (180,350,440):
            cv2.line(paper,(x,60),(x,740),(30,30,30),1)
        image = Image.fromarray(paper)
        crop, _ = detect_document(image)
        self.assertIsNone(crop, 'Do not mistake the inner table for the page boundary')

    def test_lighting_and_ink(self):
        paper = np.tile(np.linspace(100,210,600), (800,1)).astype(np.uint8)
        paper[100:700:40, 100:500] = 30
        result = np.array(apply_color_grade(Image.fromarray(paper),profile="Clean scan"))[:,:,0]
        self.assertGreater(np.median(result[:,20:80]), 245)
        self.assertLess(np.median(result[100:700:40,100:500]), 90)
        original = Image.fromarray(paper).convert('RGB')
        self.assertTrue(np.array_equal(np.array(original), np.array(apply_color_grade(original,intensity=0))))

    def test_low_contrast_paper_outer_edge(self):
        image = np.full((700,900,3),180,np.uint8)
        cv2.rectangle(image,(120,70),(780,630),(200,200,200),-1)
        cv2.rectangle(image,(200,150),(700,550),(20,20,20),2)
        cropped,points=detect_document(Image.fromarray(image))
        self.assertIsNotNone(cropped)
        self.assertGreater(cropped.width,640)
        self.assertGreater(cropped.height,540)

    def test_no_grey_halo_around_text(self):
        paper = np.full((400,600), 160, np.uint8)
        cv2.putText(paper, 'Clean text', (40,210), cv2.FONT_HERSHEY_SIMPLEX, 2, 25, 3)
        ink = (paper < 100).astype(np.uint8)
        ring = (cv2.dilate(ink, np.ones((21,21), np.uint8)) > 0) & (ink == 0)
        result = np.array(apply_color_grade(Image.fromarray(paper),profile="Clean scan"))[:,:,0]
        self.assertGreater(np.percentile(result[ring], 5), 250)
        self.assertLess(np.median(result[ink > 0]), 30)

    def test_original_profile_is_unchanged(self):
        rgb=np.random.default_rng(7).integers(0,256,(80,100,3),dtype=np.uint8)
        out=apply_color_grade(Image.fromarray(rgb),profile="Original (no filter)")
        self.assertTrue(np.array_equal(rgb,np.array(out)))

    def test_pdf_pages_and_size(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = str(Path(folder)/'test.pdf')
            export_pdf([Image.new('RGB',(500,700),'white')]*2,path,dpi=150)
            with pikepdf.open(path) as pdf:
                self.assertEqual(len(pdf.pages),2)
                self.assertAlmostEqual(float(pdf.pages[0].MediaBox[2]),595,delta=1)
                self.assertAlmostEqual(float(pdf.pages[0].MediaBox[3]),842,delta=1)
        with self.assertRaises(ValueError):
            export_pdf([], 'unused.pdf')

if __name__ == '__main__':
    unittest.main()

