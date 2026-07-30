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
