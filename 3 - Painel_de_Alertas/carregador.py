# carregador.py
import duckdb

COLUNAS_OBRIGATORIAS = ["cpf", "id_aluno", "id_turma", "nm_aluno", "data_nascimento"]

_FILTRO_ANOS_2026 = """
    num_ano_letivo LIKE '%2026%'
    AND num_ano_letivo NOT IN (
        '2026 - MEPES', '2026/1S', '2026/1S - IASES',
        '2026/1S - UP', '2026/2S CEEJA/NEEJA'
    )
"""

_FILTRO_ANOS_2026_CPF = """
    num_ano_letivo LIKE '%2026%'
    AND num_ano_letivo != '2026 - MEPES'
"""


def carregar_base(nome_arquivo):
    """
    Lê uma base empilhada de alunos via DuckDB (out-of-core, sem
    materializar tudo em pandas antes de ter certeza de que precisa).
    """
    con = duckdb.connect()
    df = con.execute("""
        SELECT *
        FROM read_parquet(?)
    """, [nome_arquivo]).df()
    df.columns = df.columns.str.strip().str.lower()
    return df


# filtro geral para outros alertas
def aplicar_filtros(df):
    con = duckdb.connect()
    return con.execute(f"""
        SELECT *
        FROM df
        WHERE {_FILTRO_ANOS_2026}
          AND TRIM(situacao_enturmacao) = 'Em curso'
          AND TRIM(situacao_matricula) = 'Em curso'
          AND data_encerramento_matricula IS NULL
          AND tipo_atendimento = 'Regular'
    """).df()


# filtro exclusivo para o CPF — tipo_atendimento inclui todos
def aplicar_filtros_cpf(df):
    """
    Réplica de df.drop_duplicates(subset=["id_aluno"], keep="first").

    IMPORTANTE: "primeiro" aqui depende da ordem física das linhas no
    parquet/DataFrame de entrada — a coluna _seq preserva essa ordem via
    row_number() OVER () sem ORDER BY, que reflete a ordem de leitura.
    Se a base de entrada não estiver na ordem que você espera (ex: já foi
    reordenada por outra etapa do pipeline), esse dedup não é equivalente
    ao pandas original.
    """
    con = duckdb.connect()
    return con.execute(f"""
        WITH numerado AS (
            SELECT *, row_number() OVER () AS _seq
            FROM df
        ),
        filtrado AS (
            SELECT *,
                   row_number() OVER (PARTITION BY id_aluno ORDER BY _seq) AS _rn
            FROM numerado
            WHERE {_FILTRO_ANOS_2026_CPF}
              AND TRIM(situacao_enturmacao) = 'Em curso'
              AND TRIM(situacao_matricula) = 'Em curso'
              AND data_encerramento_matricula IS NULL
        )
        SELECT * EXCLUDE (_seq, _rn)
        FROM filtrado
        WHERE _rn = 1
    """).df()
