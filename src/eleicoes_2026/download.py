"""Baixa os Boletins de Urna (BU) da eleição presidencial de 2026 (ou de outro ano, via ELEICOES_ANO) do portal de dados abertos do TSE.

Os arquivos são descobertos pela API CKAN do portal (dadosabertos.tse.jus.br), então o
script funciona mesmo quando o TSE republica arquivos com novo carimbo de data/hora: para
cada (turno, UF) é escolhida a versão mais recente. Cada zip é conferido contra o .sha512
publicado pelo TSE.

Uso:
    uv run baixar                     # 1º e 2º turnos, todas as UFs
    uv run baixar --turno 2 --uf SP RJ
    uv run baixar --listar            # só mostra o que está disponível
    ELEICOES_ANO=2022 uv run baixar   # eleição de 2022, gravada em data/2022
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from tqdm import tqdm

from .config import ANO, CKAN, CKAN_QUERY_BU, RAW, UFS

# ex.: .../buweb/bweb_1t_AC_051020261403.zip
RE_BWEB = re.compile(r"/bweb_(?P<turno>[12])t_(?P<uf>[A-Z]{2})_(?P<ts>\d{12})\.zip$")

session = requests.Session()
session.headers["User-Agent"] = "eleicoes-2026-analise/0.1 (pesquisa acadêmica)"


@dataclass(frozen=True)
class Recurso:
    turno: int
    uf: str
    ts: str  # ddmmaaaaHHMM
    url: str

    @property
    def ordem(self) -> str:  # aaaammddHHMM, ordenável
        t = self.ts
        return t[4:8] + t[2:4] + t[0:2] + t[8:]

    @property
    def destino(self) -> Path:
        return RAW / f"{self.turno}t" / Path(self.url).name


def listar_recursos() -> dict[tuple[int, str], Recurso]:
    """Retorna o arquivo de BU mais recente para cada (turno, UF)."""
    r = session.get(f"{CKAN}/package_search", params={"q": CKAN_QUERY_BU, "rows": 100}, timeout=60)
    r.raise_for_status()
    melhores: dict[tuple[int, str], Recurso] = {}
    for pkg in r.json()["result"]["results"]:
        if pkg["name"] != f"resultados-{ANO}-boletim-de-urna":
            continue
        for res in pkg["resources"]:
            m = RE_BWEB.search(res["url"])
            if not m:
                continue
            rec = Recurso(int(m["turno"]), m["uf"], m["ts"], res["url"])
            chave = (rec.turno, rec.uf)
            if chave not in melhores or rec.ordem > melhores[chave].ordem:
                melhores[chave] = rec
    return melhores


def _sha512(path: Path) -> str:
    h = hashlib.sha512()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _hash_publicado(url: str) -> str | None:
    try:
        r = session.get(url + ".sha512", timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    m = re.search(r"[0-9a-fA-F]{128}", r.text)
    return m.group(0).lower() if m else None


def baixar(rec: Recurso, forcar: bool = False) -> Path:
    dest = rec.destino
    dest.parent.mkdir(parents=True, exist_ok=True)
    esperado = _hash_publicado(rec.url)
    if dest.exists() and not forcar:
        if esperado is None or _sha512(dest) == esperado:
            return dest
    tmp = dest.with_suffix(".part")
    with session.get(rec.url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with tmp.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name, leave=False) as bar:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
                bar.update(len(bloco))
    if esperado is not None and _sha512(tmp) != esperado:
        tmp.unlink()
        raise RuntimeError(f"SHA-512 não confere para {rec.url}")
    tmp.replace(dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--turno", type=int, nargs="+", default=[1, 2], choices=[1, 2])
    p.add_argument("--uf", nargs="+", default=UFS, type=str.upper)
    p.add_argument("--listar", action="store_true", help="apenas lista os arquivos disponíveis")
    p.add_argument("--forcar", action="store_true", help="baixa de novo mesmo se já existir")
    a = p.parse_args(argv)

    recursos = listar_recursos()
    faltando = []
    for turno in a.turno:
        disponiveis = [recursos[(turno, uf)] for uf in a.uf if (turno, uf) in recursos]
        ausentes = [uf for uf in a.uf if (turno, uf) not in recursos]
        print(f"{turno}º turno: {len(disponiveis)} UFs disponíveis no portal", end="")
        print(f" | ainda não publicadas: {' '.join(ausentes)}" if ausentes else "")
        faltando += [(turno, uf) for uf in ausentes]
        if a.listar:
            for rec in disponiveis:
                print(f"   {rec.uf}  {rec.url}")
            continue
        for rec in tqdm(disponiveis, desc=f"{turno}º turno", unit="UF"):
            baixar(rec, a.forcar)

    if faltando and 2 in a.turno and any(t == 2 for t, _ in faltando):
        print(
            "\nO TSE publica o BU em CSV cerca de 1 dia após cada turno. Rode `uv run baixar --turno 2`"
            " novamente mais tarde para completar o 2º turno."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
