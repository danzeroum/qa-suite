# Ordens de Serviço em aberto — Dimensão `seguranca` + Camada LLM

Todas as OS abaixo estão **prontas para execução**, na ordem de dependência.
Cada bloco é colável isoladamente. Contratos de arquitetura: `docs/SEGURANCA.md`
(dimensão de segurança) e `docs/LLM.md` (camada de LLM local).

Base do repositório: `main` atual (pós dimensão frontend/ux/lgpd, campanha,
ledger com quarentena por versão de classificador, runtime Docker da VPS).

---

## Sequência e dependências

```
OS-20 v2 (network_log + value objects Finding/Recurso)
   └── OS-21 (Fase A: headers/mixed/MIME/segredos/cookies)
          └── OS-22 (Fase B: magic bytes/metadados/SVG/sourcemap/SRI)
                 └── [Fase C — apenas desenhada em docs/SEGURANCA.md, TRAVADA]

OS-23 v2 (webqa/llm.py — abstração + gate + veto de endpoint por IP)
   └── OS-24 v2 (scripts/sumario.py — processo separado + guardas)
```

As duas trilhas (segurança e LLM) são independentes entre si; a LLM só depende de
que o `summary.json` exista, o que já é verdade hoje.

---

## OS-20 v2 — `network_log` enriquecida + `Finding` como linguagem ubíqua (DDD)

```xml
<lang>Python 3.11 stdlib + Playwright (webqa/dominio.py novo, webqa/trackers.py, conftest.py; base: main atual)</lang>
<task>Introduzir os value objects Finding/Recurso da dimensão seguranca e enriquecer a network_log com metadados de resposta, sem persistir corpo em disco. Commitar docs/SEGURANCA.md.</task>
<context>Hoje NetworkLog guarda só (url, resource_type), frozen. Ver docs/SEGURANCA.md (deste PR). Finding é value object cuja invariante "evidência nunca em claro" mora no construtor. sanitize.py já existe e mascara PII na borda.</context>
<rules>
- webqa/dominio.py: @dataclass(frozen=True) Finding(tipo, recurso, severidade:Literal["alta","media","baixa"], evidencia, fase:Literal["A","B","C"]); no __post_init__ a evidencia passa por sanitize — impossível instanciar com segredo em claro.
- Recurso(url, status, headers lowercase, content_type, size, scheme, from_origin:bool) via context.on("response"); ler_corpo(rec, max_bytes=512_000) em memória, retorna None+truncado acima do teto, NUNCA grava em disco.
- from_origin normaliza www/sem-www reusando a normalização do inventário de terceiros.
- Compatibilidade: campos antigos preservados; nenhum check atual regride.
</rules>
<aceite>
- Finding com evidencia "AKIA1234..." nasce mascarado (teste prova a invariante; instanciar em claro é impossível).
- network_log contra fixture expõe headers/content_type por Recurso; grep no PR confirma zero escrita de corpo em disco; git status limpo.
- Recurso de 3ª parte from_origin=False; www e sem-www do alvo = True.
</aceite>
<testes>
- Unit (sem rede): Finding mascara evidência com segredo; Recurso de response fake; normalização www.
- ler_corpo >512KB → None+truncado; segunda leitura não falha.
- Regressão: -m "lgpd or frontend or ux" contra o fixture sem quebra.
</testes>
<recomendacao>
- DDD: Finding e Recurso são value objects imutáveis, NetworkLog é o aggregate; a invariante mora no construtor, não repetida em cada check.
- Separe verificação (unit dos value objects sem rede) de validação (network_log real contra o fixture).
</recomendacao>
```

---

## OS-21 — Dimensão `seguranca`, Fase A (passiva: headers/mixed/MIME/segredos/cookies)

```xml
<lang>Python 3.11 stdlib + pytest (checks/seguranca/; base: OS-20 mergeada)</lang>
<task>Criar a dimensão seguranca com os checks passivos da Fase A sobre a network_log enriquecida, emitindo Finding.</task>
<context>Ver docs/SEGURANCA.md Fase A. Reusar sanitize.py como DETECTOR: publicar find_secrets(text)->list[Finding] com AWS AKIA, JWT eyJ, Google AIza, GitHub ghp_, Stripe sk_live_, PEM privado (alta), genérico api_key/secret/token. Registrar "seguranca" em DIMENSIONS, pytest.ini, checks/seguranca/__init__.py.</context>
<rules>
- Agrupar por tema (não 1 arquivo por check): headers+mixed+MIME juntos; segredos; cookies.
- headers por ASSET (não duplicar o HTML principal que backend já cobre): 3ª parte executável sem CSP/XCTO → xfail; mixed content http:// em https:// → FAIL.
- MIME: content_type vs magic bytes (js como text/html) → FAIL crítico.
- segredos em corpos js/json de 1ª parte → FAIL via Finding (valor mascarado); cookies: Secure/HttpOnly/SameSite, SameSite=None sem Secure → FAIL.
</rules>
<aceite>
- fixture ganha 1 asset com AKIA fake e 1 http:// → ambos detectados; segredo mascarado no laudo, nunca em claro.
- esperado.json do fixture atualizado 1:1 (nem a mais nem a menos).
- Corpo truncado (>512KB) → check declara "não avaliado", não PASS silencioso.
</aceite>
<testes>
- Unit find_secrets: AKIA+JWT+PEM+ghp_ detectados; sha256 hex → não falso-positiva; texto limpo → vazio.
- Mixed content protocol-relative (//host) → herda https, não FAIL.
- SameSite=None sem Secure → FAIL; com Secure → PASS.
</testes>
<recomendacao>
- Cubra unidade (find_secrets, magic bytes) → sistema (dimensão contra o fixture) → aceitação (contrato esperado.json), focando limites e riscos.
- Gere o teste do segredo fake antes do check (TDD).
</recomendacao>
```

---

## OS-22 — Fase B (passiva: magic bytes/metadados/SVG/sourcemap/SRI)

```xml
<lang>Python 3.11 stdlib + lxml (checks/seguranca/; base: OS-21 mergeada)</lang>
<task>Adicionar à dimensão seguranca os checks passivos de análise de arquivos baixados (Fase B), emitindo Finding.</task>
<context>Ver docs/SEGURANCA.md Fase B. Opera sobre corpos JÁ baixados via ler_corpo. Stdlib para magic bytes (struct) e presença de EXIF/PDF-meta; lxml (já no projeto) para SVG. Dependência pesada (Pillow/pypdf/python-magic) PROIBIDA — fallback xfail "não avaliado". Baixar arquivo novo é Fase C.</context>
<rules>
- Agrupar em test_arquivos_e_metadados.py: magic bytes vs extensão/content_type (pdf %PDF, png, jpg, zip PK) → FAIL; SVG com <script>/on*= → FAIL; sourcemap //# sourceMappingURL → xfail apontando o .map SEM baixá-lo; EXIF-GPS → FAIL, EXIF-autor/PDF-Author → xfail (só presença, valor mascarado); SRI ausente em 3ª parte → xfail.
- Nenhum download novo: recurso fora da network_log → "não presente na navegação", não sonda.
</rules>
<aceite>
- fixture ganha 1 svg com onload, 1 js com sourceMappingURL, 1 img com EXIF-GPS → cada um detectado; esperado.json 1:1.
- Contagem de requests da network_log inalterada pelos checks da Fase B (prova de que nada foi baixado).
- Coordenada GPS reportada mascarada, nunca em claro.
</aceite>
<testes>
- Unit magic bytes: .png renomeado .jpg → detectado; arquivo íntegro → PASS.
- SVG com xlink:href javascript: → FAIL; SVG limpo → PASS.
- Formato inviável em stdlib → xfail "não avaliado", nunca erro nem dependência nova.
</testes>
<recomendacao>
- Separe verificação (unit dos parsers com arquivos fabricados em tmp_path) de validação (fixture real).
- Foque limites: arquivo corrompido, extensão trocada, metadado ausente — as bordas onde o parser quebra.
</recomendacao>
```

---

## OS-23 v2 — `webqa/llm.py` (abstração + gate + veto de endpoint por IP resolvido)

```xml
<lang>Python 3.11 + httpx (webqa/llm.py, webqa/gates.py; base: dimensão seguranca. Contrato: docs/LLM.md)</lang>
<task>Criar a abstração ResumidorLLM (Protocol) para runtime LLM local OpenAI-compat, atrás do gate WEBQA_LLM_ENABLED, com veto ESTRUTURAL a endpoint não-local por IP resolvido.</task>
<context>Ver docs/LLM.md. gates.py tem _enabled(); adicionar llm_enabled(). summary.json traz results[] com estado∈{passed,failed,xfail,skipped,error} e detail já sanitizado. Só httpx (já no projeto).</context>
<rules>
- Protocol ResumidorLLM.resumir(findings: list[dict]) -> str; impl ResumidorOllamaCompat com temperature 0.2, teto 80 achados, filtro estado∈{failed,xfail,error} (passed nunca entra).
- Veto por IP RESOLVIDO (não string): socket.getaddrinfo(host) + ipaddress; aceita só is_loopback/is_private/is_link_local; qualquer IP público → ValueError claro ("nuvem fora de escopo"). NUNCA aceitar 0.0.0.0.
- Guarda de linguagem: se saída contém aprovado/conforme/seguro/certificado → prefixa "revisar: linguagem de certificação" + mantém rótulo; NÃO descarta.
- Assinatura só aceita list[dict] do summary.json; nunca corpo bruto. Não re-sanitiza (detail já vem mascarado).
</rules>
<aceite>
- Endpoint https://api.openai.com → ValueError; http://localhost:11434 e http://192.168.1.x → aceitos; http://0.0.0.0 → rejeitado.
- Hostname que resolve para IP público → rejeitado (prova o veto por resolução, não string).
- Saída "site aprovado" → prefixada "revisar", texto preservado.
</aceite>
<testes>
- Unit (sem rede, monkeypatch getaddrinfo): loopback/privado aceito; público rejeitado; 0.0.0.0 rejeitado.
- resumir monta prompt só com failed/xfail/error; passed ausente do payload.
- guarda: texto limpo passa inalterado; com certificação vira "revisar".
</testes>
<recomendacao>
- SOLID: dependa da abstração ResumidorLLM (Protocol), impl trocável por fake em teste.
- Segurança de IA: o veto por IP resolvido é a promessa "nada sai da máquina" como código, não convenção.
</recomendacao>
```

---

## OS-24 v2 — `scripts/sumario.py` (processo separado + guardas)

```xml
<lang>Python 3.11 (scripts/sumario.py; consome webqa/llm.py da OS-23; base: OS-23 mergeada. Contrato: docs/LLM.md)</lang>
<task>Gerar report/sumario.md a partir do summary.json via ResumidorLLM local, como etapa SEPARADA (nunca dentro do pytest_sessionfinish), anexo rotulado que nunca certifica nem altera o laudo.</task>
<context>Ver docs/LLM.md. summary.json já é fonte da verdade e seus detail já nascem sanitizados (invariante do report.py — NÃO re-sanitizar). Separação de processo é exigência: falha da LLM não pode compartilhar o corpo do hook que escreve o laudo (lição do bug de erros engolidos no report.py). Lê WEBQA_REPORT_DIR com o mesmo default do report.py.</context>
<rules>
- scripts/sumario.py roda APÓS o pytest, lê summary.json; se gate off ou runtime local ausente → não gera nada, exit 0, laudo íntegro.
- Health-check fail-fast: sonda GET no endpoint (timeout 2s) antes de montar o prompt; falha → log de 1 linha + exit 0 (não esperar o timeout de 120s do POST).
- Ordenar achados failed→error→xfail (estável) ANTES do teto de 80; prompt só com esses estados; temperature 0.2.
- Guarda de linguagem: termo de certificação → prefixa "revisar", mantém rótulo, NÃO descarta.
- Detector de omissão: para cada dimensão com ≥1 failed, o nome da dimensão deve aparecer no sumario.md; ausente → prefixa "revisar: achados de {dimensão} não cobertos".
- summary.json/summary.html NUNCA tocados. sumario.md coberto por report/ no .gitignore. Cabeçalho do arquivo traz model/timestamp (rastreabilidade), mas NÃO no corpo do prompt.
</rules>
<aceite>
- Gate off → nenhum sumario.md, exit 0, summary.json byte-idêntico.
- Modelo fake "site conforme e aprovado" → guarda marca "revisar", rótulo permanece, texto não some.
- Dimensão com failed ausente do texto → prefixo de omissão adicionado.
- Runtime local ausente → exit 0 em ≤2s (não 120s); laudo completo.
</aceite>
<testes>
- Unit: guarda de linguagem e detector de omissão com modelo fake; ordenação failed→error→xfail antes do corte.
- Prompt montado só com failed/xfail/error; passed ausente (inspeção do payload).
- >80 achados → truncado após ordenar por severidade; detail já sanitizado aparece como está (sem 2ª sanitização).
</testes>
<recomendacao>
- Separe verificação (unit das guardas e do montador com modelo fake) de validação (sumário real contra o fixture com modelo local).
- Clean code: etapa isolada, processo próprio, zero efeito colateral no laudo determinístico.
</recomendacao>
```

---

## Fase C — desenhada, NÃO implementar agora

A sondagem ativa (`/.git/`, `.env`, `.map`, sublinks) está especificada em
`docs/SEGURANCA.md §7`, atrás do gate `WEBQA_ACTIVE_PROBES_AUTHORIZED` com audit
log. **Não emitir OS** até haver autorização explícita do dono de um alvo — é
capacidade intrusiva (prima de pentest) e construí-la antes da demanda real é
YAGNI com peso ético.

---

## Critérios de review do arquiteto (ao entregar)

1. **OS-20:** grep no PR confirmando zero escrita de corpo de resposta em disco;
   teste provando que `Finding` com segredo nasce mascarado (invariante estrutural).
2. **OS-21:** o segredo fake aparece mascarado no laudo, nunca em claro; `esperado.json` 1:1.
3. **OS-22:** contagem de requests da `network_log` inalterada pelos checks (nada baixado).
4. **OS-23:** o veto de endpoint funciona por IP resolvido (hostname público
   rejeitado, `0.0.0.0` rejeitado, `192.168.x` aceito).
5. **OS-24:** processo separado (não no `pytest_sessionfinish`); ausência de
   modelo → exit 0 em ≤2s; guarda de linguagem e detector de omissão marcam "revisar".
