# alertas_config.py
"""
Configuração centralizada de rótulos de alertas.
FONTE ÚNICA DE VERDADE.
"""

TODOS_ALERTAS = [
    "CPF inválido/em branco",    
    "Matrícula duplicada",
    "Deficiência sem descrição",
    "Descrição de deficiência indevida",
    "dt_matricula alterada",
    "Matrícula retroativa",
    "Mudança de id_aluno",
    "Frequência io-iô",
    "Sem_autodeclaracao_racial",
    "Última aparição anterior a hoje",
    "AEE_AC_sem_Regular",
    "Deixou de frequentar (situação atual)",
]

# ─── Rótulos específicos para matricula_data.py ──
ALERTA_DT_MATRICULA    = "dt_matricula alterada"
ALERTA_RETROATIVA      = "Matrícula retroativa"
ALERTA_MUDANCA_ID      = "Mudança de id_aluno"
ALERTA_IOIO            = "Frequência io-iô"
ALERTA_ULTIMA_APARICAO = "Última aparição anterior a hoje"
ALERTA_DEIXOU_FREQUENTAR = "Deixou de frequentar - última aparição"#
ALERTA_TRANSFERIDO = "Transferido - última aparição"#
ALERTA_SEM_AUTODECLARACAO_RACIAL = "Sem_autodeclaracao_racial"
ALERTA_AEE_AC_SEM_REGULAR = "AEE_AC_sem_Regular"
# Regra 5 (matricula_regra5_deixou_frequentar). NÃO reutilizar ALERTA_DEIXOU_FREQUENTAR,
# que é o rótulo do desdobramento da "Última aparição".
ALERTA_DEIXOU_FREQUENTAR_ATUAL = "Deixou de frequentar (situação atual)"

ALERTAS_AUDITORIA = {
    ALERTA_DT_MATRICULA,
    ALERTA_RETROATIVA,    
    ALERTA_MUDANCA_ID,
    ALERTA_IOIO,
    ALERTA_ULTIMA_APARICAO,    
    ALERTA_DEIXOU_FREQUENTAR_ATUAL,
}