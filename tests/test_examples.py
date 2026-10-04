"""Offline regression checks for the public examples and metadata handling."""

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from _extracted import email, html, xlsx
from scripts.export_notebooks import NOTEBOOKS, ROOT, module_source


class PublicExamples(unittest.TestCase):
    def test_exports_match_notebook_definitions(self):
        for name in NOTEBOOKS:
            with self.subTest(module=name):
                self.assertEqual((ROOT / "_extracted" / f"{name}.py").read_text(encoding="utf-8"), module_source(name))

    def test_notebooks_do_not_contain_saved_outputs(self):
        for relative_path, _ in NOTEBOOKS.values():
            notebook = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    self.assertFalse(cell.get("outputs"))
                    self.assertIsNone(cell.get("execution_count"))

    def test_exports_do_not_execute_notebook_demos(self):
        allowed = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.If)
        for name in NOTEBOOKS:
            tree = ast.parse(module_source(name))
            for node in tree.body[1:]:  # module docstring
                with self.subTest(module=name, line=node.lineno):
                    self.assertIsInstance(node, allowed)
                    if isinstance(node, ast.Assign):
                        self.assertTrue(all(isinstance(t, ast.Name) and (t.id.startswith("_") or t.id.isupper()) for t in node.targets))

    def test_html_removes_noise_and_preserves_table(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.html"
            source.write_text('<body><nav>SECRET_NAV</nav><h1>Chapter</h1><p>Useful body content for indexing.</p><table><tr><td>Value 12 units</td></tr></table></body>', encoding="utf-8")
            elements, _ = html.extract(source)
            chunks = html.chunk_elements(elements, source.name)
            self.assertNotIn("SECRET_NAV", " ".join(c.text for c in chunks))
            self.assertTrue(any("Value 12" in c.text for c in chunks))
            self.assertTrue(all(c.section == "Chapter" for c in chunks))

    def test_eml_removes_quote_and_signature(self):
        text = "Useful current message.\n\n-- \nSignature\nOn Mon, someone wrote:\n> Old content"
        cleaned = email.strip_signature(email.strip_quoted_reply(text))
        self.assertIn("Useful current message", cleaned)
        self.assertNotIn("Old content", cleaned)
        self.assertNotIn("Signature", cleaned)

    def test_invalid_windows_are_rejected(self):
        for module in (html, email):
            for size, overlap in ((0, 0), (-1, 0), (10, 10), (10, -1)):
                with self.subTest(module=module.__name__, size=size, overlap=overlap):
                    with self.assertRaises(ValueError):
                        module.chunk_elements([], "sample", chunk_size=size, overlap=overlap)

    def test_xlsx_skips_empty_sheet(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.xlsx"
            workbook = Workbook()
            workbook.active.title = "Inventory"
            workbook.active.append(["Name", "Count"])
            workbook.active.append(["Sample", 12])
            workbook.create_sheet("Empty")
            workbook.save(source)
            workbook.close()
            elements = xlsx.extract(source)
            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0].sheet, "Inventory")
            self.assertIn("Sample | 12", elements[0].text)


@unittest.skipUnless(importlib.util.find_spec("pymupdf4llm") and importlib.util.find_spec("openai"), "install document dependencies")
class PDFRegression(unittest.TestCase):
    def test_page_boundary_preserves_previous_page(self):
        from _extracted import pdf_text
        pages = [
            {"metadata": {"page_number": 1}, "text": "# First\n" + "first page content " * 3},
            {"metadata": {"page_number": 2}, "text": "# Second\n" + "second page content " * 3},
        ]
        with patch.object(pdf_text.pymupdf4llm, "to_markdown", return_value=pages):
            chunks = pdf_text.extract_and_chunk(Path("dummy.pdf"))
        self.assertEqual([c.page for c in chunks], [1, 2])
        self.assertEqual([c.section for c in chunks], ["First", "Second"])

    def test_invalid_pdf_window_before_parser_runs(self):
        from _extracted import pdf_text, pdf_scan, pdf_mixed
        for module in (pdf_text, pdf_scan, pdf_mixed):
            with self.subTest(module=module.__name__):
                with self.assertRaises(ValueError):
                    module.extract_and_chunk(Path("nonexistent.pdf"), chunk_size=20, overlap=20)

    def test_mixed_pdf_does_not_call_model_by_default(self):
        import fitz
        from _extracted import pdf_mixed
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.pdf"
            with fitz.open() as document:
                page = document.new_page()
                page.insert_text((50, 50), "Useful text for offline extraction. " * 2)
                document.save(source)
            with patch.object(pdf_mixed, "add_captions", side_effect=AssertionError("unexpected model call")):
                self.assertTrue(pdf_mixed.extract_and_chunk(source))


@unittest.skipUnless(importlib.util.find_spec("pptx") and importlib.util.find_spec("openai"), "install document dependencies")
class PPTRegression(unittest.TestCase):
    def test_picture_caption_is_opt_in(self):
        from _extracted import pptx
        element = pptx.Element(index=0, category="Image", text="[图片: sample.png]", slide_num=1, image_path="missing.png")
        with patch.object(pptx, "caption_image", side_effect=AssertionError("unexpected model call")):
            self.assertEqual(len(pptx.chunk_slides([element], "sample.pptx")), 1)


if __name__ == "__main__":
    unittest.main()
