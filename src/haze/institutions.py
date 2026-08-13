"""The demo institution set - single source of truth.

Six institutions, three roles (school / hospital / authority) in each of two
countries: West Kalimantan, Indonesia (the source region) and Sarawak,
Malaysia (the affected region across the border).

These are real places with approximate published coordinates. The *users* are
illustrative - no real personal data is involved anywhere in this system.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class Institution:
    id: str
    name: str
    type: str  # school | hospital | authority
    country: str  # ISO-3166-1 alpha-2
    country_name: str
    admin_region: str
    city: str
    lat: float
    lon: float
    population_served: int
    role: str  # source_region | affected_region
    contact_channels: tuple[str, ...] = ("sms", "whatsapp")
    languages: tuple[str, ...] = ("en",)
    recipient_group: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["contact_channels"] = list(self.contact_channels)
        d["languages"] = list(self.languages)
        return d

    def compact(self) -> dict:
        """Trimmed representation for embedding inside forecast/alert payloads."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "country": self.country,
            "city": self.city,
            "lat": self.lat,
            "lon": self.lon,
        }


INSTITUTIONS: tuple[Institution, ...] = (
    # ---- Source region: West Kalimantan, Indonesia -------------------------
    Institution(
        id="id-ptk-sman1",
        name="SMA Negeri 1 Pontianak",
        type="school",
        country="ID",
        country_name="Indonesia",
        admin_region="West Kalimantan",
        city="Pontianak",
        lat=-0.0263,
        lon=109.3425,
        population_served=1080,
        role="source_region",
        languages=("id", "en"),
        recipient_group="parents_sman1_pontianak",
    ),
    Institution(
        id="id-ptk-soedarso",
        name="RSUD dr. Soedarso",
        type="hospital",
        country="ID",
        country_name="Indonesia",
        admin_region="West Kalimantan",
        city="Pontianak",
        lat=-0.0554,
        lon=109.3389,
        population_served=4200,
        role="source_region",
        languages=("id", "en"),
        recipient_group="staff_rsud_soedarso",
    ),
    Institution(
        id="id-ptk-bpbd",
        name="BPBD Kota Pontianak",
        type="authority",
        country="ID",
        country_name="Indonesia",
        admin_region="West Kalimantan",
        city="Pontianak",
        lat=-0.0349,
        lon=109.3300,
        population_served=672000,  # city population under its remit
        role="source_region",
        languages=("id", "en"),
        recipient_group="public_pontianak",
    ),
    # ---- Affected region: Sarawak, Malaysia --------------------------------
    Institution(
        id="my-kch-greenroad",
        name="SMK Green Road",
        type="school",
        country="MY",
        country_name="Malaysia",
        admin_region="Sarawak",
        city="Kuching",
        lat=1.5385,
        lon=110.3560,
        population_served=1240,
        role="affected_region",
        languages=("ms", "en"),
        recipient_group="parents_smk_green_road",
    ),
    Institution(
        id="my-kch-hus",
        name="Hospital Umum Sarawak",
        type="hospital",
        country="MY",
        country_name="Malaysia",
        admin_region="Sarawak",
        city="Kuching",
        lat=1.5350,
        lon=110.3480,
        population_served=6800,
        role="affected_region",
        languages=("ms", "en"),
        recipient_group="staff_hospital_umum_sarawak",
    ),
    Institution(
        id="my-kch-jpbn",
        name="JPBN Sarawak (State Disaster Management Committee)",
        type="authority",
        country="MY",
        country_name="Malaysia",
        admin_region="Sarawak",
        city="Kuching",
        lat=1.5533,
        lon=110.3592,
        population_served=617900,
        role="affected_region",
        languages=("ms", "en"),
        recipient_group="public_kuching",
    ),
)

BY_ID: dict[str, Institution] = {i.id: i for i in INSTITUTIONS}
SITE_IDS: tuple[str, ...] = tuple(i.id for i in INSTITUTIONS)


def get(institution_id: str) -> Institution | None:
    return BY_ID.get(institution_id)


def by_country(country: str) -> list[Institution]:
    return [i for i in INSTITUTIONS if i.country == country.upper()]
