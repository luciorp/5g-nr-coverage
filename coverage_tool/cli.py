"""CLI: gera um mapa de cobertura 5G NR (HTML interativo) a partir dos
parâmetros do rádio, da antena e do relevo (SRTM via Open-Topo-Data)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from .mapviz import build_map
from .nr_bands import NR_BANDS, resolve_frequency_mhz
from .propagation import AntennaConfig, LinkParams, rsrp_grid
from .terrain import FlatTerrain, METERS_PER_DEG_LAT, _meters_per_deg_lon, fetch_elevation_grid


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Simulador de cobertura 5G NR")

    site = p.add_argument_group("Site / antena")
    site.add_argument("--lat", type=float, required=True, help="Latitude da antena")
    site.add_argument("--lon", type=float, required=True, help="Longitude da antena")
    site.add_argument("--antenna-height-m", type=float, default=30.0, help="Altura da antena (m AGL)")
    site.add_argument("--rx-height-m", type=float, default=1.5, help="Altura do terminal receptor (m)")
    site.add_argument("--azimuth-deg", type=float, default=0.0, help="Azimute do setor (0=Norte, horário)")
    site.add_argument("--downtilt-deg", type=float, default=2.0, help="Downtilt (graus, positivo p/ baixo)")
    site.add_argument("--h-beamwidth-deg", type=float, default=65.0,
                       help="Largura de feixe horizontal (graus). Use 0 para onidirecional")
    site.add_argument("--v-beamwidth-deg", type=float, default=65.0,
                       help="Largura de feixe vertical (graus). Use 0 para desativar padrão vertical")

    radio = p.add_argument_group("Rádio")
    radio.add_argument("--band", choices=sorted(NR_BANDS), help="Banda NR (ex: n78, n41, n28)")
    radio.add_argument("--freq-mhz", type=float, help="Frequência exata em MHz (dentro da banda, se informada)")
    radio.add_argument("--tx-power-dbm", type=float, default=43.0, help="Potência do rádio na entrada da antena (dBm)")
    radio.add_argument("--tx-power-w", type=float,
                        help="Potência por ramo/saída em Watts (alternativa a --tx-power-dbm). "
                             "Use com --tx-branches para somar múltiplas saídas (ex: RU 4x5W: --tx-power-w 5 --tx-branches 4)")
    radio.add_argument("--tx-branches", type=int, default=1,
                        help="Número de saídas/ramos de RF somados a --tx-power-w (default 1)")
    radio.add_argument("--antenna-gain-dbi", type=float, default=17.0, help="Ganho da antena (dBi)")

    area = p.add_argument_group("Área / terreno")
    area.add_argument("--radius-km", type=float, default=3.0, help="Raio da área simulada (km)")
    area.add_argument("--resolution", type=int, default=80, help="Resolução da grade de cobertura (NxN pontos)")
    area.add_argument("--terrain-resolution", type=int, default=40, help="Resolução da grade de elevação (NxN)")
    area.add_argument("--environment", choices=["rural", "suburban", "urban", "dense_urban"],
                       default="suburban", help="Perda de clutter por ambiente")
    area.add_argument("--no-terrain", action="store_true", help="Ignora relevo (terreno plano, mais rápido, offline)")
    area.add_argument("--elevation-dataset", default="srtm30m", help="Dataset da API Open-Topo-Data")

    out = p.add_argument_group("Saída")
    out.add_argument("--output", type=Path, default=Path("coverage_map.html"), help="Arquivo HTML de saída")
    out.add_argument("--cache-dir", type=Path, default=Path(".terrain_cache"), help="Diretório de cache do relevo")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        freq_mhz = resolve_frequency_mhz(args.band, args.freq_mhz)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    if args.tx_power_w is not None:
        total_w = args.tx_power_w * args.tx_branches
        tx_power_dbm = 10 * np.log10(total_w * 1000.0)
        print(f"[1/4] Potência TX: {args.tx_power_w:.2f} W x {args.tx_branches} ramo(s) "
              f"= {total_w:.2f} W = {tx_power_dbm:.2f} dBm")
    else:
        tx_power_dbm = args.tx_power_dbm
        print(f"[1/4] Potência TX: {tx_power_dbm:.2f} dBm")

    print(f"      Frequência de operação: {freq_mhz:.1f} MHz"
          + (f" (banda {args.band})" if args.band else ""))

    if args.no_terrain:
        print("[2/4] Terreno plano (--no-terrain).")
        terrain = FlatTerrain()
    else:
        print(f"[2/4] Baixando/consultando relevo (grade {args.terrain_resolution}x{args.terrain_resolution}, "
              f"raio {args.radius_km} km)...")
        t0 = time.time()
        try:
            terrain = fetch_elevation_grid(
                args.lat, args.lon, args.radius_km,
                resolution=args.terrain_resolution,
                dataset=args.elevation_dataset,
                cache_dir=args.cache_dir,
            )
            print(f"      OK ({time.time() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001 - fallback deliberado
            print(f"      Falha ao obter relevo ({exc}). Usando terreno plano.", file=sys.stderr)
            terrain = FlatTerrain()

    ant = AntennaConfig(
        gain_dbi=args.antenna_gain_dbi,
        azimuth_deg=args.azimuth_deg,
        downtilt_deg=args.downtilt_deg,
        h_beamwidth_deg=None if args.h_beamwidth_deg <= 0 else args.h_beamwidth_deg,
        v_beamwidth_deg=None if args.v_beamwidth_deg <= 0 else args.v_beamwidth_deg,
    )
    link = LinkParams(
        tx_power_dbm=tx_power_dbm,
        freq_mhz=freq_mhz,
        tx_height_m=args.antenna_height_m,
        rx_height_m=args.rx_height_m,
        environment=args.environment,
    )

    dlat = args.radius_km * 1000.0 / METERS_PER_DEG_LAT
    dlon = args.radius_km * 1000.0 / _meters_per_deg_lon(args.lat)
    lats = np.linspace(args.lat - dlat, args.lat + dlat, args.resolution)
    lons = np.linspace(args.lon - dlon, args.lon + dlon, args.resolution)
    grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")

    print(f"[3/4] Calculando RSRP na grade de cobertura ({args.resolution}x{args.resolution} pontos)...")
    t0 = time.time()
    rsrp = rsrp_grid(terrain, ant, link, args.lat, args.lon, grid_lat, grid_lon)
    print(f"      OK ({time.time() - t0:.1f}s) | RSRP min={rsrp.min():.1f} dBm max={rsrp.max():.1f} dBm")

    site_info = {
        "Latitude": f"{args.lat:.5f}",
        "Longitude": f"{args.lon:.5f}",
        "Frequência": f"{freq_mhz:.1f} MHz" + (f" ({args.band})" if args.band else ""),
        "Altura da antena": f"{args.antenna_height_m:.1f} m",
        "Potência TX": f"{tx_power_dbm:.1f} dBm",
        "Ganho da antena": f"{args.antenna_gain_dbi:.1f} dBi",
        "Azimute": f"{args.azimuth_deg:.0f}°",
        "Downtilt": f"{args.downtilt_deg:.1f}°",
        "Ambiente": args.environment,
    }

    print(f"[4/4] Renderizando mapa em {args.output} ...")
    build_map(rsrp, lats, lons, args.lat, args.lon, site_info, args.output)
    print("Concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
