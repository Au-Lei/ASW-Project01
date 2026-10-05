"""Company conventions shared by extraction, review, and export."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldDefinition:
    key: str
    label: str
    cell: str
    automatic: bool = True


FIELD_DEFINITIONS = (
    FieldDefinition("bl_number", "提单号/订舱号", "B8"),
    FieldDefinition("vessel", "船名", "B9"),
    FieldDefinition("voyage", "航次", "E9"),
    FieldDefinition("sailing_date", "船期", "B10"),
    FieldDefinition("containers", "箱量及类型", "B11"),
    FieldDefinition("station", "场站", "B12"),
    FieldDefinition("destination", "目的港", "B13"),
    FieldDefinition("origin", "起运港", "E13"),
    FieldDefinition("carrier", "承运公司", "B4", False),
    FieldDefinition("sales", "揽货人", "B39", False),
    FieldDefinition("customer_service", "客服", "E3", False),
    FieldDefinition("contract", "合约", "E5", False),
)
STAFF_NAMES = {
    "sales": ["ROBIN", "DAVID", "SAM", "RUIBY", "BELL", "LUCKY", "CASSIE", "SVEN", "RICHI", "ECHO", "JASPER", "GAVIN", "JASON", "MIKE", "VICTOR"],
    "customer_service": ["SISSIE", "CELIA", "VIKY", "SIENNA", "MIA", "HELEN", "DROVAN", "JOCELYN", "IRIS"],
}
DOCUMENT_ROLES = frozenset({"订舱委托书", "入货通知"})
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx", ".doc", ".rtf", ".xls"})
EXTRACTION_MODES = frozenset({"rules", "ai"})
CONTAINER_EQUIVALENTS = {"DV": "GP", "HC": "HQ"}
ORIGIN_ALIASES = (
    (r"^(?:CNTAO|CNQDG)", "QD"),
    (r"^(?:QINGDAO|QINDAO|青岛|青島)", "QD"),
    (r"^(?:TIANJIN|天津)", "TJ"),
    (r"^(?:RIZHAO|日照)", "RZ"),
    (r"^(?:DALIAN|大连)", "DL"),
    (r"^(?:CNNSA|NANSHA|南沙)", "NS"),
    (r"^(?:NINGBO|宁波)", "NB"),
    (r"^(?:LIANYUNGANG|连云港|連雲港)", "LYG"),
)
COUNTRY_SUFFIXES = (
    "QATAR", "CHINA", "MALAYSIA", "INDONESIA", "INDIA", "JAPAN",
    "SOUTH KOREA", "KOREA", "THAILAND", "VIETNAM", "CANADA",
    "UNITED ARAB EMIRATES", "TURKEY", "PHILIPPINES", "BANGLADESH",
    "SINGAPORE", "AUSTRALIA", "UNITED STATES", "USA",
    "TAIWAN", "ARGENTINA", "GUATEMALA", "PEOPLE'S REPUBLIC OF CHINA",
)

# Codes observed in carrier confirmations. Keep this small and reviewed: never
# guess an unfamiliar overseas code from its spelling alone.
DESTINATION_PORT_CODES = {
    "CAVAN": "VANCOUVER",
    "IDSUB": "SURABAYA",
    "ITGOA": "GENOVA",
}


def review_config() -> dict:
    return {
        "fields": {f.key: f.label for f in FIELD_DEFINITIONS if f.automatic},
        "manual_fields": {f.key: f.label for f in FIELD_DEFINITIONS if not f.automatic},
        "staff_names": {key: list(names) for key, names in STAFF_NAMES.items()},
    }
