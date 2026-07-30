# language: pt
# Cenários de ACEITAÇÃO (validação): descrevem o que o usuário precisa,
# em Given/When/Then (BDD).

Funcionalidade: Acesso básico à aplicação
  Como visitante
  Quero acessar a aplicação com rapidez e clareza
  Para realizar minhas tarefas sem fricção

  Cenário: Visitante abre a página inicial
    Dado que o serviço está publicado
    Quando o visitante acessa a página inicial
    Então a resposta chega com sucesso em tempo aceitável
    E a página possui um título que orienta o visitante
    E a página oferece navegação para outras áreas
