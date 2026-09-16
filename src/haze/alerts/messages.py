"""Mocked last-mile notification content.

These are the messages indirect beneficiaries - parents, patients, the general
public - would receive. Nothing is actually sent: this MVP has no SMS or
WhatsApp integration, and every generated notification is flagged
`simulated: true` in the API.

Templates are written in the language the recipients actually use: Indonesian
for West Kalimantan, Malay for Sarawak, with English fallback.
"""

from __future__ import annotations

from datetime import datetime

from ..institutions import Institution

# Local time offsets. Both regions are UTC+8 (WITA / MYT) and neither observes
# daylight saving, so a fixed offset is correct here.
LOCAL_UTC_OFFSET_HOURS = 8

_SEVERITY_TEXT = {
    "id": {
        "UNHEALTHY_SENSITIVE": "tidak sehat bagi kelompok sensitif",
        "UNHEALTHY": "tidak sehat",
        "VERY_UNHEALTHY": "sangat tidak sehat",
        "HAZARDOUS": "berbahaya",
    },
    "ms": {
        "UNHEALTHY_SENSITIVE": "tidak sihat bagi kumpulan sensitif",
        "UNHEALTHY": "tidak sihat",
        "VERY_UNHEALTHY": "sangat tidak sihat",
        "HAZARDOUS": "berbahaya",
    },
    "en": {
        "UNHEALTHY_SENSITIVE": "unhealthy for sensitive groups",
        "UNHEALTHY": "unhealthy",
        "VERY_UNHEALTHY": "very unhealthy",
        "HAZARDOUS": "hazardous",
    },
}

_MONTHS = {
    "id": ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
    "ms": ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogo", "Sep", "Okt", "Nov", "Dis"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}

_TEMPLATES = {
    "id": (
        "PERINGATAN ASAP - {city}: Kualitas udara di {name} diperkirakan mencapai "
        "tingkat {severity} pada {when} (PM2.5 ~{pm:.0f} ug/m3). {action} "
        "Peringatan dikeluarkan {lead} jam sebelumnya."
    ),
    "ms": (
        "AMARAN JEREBU - {city}: Kualiti udara di {name} dijangka mencapai tahap "
        "{severity} pada {when} (PM2.5 ~{pm:.0f} ug/m3). {action} "
        "Amaran dikeluarkan {lead} jam lebih awal."
    ),
    "en": (
        "HAZE ALERT - {city}: Air quality at {name} is forecast to reach "
        "{severity} levels at {when} (PM2.5 ~{pm:.0f} ug/m3). {action} "
        "Warning issued {lead} hours in advance."
    ),
}

_ACTION_LINE = {
    "id": {
        "school": "Kegiatan luar ruangan dibatalkan.",
        "hospital": "Pasien pernapasan harap tetap di dalam ruangan.",
        "authority": "Warga diimbau tetap di dalam ruangan dan gunakan masker N95.",
    },
    "ms": {
        "school": "Aktiviti luar dibatalkan.",
        "hospital": "Pesakit pernafasan dinasihati kekal di dalam bangunan.",
        "authority": "Orang ramai dinasihati kekal di dalam dan memakai pelitup N95.",
    },
    "en": {
        "school": "Outdoor activities are cancelled.",
        "hospital": "Respiratory patients should remain indoors.",
        "authority": "Residents are advised to stay indoors and wear an N95 mask.",
    },
}


def _format_local(dt: datetime, lang: str) -> str:
    from datetime import timedelta

    local = dt + timedelta(hours=LOCAL_UTC_OFFSET_HOURS)
    month = _MONTHS.get(lang, _MONTHS["en"])[local.month - 1]
    return f"{local.day} {month}, {local:%H:%M}"


def default_language(inst: Institution) -> str:
    return inst.languages[0] if inst.languages else "en"


def render(
    inst: Institution,
    severity: str,
    peak_pm25: float,
    peak_at: datetime,
    lead_hours: int,
    language: str | None = None,
) -> str:
    """Render the last-mile message for one institution's audience."""
    lang = language or default_language(inst)
    if lang not in _TEMPLATES:
        lang = "en"

    severity_text = _SEVERITY_TEXT[lang].get(
        severity, _SEVERITY_TEXT[lang]["UNHEALTHY_SENSITIVE"]
    )
    action = _ACTION_LINE[lang].get(inst.type, _ACTION_LINE[lang]["authority"])

    return _TEMPLATES[lang].format(
        city=inst.city,
        name=inst.name,
        severity=severity_text,
        when=_format_local(peak_at, lang),
        pm=peak_pm25,
        action=action,
        lead=lead_hours,
    )
