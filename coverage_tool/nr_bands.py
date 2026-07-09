"""Tabela de bandas 5G NR (3GPP TS 38.101) — faixas de downlink em MHz.

Uso: escolher uma banda com --band e opcionalmente fixar a frequência exata
dentro da faixa com --freq-mhz. Se --freq-mhz não for passado, usa o centro
da faixa da banda escolhida.
"""

# band -> (f_min_MHz, f_max_MHz, duplex, apelido)
NR_BANDS = {
    "n1":   (2110, 2170, "FDD", "2100 MHz"),
    "n3":   (1805, 1880, "FDD", "1800 MHz"),
    "n5":   (869, 894, "FDD", "850 MHz"),
    "n7":   (2620, 2690, "FDD", "2600 MHz"),
    "n8":   (925, 960, "FDD", "900 MHz"),
    "n28":  (758, 803, "FDD", "700 MHz"),
    "n40":  (2300, 2400, "TDD", "2300 MHz"),
    "n41":  (2496, 2690, "TDD", "2600 MHz TDD"),
    "n77":  (3300, 4200, "TDD", "3.5 GHz (C-band)"),
    "n78":  (3300, 3800, "TDD", "3.5 GHz (C-band)"),
    "n79":  (4400, 5000, "TDD", "4.7 GHz"),
    "n257": (26500, 29500, "TDD", "mmWave 28 GHz"),
    "n258": (24250, 27500, "TDD", "mmWave 26 GHz"),
    "n260": (37000, 40000, "TDD", "mmWave 39 GHz"),
    "n261": (27500, 28350, "TDD", "mmWave 28 GHz"),
}


def resolve_frequency_mhz(band: str | None, freq_mhz: float | None) -> float:
    """Resolve a frequência de operação em MHz a partir da banda e/ou valor explícito."""
    if freq_mhz is not None:
        if band is not None:
            lo, hi, _, _ = NR_BANDS[band]
            if not (lo <= freq_mhz <= hi):
                raise ValueError(
                    f"--freq-mhz {freq_mhz} fora da faixa da banda {band} ({lo}-{hi} MHz)"
                )
        return freq_mhz

    if band is None:
        raise ValueError("Informe --band ou --freq-mhz")
    if band not in NR_BANDS:
        opts = ", ".join(sorted(NR_BANDS))
        raise ValueError(f"Banda '{band}' desconhecida. Opções: {opts}")
    lo, hi, _, _ = NR_BANDS[band]
    return (lo + hi) / 2
