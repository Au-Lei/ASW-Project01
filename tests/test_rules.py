"""Focused rules regression tests, preserved from the original workflow suite."""

import unittest
from unittest.mock import patch
from app.graph import comparable_value, extract
from app.nodes.rule_extract import rule_extract
from app.nodes.normalize import normalize_origin
from app.tools.document_reader import read_document


class RulesTests(unittest.TestCase):
    def test_each_single_document_is_extracted_without_prior_shipment(self):
        first = [{"name": "A委托书.pdf", "role": "订舱委托书", "data": b"first"}]
        second = [{"name": "B入货通知.pdf", "role": "入货通知", "data": b"second"}]
        with patch("app.graph.read_document", side_effect=["提单号: FIRST12345\n装货港: QINGDAO", "提单号: SECOND67890\n目的港: PORT KLANG WEST"]):
            first_result = extract(first, "rules")
            second_result = extract(second, "rules")
        self.assertEqual(first_result["fields"]["bl_number"]["value"], "FIRST12345")
        self.assertEqual(first_result["fields"]["origin"]["value"], "QD")
        self.assertEqual(second_result["fields"]["bl_number"]["value"], "SECOND67890")
        self.assertEqual(second_result["fields"]["destination"]["value"], "PORT KLANG WEST")
        self.assertEqual(second_result["fields"]["origin"]["value"], "")
        self.assertEqual(len(second_result["documents"]), 1)

    def test_two_column_notice_keeps_fields_separate(self):
        notice = (
            "船名/航次: XIN QIN HUANG DAO/135S   提单号: COAU9509489770\n"
            "装货港: QINGDAO, CHINA   目的港: PORT KLANG WEST\n"
            "船期: 2026/9/13   箱量: 40HC*1\n"
            "场站: 神州行场站"
        )
        fields = rule_extract(notice)
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "COAU9509489770", "vessel": "XIN QIN HUANG DAO", "voyage": "135S", "sailing_date": "9.13",
            "containers": "1X40HC", "station": "神州行场站", "destination": "PORT KLANG WEST", "origin": "QINGDAO, CHINA",
        })

    def test_real_case_1_notice_extracts_all_eight_target_fields(self):
        notice = (
            "贵司委托我司出口  QINGDAO CHINA -- PYEONGTAEK, SOUTH KOREA\n"
            "预计船期: 2026.09.24\n"
            "船名: PACIFIC SINGAPORE   航次: 2653E\n"
            "提单号: DSLPP2653EQD007\n"
            "箱型: 2X20GP\n"
            "场站: 青岛世腾克运物流有限公司\n"
        )
        fields = rule_extract(notice)
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "DSLPP2653EQD007", "vessel": "PACIFIC SINGAPORE", "voyage": "2653E",
            "sailing_date": "9.24", "containers": "2X20GP", "station": "青岛世腾克运",
            "destination": "PYEONGTAEK", "origin": "QINGDAO CHINA",
        })

    def test_real_case_1_document_merges_notice_and_entrustment(self):
        documents = [
            {"name": "委托书.doc", "role": "订舱委托书", "data": b"entrustment"},
            {"name": "入货通知.xls", "role": "入货通知", "data": b"notice"},
        ]
        entrustment = "目的港 PYEONGTAEK, KOREA\nLoading Port QINGDAO PORT,CHINA\nDischarging Port PYEONGTAEK, SOUTH KOREA"
        notice = "贵司委托我司出口 QINGDAO CHINA -- PYEONGTAEK, SOUTH KOREA\n预计船期: 2026.09.24\n船名: PACIFIC SINGAPORE   航次: 2653E\n提单号: DSLPP2653EQD007\n箱型: 2X20GP\n场站: 青岛世腾克运物流有限公司"
        with patch("app.graph.read_document", side_effect=[entrustment, notice]):
            fields = extract(documents, "rules")["fields"]
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "DSLPP2653EQD007", "vessel": "PACIFIC SINGAPORE", "voyage": "2653E",
            "sailing_date": "9.24", "containers": "2X20GP", "station": "青岛世腾克运",
            "destination": "PYEONGTAEK", "origin": "QD",
        })

    def test_real_case_2_old_word_notice_extracts_all_fields(self):
        notice = (
            "入 货 通 知\r"
            "贵司订舱的QINGDAO\xa0 TO   ISTANBUL\r"
            "船名/航次：CMA CGM MARCO POLO/0MEOTW1MA\r"
            "B/L NO.QGD3448819\r"
            "箱型/量:1*20GP\r"
            "预计开船期：2026-9-17\r"
            "场站：港捷丰（暂定 实际以打出小票的场站为准）\r"
        )
        fields = rule_extract(notice)
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "QGD3448819", "vessel": "CMA CGM MARCO POLO", "voyage": "0MEOTW1MA",
            "sailing_date": "9.17", "containers": "1X20GP", "station": "港捷丰",
            "destination": "ISTANBUL", "origin": "QINGDAO",
        })

    def test_real_case_2_notice_wins_old_entrustment_without_false_port_conflict(self):
        entrustment = "装运港:\xa0QINGDAO,CHINA\r卸货港:\xa0ISTANBUL,Turkey\r备注：ETD 8.15"
        notice = "贵司订舱的QINGDAO TO ISTANBUL\r预计开船期：2026-9-17\r船名/航次：CMA CGM MARCO POLO/0MEOTW1MA\rB/L NO.QGD3448819\r箱型/量:1*20GP\r场站：港捷丰（暂定）"
        documents = [{"name": "海运委托书.doc", "role": "订舱委托书", "data": b"entrustment"}, {"name": "入货通知.doc", "role": "入货通知", "data": b"notice"}]
        with patch("app.graph.read_document", side_effect=[entrustment, notice]):
            fields = extract(documents, "rules")["fields"]
        self.assertEqual(fields["sailing_date"]["value"], "9.17")
        self.assertEqual(fields["destination"]["value"], "ISTANBUL")
        self.assertEqual(fields["origin"]["value"], "QD")
        self.assertFalse(fields["destination"]["conflict"])
        self.assertFalse(fields["origin"]["conflict"])

    def test_real_case_3_booking_confirmation_extracts_without_inventing_station(self):
        confirmation = (
            "Booking Confirmation\nCNH1129869 Booking Date: 17-AUG-2026\n"
            "Shipping Order No.: Electronic Ref.: CNH1129869\n"
            "Vessel/Voyage: APL PUSAN / CS20C0S89\n"
            "Feeder Vessel/Voyage: / ETD: 19-SEP-2026 16:00\n"
            "Port of Loading: CNNSA ( NANSHA ) ETD: 19-SEP-2026 16:00\n"
            "Loading Terminal: Guangzhou South China Oceangate\n"
            "VGM Cut-Off Date/Time: 18-SEP-2026 08:00\n"
            "Port of Discharge: IDSRG ( SEMARANG ) Booking Pty. Ref.:\n"
            "Container Type / Size Total Gross Weight\n"
            "40HC GP WITHOUT VENTILATION HC X1 23.9\n"
            "1.起运港：黄埔\n2.起运港：南沙\n"
        )
        fields = rule_extract(confirmation)
        fields["origin"]["value"] = normalize_origin(fields["origin"]["value"])
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "CNH1129869", "vessel": "APL PUSAN", "voyage": "CS20C0S89",
            "sailing_date": "9.19", "containers": "1X40HC", "station": "",
            "destination": "IDSRG", "origin": "NS",
        })

    def test_real_case_4_wan_hai_notice_uses_so_number_and_confirmed_yard_alias(self):
        notice = (
            "入貨通知\n"
            "VSL/VOY: INTERASIA AMBITION/W003 ETD: 2026-09-17\n"
            "SO/NO: JIAB003359 B/L: 034G570630\n"
            "VOL: 1x40HQ\n"
            "PLD: NHAVA SHEVA, INDIA\n"
            "POD: NHAVA SHEVA, INDIA\n"
            "DEPOT: 青岛港联荣場站\n"
            "注: DEPOT: 青岛港联荣場站\n"
        )
        fields = rule_extract(notice)
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "JIAB003359", "vessel": "INTERASIA AMBITION", "voyage": "W003",
            "sailing_date": "9.17", "containers": "1X40HQ", "station": "青岛港",
            "destination": "NHAVA SHEVA", "origin": "QD",
        })
        self.assertIn("由场站推断", fields["origin"]["evidence"])

    def test_unrelated_depot_does_not_invent_origin(self):
        fields = rule_extract("DEPOT: 青岛其他场站\nPOD: NHAVA SHEVA, INDIA")
        self.assertEqual(fields["origin"]["value"], "")

    def test_real_case_5_single_container_certificate_uses_main_box_type(self):
        certificate = (
            "电子箱单凭证(按箱)\n"
            "提单号 W232695038 托运编号： LYCW26345177\n"
            "箱型/箱量： 40HQ 船公司： YML\n"
            "起运港： NINGBO 目的港： MONTREAL,QC\n"
            "船名/航次： YM MASCULINITY/108E\n"
            "截关时间： 2026-09-10 预计开航： 2026-09-15\n"
            "箱唯一标识：ILD37402126\n"
            "易港通预约信息\n箱主： YML 箱型： 40HC\n"
            "提箱堆场： 大榭集司\n"
        )
        fields = rule_extract(certificate)
        fields["origin"]["value"] = normalize_origin(fields["origin"]["value"])
        self.assertEqual({key: fields[key]["value"] for key in ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")}, {
            "bl_number": "W232695038", "vessel": "YM MASCULINITY", "voyage": "108E",
            "sailing_date": "9.15", "containers": "1X40HQ", "station": "大榭集司",
            "destination": "MONTREAL", "origin": "NB",
        })
        self.assertIn("按箱", fields["containers"]["evidence"])

    def test_box_type_without_single_box_context_does_not_invent_count(self):
        fields = rule_extract("箱型/箱量：40HQ\n箱主：YML 箱型：40HC")
        self.assertEqual(fields["containers"]["value"], "")

    def test_real_case_6_equivalent_box_types_and_lianyungang_abbreviation(self):
        entrustment = "备注信息：WHL  1X40HQ\nPort of discharge: BELAWAN"
        notice = (
            "提单号：127G504779 SO: LJDF6190699\n"
            "船期：2026-09-22\n船名航次:DONG FANG QIANG/2619S\n"
            "箱型箱量：1*40HC\nPOL: LIANYUNGANG,CHINA\n"
            "POD:BELAWAN, SUMATRA\n"
        )
        documents = [{"name": "委托.xls", "role": "订舱委托书", "data": b"xls"}, {"name": "入货通知.pdf", "role": "入货通知", "data": b"pdf"}]
        with patch("app.graph.read_document", side_effect=[entrustment, notice]):
            fields = extract(documents, "rules")["fields"]
        self.assertEqual(fields["containers"]["value"], "1X40HC")
        self.assertFalse(fields["containers"]["conflict"])
        self.assertEqual(fields["destination"]["value"], "BELAWAN, SUMATRA")
        self.assertEqual(fields["origin"]["value"], "LYG")

    def test_box_aliases_are_equivalent_without_hiding_different_sizes_or_reefer_use(self):
        self.assertEqual(comparable_value("containers", "1X20GP"), comparable_value("containers", "1X20DV"))
        self.assertEqual(comparable_value("containers", "1X40HQ"), comparable_value("containers", "1X40HC"))
        self.assertNotEqual(comparable_value("containers", "1X40HQ"), comparable_value("containers", "2X40HC"))
        self.assertNotEqual(comparable_value("containers", "1X40NOR"), comparable_value("containers", "1X40REEF"))

    def test_reef_as_dry_becomes_nor_only_with_explicit_context(self):
        self.assertEqual(rule_extract("箱量：1X40REEF 冻代干")["containers"]["value"], "1X40NOR")
        self.assertEqual(rule_extract("箱量：1X40REEF 冷代干")["containers"]["value"], "1X40NOR")
        self.assertEqual(rule_extract("箱量：1X40REEF")["containers"]["value"], "1X40REEF")
        self.assertEqual(rule_extract("箱量：1X20DV")["containers"]["value"], "1X20DV")

    def test_msc_booking_note_prefers_bill_and_reads_pickup_details(self):
        text = ("订舱号: 181AN26S4190223X1\n"
                "相关提柜地点\n20' DRY VAN\n1\nTotal 1\n"
                "船名/航次: MSC MARGRIT XIII / FK636A PROFORMA ETD:08-Sep-2026\n"
                "柜型/数量: 20' DRY VAN\n提单号: MEDUAEZ40641\n"
                "提柜地点: Dummy Depot (Guangzhou) 码头/堆场热线:\n")
        fields = rule_extract(text)
        self.assertEqual(fields["bl_number"]["value"], "MEDUAEZ40641")
        self.assertEqual(fields["sailing_date"]["value"], "9.8")
        self.assertEqual(fields["containers"]["value"], "1X20GP")
        self.assertEqual(fields["station"]["value"], "Dummy Depot (Guangzhou)")
        self.assertEqual(rule_extract("订舱号: 181AN26S4190223X1")["bl_number"]["value"], "181AN26S4190223X1")
        self.assertEqual(rule_extract("（LCL 必须要有唛头）")["containers"]["value"], "")

    def test_destination_can_follow_another_field_without_separator(self):
        fields = rule_extract("装货港: QINGDAO,CHINA目的港: PORT KLANG WEST\n目 的 港：PORT KLANG WEST")
        self.assertEqual(fields["destination"]["value"], "PORT KLANG WEST")

    def test_domestic_origin_uses_company_abbreviation(self):
        self.assertEqual(normalize_origin("QINGDAO, CHINA"), "QD")
        self.assertEqual(normalize_origin("TIANJIN XINGANG"), "TJ")
        self.assertEqual(normalize_origin("PORT KLANG"), "PORT KLANG")

    def test_notice_wins_and_conflict_is_visible(self):
        entrust = "PORT OF LOADING: QINGDAO\nPORT OF DISCHARGE: JAKARTA\n2X40HQ"
        notice = "BOOKING NUMBER : 2339673950\nETD : 14 Oct 2026\nDESPATCH QUANTITY FCL QTY : 3 X 40HQ"
        documents = [{"name": "委托书.pdf", "role": "订舱委托书", "data": b"first"}, {"name": "入货通知.pdf", "role": "入货通知", "data": b"second"}]
        with patch("app.graph.read_document", side_effect=[entrust, notice]):
            result = extract(documents, "rules")
        self.assertEqual(result["fields"]["sailing_date"]["value"], "10.14")
        self.assertEqual(result["fields"]["containers"]["value"], "3X40HQ")
        self.assertTrue(result["fields"]["containers"]["conflict"])
        self.assertEqual(result["fields"]["containers"]["source"], "入货通知.pdf")
        self.assertEqual(result["fields"]["origin"]["value"], "QD")
