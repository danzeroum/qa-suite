# Dimensão `seguranca` — Documento de Arquitetura Consolidado

Auditoria de segurança da informação sobre **tudo que o navegador baixa** ao
carregar um alvo e seus sublinks. Espelha o desenho da dimensão `lgpd`: começa
passiva e barata, cresce em profundidade, e a parte intrusiva fica atrás de gate.
Este documento consolida a arquitetura em 3 fases, a modelagem de domínio (DDD) e
o veredito sobre cinco pareceres externos de consultoria.

---

## 1. Princípio de separação (regra da casa, inegociável)

Sob a ótica DDD, passivo × ativo não é detalhe técnico — são **dois bounded
contexts** com regras e autorização diferentes:

| Contexto | Subdomínio | O que faz | Requisitos |
|---|---|---|---|
| **Passivo** | "análise do que foi entregue" | Analisa o que o navegador JÁ baixou. Zero requisição nova. | Regras atuais. Sem gate. |
| **Ativo** | "investigação do que não foi oferecido" | Sonda caminhos (`/.git/`, `.env`, `.map`), segue sublinks, baixa arquivos extras. | **Exige `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`**. |

O gate é a **anti-corruption layer** entre os dois contextos. Sondar caminhos de
servidor alheio sem autorização é a linha que separa auditoria de intrusão.

## 2. Fronteiras duras (valem para as 3 fases)

1. **Conteúdo baixado NUNCA é persistido em disco versionável.** Analisado em
   memória (teto 512 KB); descartado ao fim. Nem em `report/`.
2. **Segredo encontrado NUNCA aparece em claro no relatório.** Reporta-se tipo +
   local com valor mascarado por `sanitize`. Republicar o segredo reencena o risco.
3. **Achado de segurança de terceiro é diagnóstico local, nunca versionado.**
4. **`error` (infra) ≠ achado de segurança.** Recurso não avaliado (timeout, 5xx)
   é registrado como não-avaliado, nunca como seguro.

## 3. Modelagem de domínio (DDD) — a linguagem ubíqua

Nenhum dos cinco pareceres modelou o domínio; todos pensaram em arquivos e
funções. A coesão da dimensão vem de tornar explícito o vocabulário:

- **Value objects imutáveis:** `Finding(tipo, recurso, severidade, evidencia, fase)`
  e `Recurso(url, status, headers, content_type, size, from_origin, scheme)`.
- **Aggregate:** `NetworkLog` reúne os `Recurso` e é a raiz de acesso.
- **Invariante estrutural:** a `evidencia` de um `Finding` passa por `sanitize` no
  **construtor** — é impossível instanciar um `Finding` com segredo em claro. A
  fronteira ética mais dura deixa de ser regra que cada check lembra de seguir e
  vira impossibilidade estrutural. É a jogada do `sanitize.py` (mascarar na borda)
  elevada a value object.
- **A segunda invariante, mesma jogada (OS-37):** não existe `Credencial` cuja
  senha não esteja registrada para mascaramento — o registro é feito pelo
  `__post_init__` de `webqa/auth.py::Credencial`. A diferença em relação ao
  `Finding` é o mecanismo: um segredo de terceiro é reconhecido por FORMATO
  (`AKIA…`, `ghp_…`), mas a senha de um Basic Auth de nginx não tem prefixo de
  emissor, não tem rótulo e não tem forma — só quem a configurou sabe que aquilo
  é segredo. Por isso ela é mascarada por **valor**, e em todas as formas em que
  pode reaparecer num artefato (escapada para JSON, escapada para HTML,
  percent-encoded, e o blob base64 do cabeçalho `Authorization`). Varrer o
  arquivo procurando só o valor cru falharia justamente com as senhas boas — as
  que têm caractere especial.
- **Onde a credencial NÃO vai** (`webqa/auth.py::pode_enviar_credencial`): o
  cliente HTTP é de sessão e visita hosts que não são o alvo — o CDN do axe-core
  e o host da política de privacidade. Um `httpx.BasicAuth` comum anexa
  `Authorization` em toda requisição do cliente, o que mandaria a senha do
  operador para a Cloudflare e a faria trafegar em claro no teste que bate em
  `http://` de propósito. A autenticação é presa a **origem + esquema**; a
  exceção para rede local existe pelo alvo fixture e é decidida por IP resolvido
  (`webqa/rede.py`), nunca por casar string.

Hoje um achado é uma string de mensagem de assert — dado sem modelo. Com `Finding`,
checks, relatório e contrato do fixture compartilham o mesmo vocabulário.

## 4. Pré-requisito: enriquecer `network_log`

`NetworkLog` guarda hoje só `(url, resource_type)`. As três fases dependem de
capturar, por resposta, sem persistir corpo: `status`, `headers` (lowercase),
`content_type`, `size`, `from_origin` (1ª × 3ª parte, normalizando www), `scheme`
e leitura de corpo sob demanda em memória com teto.

## 5. Fase A — Passiva, cabeçalhos e conteúdo (alto valor / baixo custo)

- **Cabeçalhos de segurança por asset**, não só no HTML principal (foco: script de
  3ª parte pelado numa página blindada — não duplicar o que `backend` já cobre no HTML).
- **Mixed content**: asset `http://` em página `https://` → FAIL.
- **Tipo declarado × real**: `Content-Type` vs. magic bytes → `.js` como `text/html` FAIL.
- **Scan de segredos** nos corpos JS/JSON: reusa o motor do `sanitize.py` como
  detector. Padrões: AWS `AKIA`, JWT `eyJ`, Google `AIza`, GitHub `ghp_`, Stripe
  `sk_live_`, **PEM privado `-----BEGIN...PRIVATE KEY-----` (severidade alta)**,
  genérico `api_key/secret/token`. Valor sempre mascarado.
- **Cookies por asset**: Secure/HttpOnly/SameSite; `SameSite=None` sem `Secure` → FAIL.

## 6. Fase B — Passiva, análise de arquivos e metadados

- **Formato por magic bytes** (não pela extensão) — stdlib (`struct`).
- **Metadados**: presença de EXIF-GPS/autor em imagens e `/Author`/`/Creator` em
  PDF → xfail; GPS → FAIL. Detecta presença (minimização: não extrai o valor). Stdlib.
- **SVG com script** (`<script>`, `on*=`) → FAIL (XSS). Via `lxml` (já no projeto).
- **Sourcemap referenciado** (`//# sourceMappingURL`): xfail apontando o `.map`.
  **Não baixar** o `.map` — baixar é Fase C.
- **SRI ausente** em asset de 3ª parte → xfail.

Fallback se um formato for inviável em stdlib: xfail "não avaliado", **nunca**
dependência pesada (`Pillow`/`piexif`/`pypdf`/`python-magic` rejeitadas).

## 7. Fase C — Ativa (atrás do gate, desenhada mas NÃO implementada agora)

Só com `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`: sondar `/.git/HEAD`, `/.env`,
`/backup.zip`, `/.DS_Store`, `/wp-config.php~`, o `.map` da Fase B; seguir
sublinks; baixar arquivos extras. Rate-limit obrigatório, user-agent
identificável, **audit log** (`logging.warning` + timestamp) ao acionar o gate.

## 8. Estados no relatório (reusa a semântica existente)

`failed` = risco confirmado observável; `xfail` = maturidade ausente sem obrigação
direta; `skipped` = não aplicável; `error` = não pôde ser avaliado. Achado nunca é
"certificação de seguro" — mesma nota epistêmica da dimensão `lgpd`.

### 8.1 Severidade — critério e tabela

**Só `failed` tem severidade.** `xfail` é alerta no vocabulário do relatório, e
alerta com selo de severidade seria um segundo semáforo dentro do estado — o que
a regra 2.5 evita, porque some na impressão em preto e branco. Há teste fixando
que nenhum caminho de `xfail` constrói `Finding`.

O critério, em uma frase: **alta é o risco que já se realizou no cliente; média
é o que depende de uma pré-condição que a bateria não observa.**

| Severidade | Achado | Por que aqui |
|---|---|---|
| **alta** | `segredo:*` (A) | credencial servida ao navegador já é credencial pública — todo visitante leu |
| **alta** | `tipo-declarado-divergente` (A) | executável mal declarado já está sendo interpretado no navegador do titular |
| **alta** | `mixed-content` (A) | o conteúdo em claro já trafegou e já pôde ser adulterado; o TLS da página está anulado |
| **alta** | `svg-executavel` (B) | documento com DOM servido como imagem executa no contexto de origem do alvo |
| **alta** | `exif-gps` (B) | dado pessoal por consequência, já publicado — revela onde o titular esteve |
| **média** | `cookie-samesite-none-sem-secure` (A) | exposição em trânsito, condicionada a interceptação |
| **média** | `cookie-sessao-sem-httponly` (A) | só vira incidente se houver XSS na página |
| **média** | `cookie-sessao-sem-secure` (A) | só vira incidente num downgrade para http |
| **média** | `formato-divergente` (B) | sintoma de validação ausente no upload; se executa depende do tratamento a jusante |

Nenhum achado usa **baixa** hoje. O rótulo existe no value object e fica
disponível, mas inventar ocupante para ele agora só diluiria os outros dois.

Se tudo é alta, "alta" para de significar alguma coisa — e quem lê o laudo
precisa saber o que fazer **hoje**. A dúvida se resolve para média: superestimar
severidade queima a credibilidade da bateria do mesmo jeito que um falso
positivo, só que mais devagar.

Esta tabela é a fonte de verdade da decisão. Achado novo entra aqui no mesmo PR
em que nasce — severidade decidida em revisão de PR e não registrada vira
memória, e memória não sobrevive à próxima pessoa.

---

## 9. Veredito sobre os cinco pareceres externos

**Convergência que ratifica o desenho** (todos os cinco acertaram, sem mudar nada):
`network_log` como pré-requisito bloqueante; corpo em memória com teto, nunca em
disco; `find_secrets` reusando `sanitize.py`; mixed content FAIL; MIME por magic
bytes; cookies por asset; sourcemap detectado mas não baixado; gate para Fase C;
`error ≠ seguro`.

**Incorporado (novidade real frente ao desenho original):**
1. Padrões de segredo adicionais: GitHub PAT, Stripe, **PEM privado**.
2. `Authorization`/`x-api-key`/`bearer` nos parâmetros sensíveis do `sanitize.py`.
3. Audit log ao acionar o gate ativo (rastreabilidade).
4. `SameSite=None` sem `Secure` como FAIL específico.

**Rejeitado, com fundamento:**
- **Split em 9 módulos** (`webqa/seguranca/*.py`): over-engineering; a casa agrupa
  checks correlatos por arquivo, não um-por-função.
- **Marcadores `seguranca_passiva`/`seguranca_ativa`**: redundante — o gate já separa.
- **Dependências `Pillow`/`piexif`/`pypdf`/`python-magic`**: contra a filosofia
  stdlib-first firmada; detecção de presença cabe em stdlib.
- **`disconnect.me` em runtime**: dependência de rede de terceiro — o que a suíte
  critica nos alvos.
- **`imghdr`**: deprecado/removido no Python 3.13.

**Diferença central:** os pareceres otimizaram a *estrutura de arquivos*; a
arquitetura protege o *modelo de domínio*. O `Finding` com invariante no construtor
é o que nenhum consultor viu — porque pensaram em funções, não em domínio.

---

## 10. Sequência de implementação

| OS | Escopo | Depende de |
|---|---|---|
| **OS-20 v2** | `network_log` enriquecida + value objects `Finding`/`Recurso` + `docs/SEGURANCA.md` | base atual |
| **OS-21** | Fase A: headers/mixed/MIME/segredos/cookies | OS-20 |
| **OS-22** | Fase B: magic bytes/metadados/SVG/sourcemap/SRI | OS-21 |
| **(futura)** | Fase C: sondagem ativa atrás do gate + audit log | OS-22 + autorização do dono |
