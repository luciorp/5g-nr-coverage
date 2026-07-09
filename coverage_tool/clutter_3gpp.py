"""Perda de percurso estatística por cenário — 3GPP TR 38.901 Tabela 7.4.1-1.

Substitui o antigo offset fixo de clutter por um modelo que escala com
distância e frequência, combinando LOS/NLOS pela probabilidade de LOS de
cada cenário (RMa = macro rural, UMa = macro urbano) em vez de somar um
valor único de perda por cima da perda de espaço livre.

A perda retornada aqui SUBSTITUI a perda de espaço livre (ela já está
embutida nas fórmulas de PL_LOS) — não some FSPL por cima dela. A perda
por difração de relevo (ITU-R P.526, calculada à parte a partir do SRTM)
continua sendo somada: RMa/UMa assumem terreno essencialmente plano e
modelam apenas o clutter urbano médio (prédios), não morros/vales reais.

Combinação LOS/NLOS: em vez de sortear LOS/NLOS por ponto (o que
introduziria ruído aleatório num mapa que hoje é determinístico), usamos
a perda esperada ponderada pela probabilidade de LOS:
  PL = P_LOS(d) * PL_LOS(d) + (1 - P_LOS(d)) * PL_NLOS(d)
Simplificação comum em ferramentas de planejamento; a especificação em si
não define como combinar as duas em um valor único determinístico.
"""
from __future__ import annotations

import numpy as np

C_LIGHT = 299_792_458.0  # m/s


def _pl1_rma(d3d: np.ndarray, fc_ghz: float, h_building_m: float) -> np.ndarray:
    return (
        20 * np.log10(40 * np.pi * d3d * fc_ghz / 3)
        + min(0.03 * h_building_m ** 1.72, 10) * np.log10(d3d)
        - min(0.044 * h_building_m ** 1.72, 14.77)
        + 0.002 * np.log10(h_building_m) * d3d
    )


def rma_pathloss_db(
    d2d_m: np.ndarray, h_bs_m: float, h_ut_m: float, fc_ghz: float,
    h_building_m: float = 5.0, w_street_m: float = 20.0,
) -> np.ndarray:
    """RMa (Rural Macro), 3GPP TR 38.901 Tabela 7.4.1-1.

    Válido para d2D 10m-10km, fc 0.5-30GHz, h_BS 10-150m, h_UT 1-10m.
    """
    d2d = np.maximum(np.asarray(d2d_m, dtype=float), 10.0)
    d3d = np.sqrt(d2d ** 2 + (h_bs_m - h_ut_m) ** 2)

    d_bp = 2 * np.pi * h_bs_m * h_ut_m * (fc_ghz * 1e9) / C_LIGHT
    d3d_bp = np.sqrt(d_bp ** 2 + (h_bs_m - h_ut_m) ** 2)

    pl1 = _pl1_rma(d3d, fc_ghz, h_building_m)
    pl1_bp = _pl1_rma(d3d_bp, fc_ghz, h_building_m)
    pl2 = pl1_bp + 40 * np.log10(d3d / d3d_bp)
    pl_los = np.where(d2d <= d_bp, pl1, pl2)

    pl_nlos_raw = (
        161.04 - 7.1 * np.log10(w_street_m) + 7.5 * np.log10(h_building_m)
        - (24.37 - 3.7 * (h_building_m / h_bs_m) ** 2) * np.log10(h_bs_m)
        + (43.42 - 3.1 * np.log10(h_bs_m)) * (np.log10(d3d) - 3)
        + 20 * np.log10(fc_ghz)
        - (3.2 * (np.log10(11.75 * h_ut_m)) ** 2 - 4.97)
    )
    pl_nlos = np.maximum(pl_los, pl_nlos_raw)

    p_los = np.where(d2d <= 10.0, 1.0, np.exp(-(d2d - 10.0) / 1000.0))
    return p_los * pl_los + (1 - p_los) * pl_nlos


def uma_pathloss_db(
    d2d_m: np.ndarray, h_bs_m: float, h_ut_m: float, fc_ghz: float,
) -> np.ndarray:
    """UMa (Urban Macro), 3GPP TR 38.901 Tabela 7.4.1-1.

    Válido para d2D 10m-5km, fc 0.5-100GHz, h_BS ~25m, h_UT 1.5-22.5m.
    """
    d2d = np.maximum(np.asarray(d2d_m, dtype=float), 10.0)
    d3d = np.sqrt(d2d ** 2 + (h_bs_m - h_ut_m) ** 2)

    h_e = 1.0
    d_bp = max(4 * (h_bs_m - h_e) * (h_ut_m - h_e) * (fc_ghz * 1e9) / C_LIGHT, 1.0)
    d3d_bp = np.sqrt(d_bp ** 2 + (h_bs_m - h_ut_m) ** 2)

    pl1 = 28.0 + 22 * np.log10(d3d) + 20 * np.log10(fc_ghz)
    pl2 = 28.0 + 40 * np.log10(d3d) + 20 * np.log10(fc_ghz) - 9 * np.log10(d3d_bp ** 2)
    pl_los = np.where(d2d <= d_bp, pl1, pl2)

    pl_nlos_raw = 13.54 + 39.08 * np.log10(d3d) + 20 * np.log10(fc_ghz) - 0.6 * (h_ut_m - 1.5)
    pl_nlos = np.maximum(pl_los, pl_nlos_raw)

    if h_ut_m <= 13.0:
        c_factor = 0.0
    else:
        g = np.where(d2d > 18.0, 1.25e-6 * d2d ** 3 * np.exp(-d2d / 150.0), 0.0)
        c_factor = ((h_ut_m - 13.0) / 10.0) ** 1.5 * g

    p_los_far = (18.0 / d2d + np.exp(-d2d / 63.0) * (1 - 18.0 / d2d)) * (
        1 + c_factor * 5.0 / 4.0 * (d2d / 100.0) ** 3 * np.exp(-d2d / 150.0)
    )
    p_los = np.where(d2d <= 18.0, 1.0, p_los_far)
    return p_los * pl_los + (1 - p_los) * pl_nlos


# Mapeamento --environment -> cenário 3GPP + morfologia assumida.
# "dense_urban" não existe como cenário separado na 38.901: usamos UMa com
# uma margem extra fixa (heurística documentada, não parte da especificação).
SCENARIOS = {
    "rural": dict(model="rma", h_building_m=5.0, w_street_m=25.0, extra_db=0.0),
    "suburban": dict(model="rma", h_building_m=10.0, w_street_m=20.0, extra_db=0.0),
    "urban": dict(model="uma", extra_db=0.0),
    "dense_urban": dict(model="uma", extra_db=4.0),
}


def pathloss_db(
    environment: str, d2d_m: np.ndarray, h_bs_m: float, h_ut_m: float, fc_ghz: float,
) -> np.ndarray:
    cfg = SCENARIOS.get(environment, SCENARIOS["suburban"])
    if cfg["model"] == "rma":
        pl = rma_pathloss_db(d2d_m, h_bs_m, h_ut_m, fc_ghz, cfg["h_building_m"], cfg["w_street_m"])
    else:
        pl = uma_pathloss_db(d2d_m, h_bs_m, h_ut_m, fc_ghz)
    return pl + cfg["extra_db"]
