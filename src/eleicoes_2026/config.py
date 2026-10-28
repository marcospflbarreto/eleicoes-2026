"""Caminhos e constantes do projeto."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Ano da eleição. 2026 é o padrão; outro ano (ex.: ELEICOES_ANO=2022) serve de referência e fica em data/<ano>.
ANO = int(os.environ.get("ELEICOES_ANO", "2026"))
DATA = Path(os.environ.get("ELEICOES_DADOS", ROOT / "data" if ANO == 2026 else ROOT / "data" / str(ANO)))  # sobrescrevível p/ testes


def pasta_processada(ano: int) -> Path:
    """data/processed de outra eleição (ex.: 2022, usada como referência)."""
    return DATA / "processed" if ano == ANO else ROOT / "data" / ("" if ano == 2026 else str(ano)) / "processed"


RAW = DATA / "raw"  # zips originais do TSE (dados não confiáveis: nunca executar nada daqui)
INTERIM = DATA / "interim"  # parquet por UF, apenas cargo Presidente
PROCESSED = DATA / "processed"  # tabelas finais usadas pelos notebooks
FIGURES = ROOT / "reports" / "figures"

CKAN = "https://dadosabertos.tse.jus.br/api/3/action"
# Pacote(s) do portal de dados abertos com os Boletins de Urna (BU) em CSV.
CKAN_PACOTE_BU = f"resultados-{ANO}-boletim-de-urna"

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
    "ZZ",  # exterior
]

CD_CARGO_PRESIDENTE = "1"

REGIAO = {
    "AC": "Norte", "AM": "Norte", "AP": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MS": "Centro-Oeste", "MT": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
    "ZZ": "Exterior",
}
