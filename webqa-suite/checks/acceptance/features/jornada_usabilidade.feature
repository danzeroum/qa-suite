# language: pt
# Cenários de jornada — GUI-JORN-01/02 (OS-51).
#
# ESTES cenários são os mesmos que o protocolo humano (OS-54) usará numa sessão
# moderada, e é por isso que a feature existe separada dos checks: vocabulário
# único é o que torna TSR e ToT sintético e humano comparáveis na MESMA régua.
# Duas réguas com o mesmo nome não se comparam — comparam-se por engano.
#
# O teste de leitura, aplicado a cada passo antes de ele entrar aqui: uma pessoa
# moderando uma sessão consegue executar o passo lendo-o em voz alta, sem
# tradução? Passo que só faz sentido para o robô ("o grafo não contém ciclo",
# "o BFS retorna caminho mínimo") mata a comparabilidade na escrita, e nenhuma
# implementação a ressuscita depois.
#
# O que a pessoa faz e o robô imita: LER OS RÓTULOS e seguir o que parece levar
# à tarefa. Não é o caminho ótimo de propósito — o ótimo é a régua contra a qual
# o percurso é medido, e a diferença entre os dois é o preço do rótulo ruim.
#
# Tudo passivo: clique de leitura em mesma origem, nada que submeta formulário.

Funcionalidade: Jornada de usabilidade
  Como visitante
  Quero chegar ao que vim fazer sem me perder
  Para não desistir no meio do caminho

  Cenário: O visitante encontra a política de privacidade
    Dado que o visitante está na página inicial
    E que a tarefa é "encontrar a política de privacidade"
    Quando ele lê os links de cada página e segue o que parece levar à tarefa
    Então ele chega à página da tarefa
    E não precisa de mais cliques do que a tarefa admite

  Cenário: O visitante procura como falar com a loja
    Dado que o visitante está na página inicial
    E que a tarefa é "encontrar como falar com a loja"
    Quando ele lê os links de cada página e segue o que parece levar à tarefa
    Então ele chega à página da tarefa

  Cenário: Nenhuma página deixa o visitante sem saída
    Dado que o visitante está na página inicial
    Quando ele percorre as páginas que a aplicação oferece
    Então nenhuma delas o obriga a voltar para continuar

  Cenário: O visitante conclui a tarefa no tempo previsto
    Dado que o visitante está na página inicial
    E que a tarefa é "encontrar a política de privacidade"
    Quando ele lê os links de cada página e segue o que parece levar à tarefa
    Então ele conclui dentro do tempo previsto para a tarefa
