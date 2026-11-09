"""
processar.py — Orquestrador de validações da Base de Frequência
Executa todas as validações em sequência e consolida o resumo.parquet

Uso:
    python processar.py
    python processar.py --force   # regenera mesmo se já existir resultado
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

import polars as pl

# ── Caminhos ──────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
BDADOS       = BASE_DIR / "BDados" / "BASE_EMPILHADA.parquet"
RESULTADOS   = BASE_DIR / "Resultados"
RESUMO_PATH  = RESULTADOS / "resumo.parquet"
TOTAL_ATIVOS_PATH = RESULTADOS / "total_ativos.json"

# Mesmos filtros do app_frequencia (e de validacoes/professores_excedentes.py).
# Se esta lista mudar, mude nos dois lugares.
ANOS_LETIVOS_VALIDOS = [
    "2026",
    "2026 - IASES",
    "2026/2S",
    "2026/2S - UP",
    "2026/2S - IASES",
    "2026/2S CEEJA/NEEJA",
]

RESULTADOS.mkdir(parents=True, exist_ok=True)

# ── Registro de validações ────────────────────────────────────────────────────
# Cada validação exporta: NOME, ARQUIVO_SAIDA, COLUNAS_RESUMO, run(df_base) -> pl.DataFrame
from validacoes import faltas_decrescentes
from validacoes import v2_faltas_decrescentes
from validacoes import frequencia_ioio
from validacoes import carga_horaria
from validacoes import ultima_aparicao
from validacoes import cor_raca
from validacoes import cpf
from validacoes import mudanca_id
from validacoes import nome_alterado   
from validacoes import mudanca_modalidade_etapa
from validacoes import turma_sem_carga_horaria
from validacoes import turma_sem_carga_horaria_registrada
from validacoes import distorcao_idade_serie

# Alertas que leem a base consolidada (Excel em BDados) — ignoram df_base.
from validacoes import frequencia_maior_100
from validacoes import frequencia_negativa


VALIDACOES = [
    faltas_decrescentes,
    v2_faltas_decrescentes,
    frequencia_ioio,
    carga_horaria,
    ultima_aparicao,
    cor_raca,
    cpf,
    mudanca_id,
    frequencia_maior_100,
    frequencia_negativa,
    nome_alterado,
    mudanca_modalidade_etapa,
    turma_sem_carga_horaria,
    turma_sem_carga_horaria_registrada,
    distorcao_idade_serie,
    # adicione novos módulos aqui
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def carregar_base() -> pl.DataFrame:
    log(f"Lendo base: {BDADOS}")
    if not BDADOS.exists():
        sys.exit(f"[ERRO] Arquivo não encontrado: {BDADOS}")
    df = pl.read_parquet(BDADOS)
    log(f"  {len(df):,} linhas | {df['dt_referencia'].n_unique()} datas | "
        f"{df['id_aluno'].n_unique():,} alunos únicos")
    return df


def gerar_total_ativos(df_base: pl.DataFrame) -> None:
    """
    Grava Resultados/total_ativos.json com o nº de alunos DISTINTOS com matrícula ATIVA,
    em turma ATIVA, nos anos letivos válidos, no snapshot mais recente (dt_referencia máx.).
    O app_frequencia lê este arquivo (pequeno) em vez do BASE_EMPILHADA.parquet,
    que não vai para o GitHub / Streamlit Cloud.
    """
    data_ref = df_base["dt_referencia"].max()
    total = (
        df_base.filter(
            (pl.col("dt_referencia") == data_ref)
            & (pl.col("num_ano_letivo").is_in(ANOS_LETIVOS_VALIDOS))
            & (pl.col("status_turma") == "ATIVA")
            & (pl.col("situacao_matricula") == "ATIVA")
        )
        .select(pl.col("id_aluno").n_unique())
        .item()
    )
    conteudo = {
        "total": int(total),
        "dt_referencia": str(data_ref),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }
    TOTAL_ATIVOS_PATH.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"✔ total_ativos.json salvo: {total:,} alunos ativos (ref. {data_ref})")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Regenera resultados mesmo se já existirem")
    args = parser.parse_args()

    log("═" * 60)
    log("PAINEL DE ALERTAS — FREQUÊNCIA")
    log("═" * 60)

    df_base = carregar_base()
    gerar_total_ativos(df_base)   # sempre regenera: é barato e não depende de --force
    frames_resumo = []

    for modulo in VALIDACOES:
        nome = modulo.NOME
        saida = RESULTADOS / modulo.ARQUIVO_SAIDA
        log(f"\n▶ Validação: {nome}")

        if saida.exists() and not args.force:
            log(f"  Já existe → {saida.name}. Use --force para regenerar.")
            df_existente = pl.read_parquet(saida)
            frames_resumo.append(df_existente.select(pl.col(modulo.COLUNAS_RESUMO)))
            continue

        try:
            df_resultado = modulo.run(df_base)
            df_resultado.write_parquet(saida)
            log(f"  ✔ {len(df_resultado):,} alertas → {saida.name}")
            frames_resumo.append(df_resultado.select(pl.col(modulo.COLUNAS_RESUMO)))
        except Exception as e:
            log(f"  ✘ ERRO em {nome}: {e}")
            raise

    # ── Consolida resumo ──────────────────────────────────────────────────────
    if frames_resumo:
        
                # Harmoniza tipos de colunas-chave antes do concat diagonal.
        # Evita SchemaError quando um módulo esquece de castar id_aluno/id_turma.
        COLUNAS_FORCAR_STRING = ["id_aluno", "id_turma"]

        frames_resumo = [
            frame.with_columns([
                pl.col(c).cast(pl.String, strict=False)
                for c in COLUNAS_FORCAR_STRING
                if c in frame.columns
            ])
            for frame in frames_resumo
        ]
        
        
        resumo = pl.concat(frames_resumo, how="diagonal")
        resumo = resumo.sort(["script", "id_aluno"])
        resumo.write_parquet(RESUMO_PATH)
        log(f"\n✔ resumo.parquet salvo: {len(resumo):,} alertas totais → {RESUMO_PATH}")
    else:
        log("\n[AVISO] Nenhum alerta gerado.")

    log("\n" + "═" * 60)
    log("Processamento concluído.")


if __name__ == "__main__":
    main()
