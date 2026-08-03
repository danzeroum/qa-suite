# Ordens de Serviço — Fase C (motor de sondagem) — estado e fila

Base: `main` @ `43373ad` (#43, C1b fatia 1 mergeada e confirmada).
Contrato do módulo: `webqa-suite/docs/handoff/FASE-C.md` · invariantes: 3 portões
(`require_discovery`/`require_escopo`/prova de posse) + HEAD-only + stdlib-first
+ escopo por origem exata + determinístico/auditável.

---

## Concluído

| OS | PR | Commit | Entrega |
|---|---|---|---|
| C1a | #42 | `174671b` | motor `webqa/sondagem.py` gated, HEAD-only, `--dry-run` default; trava invertida reconhece `sondar_caminho`; 2 specs `xfail(strict)` registram o C1b |
| C1b fatia 1 | #43 | `43373ad` | Tier A #2–#6: erro de rede por-probe (não derruba o run), `run_id` uuid, soft-404 com tipo vazio, validação de alvo, código morto removido |

Triagem das ~90 sugestões externas: **feita**. Aceitas só as que respeitam os 3
portões + HEAD-only; rejeitadas por princípio (Tier C): red-team/fuzzing,
jitter-de-evasão, bruteforce de subdomínio, timing side-channel (numpy), Host
spoofing, adaptativo/ML, supressão por honeypot. Fora do módulo (Tier D): escopo
auto-gerado, LLM dentro do `sondagem.py` (proibido por `test_convencoes`),
threat-intel externa, ZAP, servidor HTTP.

---

## Fila (ordem de execução)

### 1. C1c — DNS rebinding / TOCTOU (A#1) — PRÓXIMA, maior peso de segurança

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

Notas: a dobra do TLS é o ponto que quase toda implementação erra (pinar IP sem
`verify=False`, preservando SNI); a prova por mutação é o centro desta OS. Muda a
assinatura de `verificar_posse` (`bool` -> `frozenset`), portanto passa pela
revisão de CODEOWNERS. Os dois IPs de teste são faixas RFC 5737 e ambos
respondem `is_private=True` no 3.11 — irrelevante aqui, porque `verificar_posse`
compara IGUALDADE DE CONJUNTOS de IPs, não localidade.

### 2. C1b fatia 2 — 405 -> GET `Range: bytes=0-0` + backoff 429/503

Implementar as duas specs `xfail(strict=True)` já na `main`; implementá-las
remove os marcadores. Só `sondagem.py`. Continua HEAD-first, lê no máximo 1 byte
no fallback, nunca o corpo.

### 3. C2 — Tier B (CODEOWNERS: escopo.py + data/caminhos-sensiveis.yaml)

- soft-404 dinâmico (baseline por caminho-fantasma; +1 probe auditado)
- prova de posse por DNS-TXT / `/.well-known` (já previsto no `.example`)
- saída `--saida results.json` + SARIF (aba Security do GitHub)
- teste de sistema com os canários do fixture (`/.git/HEAD`, `/.env`, `/backup.zip`) — fecha a lacuna A.4
- ciclo de vida do finding (`baseline.yaml`: novo/reaberto/persistente)
- `procedencia` no output; `--multi-alvo` iterando o próprio escopo

---

## Pendências do dono (não-código)

- Tornar `quality-gate` required check (Settings -> Branches).
- Apagar apenas `danzeroum-patch-1` (#40) e `danzeroum-patch-2` (#41). NÃO apagar a branch de trabalho ativa (`claude/http-basic-auth-tests-i76wg8`, origem de #42/#43); `claude/ci-gate-negative-test-jnf111` já não existe no remoto.
- Assinar commits (resolver o "Unverified" para frente — nunca reescrever história).
- Portão do escopo: `escopo-autorizado.yaml` + prova de posse do `docker.danzeroum.com` (gate `WEBQA_DISCOVERY_AUTHORIZED=1`). Fechado até você abrir.
