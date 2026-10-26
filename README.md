# Eleição Presidencial 2026: análise dos Boletins de Urna

Baixa os Boletins de Urna (BU) do 1º e do 2º turno da eleição presidencial de 2026 no portal de dados abertos do TSE,
converte para Parquet e gera notebooks com gráficos e testes de anomalia em duas abordagens:

| Notebook | Abordagem |
|---|---|
| `notebooks/01_analise_neutra.ipynb` | **Neutra**: descreve o resultado e aplica testes forenses de forma simétrica a todos os candidatos, sempre comparando com o que o acaso produziria. |
| `notebooks/02_auditoria_adversarial.ipynb` | **Advogado do diabo**: procura qualquer brecha que pudesse sustentar um pedido de anulação de urnas ou da eleição. Cada achado passa por *hipótese → teste ingênuo → controle → materialidade* (anular todas as seções sinalizadas reverteria a margem?). No fim calcula a "menor brecha": quantas seções precisariam ser anuladas para inverter o resultado e quantas delas têm alguma anomalia técnica. |

## Instalação

Requer [uv](https://docs.astral.sh/uv/). O `uv` cria o ambiente virtual em `.venv` (Python 3.12) e instala as dependências:

```bash
uv sync
```

## Uso

```bash
uv run baixar                     # baixa o BU dos 2 turnos (≈5 GB por turno), conferindo o SHA-512 do TSE
uv run processar                  # filtra o cargo Presidente e gera data/processed/*.parquet (~2 min por turno)
uv run python scripts/gerar_notebooks.py --executar   # gera e executa os dois notebooks
uv run jupyter lab                # para explorar interativamente
```

Outras opções: `uv run baixar --listar` mostra o que já foi publicado; `--turno 2`, `--uf SP RJ`.

**2º turno:** o TSE publica o CSV do BU cerca de 1 dia depois de cada turno (o do 1º turno saiu em 05/10). Quando
`uv run baixar --listar` mostrar o 2º turno, rode:

```bash
uv run baixar --turno 2 && uv run processar --turno 2 && uv run python scripts/gerar_notebooks.py --executar
```

Os notebooks detectam sozinhos se o 2º turno está disponível. As seções que comparam os dois turnos só rodam quando ele está.

## Estrutura

```
src/eleicoes_2026/
  config.py      caminhos, UFs, endpoint CKAN
  download.py    descoberta via API CKAN + download com verificação SHA-512
  process.py     zip → Parquet (DuckDB), tabela longa e tabela por seção
  analise.py     funções estatísticas usadas pelos notebooks
scripts/
  nb_neutro.py, nb_adversarial.py   conteúdo das células
  gerar_notebooks.py                monta e executa os .ipynb
data/            (fora do git) raw/ zips do TSE · interim/ parquet por UF · processed/ tabelas finais
notebooks/       notebooks gerados (com saídas)
```

Para alterar um notebook, edite `scripts/nb_*.py` e rode o gerador de novo. Assim os dois notebooks continuam
reproduzíveis. Edições feitas direto no `.ipynb` são sobrescritas.

## Métodos

- **Consistência aritmética** do BU (aptos = comparecimento + abstenções; votos = comparecimento).
- **Impressão digital de Klimek** (comparecimento × % do candidato), usada para detectar enchimento de urnas.
- **2º dígito de Benford (2BL)** e **último dígito**. O 1º dígito não é usado porque não se aplica a seções de tamanho limitado.
- **Homogeneidade no local de votação**: cada seção é comparada com as outras do mesmo prédio usando um z-score
  quase-binomial, e o número de extremos é comparado com uma simulação beta-binomial sob acaso.
- **Isolation Forest** para triagem multivariada.
- **Efeitos fixos de município** para separar padrões geográficos de padrões da urna (biometria, lote de urnas, comparecimento).
- **Modelo de transição 1º→2º turno** (regressão ecológica com efeito fixo de município).
- **Materialidade**: impacto de anular as seções sinalizadas sobre a margem.

## Limitações

- O CSV do BU não informa o **modelo da urna**. O notebook adversarial usa a faixa do nº de série e a data de carga
  como aproximação. Para ter o modelo real é preciso processar os logs das urnas ("arquivos transmitidos para
  totalização", também no portal do TSE).
- Os horários do BU estão no fuso local. O fuso de cada município é deduzido da hora de abertura mais comum ali, e o exterior fica de fora.
- Anomalia estatística não prova irregularidade. Ela só indica seções a inspecionar: BU impresso, log da urna, ata da mesa.
