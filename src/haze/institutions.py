"""The demo institution set - single source of truth.

Six institutions, three roles (school / hospital / authority) in each of two
countries: West Kalimantan, Indonesia (the source region) and Sarawak,
Malaysia (the affected region across the border).

These are real places with approximate published coordinates. The *users* are
illustrative - no real personal data is involved anywhere in this system.

`population_served` is NOT uniformly sourced, and the difference matters if the
number is ever quoted as evidence:

  - The two `authority` sites carry real, cited figures - BPS for Kota
    Pontianak, DOSM for the state of Sarawak - with source, reference year and
    retrieval date recorded inline at each record.
  - The four school and hospital sites carry ILLUSTRATIVE figures with no
    source. They are plausible institution sizes, not published statistics.
    Do not cite them, and do not add a citation without an actual source to
    back it.
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
        # Population of the jurisdiction under this agency's remit: Kota
        # Pontianak (the city), which is what "Kota" in the agency name denotes.
        #
        #   Source:    BPS (Badan Pusat Statistik), Kota Pontianak
        #   Figure:    682.9 thousand  ->  682,900
        #   Reference: mid-year 2024 (most recent BPS figure available)
        #   Retrieved: 2026-08-14
        #
        # BPS publishes this series in thousands, so the figure is precise only
        # to the nearest hundred - do not present it as an exact headcount.
        #
        # A second, larger series exists and is NOT used here: Disdukcapil, the
        # civil registry, recorded 687,031 for semester II 2024 and 693,685 for
        # semester II 2025. That is an administrative count of registered
        # residents, a different method from the BPS census projection. Both are
        # legitimate; mixing them is not. Noted so this is not later "corrected"
        # to a Disdukcapil number without also changing the attribution.
        population_served=682900,
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
        # Population of the jurisdiction under this committee's remit: the whole
        # STATE of Sarawak, not Kuching. JPBN is the State Disaster Management
        # Committee, so a city-scale figure understated its remit by roughly
        # four times. The previous value here was 617,900 - city scale, and
        # uncited.
        #
        #   Source:    DOSM (Department of Statistics Malaysia),
        #              Population Table: States, series population_state
        #              https://storage.dosm.gov.my/population/population_state.csv
        #   Series:    state=Sarawak, sex=both, age=overall, ethnicity=overall
        #   Figure:    2,539.8 thousand  ->  2,539,800
        #   Reference: 2026 (most recent in the series; 2024 = 2,517,500 and
        #              2025 = 2,528,900 if a year matching the 2023 scenario
        #              window is wanted instead)
        #   Retrieved: 2026-08-14
        #
        # DOSM publishes this series in thousands, so as with Pontianak the
        # figure is precise only to the nearest hundred.
        population_served=2539800,
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
