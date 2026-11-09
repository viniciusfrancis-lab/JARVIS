# matricula_pipeline.py
"""
Lógica de carga da base de matrícula (EMPILHADO_MATRICULAS.parquet), das
5 regras de auditoria e da checagem "Última aparição".

ISOLAMENTO DE MEMÓRIA — leia antes de mexer aqui
--------------------------------------------------
Este módulo é chamado por processar_log.py em DOIS SUBPROCESSOS
SEPARADOS — --worker-matricula-regras e --worker-ultima-aparicao — não
in-process, e não como um único subprocesso combinado. Motivo,
confirmado por dois logs de produção em 2026-08-10:

  1) (processar_20260810_151248.log) del df_matricula; del base_enriq;
     gc.collect() já existia no código original, exatamente antes de
     "Última aparição" rodar — e o RSS do processo NÃO caiu (25.30 GB
     antes -> 25.32 GB depois). gc.collect() só varre objetos Python; o
     Polars aloca memória nativa via seu próprio allocator (mimalloc, em
     Rust), que RETÉM as páginas liberadas no seu arena interno em vez de
     devolvê-las ao SO. O pandas/pyarrow (usado na leitura de
     MATRICULAS_GERAIS.parquet dentro de "Última aparição") usa um
     allocator C++ diferente, que não enxerga nem reaproveita essa
     memória "livre" retida pelo Polars — resultado: OOM mesmo com
     del/gc corretos, numa máquina com ~26GB de RAM total.

  2) (processar_20260810_155513.log) Isolar as regras + "Última
     aparição" num ÚNICO subprocesso resolveu a poluição de memória
     pro PAI (confirmado: RAM livre volta a 27.94 GB depois do crash),
     mas o MemoryError continuou — porque agora era o PRÓPRIO filho que
     acumulava a mesma pressão: carregava a matrícula, rodava as 5
     regras, e SÓ DEPOIS disso, ainda vivo, tentava ler outro parquet
     grande. Só separando em DOIS processos — um que termina e devolve
     100% da RAM ao SO ANTES do outro nascer — é que "Última aparição"
     roda com o teto de RAM inteiro disponível, não a sobra de outra
     etapa.

Por isso as funções aqui usam print(flush=True) em vez de um logger
próprio: rodando como subprocesso, o stdout é capturado linha a linha
pelo processo pai (_rodar_worker em processar_log.py) e relogado lá — o
.log final continua unificado, com timestamp do pai.
"""
from __future__ import annotations

import gc
import sys
import traceback
from pathlib import Path

import duckdb
import polars as pl
import pandas as pd

from alertas_config import (
    ALERTA_DT_MATRICULA, ALERTA_RETROATIVA, ALERTA_MUDANCA_ID, ALERTA_IOIO,
    ALERTA_DEIXOU_FREQUENTAR_ATUAL,
)
from validacoes.alerta_ultima_aparicao import checar_ultima_aparicao, gerar_alerta
from validacoes import matricula_regra1_retroativa as regra1
from validacoes import matricula_regra2_ioio as regra2
from validacoes import matricula_regra3a_mudanca_id as regra3a
from validacoes import matricula_regra3b_unificacao_id as regra3b
from validacoes import matricula_regra4_dt_matricula as regra4
from validacoes import matricula_regra5_deixou_frequentar as regra5

COLUNAS_ALVO_MATRICULA = [
    "id_aluno", "nm_aluno", "data_nascimento",
    "inep_escola", "nm_escola", "nm_regional", "nm_municipio",
    "nome_turma", "nome_ano_escolaridade",
    "id_ano", "id_ano_letivo", "num_ano_letivo",
    "dt_matricula", "dt_enturmacao",
    "situacao_enturmacao", "situacao_matricula", "tipo_atendimento",
    "cpf", "data_referencia",
    "nm_filiacao_1", "nm_filiacao_2",
]

# (nome legível, arquivo final, módulo da regra, nome do alerta, coluna de
# detalhe no resultado bruto, coluna de data_retorno se houver)
REGRAS_MATRICULA = [
    ("Regra 1 - Matrícula Retroativa",   "regra1_matricula_retroativa.parquet",    regra1,  ALERTA_RETROATIVA,  "Detalhe_Retroativa",         None),
    ("Regra 2 - Frequência Io-iô",       "regra2_frequencia_ioio.parquet",         regra2,  ALERTA_IOIO,        "Detalhe_Frequencia",         "Data_Retorno"),
    ("Regra 3A - Mudança de ID Interna", "regra3a_mudanca_id.parquet",             regra3a, ALERTA_MUDANCA_ID,  "Detalhe_Mudanca_ID",         None),
    ("Regra 3B - Unificação Externa ID", "regra3b_unificacao_id.parquet",          regra3b, ALERTA_MUDANCA_ID,  "Detalhe_Unificacao",         None),
    ("Regra 4 - Alteração dt_matricula", "regra4_alteracao_dt_matricula.parquet",  regra4,  ALERTA_DT_MATRICULA,"Detalhe_Mudanca_Matricula",  None),
    ("Regra 5 - Deixou de Frequentar",   "regra5_deixou_frequentar.parquet",       regra5,  ALERTA_DEIXOU_FREQUENTAR_ATUAL, "Detalhe_Deixou_Frequentar", None),
]
_REGRAS_COM_DATAS_SEMANAS = {regra2, regra3b}
# Regra 5 precisa das linhas com situacao_matricula != 'Em curso', que o
# _carregar_matricula_filtrada descarta — então lê o parquet BRUTO direto.
_REGRAS_COM_BASE_BRUTA = {regra5}

# Duplicado intencionalmente de processar_log.py (mesma lista). Este
# módulo é importado POR processar_log.py (modo --worker-matricula) —
# importar de lá criaria import circular. É uma lista de 10 nomes de
# coluna; se um dia divergir, o schema do parquet consolidado quebra na
# hora óbvia (_consolidar_parquets), então o risco de dessincronia
# silenciosa é baixo.
COLUNAS_FORCAR_STRING = [
    "id_aluno", "cpf", "inep_escola", "ra_aluno", "id_turma",
    "ultima_aparicao", "primeira_aparicao",
    "dt_matricula", "data_nascimento", "data_referencia",
]


def _log(msg: str) -> None:
    print(msg, flush=True)


def _normalizar_tipos(df: pd.DataFrame) -> pd.DataFrame:
    for col in COLUNAS_FORCAR_STRING:
        if col in df.columns:
            df[col] = df[col].astype("string")
    return df


def _ja_existe(caminho: Path, forcar: bool) -> bool:
    return not forcar and caminho.exists()


def _collect_streaming_matricula(lf: pl.LazyFrame) -> pl.DataFrame:
    try:
        return lf.collect(engine="streaming")
    except TypeError:
        pass
    try:
        return lf.collect(streaming=True)
    except TypeError:
        pass
    _log("  ⚠️  Modo streaming indisponível nesta versão do Polars — usando collect() padrão.")
    return lf.collect()


def _carregar_matricula_filtrada(caminho_parquet_matricula: Path) -> pl.DataFrame:
    """
    Lê EMPILHADO_MATRICULAS.parquet via Polars lazy e aplica os mesmos
    filtros do carregador.py: ano letivo 2026 sem MEPES, matrícula/
    enturmação "Em curso", sem data de encerramento, atendimento Regular.
    """
    if not caminho_parquet_matricula.exists():
        _log(f"  ❌ Arquivo não encontrado: {caminho_parquet_matricula}")
        return pl.DataFrame()

    schema = pl.read_parquet_schema(caminho_parquet_matricula)
    colunas_extras = ["data_encerramento_matricula"]
    cols_ler = [c for c in COLUNAS_ALVO_MATRICULA + colunas_extras if c in schema]

    lf = pl.scan_parquet(caminho_parquet_matricula).select(cols_ler)

    n_total = lf.select(pl.len()).collect().item()
    _log(f"  Total bruto (matrícula): {n_total:,} linhas")

    if "num_ano_letivo" in cols_ler:
        col_ano = pl.col("num_ano_letivo").cast(pl.Utf8)
        lf = lf.filter(col_ano.str.contains("2026") & ~col_ano.str.contains("MEPES"))
    if "situacao_matricula" in cols_ler:
        lf = lf.filter(
            pl.col("situacao_matricula").cast(pl.Utf8).str.to_lowercase()
              .str.replace_all(r"\s+", "", literal=False) == "emcurso"
        )
    if "situacao_enturmacao" in cols_ler:
        lf = lf.filter(
            pl.col("situacao_enturmacao").cast(pl.Utf8).str.to_lowercase()
              .str.replace_all(r"\s+", "", literal=False) == "emcurso"
        )
    if "data_encerramento_matricula" in cols_ler:
        lf = lf.filter(pl.col("data_encerramento_matricula").is_null())
    if "tipo_atendimento" in cols_ler:
        lf = lf.filter(
            pl.col("tipo_atendimento").cast(pl.Utf8).str.to_lowercase()
              .str.replace_all(r"\s+", "", literal=False) == "regular"
        )

    df = _collect_streaming_matricula(lf)
    _log(f"  ✅ {len(df):,} linhas de matrícula após filtros")
    return df


def _preparar_matricula(df: pl.DataFrame) -> pl.DataFrame:
    """Normaliza campos, parseia datas, adiciona coluna 'semana' e 'nasc_str'."""
    if "nm_filiacao_1" not in df.columns:
        df = df.with_columns(pl.lit("").alias("nm_filiacao_1"))
    if "nm_filiacao_2" not in df.columns:
        df = df.with_columns(pl.lit("").alias("nm_filiacao_2"))

    df = df.with_columns([
        pl.col("id_aluno").cast(pl.Int64, strict=False),
        pl.col("nm_aluno").cast(pl.Utf8).str.to_uppercase().str.strip_chars(),
        pl.col("nm_filiacao_1").cast(pl.Utf8).str.to_uppercase().str.strip_chars().fill_null(""),
        pl.col("nm_filiacao_2").cast(pl.Utf8).str.to_uppercase().str.strip_chars().fill_null(""),
    ])
    df = df.with_columns(
        pl.col("data_referencia").cast(pl.Utf8).str.slice(0, 10)
          .str.to_date(format="%Y-%m-%d", strict=False).alias("semana")
    )
    df = df.with_columns(
        pl.col("dt_matricula").cast(pl.Utf8).str.slice(0, 10)
          .str.to_date(format="%Y-%m-%d", strict=False).alias("dt_matricula_dt")
    )
    df = df.with_columns(
        pl.col("data_nascimento").cast(pl.Utf8).str.slice(0, 10)
          .str.to_date(format="%Y-%m-%d", strict=False)
          .dt.strftime("%d/%m/%Y").fill_null("DATA_INVALIDA").alias("nasc_str")
    )
    return df.filter(pl.col("semana").is_not_null())


def _montar_base_enriquecimento_matricula(df: pl.DataFrame) -> pl.DataFrame:
    """
    ⚠️ MANTIDA só como referência/fallback manual — não é mais chamada
    pelo fluxo principal (ver _montar_base_enriquecimento_via_duckdb).
    Rodar isso exigiria ter df_matricula inteiro (22M+ linhas) ainda em
    RAM, que é exatamente o que a reestruturação de 13/08/2026 elimina.

    Agregação por aluno (nm_aluno + nasc_str) com os campos que cada
    resultado bruto de regra não tem: escola, regional, IDs, datas de
    aparição.
    """
    return (
        df.group_by(["nm_aluno", "nasc_str"])
          .agg([
              pl.col("nm_escola").first().alias("nm_escola"),
              pl.col("nm_regional").first().alias("nm_regional"),
              pl.col("id_aluno").unique().sort().str.join(", ").alias("id_aluno"),
              pl.col("semana").min().dt.strftime("%d/%m/%Y").alias("primeira_aparicao"),
              pl.col("semana").max().dt.strftime("%d/%m/%Y").alias("ultima_aparicao"),
              pl.col("semana").n_unique().alias("total_semanas"),
          ])
    )


def _montar_base_enriquecimento_via_duckdb(caminho_parquet: str) -> pl.DataFrame:
    """
    NOVO (13/08/2026) — substitui _montar_base_enriquecimento_matricula.
    Mesma agregação, mas lida do parquet via DuckDB em vez de rodar sobre
    o df_matricula inteiro ainda em RAM. Faz parte da correção estrutural:
    df_matricula agora é gravado uma vez em disco e liberado da memória
    ANTES de qualquer regra ou agregação rodar (ver rodar_regras_auditoria).

    FIRST(... ORDER BY semana) por determinismo explícito — o .first() do
    Polars original não garantia ordem sem sort prévio; isso corrige a
    ambiguidade, não muda a intenção. string_agg usa a subquery DISTINCT +
    ORDER BY interno (padrão obrigatório — ver aviso nas regras 3A/3B:
    string_agg(DISTINCT x) sem ORDER BY produz ordem não determinística
    quando há 2+ valores por grupo).
    """
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='6GB'")
    query = f"""
    WITH base AS (
        SELECT nm_aluno, nasc_str, semana, id_aluno, nm_escola, nm_regional
        FROM read_parquet('{caminho_parquet}')
    ),
    ids_distinct AS (SELECT DISTINCT nm_aluno, nasc_str, id_aluno FROM base),
    ids_agg AS (
        SELECT nm_aluno, nasc_str,
               string_agg(id_aluno, ', ' ORDER BY id_aluno) AS id_aluno
        FROM ids_distinct GROUP BY nm_aluno, nasc_str
    ),
    resumo AS (
        SELECT nm_aluno, nasc_str,
               FIRST(nm_escola ORDER BY semana)   AS nm_escola,
               FIRST(nm_regional ORDER BY semana) AS nm_regional,
               MIN(semana) AS _primeira_semana,
               MAX(semana) AS _ultima_semana,
               COUNT(DISTINCT semana) AS total_semanas
        FROM base
        GROUP BY nm_aluno, nasc_str
    )
    SELECT r.nm_aluno, r.nasc_str, r.nm_escola, r.nm_regional,
           strftime(r._primeira_semana, '%d/%m/%Y') AS primeira_aparicao,
           strftime(r._ultima_semana, '%d/%m/%Y')   AS ultima_aparicao,
           r.total_semanas, i.id_aluno
    FROM resumo r
    JOIN ids_agg i USING (nm_aluno, nasc_str)
    """
    resultado = con.execute(query).pl()
    con.close()
    return resultado


def _regra_matricula_para_longo(
    bruto: pl.DataFrame,
    base_enriq: pl.DataFrame,
    alerta_nome: str,
    col_detalhe: str,
    col_data_retorno: str | None,
) -> pd.DataFrame:
    """
    Junta o resultado BRUTO de uma regra (nm_aluno/nasc_str/Status_X) com
    a base de enriquecimento e devolve no formato longo que
    resultados.parquet espera.
    """
    colunas_finais = [
        "nm_regional", "nm_escola", "nm_aluno", "id_aluno", "data_nascimento",
        "primeira_aparicao", "ultima_aparicao", "total_semanas", "alerta", "detalhe",
        "data_retorno",
    ]

    if bruto.is_empty():
        return pd.DataFrame({
            "nm_regional":       pd.Series(dtype="string"),
            "nm_escola":         pd.Series(dtype="string"),
            "nm_aluno":          pd.Series(dtype="string"),
            "id_aluno":          pd.Series(dtype="string"),
            "data_nascimento":   pd.Series(dtype="string"),
            "primeira_aparicao": pd.Series(dtype="string"),
            "ultima_aparicao":   pd.Series(dtype="string"),
            "total_semanas":     pd.Series(dtype="UInt32"),
            "alerta":            pd.Series(dtype="string"),
            "detalhe":           pd.Series(dtype="string"),
            "data_retorno":      pd.Series(dtype="datetime64[ms]"),
        })[colunas_finais]

    enriquecido = bruto.join(base_enriq, on=["nm_aluno", "nasc_str"], how="left")
    enriquecido = enriquecido.with_columns([
        pl.lit(alerta_nome).alias("alerta"),
        pl.col(col_detalhe).alias("detalhe"),
        pl.col("nasc_str").alias("data_nascimento"),
    ])

    if col_data_retorno and col_data_retorno in enriquecido.columns:
        enriquecido = enriquecido.with_columns(pl.col(col_data_retorno).alias("data_retorno"))
    else:
        enriquecido = enriquecido.with_columns(pl.lit(None).cast(pl.Date).alias("data_retorno"))

    return enriquecido.select(colunas_finais).to_pandas()


def rodar_regras_auditoria(
    *,
    temp_dir: Path,
    temp_dir_bruto: Path,
    arq_auditoria: Path,
    caminho_parquet_matricula: Path,
    forcar: bool = False,
) -> None:
    """
    WORKER A. Carrega EMPILHADO_MATRICULAS, roda as 5 regras de auditoria
    e salva todas_regras_auditoria.parquet. NÃO toca em "Última aparição"
    — isso é o worker B, num processo separado (ver módulo main_worker_*
    e a docstring do módulo pra entender por quê os dois precisam ser
    processos DIFERENTES, não só um bloco isolado do pai).
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_dir_bruto.mkdir(parents=True, exist_ok=True)

    if _ja_existe(arq_auditoria, forcar):
        _log("  ✓ todas_regras_auditoria.parquet (já existe, pulando processamento)")
        n = len(pd.read_parquet(arq_auditoria, columns=["nm_aluno"]))
        _log(f"     {n:,} alertas lidos do disco")
        return

    precisa_base_matricula = forcar or any(
        not (temp_dir / arquivo).exists() for _, arquivo, *_ in REGRAS_MATRICULA
    )

    # NOVO (13/08/2026): antes, df_matricula (22M+ linhas) ficava vivo em
    # RAM do início ao fim das 5 regras — era passado por REFERÊNCIA pra
    # cada modulo.run(). Confirmado no log de produção de 13/08 (ACCESS_
    # VIOLATION 0xC0000005 na Regra 4, a 5ª a tocar o objeto ainda
    # residente). Agora: carrega, prepara, GRAVA uma vez em disco, solta
    # da memória — e cada regra + a agregação de enriquecimento leem do
    # parquet via DuckDB, sob demanda.
    caminho_preparado = None
    base_enriq = None
    datas_semanas = None

    if precisa_base_matricula:
        _log("▶ Iniciando: Carregar base de matrícula (EMPILHADO_MATRICULAS)")
        df_matricula = _carregar_matricula_filtrada(caminho_parquet_matricula)
        if not df_matricula.is_empty():
            df_matricula = _preparar_matricula(df_matricula)
            _log(f"  {len(df_matricula):,} registros de matrícula após preparo.")

        if not df_matricula.is_empty():
            datas_semanas = sorted(df_matricula["semana"].unique().to_list())

            caminho_preparado = temp_dir_bruto / "_matricula_preparada.parquet"
            df_matricula.write_parquet(caminho_preparado)
            del df_matricula
            gc.collect()
            _log("  ✅ Base preparada gravada em disco e liberada da memória "
                 "— nenhuma das 5 regras segura a base inteira em RAM.")

            base_enriq = _montar_base_enriquecimento_via_duckdb(caminho_preparado.as_posix())
        else:
            del df_matricula
    else:
        _log("  ✓ Todas as 5 regras de matrícula já têm parquet final — pulando carga da base.")

    partes_auditoria = []

    for nome, arquivo, modulo, alerta_nome, col_detalhe, col_retorno in REGRAS_MATRICULA:
        destino = temp_dir / arquivo
        if _ja_existe(destino, forcar):
            _log(f"  ✓ {nome:<32} (já existe, pulando)")
            partes_auditoria.append(pd.read_parquet(destino))
            continue

        _log(f"▶ Iniciando: {nome}")
        kwargs = {"datas_semanas": datas_semanas} if modulo in _REGRAS_COM_DATAS_SEMANAS else {}
        if modulo in _REGRAS_COM_BASE_BRUTA:
            kwargs["caminho_parquet_matricula"] = caminho_parquet_matricula
        caminho_bruto = modulo.run(caminho_preparado, temp_dir_bruto, forcar=forcar, **kwargs)
        bruto = pl.read_parquet(caminho_bruto)

        longo = _regra_matricula_para_longo(bruto, base_enriq, alerta_nome, col_detalhe, col_retorno)
        _log(f"     {len(longo):,} alertas")
        _normalizar_tipos(longo).to_parquet(destino, index=False)
        partes_auditoria.append(longo)
        del bruto, longo

    if base_enriq is not None:
        del base_enriq
    gc.collect()

    df_regras_auditoria = (
        pd.concat(partes_auditoria, ignore_index=True) if partes_auditoria else pd.DataFrame()
    )
    del partes_auditoria
    _normalizar_tipos(df_regras_auditoria).to_parquet(arq_auditoria, index=False)
    _log(f"  ✅ Salvo: todas_regras_auditoria.parquet ({len(df_regras_auditoria):,} linhas)")
    _log(f"  → Total regras de auditoria: {len(df_regras_auditoria):,} alertas")
    if not df_regras_auditoria.empty and "id_aluno" in df_regras_auditoria.columns:
        _log(f"     ({df_regras_auditoria['id_aluno'].nunique():,} alunos únicos)")
    # Esse processo termina logo em seguida (é um worker de CLI) — o SO
    # recupera 100% da RAM aqui, é por isso que não tem "del" adicional
    # depois disso: não tem próxima etapa dentro deste mesmo processo.


def rodar_ultima_aparicao(
    *,
    arq_auditoria: Path,
    arq_ultima: Path,
    saida_ultima_xlsx: Path,
    forcar: bool = False,
) -> None:
    """
    WORKER B. Processo NOVO, nascido DEPOIS do worker A já ter terminado
    e devolvido toda a RAM dele ao SO — por isso lê todas_regras_auditoria
    do disco em vez de receber como parâmetro em memória: neste processo,
    nada daquilo existe ainda. Lê MATRICULAS_GERAIS.parquet (a leitura que
    sempre estourava) com o teto de RAM inteiro disponível, não a sobra
    de outra etapa.
    """
    if _ja_existe(arq_ultima, forcar):
        _log("  ✓ ultima_aparicao.parquet (já existe, pulando)")
        return

    df_regras_auditoria = pd.read_parquet(arq_auditoria) if arq_auditoria.exists() else pd.DataFrame()
    _log(f"  → {len(df_regras_auditoria):,} alertas de auditoria lidos do disco")

    _log("▶ Iniciando: Última aparição")
    resultado_ultima_aparicao = checar_ultima_aparicao(
        df_regras_auditoria=df_regras_auditoria if not df_regras_auditoria.empty else None
    )
    del df_regras_auditoria
    _log(f"     {len(resultado_ultima_aparicao):,} alertas")
    if not resultado_ultima_aparicao.empty and "id_aluno" in resultado_ultima_aparicao.columns:
        _log(f"     ({resultado_ultima_aparicao['id_aluno'].nunique():,} alunos únicos)")
        _log("     (excluídos apenas alunos das regras de auditoria)")

    _normalizar_tipos(resultado_ultima_aparicao).to_parquet(arq_ultima, index=False)
    del resultado_ultima_aparicao

    _log("  → Gerando alerta_ultima_aparicao.xlsx...")
    df_alerta_xlsx = gerar_alerta(verbose=False)
    if not df_alerta_xlsx.empty:
        saida_ultima_xlsx.parent.mkdir(parents=True, exist_ok=True)
        df_alerta_xlsx.to_excel(saida_ultima_xlsx, index=False)
        _log(f"     ✅ alerta_ultima_aparicao.xlsx atualizado ({len(df_alerta_xlsx):,} linhas)")
    del df_alerta_xlsx


def _preparar_stdout_worker() -> None:
    # Ver comentário equivalente em processar_log.py._rodar_worker: o pai
    # já força PYTHONIOENCODING=utf-8 no ambiente antes de lançar este
    # processo; isso aqui é a segunda camada, pro caso de alguém rodar
    # `python matricula_pipeline.py --worker-... ...` manualmente.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main_worker_regras(argv: list[str]) -> int:
    """
    `<python/exe> --worker-matricula-regras <temp_dir> <temp_dir_bruto>
    <arq_auditoria> <caminho_parquet_matricula> [--force]`
    """
    _preparar_stdout_worker()
    forcar = "--force" in argv
    args = [a for a in argv if a != "--force"]

    if len(args) != 4:
        print(f"[worker-regras] Argumentos inválidos, esperava 4 caminhos, recebi {len(args)}: {args}", flush=True)
        return 2

    temp_dir, temp_dir_bruto, arq_auditoria, caminho_parquet_matricula = (Path(a) for a in args)

    try:
        rodar_regras_auditoria(
            temp_dir=temp_dir,
            temp_dir_bruto=temp_dir_bruto,
            arq_auditoria=arq_auditoria,
            caminho_parquet_matricula=caminho_parquet_matricula,
            forcar=forcar,
        )
    except MemoryError:
        print("[worker-regras] ❌ ERRO FATAL: MemoryError no subprocesso.", flush=True)
        print(traceback.format_exc(), flush=True)
        return 1
    except Exception:
        print("[worker-regras] ❌ ERRO FATAL no subprocesso.", flush=True)
        print(traceback.format_exc(), flush=True)
        return 1

    return 0


def main_worker_ultima_aparicao(argv: list[str]) -> int:
    """
    `<python/exe> --worker-ultima-aparicao <arq_auditoria> <arq_ultima>
    <saida_ultima_xlsx> [--force]`
    """
    _preparar_stdout_worker()
    forcar = "--force" in argv
    args = [a for a in argv if a != "--force"]

    if len(args) != 3:
        print(f"[worker-ultima] Argumentos inválidos, esperava 3 caminhos, recebi {len(args)}: {args}", flush=True)
        return 2

    arq_auditoria, arq_ultima, saida_ultima_xlsx = (Path(a) for a in args)

    try:
        rodar_ultima_aparicao(
            arq_auditoria=arq_auditoria,
            arq_ultima=arq_ultima,
            saida_ultima_xlsx=saida_ultima_xlsx,
            forcar=forcar,
        )
    except MemoryError:
        print("[worker-ultima] ❌ ERRO FATAL: MemoryError no subprocesso.", flush=True)
        print(traceback.format_exc(), flush=True)
        return 1
    except Exception:
        print("[worker-ultima] ❌ ERRO FATAL no subprocesso.", flush=True)
        print(traceback.format_exc(), flush=True)
        return 1

    return 0


if __name__ == "__main__":
    # Permite testar cada worker isolado, sem passar pelo processar_log.py:
    #   python matricula_pipeline.py --worker-matricula-regras <...>
    #   python matricula_pipeline.py --worker-ultima-aparicao <...>
    if len(sys.argv) > 1 and sys.argv[1] == "--worker-matricula-regras":
        sys.exit(main_worker_regras(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "--worker-ultima-aparicao":
        sys.exit(main_worker_ultima_aparicao(sys.argv[2:]))
    else:
        print(
            "Uso: python matricula_pipeline.py "
            "--worker-matricula-regras <4 caminhos> [--force]\n"
            "  ou python matricula_pipeline.py "
            "--worker-ultima-aparicao <3 caminhos> [--force]",
            flush=True,
        )
        sys.exit(2)
