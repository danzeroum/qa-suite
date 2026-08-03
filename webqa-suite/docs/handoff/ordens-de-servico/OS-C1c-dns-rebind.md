# OS C1c — DNS rebinding / TOCTOU (A#1) — pronta para executar

Base: `main` @ `43373ad` (pós-#43, C1b fatia 1).
Contrato: `webqa-suite/docs/handoff/FASE-C.md`.
⚠️ Mexe em `webqa/escopo.py` → **CODEOWNERS**, passa pela revisão do dono.

---

## Bloco da OS (colar como está)

```xml
<lang>Python 3.11 + httpx + pytest (webqa/sondagem.py; webqa/escopo.py é CODEOWNERS-protegido)</lang>
<task>Fechar A#1 (DNS rebinding/TOCTOU): a prova de posse e o HEAD real usam o MESMO IP; divergência entre o snapshot e a resolução no probe aborta posse-divergente, sem desligar TLS.</task>
<context>Hoje escopo.verificar_posse(host)->bool resolve o IP e o httpx.head resolve DE NOVO — janela para reapontar a 169.254.169.254 (metadados). sondar() já é gated (require_discovery/require_escopo), cliente follow_redirects=False, HEAD-only. Não há flag pronta no httpx: exige transport/resolver que pina host->IP mantendo server_hostname no SNI.</context>
<rules>
- Pense passo a passo antes de responder.
- verificar_posse passa a devolver frozenset de IPs pinados (vazio = sem posse); sondar conecta SÓ nesses IPs. (escopo.py -> revisão de code owner.)
- TLS nunca desligado: SNI/Host permanecem o hostname, cert verificado contra ele. Proibido verify=False.
- Resolução no probe divergente do snapshot -> aborta posse-divergente, zero requisições. HEAD 405/429 e Tier B fora.
</rules>
<aceite>
- Requisição sai para o IP pinado do snapshot; host reapontado entre carregar e probe -> posse-divergente, executado=0.
- Verificação TLS ativa contra o hostname (nenhum caminho com verify=False).
- Portões, HEAD-only e follow_redirects=False intactos; sem regressão no gate.
</aceite>
<testes>
- snapshot {203.0.113.7}, probe resolve {198.51.100.9} -> posse-divergente, executado=0.
- posse ok -> transport registra IP conectado == IP pinado.
- fonte reintroduzindo verify=False ou re-resolução livre -> prova por mutação reprova.
</testes>
<recomendacao>
- Separe verificação (mock: rebind reintroduzido reprova) de validação (requisição vai ao IP certo com TLS por hostname).
</recomendacao>
```

---

## Notas de execução (para o dev)

**A dobra do TLS é o centro da OS.** Pinar IP trocando o hostname na URL quebra a
verificação do certificado (o cert é do hostname, não do IP) — e o "conserto"
tentador é `verify=False`, que destrói a garantia. O caminho correto é um
transport/resolver que mapeia `host -> IP` **preservando `server_hostname`** no
SNI e o header `Host`. Não existe flag pronta no httpx: é a fatia de maior peso.

**Por que prova por mutação, e não só asserção positiva.** O valor aqui é provar
que a janela FECHOU. Um teste que passa sem ver o rebind reprovar não provou
nada — é a classe de defeito "garantia existe, ligação não" (D6, #31). Reintroduza
o rebind e o `verify=False`, um por vez, e registre no PR que a suíte reprova.

**Sobre os IPs dos testes:** ambos (`203.0.113.7`, `198.51.100.9`) são faixas
RFC 5737 e respondem `is_private=True` no 3.11 — irrelevante aqui, porque
`verificar_posse` compara **igualdade de conjuntos** de IPs, não localidade.

**Fora do escopo desta OS:** HEAD 405 -> GET `Range` e backoff 429/503 (são os
dois `xfail(strict)` já na `main`, e são a C1b fatia 2); todo o Tier B (C2).
PR isolado e revisável, como o handoff pede.

**Fluxo:** specs `xfail` -> implementação -> prova por mutação -> PR. Nenhuma
requisição real sai (transport dublado + `getaddrinfo` dublado).

---

## Fila depois desta

1. **C1b fatia 2** — 405 -> GET `Range: bytes=0-0` + backoff 429/503 (remove os xfail strict).
2. **C2 (Tier B, CODEOWNERS)** — soft-404 dinâmico (baseline fantasma, +1 probe auditado), posse por DNS-TXT/`.well-known`, saída `--saida results.json` + SARIF, teste de sistema com os canários do fixture (`/.git/HEAD`, `/.env`, `/backup.zip` — fecha a lacuna A.4), ciclo de vida do finding (`baseline.yaml`), `procedencia` no output, `--multi-alvo`.

## Pendências do dono (não-código)

- Apagar `danzeroum-patch-1` (#40) e `danzeroum-patch-2` (#41). **Não** apagar a branch de trabalho ativa (`claude/http-basic-auth-tests-i76wg8`).
- Assinar commits — resolver o "Unverified" **para frente**, nunca reescrevendo história (o ruleset bloqueia force push).
- Portão do escopo: `escopo-autorizado.yaml` + prova de posse do `docker.danzeroum.com`, `WEBQA_DISCOVERY_AUTHORIZED=1`. Fechado até você abrir.
- ✅ Required check: **já feito** pelo ruleset `protecao-main-fase-c` (`Verificação da suíte`).
