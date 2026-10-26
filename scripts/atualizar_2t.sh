#!/usr/bin/env bash
# Verifica se o BU do 2º turno já está completo no portal do TSE e, se estiver,
# baixa, processa e reexecuta os notebooks.
#
# Códigos de saída: 0 = pipeline rodou (ou já estava em dia); 3 = ainda não publicado (ou incompleto);
# outro = erro.
set -euo pipefail
cd "$(dirname "$0")/.."

lista=$(uv run baixar --listar --turno 2)
echo "$lista" | head -1
if ! echo "$lista" | head -1 | grep -q "^2º turno: 28 UFs"; then
    exit 3
fi

uv run baixar --turno 2

# Já processado e nenhum zip mais novo (ex.: execução repetida da tarefa agendada): nada a fazer.
saida=data/processed/secoes_2t.parquet
if [ -f "$saida" ] && [ -z "$(find data/raw/2t -name 'bweb_2t_*.zip' -newer "$saida")" ]; then
    echo "2º turno já processado e sem arquivos novos."
    exit 0
fi

uv run processar --turno 2
uv run python scripts/gerar_notebooks.py --executar
