"""Synthetic behavioral tests; generated fixtures are not aerial demo results."""
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from analyze_images import DEFAULTS, analyze, compare, digest, run


class ImageIntelligenceTests(unittest.TestCase):
    def test_quality_and_conservative_filter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'input'
            source.mkdir()
            rng = np.random.default_rng(42)
            sharp = rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)
            cv2.putText(sharp, 'AeroSphere TEST', (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 3)
            cv2.imwrite(str(source / '01.png'), sharp)
            (source / '02.png').write_bytes((source / '01.png').read_bytes())
            cv2.imwrite(str(source / '02b.png'), sharp, [cv2.IMWRITE_PNG_COMPRESSION, 9])
            self.assertNotEqual(digest(source / '01.png'), digest(source / '02b.png'))
            cv2.imwrite(str(source / '03.png'), cv2.warpAffine(sharp, np.float32([[1, 0, 25], [0, 1, 0]]), (640, 480)))
            cv2.imwrite(str(source / '04.png'), cv2.GaussianBlur(sharp, (21, 21), 5))
            cv2.imwrite(str(source / '05.png'), np.zeros_like(sharp))
            (source / '06.png').write_bytes(b'not an image')
            before = {p.name: digest(p) for p in source.iterdir()}
            a = analyze(source / '01.png', DEFAULTS)
            b = analyze(source / '04.png', DEFAULTS)
            blank = analyze(source / '05.png', DEFAULTS)
            self.assertGreater(a[0]['blur_laplacian_variance'], b[0]['blur_laplacian_variance'])
            self.assertTrue(compare(a[1:], a[1:], DEFAULTS)['near_duplicate'])
            moved = analyze(source / '03.png', DEFAULTS)
            self.assertFalse(compare(a[1:], moved[1:], DEFAULTS)['near_duplicate'])
            self.assertFalse(compare(blank[1:], blank[1:], DEFAULTS)['near_duplicate'])
            summary = run(source, root / 'project', DEFAULTS)
            self.assertEqual(summary['exact_duplicates'], 1)
            self.assertEqual(summary['near_duplicates'], 1)
            self.assertEqual(summary['selected_images'], 3)
            self.assertEqual(summary['analysis_errors'], 1)
            self.assertEqual(before, {p.name: digest(p) for p in source.iterdir()})
            selected = Path(summary['selected_directory'])
            self.assertFalse((selected / '02.png').exists())
            self.assertTrue((selected / '03.png').exists())
            self.assertFalse((selected / '05.png').exists())
            with self.assertRaises(ValueError):
                run(source, source / 'unsafe', DEFAULTS)


if __name__ == '__main__':
    unittest.main()
