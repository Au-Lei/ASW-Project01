"""Portable excerpts for the latest carrier-format regressions.

The private customer documents are not copied into the repository.
"""

import unittest

from app.nodes.normalize import normalize_fields
from app.nodes.rule_extract import rule_extract


def values(text: str) -> dict[str, str]:
    return {key: item["value"] for key, item in normalize_fields(rule_extract(text)).items()}


class NewCaseRegressions(unittest.TestCase):
    def test_cosco_separate_voyage_and_hicube_pickup(self):
        result = values(
            "接货地: Qingdao,Qingdao, Shandong, China\n"
            "船名/航次: COSCO SHIPPING SAGITTARIUS ETD: 01 Oct 2026 14:00(CST)\n"
            "035W\nBOOKING QTY SIZE/TYPE: 2 X 40' Hi-Cube Container\n"
            "CARGO WEIGHT: 21000 KG 提箱地: 远洋大亚\n"
            "交货地: Mersin,Mersin, Turkey"
        )
        self.assertEqual([result[key] for key in ("voyage", "sailing_date", "containers", "station", "destination", "origin")],
                         ["035W", "10.1", "2X40HC", "远洋大亚", "Mersin", "QD"])

    def test_lcl_old_word_table_cells(self):
        result = values(
            "贵司在我司订舱出运的拼箱货物预配信息：\n"
            "船名/航次\x07SEASPAN PRIDE/640E\x07目的港\x07PUERTO QUETZAL\n"
            "预计开船日\x0710/4/2026\n入货地址\x07捷运保税区仓库(黄岛经济技术开发区前湾港路68号)"
        )
        self.assertEqual([result[key] for key in ("vessel", "voyage", "sailing_date", "containers", "station", "destination")],
                         ["SEASPAN PRIDE", "640E", "10.4", "LCL", "捷运保税区仓库", "PUERTO QUETZAL"])

    def test_zim_inline_etd_reversed_box_and_pickup(self):
        result = values(
            "提单号: ZIMUXNG1234567 ETD: 2026-10-02\n"
            "箱型箱数: 20DV×1\n提箱地点: 盛通永久 天津港跃进路与汽配路交口\n"
            "目的港: ITGOA"
        )
        self.assertEqual([result[key] for key in ("sailing_date", "containers", "station", "destination")],
                         ["10.2", "1X20GP", "盛通永久", "GENOVA"])

    def test_evergreen_empty_pickup_label_keeps_full_station_name(self):
        result = values("空箱提领处 :山東港口陸海國際物流日照有限公司\nPORT OF LOADING: RIZHAO")
        self.assertEqual(result["station"], "山東港口陸海國際物流日照有限公司")

    def test_one_dr_number_vessel_and_station(self):
        result = values(
            "D/R No. (编号)\nSHIPPER NAME\nROOM 100, SOME ROAD\n177FWWZUA0375\n"
            "场站：山港陆海联地（青岛）国际物流有限公司\n"
            "Ocean Vessel(船名) Voy. No. (航次)\nONE SERENITY -V.2639E\n"
            "Port of Discharge (卸货港)\nPUERTO QUETZAL PORT, GUATEMALA"
        )
        self.assertEqual([result[key] for key in ("bl_number", "vessel", "voyage", "station", "destination")],
                         ["177FWWZUA0375", "ONE SERENITY", "2639E", "山港陆海联地", "PUERTO QUETZAL"])

    def test_one_uses_proforma_etd_instead_of_pre_carrier_eta(self):
        result = normalize_fields(rule_extract(
            "Sales Rep: X Bill of Lading #: ONEYSZPGX4639300\n"
            "Pre Carrier : YM WINNER 050E Latest ETA/ETD : 15Oct26/18Oct26\n"
            "Place of Receipt : NANSHA, GUANGDONG Proforma 1st vessel ETD : 13Oct26\n"
            "Port of Loading : YANTIAN, GUANGDONG Terminal : YICT\n"
            "Port of Discharge : BARRANQUILLA Terminal : SOCIEDAD\n"
            "EQ Type/Q'ty : 40'DRY HC.-1"
        ))
        self.assertEqual([result[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "destination", "origin")],
                         ["ONEYSZPGX4639300", "YM WINNER", "050E", "10.13", "1X40HC", "BARRANQUILLA", "NS"])
        self.assertIn("Proforma 1st vessel", result["sailing_date"]["evidence"])
        self.assertIn("ETD", result["sailing_date"]["evidence"])

    def test_first_leg_eta_alone_does_not_fill_sailing_date(self):
        result = rule_extract("Pre Carrier : YM WINNER 050E Latest ETA/ETD : 15Oct26/18Oct26")
        self.assertEqual(result["sailing_date"]["value"], "")
        self.assertIn("ETA", result["sailing_date"]["review_reason"])

    def test_port_codes_country_suffix_and_inland_origin(self):
        self.assertEqual(values("PORT OF DISCHARGE: CAVAN ( VANCOUVER, BC )")["destination"], "VANCOUVER")
        self.assertEqual(values("PORT OF DISCHARGE: IDSUB")["destination"], "SURABAYA")
        self.assertEqual(values("PORT OF DISCHARGE: KAOHSIUNG,TAIWAN")["destination"], "KAOHSIUNG")
        self.assertEqual(values("PLACE OF RECEIPT: Zhengzhou\nPORT OF LOADING: Qingdao")["origin"], "ZZ-QD")


if __name__ == "__main__":
    unittest.main()
