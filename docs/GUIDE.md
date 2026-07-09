# Guia completo — 5g-nr-coverage

Este guia aprofunda o que o [README](../README.md) resume: o modelo físico
usado, o significado de cada parâmetro, e um exemplo real de ponta a ponta
com equipamento comercial (RU Benetel RAN650 + antenas Alpha Wireless).

## Índice

1. [Pré-requisitos e instalação](#pré-requisitos-e-instalação)
2. [Como o modelo funciona](#como-o-modelo-funciona)
3. [Referência completa de parâmetros](#referência-completa-de-parâmetros)
4. [Exemplo real: Benetel RAN650 + Alpha Wireless](#exemplo-real-benetel-ran650--alpha-wireless)
5. [Interpretando o mapa gerado](#interpretando-o-mapa-gerado)
6. [Erros comuns e troubleshooting](#erros-comuns-e-troubleshooting)
7. [Referências](#referências)

---

## Pré-requisitos e instalação

### 1. Python

É necessário Python 3.10+ (o projeto foi testado com 3.13). Verifique se
já tem um interpretador instalado:

```powershell
python --version
```

Se não tiver (ou só existir o alias da Microsoft Store, que dá erro), instale
uma das opções:

- **[python.org/downloads](https://www.python.org/downloads/)** — instalador oficial, mais simples.
- **[WinPython](https://winpython.github.io/)** — distribuição portátil (não mexe no sistema), boa opção se você não quer instalar nada globalmente.
- `winget install Python.Python.3.13` — se tiver o `winget` disponível.

### 2. Clonar o repositório

```powershell
git clone https://github.com/luciorp/5g-nr-coverage
cd 5g-nr-coverage
```

### 3. (Opcional, recomendado) Ambiente virtual

Evita conflitar com outras instalações de pacotes Python na máquina:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 4. Instalar dependências

```powershell
pip install -r requirements.txt
```

Isso instala: `numpy`, `scipy` (interpolação do relevo), `folium` (mapa
interativo), `matplotlib` (renderização do heatmap) e `requests` (consulta
à API de elevação).

### 5. Testar

```powershell
python -m coverage_tool.cli --lat -23.5505 --lon -46.6333 --band n78 --antenna-height-m 25 --tx-power-dbm 43 --antenna-gain-dbi 17 --radius-km 2 --output teste.html
```

Se gerar `teste.html` sem erro, está tudo funcionando. Abra o arquivo em
qualquer navegador.

> **Nota:** se o comando `python` não for reconhecido, mas você tem uma
> instalação em outro lugar (ex.: WinPython, Anaconda), use o caminho
> completo do executável, ex.:
> `C:\tools\WPy64-313110\python\python.exe -m coverage_tool.cli ...`

---

## Como o modelo funciona

A ferramenta estima o **RSRP** (potência do sinal de referência recebida,
métrica padrão de qualidade de sinal em LTE/5G NR) em cada ponto de uma
grade ao redor da antena:

```
RSRP(dBm) = P_tx + G_antena(φ, θ) − FSPL − L_difração − L_clutter
```

### P_tx — potência de transmissão

Potência entregue à antena, em dBm (ou em Watts, ver `--tx-power-w`).

### FSPL — perda de espaço livre (ITU-R P.525)

```
FSPL(dB) = 32.44 + 20·log₁₀(d_km) + 20·log₁₀(f_MHz)
```

Perda que o sinal sofreria no vácuo, sem nenhum obstáculo — a base de
qualquer link budget de rádio.

### L_difração — perda por obstrução de relevo (ITU-R P.526)

Para cada ponto do mapa, a ferramenta:

1. Busca a elevação do terreno (SRTM) ao longo da linha reta entre a antena
   e aquele ponto (perfil de 32 amostras por padrão).
2. Traça a linha de visada (LOS) entre a altura absoluta da antena
   (elevação do terreno no site + `--antenna-height-m`) e a altura absoluta
   do receptor (elevação do terreno *naquele ponto* + `--rx-height-m`).
3. Encontra o ponto do perfil onde o terreno mais invade essa linha de
   visada (pior obstrução — construção tipo Bullington) e calcula o
   parâmetro de difração de Fresnel-Kirchhoff:

   ```
   v = h · √( 2·d / (λ·d1·d2) )
   ```

   onde `h` é a altura da obstrução acima da LOS, `d1`/`d2` são as
   distâncias da obstrução até antena/receptor, `d` a distância total e
   `λ` o comprimento de onda.
4. Converte `v` em perda (dB) pela aproximação da ITU-R P.526 §4.1:

   ```
   J(v) = 6.9 + 20·log₁₀( √((v−0.1)² + 1) + v − 0.1 ),   v > −0.78
   J(v) = 0,                                              v ≤ −0.78
   ```

Se não há obstrução (visada livre com folga), a perda é zero.

### G_antena — padrão de antena (3GPP TR 38.901, Tabela 7.3-1)

Ganho na direção de cada ponto, considerando o padrão setorizado padrão do
3GPP para antenas de estação-base:

```
A_H(φ) = min( 12·(φ/φ_3dB)², A_max )        — atenuação horizontal
A_V(θ) = min( 12·(θ_offset/θ_3dB)², SLA_max) — atenuação vertical
G(φ,θ) = G_max − min( A_H + A_V, A_max )
```

`φ` é o desvio angular do azimute apontado (`--azimuth-deg`), `θ_offset` é
o desvio vertical em relação ao downtilt (`--downtilt-deg`). Com
`--h-beamwidth-deg 0`, a atenuação horizontal é desativada (antena
onidirecional).

### L_clutter — perda de ambiente

Offset fixo de planejamento por tipo de ambiente (não é um modelo
estatístico completo como Okumura-Hata ou 3GPP UMa/RMa — é uma
simplificação deliberada):

| `--environment` | Perda adicional |
|---|---|
| `rural` | 0 dB |
| `suburban` | 5 dB |
| `urban` | 10 dB |
| `dense_urban` | 16 dB |

---

## Referência completa de parâmetros

### Site / antena

| Parâmetro | Unidade | Significado |
|---|---|---|
| `--lat`, `--lon` | graus decimais | Coordenadas de onde a antena está **fisicamente instalada**. |
| `--antenna-height-m` | metros | Altura da antena **acima do relevo no local da antena** (não do ponto analisado — ver [nota sobre altura](#nota-importante-altura-da-antena)). |
| `--rx-height-m` | metros | Altura assumida do terminal/celular receptor acima do solo em cada ponto analisado. Padrão 1.5m. |
| `--azimuth-deg` | graus, 0=Norte, sentido horário | Direção para onde o setor aponta. Só importa se a antena não for onidirecional. |
| `--downtilt-deg` | graus, positivo = para baixo | Inclinação elétrica/mecânica da antena. |
| `--h-beamwidth-deg` | graus | Largura de feixe horizontal (do datasheet da antena). **Use `0` para antena onidirecional.** |
| `--v-beamwidth-deg` | graus | Largura de feixe vertical/elevação (do datasheet). Use `0` para desativar o padrão vertical. |

### Rádio

| Parâmetro | Unidade | Significado |
|---|---|---|
| `--band` | código NR | Banda 5G (`n78`, `n77`, `n41`, `n28`...). Define a frequência central automaticamente — ver `coverage_tool/nr_bands.py`. |
| `--freq-mhz` | MHz | Frequência exata, caso queira sobrepor o centro da banda. |
| `--tx-power-dbm` | dBm | Potência na porta de entrada da antena. |
| `--tx-power-w` + `--tx-branches` | Watts + inteiro | Alternativa mais prática a `--tx-power-dbm`: potência **por ramo/porta** × número de ramos somados. Ex.: rádio com 4 saídas de 5W → `--tx-power-w 5 --tx-branches 4` (a ferramenta calcula 20W = 43.01 dBm). Válido para RUs convencionais 4T4R com antena passiva externa — **não** some as portas se a RU for um AAU com beamforming ativo embutido (o ganho da antena já incluiria o ganho de array, e você contaria duas vezes). |
| `--antenna-gain-dbi` | dBi | Ganho da antena (do datasheet), na direção de boresight. |

### Área / terreno

| Parâmetro | Unidade | Significado |
|---|---|---|
| `--radius-km` | km | Raio da área simulada ao redor da antena. |
| `--resolution` | pontos (NxN) | Densidade da grade de cobertura. Mais alto = mapa mais nítido, porém mais lento (cresce com o quadrado). |
| `--terrain-resolution` | pontos (NxN) | Densidade da grade de elevação usada para interpolar o relevo. Independente de `--resolution`. |
| `--environment` | enum | `rural` / `suburban` / `urban` / `dense_urban` — ver tabela de clutter acima. |
| `--no-terrain` | flag | Ignora relevo (terreno plano). Mais rápido, funciona 100% offline, mas perde a modelagem de obstáculos. |
| `--elevation-dataset` | string | Dataset da API Open-Topo-Data (padrão `srtm30m`). |

### Saída

| Parâmetro | Significado |
|---|---|
| `--output` | Caminho do arquivo HTML gerado. |
| `--cache-dir` | Onde salvar o cache de relevo (padrão `.terrain_cache/`), evita reconsultar a API para a mesma área. |

### Nota importante: altura da antena

`--antenna-height-m` é a altura **acima do relevo no ponto onde a antena
está instalada** (`--lat`/`--lon`) — como uma antena física real, que tem
altura fixa acima do próprio mastro, não acima do terreno de cada lugar
distante que está sendo analisado. Para cada ponto do mapa, a ferramenta
usa a elevação do terreno *daquele ponto* somada a `--rx-height-m` (altura
do receptor, não a da antena). A comparação entre as duas elevações
absolutas é o que gera a obstrução por relevo.

---

## Exemplo real: Benetel RAN650 + Alpha Wireless

Este é o equipamento usado para validar a ferramenta.

### RU: Benetel RAN650 (variante n78)

O-RU O-RAN split 7.2x, 4T4R, banda n78 (3300–3800 MHz), 4 portas N-type,
até 5W (37 dBm) por porta — total 4×5W = 20W = 43 dBm conduzidos.
([datasheet oficial](https://cdn.prod.website-files.com/665f1b4b8eba5127ca955ccd/66f5617093fe23afc928b998_RAN650_n78_Datasheet_v1.3.pdf))

### Opção A — Antena setorial: Alpha Wireless AWL3970-T0-F

Canister 4 portas, 65° de abertura horizontal, 14.0 dBi (3300–3800MHz),
downtilt elétrico fixo 0°, conector 4.3-10.
([datasheet](https://alphawireless.com/wp-content/uploads/AWL3970-T0-F.pdf))

```powershell
python -m coverage_tool.cli `
  --lat -29.794743 --lon -51.156653 `
  --band n78 `
  --antenna-height-m 30 `
  --tx-power-w 5 --tx-branches 4 `
  --antenna-gain-dbi 14.0 `
  --azimuth-deg 90 `
  --downtilt-deg 0 `
  --h-beamwidth-deg 65 --v-beamwidth-deg 14.5 `
  --environment urban `
  --radius-km 2 `
  --resolution 80 `
  --output coverage_sector.html
```

Use isso quando quer concentrar o sinal em **uma direção específica**
(ex.: ao longo de uma via, cobrindo um bairro específico).

### Opção B — Antena onidirecional: Alpha Wireless AW3941-T0-F

Canister 4 portas, 360° (pseudo-omni), 8.0 dBi (3300–3800MHz), downtilt
elétrico fixo 0°, conector 4.3-10 — mesmo formato físico da AWL3970, mas
trocando abertura por ganho (6 dB a menos).
([datasheet](https://alphawireless.com/ds/AW3941-T0-F.pdf))

```powershell
python -m coverage_tool.cli `
  --lat -29.794743 --lon -51.156653 `
  --band n78 `
  --antenna-height-m 15 `
  --tx-power-w 5 --tx-branches 4 `
  --antenna-gain-dbi 8.0 `
  --h-beamwidth-deg 0 --v-beamwidth-deg 23 `
  --downtilt-deg 0 `
  --environment urban `
  --radius-km 3 `
  --resolution 80 `
  --output coverage_omni.html
```

Use isso quando quer cobertura **em todas as direções** ao redor do
mastro, aceitando um raio de alcance menor por conta do ganho mais baixo.

### Compatibilidade de conectores

A RAN650 usa portas **N-type**; as duas antenas Alpha Wireless usam
**4.3-10**. São necessários 4 jumpers **4.3-10(macho) / N-type(macho)**
entre a RU e a antena — a própria Alpha Wireless vende o cabo certo,
código `AW1012-2-FM-NM`.

---

## Interpretando o mapa gerado

O HTML abre num mapa OpenStreetMap com uma camada colorida semitransparente
sobre a área simulada, e uma legenda no canto inferior esquerdo:

| Cor | Faixa de RSRP | Leitura prática |
|---|---|---|
| Verde escuro | > −80 dBm | Excelente — sinal forte, taxas altas |
| Verde claro | −90 a −80 dBm | Muito bom |
| Amarelo | −95 a −90 dBm | Bom |
| Laranja | −100 a −95 dBm | Regular — pode haver perda de throughput |
| Vermelho | −110 a −100 dBm | Fraco — conexão instável |
| Transparente | < −110 dBm | Sem cobertura estimada |

Clique no marcador azul (local da antena) para ver um resumo dos
parâmetros usados naquela simulação.

---

## Erros comuns e troubleshooting

**`ModuleNotFoundError: No module named 'coverage_tool'`**
Rode o comando de dentro da pasta do projeto (onde está a pasta
`coverage_tool/`), ou onde o `pip install` foi feito nesse mesmo
interpretador Python.

**Demora muito no passo `[2/4] Baixando/consultando relevo...`**
A API pública de elevação (Open-Topo-Data) limita a ~1 requisição/s.
Grades grandes (`--terrain-resolution` alto) demoram na primeira execução;
execuções seguintes para a mesma área usam o cache em `.terrain_cache/` e
são instantâneas. Para testes rápidos, use `--no-terrain`.

**Erro HTTP / timeout na API de elevação**
A ferramenta cai automaticamente para terreno plano (com aviso no
console) se a API falhar — o mapa ainda é gerado, só sem modelagem de
obstáculos por relevo.

**PowerShell: erro de sintaxe ao quebrar linha com `\`**
No PowerShell use o backtick `` ` `` para continuar a linha, não `\`
(que funciona em bash/Git Bash). Os exemplos deste guia já usam o
backtick.

---

## Referências

- ITU-R P.525 — Calculation of free-space attenuation
- ITU-R P.526 — Propagation by diffraction
- 3GPP TR 38.901 — Study on channel model for frequencies from 0.5 to 100 GHz
- 3GPP TS 38.101 — NR User Equipment radio transmission and reception (bandas)
- [Open-Topo-Data](https://www.opentopodata.org/) — API de elevação (SRTM)
