# 5g-nr-coverage

Ferramenta em Python para simular a cobertura de uma célula 5G NR e gerar um
mapa de calor interativo (HTML) sobre tiles do OpenStreetMap, considerando
relevo (terreno) e parâmetros reais de rádio.

## Modelo matemático

RSRP(dBm) = P_tx + G_antena(azimute, elevação) − FSPL − L_difração_relevo − L_clutter

- **FSPL** (perda de espaço livre): ITU-R P.525.
- **L_difração_relevo**: perda por obstrução de terreno, calculada a partir do
  perfil de elevação (SRTM) entre a antena e cada ponto, usando o parâmetro de
  Fresnel-Kirchhoff e a aproximação de difração de gume-de-faca da ITU-R P.526
  (§4.1), escolhendo o ponto de pior obstrução ao longo do perfil (construção
  tipo Bullington, ITU-R P.526 §4.3).
- **G_antena**: padrão de antena setorizada do 3GPP TR 38.901 (Tabela 7.3-1),
  parametrizado por azimute, downtilt e larguras de feixe horizontal/vertical.
- **L_clutter**: offset típico de perda por ambiente (rural/suburbano/
  urbano/urbano denso) — simplificação de planejamento; não substitui um
  modelo estatístico completo (ex.: 3GPP 38.901 UMa/RMa, Okumura-Hata).

Essa combinação segue a mesma lógica usada por ferramentas conhecidas de
predição de cobertura baseadas em terreno (SPLAT!, Radio Mobile), com o
padrão de antena e as bandas alinhados ao 5G NR (3GPP). O ITU-R P.1812 é a
recomendação mais completa/precisa para esse tipo de predição, mas exige
dezenas de fatores de correção adicionais — fora do escopo de um script
enxuto como este.

## Dados de terreno e mapa

- **Elevação**: API pública e gratuita [Open-Topo-Data](https://www.opentopodata.org/)
  (dataset `srtm30m` por padrão), sem necessidade de chave de API. Os
  resultados são cacheados em `.terrain_cache/` para não repetir requisições.
  Use `--no-terrain` para rodar totalmente offline (modelo sem relevo).
- **Mapa base**: [OpenStreetMap](https://www.openstreetmap.org/) via
  [Folium](https://python-visualization.github.io/folium/) (Leaflet.js),
  gratuito e sem chave de API.

## Instalação

Requer Python 3.10+. Passo a passo completo (incluindo o que fazer se não
tiver Python instalado) em **[docs/GUIDE.md](docs/GUIDE.md#pré-requisitos-e-instalação)**.

```
pip install -r requirements.txt
```

## Uso

```
python -m coverage_tool.cli \
  --lat -23.5505 --lon -46.6333 \
  --band n78 \
  --antenna-height-m 25 \
  --tx-power-dbm 43 \
  --antenna-gain-dbi 17 \
  --azimuth-deg 90 \
  --downtilt-deg 3 \
  --environment urban \
  --radius-km 2 \
  --resolution 80 \
  --output coverage_map.html
```

Abra o `coverage_map.html` gerado em qualquer navegador.

📖 **Guia completo, com explicação detalhada de cada parâmetro e um
exemplo real de ponta a ponta (RU Benetel RAN650 + antenas setorial e
onidirecional da Alpha Wireless):
[docs/GUIDE.md](docs/GUIDE.md)**

### Parâmetros principais

| Parâmetro | Descrição |
|---|---|
| `--lat` / `--lon` | Coordenadas da antena |
| `--band` | Banda NR (ex.: `n1`, `n28`, `n41`, `n77`, `n78`, `n257`...) — ver `coverage_tool/nr_bands.py` |
| `--freq-mhz` | Frequência exata em MHz (alternativa/complemento a `--band`) |
| `--antenna-height-m` | Altura da antena (m) |
| `--tx-power-dbm` | Potência do rádio na entrada da antena (dBm) |
| `--tx-power-w` / `--tx-branches` | Potência em Watts por ramo/saída, somada pelo número de ramos (alternativa a `--tx-power-dbm`). Ex.: RU com 4 saídas de 5W → `--tx-power-w 5 --tx-branches 4` (= 20W = 43 dBm) |
| `--antenna-gain-dbi` | Ganho da antena (dBi) — use o ganho da antena passiva externa do datasheet |
| `--azimuth-deg` / `--downtilt-deg` | Apontamento do setor |
| `--h-beamwidth-deg` / `--v-beamwidth-deg` | Largura de feixe (use `0` para onidirecional) |
| `--environment` | `rural`, `suburban`, `urban`, `dense_urban` |
| `--radius-km` / `--resolution` | Área e resolução da grade de cobertura |
| `--terrain-resolution` | Resolução da grade de elevação (relevo) |
| `--no-terrain` | Desliga o relevo (mais rápido, funciona offline) |

Rode `python -m coverage_tool.cli --help` para a lista completa.

> **Nota sobre `--tx-power-w`/`--tx-branches`:** a soma linear das saídas só é
> correta para RUs convencionais 4T4R conectadas a uma antena passiva externa
> (ex.: Benetel RAN650) — cada porta radia de forma independente pelos
> conectores da antena, então a potência conduzida total é a soma dos ramos.
> Se a sua RU for um AAU/massive-MIMO com beamforming ativo embutido (array
> integrado), o ganho da antena já inclui o ganho de array do beamforming e
> somar as saídas de novo superestima o link budget (dupla contagem).

## Limitações conhecidas

- Modelo de clutter é um offset fixo por ambiente, não estatístico.
- Difração considera apenas o pior obstáculo do perfil (single knife-edge),
  não múltiplos obstáculos (ITU-R P.526 §4.5) nem efeitos de multipercurso.
- Em mmWave (bandas n257/n258/n260/n261) a difração por relevo é pouco
  representativa da propagação real (dominada por bloqueio de linha de
  visada e perdas atmosféricas) — use com cautela nessas bandas.
- A API pública de elevação tem limite de ~1 req/s e cache local; para áreas
  grandes com `--terrain-resolution` alta, a primeira execução pode demorar.
