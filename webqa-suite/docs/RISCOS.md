# Gerenciamento de Riscos

Matriz probabilidade (P) × impacto (I), com resposta planejada e monitoramento.

| # | Risco | Tipo | P | I | Resposta | Como é monitorado |
|---|---|---|---|---|---|---|
| R1 | Rodar carga contra alvo sem autorização (legal/ético) | negócio | M | Alto | **Evitar**: carga fora do default; aviso no locustfile; rajada leve limitada por config | revisão de PR; `load_burst` no config |
| R2 | Falso negativo por CDN/WAF mascarando o backend | técnico | M | Médio | **Mitigar**: medir percentis e TTFB, não só status; documentar no relatório | `report/summary.json` |
| R3 | Flakiness de rede gerando falha intermitente | técnico | Alto | Médio | **Mitigar**: timeouts generosos, fixtures de sessão, xfail para sinais opcionais | taxa de skip/xfail no relatório |
| R4 | Alvo bloquear o user-agent da suíte | técnico | M | Baixo | **Aceitar** + user-agent identificável e configurável | falha explícita no primeiro GET |
| R5 | Thresholds errados p/ o contexto (falso alarme) | negócio | Alto | Médio | **Mitigar**: YAML por produto + env override; doc pede calibração | revisões periódicas do config |
| R6 | Playwright/Chromium ausente no ambiente | técnico | M | Baixo | **Mitigar**: skip com instrução de instalação | contagem de `browser` skipped |
| R7 | Suíte contendo bug e aprovando alvo ruim | técnico | Baixo | Alto | **Mitigar**: camada de verificação (`tests/`) obrigatória no CI antes da validação | job `quality-gate` no CI |
| R8 | Vazamento de dados sensíveis em relatórios | segurança | Baixo | Alto | **Mitigar**: relatório guarda só trechos de erro (800 chars); repo ignora report/* | `.gitignore`; revisão |
| R9 | Bateria LGPD reprovar alvo conforme (falso positivo regulatório) | negócio | M | Alto | **Mitigar**: allowlist em config, casamento por rótulo de domínio, bordas cobertas em `tests/test_lgpd_checks.py` (action relativo, www vs sem-www, Expires no passado, política em PDF) | verificação obrigatória no CI |
| R10 | Relatório LGPD ser lido como certificado de conformidade | negócio | Alto | Alto | **Mitigar**: nota epistêmica no código (`DIMENSION_NOTES`), impressa no `summary.html` e no `summary.json`, não só na documentação | revisão de PR do relatório |
| R11 | Sondagem ativa (submeter formulário, clicar em banner) contra terceiro | legal | Baixo | Alto | **Evitar**: Fase 1 é 100% passiva; gate próprio `WEBQA_ACTIVE_PROBES_AUTHORIZED=1`, separado do gate de carga | `webqa/gates.py` + `tests/test_gates.py` |
| R12 | `network_log` herdar consentimento de teste anterior (falso negativo) | técnico | M | Alto | **Mitigar**: contexto Playwright novo e virgem por módulo, fechado ao final | contrato documentado na fixture |
| R13 | Deploy key do noturno vazar (escrita no repositório) | segurança | Baixo | Alto | **Mitigar**: deploy key exclusiva do repo (não PAT de pessoa), só no disco da VPS, montada `ro`, ausente de camada de imagem (`.dockerignore` + conferência com `docker history`) | `docs/VPS.md`; revisão de PR do Dockerfile |
| R14 | Dois escritores no ledger (GitHub + VPS) colidindo | técnico | M | Médio | **Evitar**: schedule removido do GitHub; único escritor é a VPS. Colisão com humano tratada com `pull --rebase` + 1 retry | log do noturno; `estabilidade.yml` reprova se tocar o ledger |
| R15 | Imagem base mudar sob os pés e falsear a sequência | técnico | M | Alto | **Mitigar**: imagem fixada por digest, não por tag; `playwright install chromium` no build casa a revisão do navegador com a do pacote | `docker/Dockerfile` |
| R16 | Credencial de Basic Auth do operador vazar em relatório, log ou artefato | segurança | Baixo | Alto | **Evitar**: só por ambiente (nunca em YAML versionado); registro por VALOR no construtor da `Credencial` (invariante estrutural); varredura da string SERIALIZADA na borda de escrita; `__repr__` redigido | `tests/test_vazamento_de_credencial.py` (grep na saída + guarda AST de toda escrita) |
| R17 | Credencial enviada a terceiro (CDN, host da política) ou em `http://` claro | segurança | M | Alto | **Evitar**: o cliente de sessão é compartilhado com CDN e links externos, então a autenticação é presa a **origem + esquema** (`AutenticacaoDeOrigem`), não ao cliente; exceção local decidida por IP resolvido | `tests/test_auth.py::test_credencial_nao_vai_para_o_cdn_do_axe` |

| R18 | Linha de base visual instável (fonte, antialiasing, revisão do navegador) reprovando alvo conforme — e treinando a equipe a aprovar imagem sem olhar | técnico | Alto | Médio | **Mitigar**: o veredito primário da camada GUI é geometria + CSS computado, nunca pixel; diff de imagem só contra o alvo fixture, por bloco 16×16 com tolerância e máscara declaradas em YAML; a linha de base carimba engine e revisão do Playwright, e procedência divergente vira **não avaliado**, jamais PASS; regravação em massa exige justificativa escrita no PR | política em `docs/GUI.md §4.3`; revisão de PR |
| R19 | Captura de tela de alvo real com PII em pixel, que `sanitize_text` não alcança | segurança | M | Alto | **Evitar (não coletar)**: `sanitize.py` mascara TEXTO e não existe mascarador de imagem. A evidência primária da camada GUI é seletor + caixa + texto sanitizado; captura de pixel é do alvo fabricado, e de alvo real só sob `WEBQA_GUI_SCREENSHOTS=1`, vivendo em `report/` (ignorado pelo Git, expurgo de 7 dias) e **nunca** em linha de base versionada | `.gitignore`; `docs/GUI.md §3.5`; teste que prova que sem a variável nenhum PNG de alvo não fabricado chega ao disco |
| R20 | Check de GUI alterar viewport ou tema no `browser_page` de sessão e contaminar as Web Vitals das demais dimensões | técnico | Alto | Médio | **Evitar**: nenhum check de `gui` toca `browser_page`; toda variação abre `browser.new_context(...)` próprio e o fecha, como o `network_log` já faz (R12) | contrato das fixtures em `conftest.py`; revisão de PR |
| R21 | Laudo de GUI ser lido como certificado de usabilidade | negócio | Alto | Alto | **Mitigar**: nota epistêmica da dimensão em `webqa/report.py::DIMENSION_NOTES`, impressa no laudo — geometria conforme não é pessoa atendida; e `docs/GUI.md §6.3` declara a fronteira entre "critérios medidos" e "o produto é usável" (mesmo desenho do R10) | revisão de PR do relatório |

Revisar esta matriz a cada release da suíte ou mudança relevante no alvo.

## Mitigações de privacidade aplicadas (parecer de proporcionalidade)

Hierarquia adotada: **não coletar > mascarar > reter pouco > criptografar**
(adequação e necessidade — Art. 6º, II/III; segurança — Art. 46).

| Risco de privacidade | Decisão | Implementação |
|---|---|---|
| PII incidental persistida no relatório | **Mitigado** | `webqa/sanitize.py::sanitize_text` aplicado na borda de escrita (`report.py`); verificado em `tests/test_sanitize.py` |
| Query strings do alvo em logs de links | **Mitigado** | `safe_url` oculta parâmetros nas mensagens (URL original segue sendo requisitada) |
| Erros de console com payloads do alvo | **Mitigado** | truncados a 200 chars + sanitizados antes de qualquer persistência |
| Script de CDN sem integridade (axe-core) | **Mitigado** | versão fixada 4.9.1 + verificação SHA-384 antes da injeção; hash divergente = erro, não skip |
| Carga sem autorização do dono do alvo | **Mitigado** | guarda técnica `WEBQA_LOAD_AUTHORIZED=1` na rajada pytest e no locustfile (aborta) |
| Interação ativa com sistema de terceiro (formulário, banner) | **Mitigado** | gate independente `WEBQA_ACTIVE_PROBES_AUTHORIZED=1` (`webqa/gates.py`); Fase 1 não o consome |
| PII do alvo capturada pela bateria LGPD (e-mail do encarregado, CPF em URL) | **Mitigado** | detector e mascarador compartilham as regexes (`sanitize.find_pii`); URL ofensora reportada via `safe_url`; cookie só por nome; e-mail do DPO nunca reproduzido |
| Inventário de terceiros persistido em `report/terceiros.json` | **Mitigado** | só hosts e contagens (sem path nem query), sanitizado na escrita, `report/` no `.gitignore` |
| Credencial de acesso do operador no relatório | **Mitigado** | `webqa/auth.py::Credencial` registra a senha — e suas formas escapadas para JSON/HTML/URL, mais o blob base64 do cabeçalho — no `sanitize` **no construtor**; a borda de escrita varre a string serializada. Mascarar por VALOR, não por nome: a senha de um nginx não tem prefixo de emissor nem rótulo que uma regex reconheça |
| Captura de tela do alvo (PII em pixel) | **Mitigado por NÃO COLETAR** | a hierarquia adotada é "não coletar > mascarar", e aqui mascarar não é opção: não existe mascarador de pixel. A camada GUI evidencia por seletor, caixa e texto sanitizado; captura é do alvo fabricado, e de alvo real só sob opt-in explícito, em `report/` (não versionado, expurgo de 7 dias) e nunca como linha de base |
| Relatório versionado no Git | **Mitigado** | `.gitignore` cobre `report/*`; atenção ao subir o repo — dotfiles se perdem em upload via interface web |
| Artefato de relatório no CI | **Mitigado** | `retention-days: 7` no upload-artifact (expurgo automático, criptografia em repouso do provedor) |
| Job de expurgo local com TTL | **Descartado (consciente)** | `summary.json` é sobrescrito a cada execução — TTL para arquivo auto-substituído é cerimônia sem risco correspondente |
| Criptografia embutida no plugin | **Descartado (consciente)** | após mascaramento não resta PII em claro; cifrar moveria o problema para gestão de chave. Se o ambiente exigir: disco cifrado do runner ou cifrar o artefato pós-geração com chave de secret |
| RIPD da própria ferramenta | **Descartado (consciente)** | tratamento incidental e efêmero não gera risco a titulares (Art. 38); RIPD é entregável de auditoria de um alvo controlador/operador |
