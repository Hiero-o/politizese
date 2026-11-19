# Citizen Assist AI — Politize-se | Título de Eleitor

Projeto acadêmico em Python para orientar a população sobre título de eleitor e serviços da Justiça Eleitoral. O sistema funciona no terminal, responde exclusivamente com informações cadastradas em JSON, apresenta fontes oficiais e implementa uma lista simplesmente encadeada própria.

> **Aviso:** este assistente não é um canal oficial da Justiça Eleitoral. As respostas são educativas e não substituem a consulta ao TSE ou ao Tribunal Regional Eleitoral (TRE).

## 1. Recorte, público e problema

**Público:** cidadãos brasileiros, especialmente jovens que vão tirar o primeiro título, pessoas que mudaram de município e eleitores com dúvidas sobre situação cadastral, multas, biometria, e-Título e votação.

**Problema:** informações eleitorais podem parecer complexas, estar distribuídas em diferentes páginas e conter prazos que mudam conforme o calendário eleitoral. O projeto reúne perguntas frequentes em linguagem simples, com indicação da fonte e da data em que a equipe verificou cada registro.

O recorte é inspirado no Politize-se: informar sem direcionar opinião política, tornar as fontes visíveis e não coletar dados pessoais.

## 2. Relação com as disciplinas

### PCP — Pensamento Computacional e Automação com Python

O projeto atende ao enunciado de PCP com:
- base de conhecimento em `data/base_conhecimento.json`, com 14 orientações, 3 categorias e pelo menos 3 palavras-chave por orientação;
- classes `Orientacao`, `BaseConhecimento` e `Assistente`, organizadas por composição;
- normalização de texto, pontuação por regras e busca em texto livre;
- navegação por categorias;
- validação de entradas e bloqueio de perguntas com 8 ou mais dígitos ou `@`;
- histórico em JSON, indicadores e exportação CSV;
- transparência: fonte, data de verificação e aviso de que o assistente não é canal oficial.

### DSA — Data Structures and Algorithms

O sistema também implementa os requisitos centrais de DSA:
- **Nó:** a classe `No`, implementada em `base_conhecimento.py`, guarda um objeto e uma referência `proximo` para o próximo nó.
- **Lista simplesmente encadeada:** `ListaEncadeada`, também em `base_conhecimento.py`, mantém `inicio`, `fim` e `tamanho`. Não utiliza `list` do Python como estrutura principal de armazenamento dos registros.
- **Inserção:** cadastro de registros no final da lista.
- **Percurso:** visita sequencial dos nós para listar, filtrar, pontuar e calcular indicadores.
- **Busca:** consulta por ID e pesquisa por título/categoria/palavras-chave.
- **Atualização:** localiza o nó, remove o registro antigo e insere o objeto atualizado.
- **Remoção:** ajusta as referências do nó anterior e do próximo, atualizando início/fim quando necessário.
- **Ordenação:** Insertion Sort implementado diretamente nos nós, reencadeando-os por título normalizado.
- **CRUD e menu:** cadastro, consulta, pesquisa, atualização, exclusão, ordenação, análise e encerramento.

A lista encadeada é a estrutura principal em memória para as orientações. O JSON é a persistência: ao iniciar, os objetos são reconstruídos e inseridos na lista; ao cadastrar, atualizar, excluir ou ordenar, a base é salva novamente.

## 3. Modelo de dados JSON

Cada objeto contém os campos obrigatórios definidos no enunciado de PCP:

| Campo | Significado |
|---|---|
| `id` | Identificador inteiro e único |
| `categoria` | Grupo de assunto |
| `titulo` | Nome curto da orientação |
| `palavras_chave` | Termos usados na busca |
| `resposta` | Explicação em linguagem simples |
| `documentos` | Documentos ou requisitos relevantes |
| `onde` | Canal ou local de atendimento |
| `fonte` | URL oficial consultada |
| `verificado_em` | Data da conferência pela equipe |

A base inicial contém 14 orientações em três categorias: Primeiro título e cadastro; Regularização e situação eleitoral; Serviços e votação.

## 4. Como funciona a busca por pontuação (PCP)

A pergunta, as palavras-chave e o título são normalizados: minúsculas, sem acentos e sem pontuação relevante.

Pontuação utilizada:
- **+3 pontos** para cada palavra-chave da orientação encontrada na pergunta;
- **+1 ponto** para cada palavra da pergunta com quatro ou mais letras que também apareça no título;
- **6 pontos ou mais:** confiança ALTA;
- **3 a 5 pontos:** confiança MÉDIA;
- **menos de 3 pontos:** resposta não encontrada; o assistente sugere reformular a pergunta ou navegar pelas categorias.

`BaseConhecimento.buscar()` devolve uma lista de tuplas `(pontos, orientacao)`, em ordem decrescente. A melhor orientação e até duas alternativas com pontuação mínima são apresentadas. A busca não usa IA generativa: é uma correspondência determinística por regras, como exige a atividade.

## 5. Lista encadeada e análise Big-O (DSA)

Considere `n` como a quantidade de orientações.

| Operação | Complexidade | Justificativa |
|---|---:|---|
| Inserir no final | O(1) | Usa referência direta para `fim` |
| Percorrer/listar | O(n) | Visita cada nó uma vez |
| Buscar por ID | O(n) | Pode precisar visitar todos os nós |
| Pesquisar atributo | O(n × k) | Visita n registros e compara até k termos/campos; para tamanho textual limitado, costuma-se expressar como O(n) |
| Remover por critério | O(n) | Localiza o nó e ajusta referências em O(1) |
| Atualizar por ID | O(n) | Busca, remove e reinsere; inserção final é O(1) |
| Insertion Sort | O(n²) | No pior caso, cada nó percorre a parte já ordenada |
| Espaço da lista | O(n) | Um nó por registro |

**Por que Insertion Sort?** É um algoritmo estudado e permite demonstrar ordenação sem recorrer a `sorted()` ou `list.sort()` na estrutura principal. A implementação reencadeia os próprios nós e usa espaço auxiliar constante, desconsiderando a recursão (não há recursão).

A busca por pontuação percorre os nós e depois ordena a lista de resultados por inserção. A complexidade dessa etapa de ordenação é O(n²) no pior caso.

## 6. Privacidade, validação e transparência

- O assistente não solicita nome, CPF, telefone ou e-mail.
- Perguntas contendo `@` ou uma sequência de 8 ou mais dígitos são recusadas antes de serem registradas.
- Perguntas vazias, opções inválidas, IDs não numéricos, IDs duplicados e consultas sem resultado são tratadas sem encerrar o programa.
- A navegação apresenta `0 para voltar` em todas as telas.
- Toda orientação mostra fonte, data de verificação e aviso de não oficialidade.
- Se o JSON estiver ausente ou inválido, o programa avisa e inicia com lista vazia, em vez de encerrar por exceção não tratada.
- O histórico não guarda perguntas recusadas por conterem possíveis dados pessoais.

**Limitação do filtro:** a regra de 8 dígitos ou `@` é uma barreira simples solicitada no enunciado, não um detector perfeito de dados pessoais. Evite inserir qualquer informação pessoal.

## 7. Histórico, indicadores e CSV (PCP)

Cada atendimento válido é gravado em `data/historico.json`, com:
- data e hora;
- origem (`pergunta` ou `categoria`);
- pergunta;
- ID da orientação (quando encontrada);
- se encontrou resposta;
- se a orientação ajudou;
- tentativas;
- tempo em segundos.

Ao encerrar, o programa solicita nota de facilidade de 1 a 5. A opção **Ver indicadores** calcula percentual de respostas encontradas, taxa de ajuda percebida, tempo médio, tentativas médias, média de facilidade e dúvidas sem solução.

A opção **Exportar CSV** gera `data/atendimentos.csv` com `csv.DictWriter`. O CSV é sobrescrito com o histórico acumulado atual.

## 8. Estrutura do projeto

```text
Citizen_ai_politizese/
├── README.md
├── main.py
├── orientacao.py
├── base_conhecimento.py
├── assistente.py
├── data/
│   ├── base_conhecimento.json
│   ├── historico.json
│   └── atendimentos.csv
└── tests/
    └── teste_basico.py
```

## 9. Requisitos e execução

- Python 3.10 ou superior (somente biblioteca padrão no programa).
- Não precisa de Ollama, LangChain, conexão com banco de dados ou instalação de pacotes externos.
- Terminal/PowerShell aberto na pasta do projeto.

Execute:

```bash
python main.py
```

Em alguns ambientes Windows, pode ser necessário:

```powershell
py main.py
```

Para executar os testes automatizados, instale `pytest` se ainda não estiver disponível e rode:

```bash
python -m pip install pytest
python -m pytest -q
```

## 10. Fontes oficiais e atualização da base

As orientações iniciais foram preparadas a partir das páginas oficiais do Tribunal Superior Eleitoral (TSE). A data `2026-11-19` registra a conferência inicial desta versão do material; antes de apresentar o projeto ou utilizar uma orientação na vida real, confira se a página oficial e o calendário eleitoral continuam iguais.

- [Carta de Serviços ao Eleitor — TSE](https://www.tse.jus.br/servicos-eleitorais/servicos/carta-de-servicos-ao-eleitor)
- [Título Eleitoral — Perguntas frequentes — TSE](https://www.tse.jus.br/servicos-eleitorais/titulo-eleitoral/titulo-eleitoral-faq)
- [Autoatendimento Eleitoral — Título Net — TSE](https://www.tse.jus.br/servicos-eleitorais/titulo-eleitoral/autoatendimento-eleitoral)
- [Consulta da situação eleitoral — TSE](https://www.tse.jus.br/institucional/corregedoria-geral-eleitoral/sistemas-e-servicos-1/consulta-situacao-eleitoral)
- [e-Título — TSE](https://www.tse.jus.br/servicos-eleitorais/servicos/e-titulo)

**Atenção a prazos:** em anos eleitorais, serviços como alistamento, transferência e revisão podem ter prazo de fechamento antes da votação. A situação pode mudar de um pleito para outro. O assistente não calcula prazos nem confirma a disponibilidade em tempo real; encaminha a pessoa à página oficial.

## 11. Testes e evidências a completar pela equipe

Os testes automatizados em `tests/teste_basico.py` verificam:
- quantidade mínima de registros e categorias;
- busca por pontuação;
- retorno da busca com orientação;
- ordenação e exclusão na lista encadeada;
- bloqueio de padrões simples de dados pessoais.

Ainda é necessário realizar o teste com **pelo menos 3 pessoas de fora da equipe e 10 atendimentos ou mais**, conforme o enunciado de PCP. Registre no README final os indicadores reais, as dúvidas sem solução e uma melhoria feita a partir dos testes. Não invente resultados nem registre nomes ou dados pessoais dos participantes.

## 12. Checklist de demonstração técnica

Para a apresentação/vídeo, demonstre:
1. Um registro JSON e seus campos.
2. Classes, atributos, métodos, `self` e composição.
3. Estrutura `No` (`dado` e `proximo`) e encadeamento de nós.
4. Cadastro, consulta, busca por atributo, atualização e exclusão.
5. Insertion Sort reencadeando os nós.
6. Busca por pontuação com uma pergunta real, mostrando os pontos.
7. Pergunta encontrada, não encontrada, entrada inválida e dado pessoal bloqueado.
8. Navegação por categoria e opção `0` para voltar.
9. Histórico JSON, indicadores e CSV.
10. Uma decisão técnica, análise Big-O e limitações.

O enunciado de PCP pede vídeo técnico de 5 a 8 minutos, com todos os integrantes explicando partes técnicas, e entrega de um `.txt` com nome do assistente, público, integrantes/RM e links. O enunciado de DSA também exige demonstração prática das estruturas e algoritmos. Esses itens ficam para a equipe completar.

## 13. Limitações conhecidas

- A busca é baseada em palavras-chave e título; sinônimos não cadastrados podem não ser reconhecidos.
- Não existe integração com API do TSE/TRE nem consulta individual da situação eleitoral.
- A base é estática até que a equipe revise e atualize o JSON.
- Prazos eleitorais e procedimentos podem mudar.
- A lista encadeada mantém os registros em memória; o JSON é usado para persistência entre execuções.
- O filtro de dados pessoais é deliberadamente simples e não substitui controles robustos de privacidade.
- O histórico local é armazenado sem identificação de usuários; ainda assim, não se deve registrar informações pessoais nas perguntas.

## 14. ODS relacionados

- **ODS 16 — Paz, Justiça e Instituições Eficazes:** facilita o acesso a informações institucionais e serviços eleitorais.
- **ODS 10 — Redução das Desigualdades:** busca diminuir barreiras de compreensão e acesso a orientações públicas.
- **ODS 4 — Educação de Qualidade:** promove compreensão cívica por meio de informação acessível.

---