"""Renderização do mapa de cobertura: grade RSRP -> imagem colorida -> mapa
Folium (tiles OpenStreetMap, gratuito, sem chave de API)."""
from __future__ import annotations

from pathlib import Path

import folium
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

# Faixas de RSRP (dBm) típicas usadas em planejamento de cobertura NR.
RSRP_BINS = [-140, -110, -100, -95, -90, -80, -40]
RSRP_LABELS = [
    "Sem cobertura (< -110 dBm)",
    "Fraco (-110 a -100 dBm)",
    "Regular (-100 a -95 dBm)",
    "Bom (-95 a -90 dBm)",
    "Muito bom (-90 a -80 dBm)",
    "Excelente (> -80 dBm)",
]
RSRP_COLORS = [
    "#00000000",  # sem cobertura -> transparente
    "#d73027",    # fraco -> vermelho
    "#fc8d59",    # regular -> laranja
    "#fee08b",    # bom -> amarelo
    "#91cf60",    # muito bom -> verde claro
    "#1a9850",    # excelente -> verde escuro
]


def _render_overlay_png(rsrp_db: np.ndarray, png_path: Path) -> None:
    cmap = ListedColormap(RSRP_COLORS)
    norm = BoundaryNorm(RSRP_BINS, cmap.N)

    fig, ax = plt.subplots(figsize=(rsrp_db.shape[1] / 50, rsrp_db.shape[0] / 50), dpi=150)
    ax.imshow(rsrp_db, cmap=cmap, norm=norm, origin="lower", aspect="auto")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, format="png", transparent=True)
    plt.close(fig)


_LEGEND_TEMPLATE = """
<div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
            background: white; padding: 10px 14px; border: 1px solid #999;
            border-radius: 6px; font-size: 13px; font-family: sans-serif;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);">
  <b>RSRP estimado</b><br>
  {rows}
</div>
"""


def _legend_html() -> str:
    rows = ""
    for color, label in zip(reversed(RSRP_COLORS[1:]), reversed(RSRP_LABELS[1:])):
        rows += (
            f'<div><span style="display:inline-block;width:12px;height:12px;'
            f'background:{color};margin-right:6px;border:1px solid #666;"></span>'
            f"{label}</div>"
        )
    return _LEGEND_TEMPLATE.format(rows=rows)


def build_map(
    rsrp_db: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    tx_lat: float,
    tx_lon: float,
    site_info: dict,
    output_html: Path,
) -> None:
    output_html.parent.mkdir(parents=True, exist_ok=True)
    png_path = output_html.with_name(output_html.stem + "_overlay.png")
    _render_overlay_png(rsrp_db, png_path)

    fmap = folium.Map(location=[tx_lat, tx_lon], zoom_start=13, tiles="OpenStreetMap")

    bounds = [[float(lats.min()), float(lons.min())], [float(lats.max()), float(lons.max())]]
    folium.raster_layers.ImageOverlay(
        image=str(png_path),
        bounds=bounds,
        opacity=0.65,
        interactive=False,
        cross_origin=False,
    ).add_to(fmap)

    popup = "<br>".join(f"<b>{k}:</b> {v}" for k, v in site_info.items())
    folium.Marker(
        [tx_lat, tx_lon],
        popup=folium.Popup(popup, max_width=300),
        icon=folium.Icon(color="blue", icon="signal", prefix="fa"),
    ).add_to(fmap)

    fmap.get_root().html.add_child(folium.Element(_legend_html()))
    folium.LayerControl().add_to(fmap)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_html))
