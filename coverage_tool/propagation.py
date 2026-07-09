"""Modelo de propagação híbrido para cobertura 5G NR:

  RSRP(dBm) = P_tx(dBm) + G_antena(phi,theta) - FSPL - L_difracao - L_clutter

Referências:
  - FSPL: ITU-R P.525
  - Difração de gume-de-faca (perda adicional por obstrução de relevo):
    ITU-R P.526 §4.1, com escolha do ponto de pior obstrução ao longo do
    perfil (construção tipo Bullington, ITU-R P.526 §4.3).
  - Padrão de antena setorizada: 3GPP TR 38.901 Tabela 7.3-1.
  - Perda de clutter: offset típico de planejamento por tipo de ambiente
    (simplificação; não substitui um modelo estatístico completo tipo
    Okumura-Hata / 3GPP 38.901 UMa-RMa).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .terrain import haversine_m

C_LIGHT = 299_792_458.0  # m/s

CLUTTER_LOSS_DB = {
    "rural": 0.0,
    "suburban": 5.0,
    "urban": 10.0,
    "dense_urban": 16.0,
}


def fspl_db(distance_m: np.ndarray, freq_mhz: float) -> np.ndarray:
    d_km = np.maximum(distance_m, 1.0) / 1000.0
    return 32.44 + 20 * np.log10(d_km) + 20 * np.log10(freq_mhz)


def knife_edge_diffraction_loss_db(
    terrain, tx_lat, tx_lon, tx_height_m, rx_lat, rx_lon, rx_height_m,
    freq_mhz: float, n_profile_samples: int = 32,
) -> float:
    """Perda de difração (dB) pelo pior obstáculo do perfil TX->RX.

    Usa o parâmetro de Fresnel-Kirchhoff v e a aproximação da ITU-R P.526:
      J(v) = 6.9 + 20*log10( sqrt((v-0.1)^2 + 1) + v - 0.1 ),  v > -0.78
      J(v) = 0,                                                v <= -0.78
    """
    dists, elevs = terrain.profile(tx_lat, tx_lon, rx_lat, rx_lon, n_profile_samples)
    d_total = dists[-1]
    if d_total < 10.0:
        return 0.0  # ponto colado à antena: sem obstrução relevante

    tx_asl = elevs[0] + tx_height_m
    rx_asl = elevs[-1] + rx_height_m
    los_height = tx_asl + (rx_asl - tx_asl) * (dists / d_total)
    obstruction = elevs - los_height  # >0 => terreno acima da linha de visada

    d1 = dists[1:-1]
    d2 = d_total - d1
    h = obstruction[1:-1]
    if h.size == 0:
        return 0.0

    wavelength_m = C_LIGHT / (freq_mhz * 1e6)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = h * np.sqrt(2.0 * d_total / (wavelength_m * np.maximum(d1 * d2, 1e-6)))

    v_max = float(np.nanmax(v)) if v.size else -999.0
    if v_max <= -0.78:
        return 0.0
    j = 6.9 + 20 * math.log10(math.sqrt((v_max - 0.1) ** 2 + 1) + v_max - 0.1)
    return max(j, 0.0)


@dataclass
class AntennaConfig:
    gain_dbi: float
    azimuth_deg: float = 0.0        # 0 = norte, sentido horário
    downtilt_deg: float = 0.0       # positivo = inclinado para baixo
    h_beamwidth_deg: float | None = 65.0   # None => onidirecional na horizontal
    v_beamwidth_deg: float | None = 65.0   # None => sem padrão vertical
    front_to_back_db: float = 30.0  # A_max / SLA_max (3GPP TR 38.901)


def _bearing_deg(lat0, lon0, lat1, lon1) -> np.ndarray:
    p1, p2 = np.radians(lat0), np.radians(lat1)
    dl = np.radians(np.asarray(lon1) - lon0)
    x = np.sin(dl) * np.cos(p2)
    y = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0


def _wrap_180(angle_deg):
    return (angle_deg + 180.0) % 360.0 - 180.0


def antenna_gain_db(
    ant: AntennaConfig, tx_lat, tx_lon, tx_height_m,
    rx_lat, rx_lon, rx_height_m, distance_m,
) -> np.ndarray:
    """Ganho de antena (dBi) na direção de cada ponto RX, seguindo o padrão
    setorizado combinado do 3GPP TR 38.901 (Tabela 7.3-1)."""
    atten_h = 0.0
    if ant.h_beamwidth_deg:
        bearing = _bearing_deg(tx_lat, tx_lon, rx_lat, rx_lon)
        phi = _wrap_180(bearing - ant.azimuth_deg)
        atten_h = np.minimum(12.0 * (phi / ant.h_beamwidth_deg) ** 2, ant.front_to_back_db)

    atten_v = 0.0
    if ant.v_beamwidth_deg:
        horiz_dist = np.maximum(distance_m, 1.0)
        elevation_deg = np.degrees(np.arctan2(tx_height_m - rx_height_m, horiz_dist))
        theta_offset = elevation_deg - (-ant.downtilt_deg)
        atten_v = np.minimum(12.0 * (theta_offset / ant.v_beamwidth_deg) ** 2, ant.front_to_back_db)

    atten_total = np.minimum(atten_h + atten_v, ant.front_to_back_db)
    return ant.gain_dbi - atten_total


@dataclass
class LinkParams:
    tx_power_dbm: float
    freq_mhz: float
    tx_height_m: float
    rx_height_m: float = 1.5
    environment: str = "suburban"
    n_profile_samples: int = 32


def rsrp_grid(
    terrain, ant: AntennaConfig, link: LinkParams,
    tx_lat: float, tx_lon: float, rx_lats: np.ndarray, rx_lons: np.ndarray,
) -> np.ndarray:
    """Calcula RSRP (dBm) para um array de pontos RX (mesma forma de rx_lats)."""
    shape = rx_lats.shape
    flat_lat = rx_lats.ravel()
    flat_lon = rx_lons.ravel()
    n = flat_lat.size

    distances = np.array([haversine_m(tx_lat, tx_lon, la, lo) for la, lo in zip(flat_lat, flat_lon)])
    loss_fspl = fspl_db(distances, link.freq_mhz)

    loss_diff = np.array([
        knife_edge_diffraction_loss_db(
            terrain, tx_lat, tx_lon, link.tx_height_m, la, lo, link.rx_height_m,
            link.freq_mhz, link.n_profile_samples,
        )
        for la, lo in zip(flat_lat, flat_lon)
    ])

    gain = antenna_gain_db(
        ant, tx_lat, tx_lon, link.tx_height_m, flat_lat, flat_lon, link.rx_height_m, distances
    )

    clutter_db = CLUTTER_LOSS_DB.get(link.environment, 5.0)

    rsrp = link.tx_power_dbm + gain - loss_fspl - loss_diff - clutter_db
    return rsrp.reshape(shape)
