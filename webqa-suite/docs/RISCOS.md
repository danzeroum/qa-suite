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
| Relatório versionado no Git | **Mitigado** | `.gitignore` cobre `report/*`; atenção ao subir o repo — dotfiles se perdem em upload via interface web |
| Artefato de relatório no CI | **Mitigado** | `retention-days: 7` no upload-artifact (expurgo automático, criptografia em repouso do provedor) |
| Job de expurgo local com TTL | **Descartado (consciente)** | `summary.json` é sobrescrito a cada execução — TTL para arquivo auto-substituído é cerimônia sem risco correspondente |
| Criptografia embutida no plugin | **Descartado (consciente)** | após mascaramento não resta PII em claro; cifrar moveria o problema para gestão de chave. Se o ambiente exigir: disco cifrado do runner ou cifrar o artefato pós-geração com chave de secret |
| RIPD da própria ferramenta | **Descartado (consciente)** | tratamento incidental e efêmero não gera risco a titulares (Art. 38); RIPD é entregável de auditoria de um alvo controlador/operador |
