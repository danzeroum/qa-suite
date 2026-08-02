"""Fronteira do não-sensível para a telemetria da Fase C.

A Fase C é sondagem ativa; quando ela emitir métrica (junto do motor, pós-C0d),
essa métrica é uma nova BORDA DE ESCRITA e tem de nascer sanitizada — como o
`Finding` nasce mascarado e a `remediacao` nasce sem markup. Este módulo é essa
borda, e existe ANTES da primeira métrica `fasec.*`: guarda que nasce junto com
a funcionalidade nasce frouxa (a mesma razão de `gates.py` preceder o primeiro
teste ativo).

A garantia é fail-closed em duas camadas, e o default é DESCARTAR:

* **allowlist de CHAVE** (`CAMPOS_DA_TELEMETRIA_FASE_C`, irmão do
  `CAMPOS_DO_PROMPT` que barra o que vai para a LLM): só contagem, tempo, razão,
  flag e hash saem. `recurso`, `evidencia`, `remediacao`, URL-com-query e corpo
  não estão na lista — logo não saem, mesmo que o emissor os passe;
* **validação de VALOR**: mesmo numa chave permitida, só número, bool, hash
  hexadecimal e dict de contagem (sub-chave enum, valor inteiro) passam. String
  livre — que poderia carregar dado — é descartada, e sub-chave suja num dict
  permitido cai sozinha.

Cinto e suspensório: `serializar` ainda passa o JSON final por
`mascarar_valores_registrados`, o MESMO mascaramento por valor do `summary.json`.
A camada de filtro já impede o dado de chegar aqui; o mascaramento é a segunda
linha para o caso de um valor registrado (uma senha construída em `Credencial`)
aparecer por um caminho não previsto.

Somente stdlib + `webqa.sanitize` (já a borda de escrita da casa).
"""
from __future__ import annotations

import json
import re

from webqa.sanitize import mascarar_valores_registrados

# Allowlist de chaves. SÓ agregado: contagem, tempo, razão, flag, hash. Nada que
# nomeie um recurso, carregue evidência ou reproduza uma URL. Estender esta lista
# é decisão de revisão — o default (chave ausente) é não sair.
CAMPOS_DA_TELEMETRIA_FASE_C = frozenset({
    # identidade agregada (hash, nunca nome)
    "alvo_sha256", "escopo_hash",
    # cobertura
    "caminhos_sondados", "caminhos_esperados", "categorias_cobertas",
    "alvos_no_escopo", "alvos_cobertos", "superficie_dry_run",
    # achados — só contagem (inclusive dicts de contagem por categoria/severidade)
    "achados_por_categoria", "achados_por_severidade", "achados_por_ambiente",
    "achados_novos", "achados_resolvidos", "achados_persistentes",
    # respeito ao alvo / operação
    "requisicoes_por_alvo", "intervalo_medio_s", "intervalo_piso_s",
    "n_429", "n_503", "aborts_por_alvo", "timeouts", "tempo_por_alvo_s",
    "kill_switch_acionado",
    # governança / estado
    "gate_discovery", "gate_escopo", "gate_active_probes",
    "n_entradas_de_escopo", "n_linhas_de_auditoria", "posse_divergente",
    "distribuicao_por_ambiente",
    # confiabilidade
    "run_inconclusivo", "falhas_de_resolucao", "taxa_de_flake",
})

# Hash hexadecimal (sha256 = 64; hashes curtos ≥ 7). É a ÚNICA string que passa:
# um rótulo mascarado (`[AWS_ACCESS_KEY_ID]`), uma URL ou um segredo cru têm
# caractere fora de [0-9a-f] e caem.
_HASH_HEX = re.compile(r"[0-9a-f]{7,64}")

# Chave de um dict de contagem: identificador curto tipo enum (categoria,
# severidade, ambiente). Uma URL como chave (`https://a/.git`) não casa e cai.
_CHAVE_DE_CONTAGEM = re.compile(r"[a-z0-9_.:-]{1,40}")

_DESCARTAR = object()


def _e_inteiro(v: object) -> bool:
    """Inteiro de verdade — `bool` é subclasse de `int` e não conta como contagem."""
    return isinstance(v, int) and not isinstance(v, bool)


def _valor_filtrado(valor: object) -> object:
    """Valor saneado, ou `_DESCARTAR`. Default fail-closed: o que não reconheço, cai."""
    if isinstance(valor, bool):            # flag
        return valor
    if isinstance(valor, (int, float)):    # contagem / tempo
        return valor
    if isinstance(valor, str):             # só hash hexadecimal
        return valor if _HASH_HEX.fullmatch(valor) else _DESCARTAR
    if isinstance(valor, dict):            # dict de contagem: sub-chave enum, valor int
        limpo = {k: v for k, v in valor.items()
                 if isinstance(k, str) and _CHAVE_DE_CONTAGEM.fullmatch(k) and _e_inteiro(v)}
        return limpo if limpo else _DESCARTAR
    return _DESCARTAR


def filtrar(dados: dict) -> dict:
    """Aplica as duas camadas: allowlist de chave, depois validação de valor.

    Retorna um dict novo só com o que é agregado e não-sensível. Chave fora da
    allowlist e valor não reconhecido são silenciosamente descartados — o
    silêncio aqui é o lado seguro: métrica é observabilidade, não veredito, e
    perder uma contagem duvidosa é melhor que vazar um dado.
    """
    limpo: dict = {}
    for chave, valor in dados.items():
        if chave not in CAMPOS_DA_TELEMETRIA_FASE_C:
            continue
        saneado = _valor_filtrado(valor)
        if saneado is not _DESCARTAR:
            limpo[chave] = saneado
    return limpo


def serializar(dados: dict) -> str:
    """JSON do agregado já filtrado, com mascaramento por valor por cima.

    A ordem importa: filtra primeiro (a garantia), serializa, e só então mascara
    — o mascaramento é a segunda linha, não a primeira.
    """
    bruto = json.dumps(filtrar(dados), ensure_ascii=False, sort_keys=True)
    return mascarar_valores_registrados(bruto)
