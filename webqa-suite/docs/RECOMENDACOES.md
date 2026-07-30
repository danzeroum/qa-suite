# Recomendações aplicadas e limites da automação

Práticas que orientaram o desenho desta suíte, com a cobertura efetiva e o
que permanece necessariamente humano.

## Garantia e Controle de Qualidade
- **V&V**: verificação em `tests/` (a suíte está correta?); validação em `checks/`
  (o alvo faz o que o usuário precisa?). O CI só valida após verificar (job gate).
- **Níveis de teste**: unidade → integração → sistema → aceitação, com foco em
  limites (percentis, listas vazias, hierarquias) e riscos (segurança, CLS, 404).
- **TDD/BDD**: aceitação escrita em Given/When/Then executável (pytest-bdd).
- **Análise estática/SAST**: ruff + bandit no CI para a suíte; headers OWASP
  verificados dinamicamente no alvo.

## UX
- **Heurísticas de Nielsen**: automatizamos os proxies objetivos (título, feedback,
  prevenção de erro, links descritivos, 404 com recuperação). **Limite**: estética,
  flexibilidade e satisfação exigem teste com usuários reais.
- **Arquitetura de informação**: organização (main/landmarks), navegação (nav),
  rotulação (textos de link/label) e hierarquia (headings).
- **Design centrado no usuário**: Web Vitals + WCAG medem a experiência real;
  recomenda-se complementar com prototipação e testes moderados.

## Arquitetura
- **Atributos de qualidade**: cada dimensão da suíte mapeia um -ility (performance,
  segurança, disponibilidade, usabilidade, observabilidade, testabilidade).
- **Observabilidade**: sinais externos verificados (health, request-id, erros estruturados).
- **Segurança por Design / LGPD**: HTTPS obrigatório, cookies endurecidos, sem
  vazamento de stack trace, sem exposição de versão.
- **Leis da arquitetura**: trade-offs documentados em ARQUITETURA.md.
- **C4**: contexto, containers e componentes em ARQUITETURA.md.

## Gestão de Projetos
- **Escopo/EAP**: ESCOPO-EAP.md, com EAP espelhando as pastas do código.
- **Riscos**: RISCOS.md (P×I, respostas evitar/mitigar/aceitar, monitoramento).
- **Modelo de gestão**: híbrido, justificado em ESCOPO-EAP.md.
