"""VERIFICAÇÃO de que `--painel` só LÊ o ledger (OS-35).

Última instância conhecida da classe de defeito que o #32 nomeou: **a garantia
existe, a ligação não.** Até aqui "o painel não escreve no ledger" era conferido
comparando md5 antes e depois — o que prova que aquela execução não escreveu, e
nada sobre a próxima linha que alguém acrescentar.

Três camadas, porque nenhuma basta sozinha:

1. **capacidade reduzida** — o caminho do painel recebe o ledger já lido
   (`dict`) e um rótulo de texto, nunca um `Path` gravável, e a leitura pede
   `O_RDONLY` ao sistema operacional;
2. **fronteira no fonte** (aqui) — o `ast` das funções do caminho é percorrido e
   qualquer escrita fora de `destino` reprova;
3. **prova por tentativa** (aqui) — o painel roda com uma armadilha instalada
   sobre as primitivas de escrita: se ele *tentar* tocar o ledger, o teste
   explode. Diferente de conferir o arquivo depois, isto falha no ato.

A honestidade que fecha o assunto: em Python **não há ponto único de
estrangulamento para escrita em arquivo**. Isto não é o `Finding`, cuja
invariante é real porque só existe um construtor e ele sanitiza. Aqui a
impossibilidade é aproximada por três camadas, e o doc diz isso em vez de
prometer o que não tem.
"""
from __future__ import annotations

import ast
import json
import os
import stat
from pathlib import Path

import pytest

from scripts import estabilidade

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
FONTE = RAIZ / "scripts" / "estabilidade.py"

# Funções que compõem o caminho de `--painel`. Lista explícita pelo mesmo motivo
# da OS-34: derivá-la do código faria a cobertura encolher junto com o caminho.
CAMINHO_DO_PAINEL = ("ler_ledger_para_painel", "escrever_painel",
                     "violacoes_do_contrato", "_sha_do_alvo_de_hoje")

# Primitivas que gravam. `mkdir` entra porque cria diretório — efeito em disco.
ESCRITORES = {"write_text", "write_bytes", "mkdir", "touch", "unlink", "rename",
              "replace", "dump", "writelines", "write"}

# O painel PRECISA escrever o HTML. Só o `destino` é destinatário legítimo.
RECEPTORES_PERMITIDOS = {"destino"}


def _funcao(nome: str) -> ast.FunctionDef:
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"{nome}() sumiu de {FONTE.name} — o caminho do painel mudou")


def _raiz_do_receptor(no: ast.AST) -> str:
    """Nome da variável na base de `a.b.c.write_text()` — aqui, `a`."""
    while isinstance(no, ast.Attribute):
        no = no.value
    return no.id if isinstance(no, ast.Name) else ""


# ---------- camada 2: fronteira no fonte ----------

@pytest.mark.parametrize("nome", CAMINHO_DO_PAINEL)
def test_caminho_do_painel_nao_contem_escrita_indevida(nome):
    """Qualquer gravação fora de `destino` reprova, apontando a linha."""
    ofensores = []
    for no in ast.walk(_funcao(nome)):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
            continue
        if no.func.attr not in ESCRITORES:
            continue
        if _raiz_do_receptor(no.func.value) in RECEPTORES_PERMITIDOS:
            continue
        ofensores.append(f"{FONTE.name}:{no.lineno} → .{no.func.attr}()")

    assert not ofensores, (
        f"{nome}() grava fora de `destino`:\n  " + "\n  ".join(ofensores)
        + "\nO painel é consumidor do ledger, nunca escritor. Quem grava o ledger "
          "é o classificador, e só ele.")


@pytest.mark.parametrize("nome", CAMINHO_DO_PAINEL)
def test_caminho_do_painel_nao_abre_arquivo_para_escrita(nome):
    """`open(x, "w")` e `os.open(..., O_WRONLY)` não passam pela checagem de
    atributo acima — precisam de verificação própria."""
    for no in ast.walk(_funcao(nome)):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func.attr if isinstance(no.func, ast.Attribute) else getattr(no.func, "id", "")
        if alvo not in ("open", "fdopen"):
            continue
        modos = [a.value for a in no.args if isinstance(a, ast.Constant)
                 and isinstance(a.value, str)]
        modos += [k.value.value for k in no.keywords if k.arg == "mode"
                  and isinstance(k.value, ast.Constant)]
        for modo in modos:
            assert not set(modo) & set("wax+"), (
                f"{nome}() abre arquivo em modo {modo!r} ({FONTE.name}:{no.lineno})")


def test_leitura_do_ledger_pede_somente_leitura_ao_sistema():
    """`O_RDONLY` explícito: o que o código PEDE ao sistema fica legível na linha."""
    fonte = ast.dump(_funcao("ler_ledger_para_painel"))
    assert "O_RDONLY" in fonte
    for gravavel in ("O_WRONLY", "O_RDWR", "O_APPEND", "O_CREAT", "O_TRUNC"):
        assert gravavel not in fonte, f"o painel pediu {gravavel} ao abrir o ledger"


# ---------- camada 3: prova por tentativa ----------

class _EscritaProibida(AssertionError):
    pass


@pytest.fixture
def armadilha_de_escrita(monkeypatch):
    """Explode se QUALQUER escrita mirar o caminho vigiado.

    Independente de permissão de arquivo — e isso importa: este ambiente roda
    como root, onde `chmod 0444` não impede gravação nenhuma. Um teste que só
    conferisse a permissão daria uma garantia falsa, que é exatamente a classe
    de defeito que esta OS fecha.
    """
    vigiados: list[Path] = []

    real_write_text = Path.write_text
    real_open = os.open

    def write_text(self, *a, **k):
        if any(os.path.samestat(os.stat(self), os.stat(v))
               for v in vigiados if Path(self).exists() and Path(v).exists()):
            raise _EscritaProibida(f"o painel tentou gravar em {self}")
        return real_write_text(self, *a, **k)

    def abrir(caminho, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC):
            for v in vigiados:
                if str(caminho) == str(v):
                    raise _EscritaProibida(f"o painel abriu {caminho} para escrita")
        return real_open(caminho, flags, *a, **k)

    monkeypatch.setattr(Path, "write_text", write_text)
    monkeypatch.setattr(os, "open", abrir)
    return vigiados


def _ledger(tmp_path: Path) -> Path:
    caminho = tmp_path / "ledger.json"
    caminho.write_text(json.dumps({"schema": 5, "execucoes": [
        {"generated_at": "2026-07-30 02:38:18", "dia_utc": "2026-07-30",
         "origem": "ci", "alvo_sha256": "a" * 64, "browser_total": 9,
         "infra_flakes": 0, "streak": 1, "classificador": 1}]}), encoding="utf-8")
    return caminho


def test_painel_roda_sem_tentar_escrever_no_ledger(tmp_path, armadilha_de_escrita):
    """Falha NO ATO da tentativa, não depois por comparação de conteúdo."""
    ledger = _ledger(tmp_path)
    armadilha_de_escrita.append(ledger)
    destino = tmp_path / "report" / "estabilidade.html"

    assert estabilidade.main(["--ledger", str(ledger), "--painel", str(destino)]) == 0
    assert destino.exists() and "<h1>" in destino.read_text(encoding="utf-8")


def test_a_armadilha_realmente_pega_uma_escrita(tmp_path, armadilha_de_escrita):
    """Sem isto, o teste acima passaria mesmo com a armadilha quebrada — seria
    verde sobre guarda morta, a classe de defeito outra vez."""
    ledger = _ledger(tmp_path)
    armadilha_de_escrita.append(ledger)

    with pytest.raises(_EscritaProibida):
        ledger.write_text("{}", encoding="utf-8")


def test_painel_nao_altera_o_ledger_nem_o_mtime(tmp_path):
    """Complemento da tentativa: o arquivo em disco fica idêntico, mtime inclusive."""
    ledger = _ledger(tmp_path)
    antes = (ledger.read_bytes(), ledger.stat().st_mtime_ns)

    estabilidade.main(["--ledger", str(ledger), "--painel", str(tmp_path / "p.html")])

    assert (ledger.read_bytes(), ledger.stat().st_mtime_ns) == antes


def test_painel_funciona_com_ledger_somente_leitura(tmp_path):
    """`0444` prova que o painel NUNCA PRECISOU de escrita.

    Não prova que ele não pode escrever: como root, a permissão não bloqueia
    nada. Quem impede é a fronteira no fonte; esta camada mostra que o caminho
    feliz atravessa um ledger imutável sem reclamar.
    """
    ledger = _ledger(tmp_path)
    os.chmod(ledger, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        destino = tmp_path / "p.html"
        assert estabilidade.main(["--ledger", str(ledger), "--painel", str(destino)]) == 0
        assert destino.exists()
    finally:
        os.chmod(ledger, stat.S_IRUSR | stat.S_IWUSR)


# ---------- a trava é do painel, não do script ----------

def test_o_classificador_continua_podendo_gravar(tmp_path):
    """A restrição vale para o caminho do painel. Quem registra execução grava —
    senão a OS teria travado o ledger inteiro em vez de proteger a fonte."""
    ledger = {"schema": estabilidade.SCHEMA, "execucoes": []}
    classificacao = estabilidade.Classificacao(
        generated_at="2026-08-01 03:00:00", browser_total=7, flakes=())

    registro = estabilidade.registrar(ledger, classificacao, "b" * 64, origem="vps")
    assert registro.entrada is not None
    assert len(ledger["execucoes"]) == 1, "o classificador precisa continuar escrevendo"


def test_escrever_painel_nao_recebe_caminho_do_ledger():
    """Capacidade reduzida: a função recebe DADOS e um rótulo de texto.

    Sem um `Path` do ledger em mãos, a escrita indevida precisaria primeiro
    reconstruir o caminho — que é justamente o tipo de linha que a fronteira no
    fonte pega.
    """
    import inspect

    assinatura = inspect.signature(estabilidade.escrever_painel)
    assert "ledger_path" not in assinatura.parameters, "rótulo não é caminho"
    assert assinatura.parameters["rotulo_do_ledger"].kind is inspect.Parameter.KEYWORD_ONLY
    assert assinatura.parameters["ledger"].annotation == "dict"
