# Ordens de Serviço — registro e numeração

> ## Esta tabela é a FONTE ÚNICA DE VERDADE da numeração de OS.
>
> Antes de abrir uma OS, confira o número **aqui** — nunca contra a memória do
> chat, contra `PROXIMOS-PASSOS §4` nem contra o título de um PR. O número já
> colou no trabalho errado três vezes, sempre pela mesma causa: ele vivia em
> três lugares e os três divergiam.
>
> **Próximo número livre: OS-31.**

Estado em 2026-07-30 · base: `main` @ `da5d3cf` · 440 testes de verificação verdes.
Contratos: `docs/SEGURANCA.md`, `docs/LLM.md`, `docs/CAMPANHA.md`, e — para as OS
de design — `docs/qa-suite design brief/referencia/` (spec visual:
`componentes.html` §5/§8; folha canônica: bloco `<style>` de
`referencia/summary.html`, copiar byte a byte).

---

## Sequência e dependências (atualizada)

```
Trilha SEGURANÇA (checks) — CONCLUÍDA:
  OS-20 v2 ✓ (#15) → OS-21 ✓ (#16) → OS-22 ✓ (#17)
     └── Finding em toda a dimensão ✓ (#21, #22)
     └── [Fase C — apenas desenhada em docs/SEGURANCA.md §7, TRAVADA]

Trilha LLM — CONCLUÍDA no que independe de runtime local:
  OS-23 v2 ✓ (#24, webqa/llm.py) → OS-24 v2 ✓ (#25, scripts/sumario.py)
     └── [validação com Ollama real — pendente de ambiente]

Trilha DESIGN/RELATÓRIO — CONCLUÍDA:
  OS-25 ✓ (#18, template seguranca) → OS-26 ✓ (#26, painel de estabilidade)

Trilha CAMPANHA:
  OS-27 ✓ (#27, etiqueta: robots/recuo/sequencial)
     └── OS-28 (campanha multi-alvo) — EM ABERTO
     └── OS-29 (telemetria operacional) — EM ABERTO
     └── [validação contra sites públicos na VPS — pendente de ambiente]
```

⚠️ Numeração: OS-23/OS-24 são **LLM** (como neste pacote desde a origem). As OS
de design que circularam em chat com esses números foram renumeradas para
**OS-25/OS-26** — valem os blocos abaixo. Quatro outras foram numeradas em chat
sem consultar este arquivo e colidem com a sequência: ver "Colisões conhecidas".

---

## Concluídas (registro)

| OS | PR | Commit em `main` | Entrega |
|---|---|---|---|
| OS-20 v2 | #15 | `5dd0245` | `Finding`/`Recurso` + `network_log` enriquecida + `docs/SEGURANCA.md` |
| OS-21 | #16 | `80d8269` | Fase A: headers/mixed/MIME/segredos/cookies |
| OS-22 | #17 | `b22af7d` | Fase B: magic bytes/metadados/SVG/sourcemap/SRI · fixture com 11 FAILs · novo `alvo_sha256` |
| OS-25 | #18 | `7944fc7` | Template `seguranca` no `summary.html` (severidade tipográfica + fase) |
| OS-23 v2 | #24 | `c175eed` | `webqa/llm.py`: `ResumidorLLM` + gate + veto de endpoint por IP resolvido |
| OS-24 v2 | #25 | `0a9e6e5` | `scripts/sumario.py` em processo separado + guardas de linguagem e omissão |
| OS-26 | #26 | `172ba20` | Painel de estabilidade (`report/estabilidade.html`) + `caminhada()` + schema 5 |
| OS-27 | #27 | `db7f948` | Camada de etiqueta: robots.txt, recuo 429/503, crawl sequencial, `webqa/rede.py` |

### Fora da sequência do handoff — numeradas em chat, já em `main`

Estas quatro nasceram da leitura de compreensão e foram numeradas sem consultar
este registro. **Os números colidem** com a sequência acima; ficam registradas
com o número que está no histórico do git, porque commit mergeado é fato, e com
o apelido canônico ao lado.

| No histórico | Canônico | PR | Commit | Entrega |
|---|---|---|---|---|
| "OS-27" | **OS-27-bis** | #20 | `c869a28` | Correções D2–D6: pin do Playwright, EAP, entrada única, contagens |
| "OS-28" | **OS-28-bis** | #21 | `e391e55` | Fase B emite `Finding` (severidade/fase como dado) |
| "OS-29" | **OS-29-bis** | #22 | `980b094` | Fase A emite `Finding` — fecha o §4.2 |
| "OS-30" | **OS-30-bis** | #23 | `bdff377` | Regra de merge para pilha de PRs encadeados (§5.1) |

### Colisões conhecidas — o que fazer ao encontrar

Quem procurar um número no histórico vai achar **duas coisas diferentes** em
quatro casos. Não é erro de leitura:

| Número | Significa (canônico) | Também aparece em `main` como |
|---|---|---|
| **OS-23** | camada LLM (`webqa/llm.py`) | `7944fc7`, template `seguranca` — hoje canonicamente **OS-25** |
| **OS-27** | camada de etiqueta (`db7f948`) | `c869a28`, correções de doc — hoje **OS-27-bis** |
| **OS-28** | campanha multi-alvo (**em aberto**) | `e391e55`, Fase B `Finding` — hoje **OS-28-bis** |
| **OS-29** | telemetria operacional (**em aberto**) | `980b094`, Fase A `Finding` — hoje **OS-29-bis** |

Duas notas de auditoria, para que o histórico se explique sozinho:

* o PR **#27** foi aberto com o título "OS-25" por engano e corrigido para
  "OS-27" antes do merge; o commit de origem (`db7f948`) ainda diz OS-25;
* o commit `7944fc7` diz "OS-23" porque foi o número que circulou em chat; o
  registro já o renumerava para **OS-25**, e é esse que vale.

**A regra que fecha isto:** número novo sai da linha "Próximo número livre" do
topo deste arquivo, e essa linha é incrementada no MESMO PR que consome o
número. Enquanto o número viver em três lugares, ele vai divergir de novo.

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
<context>Ver docs/LLM.md. summary.json já é fonte da verdade e seus detail já nascem sanitizados (invariante do report.py — NÃO re-sanitizar). Separação de processo é exigência: falha da LLM não pode compartilhar o corpo do hook que escreve o laudo. Lê WEBQA_REPORT_DIR com o mesmo default do report.py.</context>
<rules>
- scripts/sumario.py roda APÓS o pytest, lê summary.json; se gate off ou runtime local ausente → não gera nada, exit 0, laudo íntegro.
- Health-check fail-fast: sonda GET no endpoint (timeout 2s) antes de montar o prompt; falha → log de 1 linha + exit 0.
- Ordenar achados failed→error→xfail (estável) ANTES do teto de 80; prompt só com esses estados; temperature 0.2.
- Guarda de linguagem: termo de certificação → prefixa "revisar", mantém rótulo, NÃO descarta.
- Detector de omissão: para cada dimensão com ≥1 failed, o nome da dimensão deve aparecer no sumario.md; ausente → prefixa "revisar: achados de {dimensão} não cobertos".
- summary.json/summary.html NUNCA tocados. sumario.md coberto por report/ no .gitignore. Cabeçalho traz model/timestamp, mas NÃO no corpo do prompt.
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

## OS-25 — Template `seguranca` no relatório (ex-"OS-23 do chat", renumerada)

```xml
<lang>Python 3.11 stdlib (report_html.py; base: main b22af7d, pós #15–#17)</lang>
<task>Estender o template do summary.html para a dimensão seguranca: severidade e fase por achado, "não avaliado" no vocabulário existente, contagens interpoladas. Painel de estabilidade FORA desta OS (é a OS-26).</task>
<context>Spec visual no repo: docs/qa-suite design brief/referencia/componentes.html §5 (achado de seguranca renderizado, exemplo AKIA) e §8 (regras); folha canônica = bloco <style> de referencia/summary.html, byte a byte. Contrato do fixture agora tem 11 FAILs; Finding{severidade, fase} são campos OPCIONAIS — dimensões antigas não os têm.</context>
<rules>
- Severidade é TIPOGRÁFICA, nunca cromática: rótulo mono caps "sev. alta/média/baixa" na margem, sob o chip de estado; ordenação alta → média → baixa dentro do grupo; os 4 estados seguem o único vocabulário de cor — nenhum tom novo.
- fase (A/B/C) como chip .chip-dim na linha meta; card seguranca entra na grade como qualquer dimensão — zero componente novo.
- "Não avaliado" (corpo truncado, formato inviável, fora_do_contrato) usa xfail/skipped existente com motivo por extenso na linha e na tabela — nunca PASS silencioso.
- Nenhuma contagem literal ("N achados", browser_total interpolados); evidência mascarada (AKIA****, GPS) chega pronta do Finding — apresentar sem re-mascarar nem re-escapar.
</rules>
<aceite>
- summary.json do fixture pós-#17 renderiza os achados de seguranca com sev./fase, ordenados, distinguíveis sem cor (P&B) nos dois temas.
- Classes .passed/.failed/.xfail/.skipped verbatim; paleta inalterada; axe sem críticas/sérias.
- Sourcemap/SRI (xfail) no bloco Alertas, fora de TODA soma de falha; fora_do_contrato pulados com motivo legível.
- Dogfooding: relatório servido local passa em zero requisição externa e HTML < 300 KB.
</aceite>
<testes>
- Grupo com sev. alta + media → alta primeiro; achado SEM severidade → margem sem rótulo, layout intacto.
- Summary antigo (sem dimensão seguranca) → saída idêntica à atual, byte a byte. <!-- retrocompatibilidade -->
- detail com "AKIA****************" → em <code>, sem escape duplo; nenhum GPS em claro no HTML.
- Corpo truncado >512 KB → "não avaliado" com motivo, ausente de qualquer soma de falha.
</testes>
<recomendacao>
- Separe verificação (summaries sintéticos com/sem severidade, sem rede) de validação (dogfooding contra o fixture pós-#17).
- Clean code: a extensão entra nas MESMAS funções de montagem (card/achado/linha) — sem branch duplicado para seguranca.
</recomendacao>
```

---

## OS-26 — Painel de Estabilidade (ex-"OS-24 do chat", renumerada)

```xml
<lang>Python 3.11 stdlib (scripts/estabilidade.py + gerador HTML novo; base: OS-25 mergeada)</lang>
<task>Gerar report/estabilidade.html a partir de docs/lgpd-estabilidade.json, espelhando a referência do designer (docs/qa-suite design brief/referencia/estabilidade.html).</task>
<context>Referência navegável já no repo; folha canônica compartilhada com o summary (copiar, não recriar). Regras do ledger: só origem vps pontua, 1 execução por dia UTC (vale a primeira), streak recalculada do histórico inteiro, por alvo. O alvo_sha256 mudou no #17 (fixture ganhou 4 violações) — o reinício já terá o que mostrar.</context>
<rules>
- Mesmas restrições do relatório: arquivo único, zero requisição externa, sem JS obrigatório, @media print, dark por prefers-color-scheme + [data-tema].
- Estrutura da referência: história em 1 parágrafo, progresso N/10 em slots, 3 cartões (zera / não zera–avança / não conta), timeline com chips de origem (vps forte; ci/local tracejados, rebaixados), marco "FASE 2" sem gamificação.
- Troca de sha → sequência reiniciada com a nota "o alvo mudou de identidade"; entradas do sha anterior rotuladas como histórico, NUNCA removidas.
- Número de violações do alvo na história interpolado do contrato (hoje 11), nunca literal; noite limpa = vocabulário passed, flake = failed com o sinal (TimeoutError etc.), informativa = skipped.
</rules>
<aceite>
- Ledger real atual renderiza a streak correta e a entrada ci de 2026-07-30 como "histórico — anterior à emenda, não conta".
- Um leigo entende a página sem explicação oral (critério §12 do brief de design).
- Diff visual ~zero contra a referência ao renderizar o ledger de demonstração dela.
- axe sem críticas/sérias; h1 único; zero requisição externa.
</aceite>
<testes>
- Ledger com 2 shas → streak recalculada só sobre o novo; antigas rotuladas, presentes.
- 2 execuções vps no mesmo dia UTC → vale a primeira; origem desconhecida ("banana") → degrada para local, não conta.
- Noite com infra_flakes>0 → linha failed com motivo + "sequência zerada"; seguinte limpa → "sequência: 1".
- Ledger vazio (instalação nova) → página válida, 0/10, estado explicativo — nunca parecer quebrada.
</testes>
<recomendacao>
- Separe verificação (ledgers sintéticos cobrindo as 4 bordas acima) de validação (ledger real + referência do designer lado a lado).
- Clean code: reuse a montagem do gerador do relatório (folha, header, footer) — um único ponto de verdade visual.
</recomendacao>
```

---

## Fase C — desenhada, NÃO implementar agora

A sondagem ativa (`/.git/`, `.env`, `.map`, sublinks) está especificada em
`docs/SEGURANCA.md §7`, atrás do gate `WEBQA_ACTIVE_PROBES_AUTHORIZED` com audit
log. **Não emitir OS** até haver autorização explícita do dono de um alvo.

---

## Critérios de review do arquiteto (ao entregar)

1. ~~OS-20/21/22~~ — entregues e verificados nos merges #15–#17.
2. **OS-23:** o veto de endpoint funciona por IP resolvido (hostname público
   rejeitado, `0.0.0.0` rejeitado, `192.168.x` aceito).
3. **OS-24:** processo separado (não no `pytest_sessionfinish`); ausência de
   modelo → exit 0 em ≤2s; guardas de linguagem e omissão marcam "revisar".
4. **OS-25:** severidade tipográfica (nunca cromática) ordenada alta→média→baixa;
   summary antigo → saída byte-idêntica; dogfooding verde contra o fixture pós-#17.
5. **OS-26:** diff ~zero contra a referência do designer; troca de sha reinicia a
   streak COM nota e SEM apagar histórico; ledger vazio nunca parece quebrado.
