"""Focused export regression tests, preserved from the original workflow suite."""

import io
import unittest
import openpyxl
from app.tools.excel_export import make_workbook


class ExportTests(unittest.TestCase):
    def test_export_preserves_template_and_blank_manual_fields(self):
        workbook = openpyxl.load_workbook(io.BytesIO(make_workbook({"bl_number": "2339673950", "vessel": "CMA CGM FORT DIAMANT", "sailing_date": "10.14"})))
        sheet = workbook["业务联系单"]
        self.assertEqual(sheet["B8"].value, "2339673950")
        self.assertEqual(sheet["B9"].value, "CMA CGM FORT DIAMANT")
        self.assertEqual(sheet["B10"].value, "10.14")
        self.assertIsNone(sheet["B4"].value)
        self.assertIsNone(sheet["E3"].value)
        self.assertEqual(sheet["A1"].value, "港捷物流业务联系单")

    def test_export_writes_confirmed_manual_fields(self):
        workbook = openpyxl.load_workbook(io.BytesIO(make_workbook({"carrier": "MSC", "customer_service": "SISSIE", "contract": "TEST-123", "sales": "ROBIN"})))
        sheet = workbook["业务联系单"]
        self.assertEqual(sheet["B4"].value, "MSC")
        self.assertEqual(sheet["E3"].value, "SISSIE")
        self.assertEqual(sheet["E5"].value, "TEST-123")
        self.assertEqual(sheet["B39"].value, "ROBIN")
        self.assertIsNone(sheet["B3"].value)
