# Camada de LLM local — Plano Compilado (versão final)

Etapa **opcional, posterior, local e desligada por padrão** que transforma os
achados já produzidos pela suíte em um sumário legível para humanos. A LLM
**apresenta**; o código **julga**. Este documento consolida a arquitetura, as
fronteiras duras, as decisões tomadas após seis pareceres externos, e as
salvaguardas de engenharia de IA aplicadas.

---

## 1. Princípio central: LLM apresenta, código julga

O veredito de qualquer teste é sempre determinístico e vive no `summary.json`. A
LLM opera SOMENTE sobre achados já produzidos e sanitizados — é camada de
apresentação, nunca de decisão. Isso preserva as três propriedades que dão
autoridade à suíte:

- **Reprodutibilidade** — o veredito não muda entre execuções (LLM é probabilística; o laudo não pode ser).
- **Defensabilidade** — um laudo cita o fato observável ("requisição a tracker no ms 200, antes do aceite"), nunca "uma IA achou".
- **Ausência de alucinação em fato** — a IA não inventa nem suaviza achado; se tentar, a guarda determinística intervém.

## 2. Fronteiras duras (inegociáveis)

1. **Local por padrão. Nada sai da máquina.** Provedor default é runtime local
   (Ollama / llama.cpp / LM Studio via endpoint loopback, formato OpenAI-compat).
   **Nuvem está FORA de escopo** — nem como opt-in. Endpoint que não seja
   loopback/rede local -> aborta com erro claro ("envio para nuvem fora de escopo").
   Isso é invariante estrutural, não default gentil.
2. **Só achado sanitizado entra no prompt.** Nunca corpo bruto de resposta, nunca
   conteúdo de arquivo do alvo. O `detail` do `summary.json` já nasce sanitizado
   (invariante do `report.py`) — **não se re-sanitiza** (isso duplicaria o ponto
   único de verdade; se a borda falha, corrige-se a borda).
3. **O texto gerado nunca certifica.** Guarda determinística de linguagem: se a
   saída contiver "aprovado/conforme/seguro/certificado", NÃO se descarta em
   silêncio — substitui-se o cabeçalho por "revisar: modelo emitiu linguagem de
   certificação" e mantém-se o rótulo de não-veredito. O sinal de mau
   comportamento do modelo é preservado, não escondido.
4. **Ausência do modelo nunca quebra nem degrada.** Sem runtime local, a etapa
   sai em silêncio (exit 0); o laudo determinístico é íntegro e completo sem ela.
5. **Desligada por padrão.** Gate `WEBQA_LLM_ENABLED` — a suíte roda sem IA a
   menos que o operador ative de propósito.
6. **Etapa em processo SEPARADO.** `scripts/sumario.py` roda APÓS o pytest, nunca
   dentro de `pytest_sessionfinish`. Um `try/except` amplo no hook que escreve o
   laudo reencenaria o pior bug do projeto (erros de setup engolidos -> "noite
   limpa" com navegador morto). Separação de processo é a lição, não preferência.

## 3. Agnosticismo de modelo

Abstração fina: `Protocol ResumidorLLM.resumir(findings) -> str`. Implementação
default fala com endpoint local por HTTP (OpenAI-compat). Trocar de modelo é
configuração (`WEBQA_LLM_MODEL`, `WEBQA_LLM_ENDPOINT`), não código. Nenhum SDK
proprietário — só `httpx`, que já existe. `Protocol` permite substituir a impl
por um fake em teste sem tocar o chamador (inversão de dependência).

## 4. Salvaguardas de engenharia de IA (o olhar novo)

A LLM numa auditoria carrega riscos específicos de IA que exigem controle além
da arquitetura de software:

- **Supervisão humana em aplicação crítica.** Um laudo de conformidade é decisão
  de consequência. Por isso o sumário é *anexo assistido*, jamais substitui o
  laudo determinístico, e traz rótulo obrigatório de não-veredito. O humano lê os
  fatos (`summary.json`) e usa o sumário como apoio — nunca o inverso.
- **Viés e distorção.** O modelo pode suavizar um `failed` grave ou dramatizar um
  `xfail` menor. Mitigações concretas: `temperature` baixa (0.2) para consistência
  sobre criatividade; instrução explícita de nunca amenizar `failed`; e a guarda
  de linguagem que barra certificação indevida. A variância entre execuções é
  reconhecida como limite, não escondida.
- **Qualidade dos dados de entrada ("garbage in, trash out").** O sumário só é tão
  bom quanto os achados que recebe. Só entram achados `failed/xfail/error`
  (`passed` nunca entra — evita "confirmar conformidade por ausência de achado");
  teto de 80 achados para não estourar o contexto do modelo local e degradar a
  saída silenciosamente.
- **Transparência e responsabilidade (IA responsável).** Toda saída é rotulada
  como assistida por IA; o prompt é versionável e auditável; a fonte da verdade
  permanece o artefato determinístico. Nada é apresentado como julgamento da máquina.

## 5. O que a LLM produz (tudo sobre achado sanitizado)

- **Sumário executivo** — 2-3 parágrafos: o mais grave, por quê, por onde começar.
- **Agrupamento por causa raiz** — achados distintos com a mesma origem.
- **Explicação didática** — cada tipo de achado traduzido para linguagem de ação.

Saída: `report/sumario.md`, anexo rotulado, no `.gitignore` (artefato de alvo
real, nunca versionado). Nunca substitui o laudo.

## 6. O que a LLM NUNCA faz

- Decidir passed/failed/xfail/skipped/error de qualquer teste.
- Alterar o `summary.json`/`summary.html` ou qualquer contagem.
- Receber conteúdo bruto do alvo ou dado não sanitizado.
- Emitir linguagem de certificação/aprovação (guarda determinística barra).
- Rodar por padrão, no caminho crítico do CI, ou dentro do hook do laudo.

## 7. Decisões tomadas após os seis pareceres externos

**Convergência que ratifica:** módulo `webqa/llm.py` isolado; gate desligado por
padrão; só `httpx`; endpoint local default; ausência do modelo não quebra.

**Incorporado (refinamentos reais):**
1. Guarda determinística de linguagem proibida — mas marcando "revisar", não
   descartando em silêncio (preserva o sinal).
2. `temperature=0.2` — consistência sobre criatividade, reduz variância.
3. Filtro de `passed` fora do prompt — evita "confirmar por ausência" e economiza contexto.
4. Teto de contexto (80 achados) — evita degradação silenciosa do modelo local.

**Rejeitado, com fundamento:**
- **`try/except Exception` no `pytest_sessionfinish`** — reencena o bug de erros
  engolidos; a etapa vai para processo separado (`scripts/sumario.py`).
- **Re-sanitizar achados na entrada da LLM** (`sanitize_findings_for_llm` com
  regex `[A-Z0-9]{20,}`) — duplica o ponto único de verdade e produz falso-positivo
  em hashes/IDs; a sanitização mora na borda de escrita do `report.py`.
- **`Finding` reconstruído dentro da camada de LLM** — cargo cult do value object
  sem sua invariante; o `Finding` é decisão de domínio da dimensão `seguranca`, não
  da apresentação. A LLM consome o que está no `summary.json`.
- **`assert "masked" in finding`** — assert sobre estrutura inexistente no
  `summary.json` real; quebraria na primeira execução.

## 8. Encaixe na arquitetura

1. Suíte roda -> `summary.json` determinístico (sem IA, como hoje). Fonte da verdade.
2. Se `WEBQA_LLM_ENABLED` e runtime local disponível: `scripts/sumario.py`
   (processo separado) lê os achados `failed/xfail/error`, chama `ResumidorLLM`,
   aplica a guarda de linguagem, grava `report/sumario.md` rotulado.
3. Sem gate ou sem modelo -> nenhum `sumario.md`, exit 0, laudo intacto.

## 9. Sequência de implementação

| OS | Escopo | Depende de |
|---|---|---|
| **OS-23** | `webqa/llm.py` (abstração `ResumidorLLM` + gate + veto a endpoint público) | dimensão seguranca |
| **OS-24 v2** | `scripts/sumario.py` (processo separado + guarda de linguagem + filtro/teto/temperature) | OS-23 |

---

_Recomendações de engenharia de IA aplicadas: Segurança de IA (supervisão humana
em aplicação crítica, IA responsável), Viés e Ética (auditoria de distorção do
modelo) e Qualidade dos Dados (garbage in/trash out no que entra no prompt); e de
analytics, a preferência por consistência da saída sobre variância._
