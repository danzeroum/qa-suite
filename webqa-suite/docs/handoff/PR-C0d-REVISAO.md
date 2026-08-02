# PR-C0d — Pacote de revisão da inversão da trava (RASCUNHO, NÃO aplicado)

> **Este documento NÃO abre a trava.** É a proposta que o code owner revisa e
> assina. A inversão só é aplicada em `tests/test_fase_c_travada.py` num PR
> isolado, DEPOIS do sign-off escrito abaixo. Enquanto este doc existir sem a
> assinatura, a trava segue fechada (`test_fase_c_nao_existe_ainda` no lugar).

## 1. Classificação de cada assertion — inverte x permanece

**Inverte** (afirmações de *ausência de capacidade*):

| assertion | por quê |
|---|---|
| docstring do módulo | postura muda de "prova que a Fase C não existe" para "prova que ela só existe gated" |
| `test_fase_c_nao_existe_ainda` -> `test_sondagem_ativa_so_existe_sob_gate_escopo_e_auditoria` | era "nenhum símbolo pode existir"; vira "onde existir, sob gate+escopo+auditoria" |

**Permanece idêntico** (estrutural — a garantia não afrouxa):

| assertion | por quê |
|---|---|
| detector `sondagens_em`/`_docstrings` + 5 auto-testes | o detector segue provado |
| `test_nenhum_check_sonda_caminho_sensivel` | checks/ (passiva) nunca sonda — antes e depois |
| `test_o_detector_de_simbolo_pega_um_plantado` | valida a detecção de símbolo que o teste invertido usa |
| gates: desligado por default, só "1" libera, require_active_probes pula/passa/mensagem | fail-closed não muda com a trava |
| matriz 2x2 + carga-não-vaza + llm-independente | independência dos gates é estrutural |
| `test_nenhum_check_consome_o_gate_ativo_hoje` | checks/ segue sem consumir o gate (só a docstring atualiza) |
| `test_o_ambiente_de_teste_nao_traz_autorizacao_ligada` | a suíte nunca roda autorizada, nem pós-trava |

## 2. Cabeçalho de sign-off (o objeto da assinatura)

```
PR-C0d — Inversão da trava da Fase C  (tests/test_fase_c_travada.py)
Autorização de code owner OBRIGATÓRIA.

INVERTE: docstring do módulo; test_fase_c_nao_existe_ainda ->
         test_sondagem_ativa_so_existe_sob_gate_escopo_e_auditoria
         (módulo de webqa/ que defina sondagem consome require_discovery +
          require_escopo + AuditLog; checks/ não define sondagem; sem motor, passa).
PERMANECEM: detector e auto-testes; checks/ nunca sonda; gates fail-closed e
            independentes; ambiente de teste nunca autorizado.
NÃO cria webqa/sondagem.py. NÃO toca gates/escopo/audit. Só stdlib.

Assino a inversão acima:
  Code owner: ____________________   Data: __________   PR: #____
```

## 3. Diff unificado proposto

```diff
--- a/tests/test_fase_c_travada.py
+++ b/tests/test_fase_c_travada.py
@@ -1,16 +1,19 @@
-"""VERIFICAÇÃO de que a Fase C continua travada (OS-36).
+"""VERIFICAÇÃO de que a Fase C só existe sob gate + escopo + auditoria (PR-C0d).
 
-Aqui não se testa **ação** nenhuma — testa-se a **recusa**. Nenhuma linha de
-sondagem ativa é escrita, e nenhuma requisição sai: o que se prova é que, sem
-`WEBQA_ACTIVE_PROBES_AUTHORIZED=1`, nada acontece; que a fronteira é estrutural
-e não convenção; e que os dois gates são independentes.
-
-Por que agora, com a Fase C ainda travada: enquanto "travada" for promessa, ela
-depende de vigilância humana — e vigilância humana é exatamente o que este
-projeto substitui por invariante estrutural em todo lugar (o `Finding` que
-sanitiza no construtor, o teste que lê o fonte da Fase B e reprova `httpx`). No
-dia em que houver alvo autorizado, a capacidade nasce sobre uma fronteira **já
-provada**, não sobre uma frase num documento.
+INVERSÃO da trava (OS-36 -> C0d). Antes, este arquivo provava a **ausência** da
+capacidade: nenhum símbolo de sondagem ativa podia existir. A trava foi aberta
+por code owner (PR-C0d, isolado e assinado), e agora ele prova o **contorno**:
+a capacidade PODE existir, mas só sob governança - todo módulo que defina
+sondagem ativa consome `require_discovery` + `require_escopo` e registra em
+auditoria. Enquanto o motor (C1, `webqa/sondagem.py`) não for escrito, nenhum
+módulo define os símbolos e a verificação passa: a trava abriu, o motor virá.
+
+O que NÃO mudou, e por quê: os gates continuam fail-closed (só `"1"` autoriza),
+independentes entre si, e `require_active_probes` continua pulando sem
+autorização; a camada passiva (`checks/`) continua sem sondar caminho não
+oferecido nem consumir o gate ativo; e o ambiente de teste continua proibido de
+rodar autorizado. Abrir a trava move a fronteira de "não existe" para "existe
+gated" - não afrouxa nenhuma das garantias estruturais.
 
 O detector é o coração deste arquivo, e ele próprio é testado: um detector de
 violação que nunca detectou uma violação plantada não está provado.
@@ -156,25 +159,39 @@
           "Pedir ao servidor o que ele não ofereceu é intrusão, não auditoria.")
 
 
-def test_fase_c_nao_existe_ainda():
-    """A ausência dos símbolos é intencional — e verificada.
+BIBLIOTECA = RAIZ / "webqa"
+_MARCAS_DE_GOVERNANCA = ("require_discovery", "require_escopo")
+_MARCA_DE_AUDITORIA = "AuditLog"
 
-    Não é sobre o nome: é sobre a capacidade. Se um deles aparecer, alguém
-    começou a codificar a sondagem ativa, e isso precisa passar por revisão
-    consciente em vez de entrar de carona num PR sobre outra coisa.
+
+def _define_sondagem(arvore: ast.AST) -> bool:
+    return any(
+        isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
+        and no.name in SIMBOLOS_DA_FASE_C
+        for no in ast.walk(arvore))
+
+
+def test_sondagem_ativa_so_existe_sob_gate_escopo_e_auditoria():
+    """INVERSÃO de `test_fase_c_nao_existe_ainda` (PR-C0d).
+
+    Todo módulo de `webqa/` que DEFINA um símbolo de sondagem consome
+    require_discovery + require_escopo e registra em AuditLog; `checks/` não
+    define sondagem alguma. Sem motor, passa (a trava abriu, C1 virá).
     """
-    definidos = []
+    ofensores = []
     for arquivo in sorted(CHECKS.rglob("*.py")):
-        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
-        for no in ast.walk(arvore):
-            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
-                if no.name in SIMBOLOS_DA_FASE_C:
-                    definidos.append(f"{arquivo.relative_to(RAIZ)}:{no.lineno} → {no.name}")
-
-    assert not definidos, (
-        "símbolo de sondagem ativa definido em checks/:\n  " + "\n  ".join(definidos)
-        + "\nA Fase C está desenhada e NÃO implementada de propósito. Construir "
-          "capacidade intrusiva antes de haver alvo autorizado é YAGNI com peso ético.")
+        if _define_sondagem(ast.parse(arquivo.read_text(encoding="utf-8"))):
+            ofensores.append(f"{arquivo.relative_to(RAIZ)}: sondagem em checks/ (camada passiva)")
+    for arquivo in sorted(BIBLIOTECA.rglob("*.py")):
+        fonte = arquivo.read_text(encoding="utf-8")
+        if not _define_sondagem(ast.parse(fonte)):
+            continue
+        faltando = [m for m in _MARCAS_DE_GOVERNANCA if m not in fonte]
+        if _MARCA_DE_AUDITORIA not in fonte:
+            faltando.append(_MARCA_DE_AUDITORIA)
+        if faltando:
+            ofensores.append(f"{arquivo.relative_to(RAIZ)} define sondagem sem: " + ", ".join(faltando))
+    assert not ofensores, ("capacidade de sondagem fora da governança de C1:\n  " + "\n  ".join(ofensores))
 
 
 def test_o_detector_de_simbolo_pega_um_plantado():
```

## 4. Prova por mutação (a executar após o sign-off, no repo real)

| cenário | esperado |
|---|---|
| sem `webqa/sondagem.py` (estado pós-C0d) | passa |
| `sondagem.py` define `probe_path` sem gate/escopo | reprova |
| mesma capacidade sob require_discovery+require_escopo+AuditLog | passa |

Ensaiado em sandbox na sessão de origem (passa / reprova / passa); a execução
formal roda no repo real depois de assinado.
