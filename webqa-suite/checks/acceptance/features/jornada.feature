# language: pt
# Cenários de ACEITAÇÃO (validação): descrevem o que o visitante precisa, em
# Given/When/Then. Genéricos por desenho — falam de necessidade do usuário, nunca
# de detalhe de um alvo específico (§3 da arquitetura: o projeto contribui
# configuração, nunca check próprio). Tudo passivo: só GET, o que um visitante faz.

Funcionalidade: Jornada básica do visitante
  Como visitante
  Quero entender e navegar a aplicação sem fricção
  Para realizar minhas tarefas com clareza

  Cenário: Visitante recebe a página no idioma declarado
    Dado que o serviço está publicado
    Quando o visitante acessa a página inicial
    Então a página declara o idioma do seu conteúdo

  Cenário: Visitante encontra conteúdo real na página inicial
    Dado que o serviço está publicado
    Quando o visitante acessa a página inicial
    Então a página apresenta um conteúdo principal com texto

  Cenário: Visitante erra o endereço e recebe uma resposta clara
    Dado que o serviço está publicado
    Quando o visitante acessa um endereço que não existe
    Então o serviço responde claramente "não encontrado"
    E não devolve um erro de servidor nem finge que a página existe
