"""Dados de elevação de terreno (SRTM) via API pública gratuita Open-Topo-Data
(https://www.opentopodata.org/), sem necessidade de GDAL/rasterio.

Estratégia: em vez de consultar a API para cada ponto de perfil (caro e sujeito
a rate limit), amostramos uma grade regular de elevação cobrindo a área de
interesse UMA vez, e interpolamos (bilinear) qualquer ponto/perfil a partir
dessa grade em memória. Resultado é cacheado em disco por área+resolução.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import requests
from scipy.interpolate import RegularGridInterpolator

OPEN_TOPO_URL = "https://api.opentopodata.org/v1/{dataset}"
MAX_LOCATIONS_PER_REQUEST = 100
REQUEST_INTERVAL_S = 1.05  # servidor público limita a ~1 req/s

METERS_PER_DEG_LAT = 111_320.0


def _meters_per_deg_lon(lat_deg: float) -> float:
    return METERS_PER_DEG_LAT * math.cos(math.radians(lat_deg))


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class TerrainGrid:
    """Grade regular de elevações (metros) com interpolação bilinear."""

    def __init__(self, lats: np.ndarray, lons: np.ndarray, elev: np.ndarray):
        self.lats = lats
        self.lons = lons
        self.elev = elev
        self._interp = RegularGridInterpolator(
            (lats, lons), elev, method="linear", bounds_error=False, fill_value=None
        )

    def elevation_at(self, lat, lon):
        pts = np.column_stack([np.atleast_1d(lat), np.atleast_1d(lon)])
        vals = self._interp(pts)
        return vals if np.ndim(lat) else float(vals[0])

    def profile(self, lat0, lon0, lat1, lon1, n_samples: int = 32):
        """Amostra elevações ao longo do segmento reto entre dois pontos.

        Retorna (dist_m: array[n_samples], elev_m: array[n_samples]).
        """
        t = np.linspace(0.0, 1.0, n_samples)
        lats = lat0 + (lat1 - lat0) * t
        lons = lon0 + (lon1 - lon0) * t
        elevs = self.elevation_at(lats, lons)
        d_total = haversine_m(lat0, lon0, lat1, lon1)
        dists = t * d_total
        return dists, elevs


def _cache_path(cache_dir: Path, key: str) -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return cache_dir / f"terrain_{h}.json"


def fetch_elevation_grid(
    center_lat: float,
    center_lon: float,
    radius_km: float,
    resolution: int = 40,
    dataset: str = "srtm30m",
    cache_dir: Path | None = None,
    timeout_s: float = 15.0,
) -> TerrainGrid:
    """Baixa (ou lê do cache) uma grade resolution x resolution de elevações
    cobrindo um quadrado de lado 2*radius_km centrado em (center_lat, center_lon).
    """
    cache_dir = cache_dir or Path.cwd() / ".terrain_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    dlat = radius_km * 1000.0 / METERS_PER_DEG_LAT
    dlon = radius_km * 1000.0 / _meters_per_deg_lon(center_lat)
    lats = np.linspace(center_lat - dlat, center_lat + dlat, resolution)
    lons = np.linspace(center_lon - dlon, center_lon + dlon, resolution)

    cache_key = f"{dataset}:{center_lat:.5f}:{center_lon:.5f}:{radius_km}:{resolution}"
    cpath = _cache_path(cache_dir, cache_key)
    if cpath.exists():
        data = json.loads(cpath.read_text())
        elev = np.array(data["elev"], dtype=float).reshape(resolution, resolution)
        return TerrainGrid(lats, lons, elev)

    grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")
    flat_lat = grid_lat.ravel()
    flat_lon = grid_lon.ravel()
    n = flat_lat.size
    elev_flat = np.empty(n, dtype=float)

    url = OPEN_TOPO_URL.format(dataset=dataset)
    session = requests.Session()
    for start in range(0, n, MAX_LOCATIONS_PER_REQUEST):
        end = min(start + MAX_LOCATIONS_PER_REQUEST, n)
        locations = "|".join(
            f"{flat_lat[i]:.6f},{flat_lon[i]:.6f}" for i in range(start, end)
        )
        resp = _post_with_retry(session, url, locations, timeout_s)
        results = resp.json()["results"]
        for i, r in enumerate(results):
            e = r.get("elevation")
            elev_flat[start + i] = 0.0 if e is None else float(e)
        if end < n:
            time.sleep(REQUEST_INTERVAL_S)

    elev = elev_flat.reshape(resolution, resolution)
    cpath.write_text(json.dumps({"elev": elev.tolist()}))
    return TerrainGrid(lats, lons, elev)


def _post_with_retry(session, url, locations, timeout_s, retries: int = 3):
    last_exc = None
    for attempt in range(retries):
        try:
            resp = session.post(url, data={"locations": locations}, timeout=timeout_s)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            resp.raise_for_status()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(
        f"Falha ao consultar API de elevação ({url}) após {retries} tentativas: {last_exc}"
    )


class FlatTerrain:
    """Terreno plano (elevação 0 em todos os pontos) — usado quando --no-terrain
    é passado ou como fallback se a API de elevação estiver indisponível."""

    def elevation_at(self, lat, lon):
        if np.ndim(lat):
            return np.zeros_like(np.atleast_1d(lat), dtype=float)
        return 0.0

    def profile(self, lat0, lon0, lat1, lon1, n_samples: int = 32):
        t = np.linspace(0.0, 1.0, n_samples)
        d_total = haversine_m(lat0, lon0, lat1, lon1)
        return t * d_total, np.zeros(n_samples)
