"""The family palette: 32 named palettes as plain data.

Eight hue families, four tones each. The catalog is a convention shared by every primary tool
in the ASI FuSa Tools; the authority is the section "The family palette" in ``ASI_FUSA_TOOLS.md``, and
each tool carries this module byte for byte. It imports nothing but ``Palette`` and typing
names, so no tool ever imports a sibling. A test hashes ``CATALOG`` and compares it with the
digest below; edit the table and the test fails until the family file, and the sibling, agree.

Key = ``<family>-<tone>``, title = ``<Family> <Tone>``. Tones run darkest first: ``noir``
(near-black, tinted, deep primary), ``neon`` (near-black, full neon), ``dusk`` (charcoal,
softened neon), ``day`` (pale tint, white fields, saturated ink).

Digest (SHA-1 of ``json.dumps({key: {slot: hex}}, sort_keys=True, separators=(",", ":"))``):
``befcfc0c8dca5479620badf1d23e2448db757910``.
"""

from typing import NamedTuple

from .theme import Palette

FAMILIES: tuple[str, ...] = ("cyan", "blue", "violet", "pink", "red", "amber", "gold", "green")
TONES: tuple[str, ...] = ("noir", "neon", "dusk", "day")
CATALOG_DIGEST = "befcfc0c8dca5479620badf1d23e2448db757910"


class PaletteEntry(NamedTuple):
    title: str
    family: str
    tone: str
    palette: Palette


def _entry(title: str, family: str, tone: str, *colours: str) -> PaletteEntry:
    bg, panel, field, grid, stripe, primary, primary_dim, accent, text, muted, on_primary, selection = colours
    return PaletteEntry(title, family, tone, Palette(
        bg=bg, panel=panel, field=field, grid=grid, stripe=stripe, primary=primary, primary_dim=primary_dim,
        accent=accent, text=text, muted=muted, on_primary=on_primary, selection=selection,
    ))


# slot order: bg panel field grid stripe primary primary_dim accent text muted on_primary selection
CATALOG: dict[str, PaletteEntry] = {
    "cyan-noir": _entry(
        "Cyan Noir", "cyan", "noir",
        "#03090a", "#061113", "#0b191c", "#14363d", "#0d1f23", "#12c0e2",
        "#0f758a", "#ec7813", "#b3d4db", "#508a95", "#051214", "#17464f",
    ),
    "cyan-neon": _entry(
        "Cyan Neon", "cyan", "neon",
        "#040e10", "#081b1f", "#0b2328", "#114550", "#0e2a2f", "#1ad9ff",
        "#0d88a0", "#ff851a", "#c9f0f7", "#609da9", "#03171c", "#125a68",
    ),
    "cyan-dusk": _entry(
        "Cyan Dusk", "cyan", "dusk",
        "#152123", "#1d2d30", "#243538", "#365c63", "#2a3d41", "#55d7f1",
        "#2d9db4", "#f19e55", "#dfeaec", "#8babb1", "#0a2429", "#326b76",
    ),
    "cyan-day": _entry(
        "Cyan Day", "cyan", "day",
        "#f2f9fb", "#e1f1f4", "#ffffff", "#b3d4db", "#edf6f7", "#0b7286",
        "#2b98ad", "#b35909", "#152528", "#627e84", "#fafcfc", "#c2e8f0",
    ),
    "blue-noir": _entry(
        "Blue Noir", "blue", "noir",
        "#03050a", "#060b13", "#0b111c", "#14233d", "#0d1523", "#3277ee",
        "#1657c8", "#ecb613", "#b3c2db", "#506a95", "#050b14", "#172c4f",
    ),
    "blue-neon": _entry(
        "Blue Neon", "blue", "neon",
        "#040910", "#08101f", "#0b1628", "#112850", "#0e1a2f", "#2977ff",
        "#1157d0", "#ffc61a", "#c9daf7", "#607ba9", "#030c1c", "#123268",
    ),
    "blue-dusk": _entry(
        "Blue Dusk", "blue", "dusk",
        "#151a23", "#1d2430", "#242b38", "#364663", "#2a3241", "#558ef1",
        "#3066c2", "#f1ca55", "#dfe4ec", "#8b99b1", "#0a1529", "#324b76",
    ),
    "blue-day": _entry(
        "Blue Day", "blue", "day",
        "#f2f5fb", "#e1e8f4", "#ffffff", "#b3c2db", "#edf1f7", "#0f4fbd",
        "#3b71ce", "#8d6b07", "#151c28", "#626e84", "#fafbfc", "#c2d3f0",
    ),
    "violet-noir": _entry(
        "Violet Noir", "violet", "noir",
        "#06030a", "#0c0613", "#130b1c", "#27143d", "#170d23", "#9d53f1",
        "#7d20e6", "#ecc813", "#c6b3db", "#725197", "#0c0514", "#31174f",
    ),
    "violet-neon": _entry(
        "Violet Neon", "violet", "neon",
        "#0a0410", "#12081f", "#190b28", "#2e1150", "#1d0e2f", "#a14fff",
        "#7e1ded", "#ffd91a", "#dfc9f7", "#8260a9", "#0e031c", "#3a1268",
    ),
    "violet-dusk": _entry(
        "Violet Dusk", "violet", "dusk",
        "#1c1523", "#261d30", "#2d2438", "#4b3663", "#352a41", "#ab6df3",
        "#8543d0", "#f1d755", "#e5dfec", "#9d8bb1", "#180a29", "#523276",
    ),
    "violet-day": _entry(
        "Violet Day", "violet", "day",
        "#f6f2fb", "#eae1f4", "#ffffff", "#c6b3db", "#f2edf7", "#600fbd",
        "#803bce", "#836e07", "#1e1528", "#726284", "#fbfafc", "#d7c2f0",
    ),
    "pink-noir": _entry(
        "Pink Noir", "pink", "noir",
        "#0a0306", "#13060d", "#1c0b13", "#3d1429", "#230d18", "#ec1380",
        "#b51465", "#13daec", "#dbb3c7", "#955073", "#14050d", "#4f1733",
    ),
    "pink-neon": _entry(
        "Pink Neon", "pink", "neon",
        "#10040a", "#1f0813", "#280b1a", "#501130", "#2f0e1f", "#ff1a8c",
        "#b80f63", "#1aecff", "#f7c9e0", "#a96085", "#1c030f", "#68123d",
    ),
    "pink-dusk": _entry(
        "Pink Dusk", "pink", "dusk",
        "#23151c", "#301d26", "#38242e", "#63364d", "#412a36", "#f155a3",
        "#ba2e74", "#55e4f1", "#ecdfe6", "#b18b9e", "#290a1a", "#763254",
    ),
    "pink-day": _entry(
        "Pink Day", "pink", "day",
        "#fbf2f6", "#f4e1eb", "#ffffff", "#dbb3c7", "#f7edf2", "#bd0f66",
        "#ce3b85", "#077d88", "#28151f", "#846273", "#fcfafb", "#f0c2d9",
    ),
    "red-noir": _entry(
        "Red Noir", "red", "noir",
        "#0a0304", "#130608", "#1c0b0d", "#3d141a", "#230d10", "#ed2641",
        "#ba152b", "#13c8ec", "#dbb3b9", "#95505a", "#140507", "#4f171e",
    ),
    "red-neon": _entry(
        "Red Neon", "red", "neon",
        "#100406", "#1f080b", "#280b0f", "#501119", "#2f0e12", "#ff1a38",
        "#bd0f26", "#1ad9ff", "#f7c9d0", "#a9606a", "#1c0306", "#68121e",
    ),
    "red-dusk": _entry(
        "Red Dusk", "red", "dusk",
        "#231517", "#301d1f", "#382426", "#63363c", "#412a2d", "#f1556a",
        "#c03043", "#55d7f1", "#ecdfe1", "#b18b90", "#290a0e", "#76323b",
    ),
    "red-day": _entry(
        "Red Day", "red", "day",
        "#fbf2f3", "#f4e1e4", "#ffffff", "#dbb3b9", "#f7edef", "#bd0f26",
        "#ce3b4f", "#087a91", "#281518", "#846266", "#fcfafa", "#f0c2c8",
    ),
    "amber-noir": _entry(
        "Amber Noir", "amber", "noir",
        "#0a0603", "#130c06", "#1c130b", "#3d2714", "#23170d", "#e27312",
        "#934d10", "#13c8ec", "#dbc6b3", "#957050", "#140c05", "#4f3117",
    ),
    "amber-neon": _entry(
        "Amber Neon", "amber", "neon",
        "#100a04", "#1f1208", "#28190b", "#502e11", "#2f1d0e", "#ff851a",
        "#a0520d", "#1ad9ff", "#f7dfc9", "#a98260", "#1c0e03", "#683a12",
    ),
    "amber-dusk": _entry(
        "Amber Dusk", "amber", "dusk",
        "#231c15", "#30261d", "#382d24", "#634b36", "#41352a", "#f19e55",
        "#b46c2d", "#55d7f1", "#ece5df", "#b19d8b", "#29180a", "#765232",
    ),
    "amber-day": _entry(
        "Amber Day", "amber", "day",
        "#fbf6f2", "#f4eae1", "#ffffff", "#dbc6b3", "#f7f2ed", "#a0520d",
        "#c87832", "#087c94", "#281e15", "#847262", "#fcfbfa", "#f0d7c2",
    ),
    "gold-noir": _entry(
        "Gold Noir", "gold", "noir",
        "#0a0803", "#131106", "#1c180b", "#3d3514", "#231f0d", "#e2b912",
        "#8a710f", "#397cef", "#dbd3b3", "#958750", "#141105", "#4f4417",
    ),
    "gold-neon": _entry(
        "Gold Neon", "gold", "neon",
        "#100e04", "#1f1a08", "#28220b", "#504311", "#2f290e", "#ffd11a",
        "#a0830d", "#337eff", "#f7eec9", "#a99b60", "#1c1703", "#685712",
    ),
    "gold-dusk": _entry(
        "Gold Dusk", "gold", "dusk",
        "#232015", "#302c1d", "#383424", "#635a36", "#413d2a", "#f1d255",
        "#b4992d", "#558ef1", "#ece9df", "#b1aa8b", "#29230a", "#766832",
    ),
    "gold-day": _entry(
        "Gold Day", "gold", "day",
        "#fbf9f2", "#f4f0e1", "#ffffff", "#dbd3b3", "#f7f5ed", "#7f680a",
        "#a58c29", "#0b51cb", "#282415", "#847d62", "#fcfcfa", "#f0e7c2",
    ),
    "green-noir": _entry(
        "Green Noir", "green", "noir",
        "#030a06", "#06130c", "#0b1c12", "#143d25", "#0d2316", "#12e269",
        "#0f8a42", "#ec13b6", "#b3dbc4", "#50956d", "#05140b", "#174f2e",
    ),
    "green-neon": _entry(
        "Green Neon", "green", "neon",
        "#041009", "#081f11", "#0b2817", "#11502b", "#0e2f1c", "#1aff79",
        "#0da04a", "#ff1ac6", "#c9f7dd", "#60a97e", "#031c0d", "#126836",
    ),
    "green-dusk": _entry(
        "Green Dusk", "green", "dusk",
        "#15231b", "#1d3025", "#24382c", "#366349", "#2a4134", "#55f196",
        "#2db465", "#f155ca", "#dfece4", "#8bb19b", "#0a2917", "#32764f",
    ),
    "green-day": _entry(
        "Green Day", "green", "day",
        "#f2fbf5", "#e1f4e9", "#ffffff", "#b3dbc4", "#edf7f1", "#0a7b39",
        "#28a15b", "#cb0b9b", "#15281d", "#628470", "#fafcfb", "#c2f0d5",
    ),
}
