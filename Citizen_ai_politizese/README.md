Citizen Assist AI — Politize-se | Título de Eleitor
Projeto acadêmico em Python para orientar a população sobre título de eleitor e serviços da Justiça Eleitoral. O sistema funciona no terminal, responde exclusivamente com informações cadastradas em JSON e apresenta fontes oficiais e a data em que cada orientação foi verificada.
Aviso: este assistente não é um canal oficial da Justiça Eleitoral. As respostas são educativas e não substituem a consulta ao TSE ou ao Tribunal Regional Eleitoral (TRE).

1. Recorte, público e problema
Público: cidadãos brasileiros, especialmente jovens que vão tirar o primeiro título, pessoas que mudaram de município e eleitores com dúvidas sobre situação cadastral, multas, biometria, e-Título e votação.

Problema: informações eleitorais podem parecer complexas, estar distribuídas em diferentes páginas e conter prazos que mudam conforme o calendário eleitoral. O projeto reúne perguntas frequentes em linguagem simples, com indicação da fonte e da data em que a equipe verificou cada registro.

O recorte é inspirado no Politize-se: informar sem direcionar opinião política, tornar as fontes visíveis e não coletar dados pessoais.
2. Relação com PCP — Pensamento Computacional e Automação com Python
O projeto atende ao recorte de PCP com:
- base de conhecimento em data/base_conhecimento.json;
- separação de responsabilidades entre as classes Orientacao, BaseConhecimento e Assistente;
- normalização de texto, pontuação por regras e busca em texto livre;
- navegação por categorias;
- validação de entradas e bloqueio de perguntas com 8 ou mais dígitos ou @;
- histórico em JSON, indicadores e exportação CSV;
- transparência por meio da fonte, data de verificação e aviso de não oficialidade.
2.1 Quantidade e organização dos registros
O arquivo data/base_conhecimento.json incluído nesta versão contém 15 registros. Foram identificados quatro valores distintos no campo categoria: Primeiro título e cadastro, Regularização e situação eleitoral, Serviços e votação e votar. O valor votar aparece isolado no registro de ID 35 e não segue a taxonomia das outras três categorias; recomenda-se revisar esse registro antes da próxima atualização da base.
3. Modelo de dados JSON
Cada orientação possui os seguintes campos:
Campo	Significado
id	Identificador inteiro e único
categoria	Grupo de assunto
titulo	Nome curto da orientação
palavras_chave	Termos usados na busca
resposta	Explicação em linguagem simples
documentos	Documentos ou requisitos relevantes
onde	Canal ou local de atendimento
fonte	URL oficial consultada
verificado_em	Data da conferência pela equipe


A base agrupa assuntos de primeiro título e cadastro, regularização e situação eleitoral, e serviços e votação. O JSON permite revisar o conteúdo sem alterar as regras de busca do programa.
4. Como funciona a busca por pontuação
A pergunta, as palavras-chave e o título são normalizados: minúsculas, sem acentos e com pontuação convertida em espaços.

Pontuação utilizada:
- +3 pontos para cada palavra-chave da orientação encontrada na pergunta;
- +1 ponto para cada palavra da pergunta com quatro ou mais letras que também apareça no título;
- 6 pontos ou mais: confiança ALTA;
- 3 a 5 pontos: confiança MÉDIA;
- menos de 3 pontos: resposta não encontrada; o assistente sugere reformular a pergunta ou navegar pelas categorias.
BaseConhecimento.buscar() calcula uma pontuação para cada orientação e devolve os resultados em ordem decrescente. A melhor orientação e até duas alternativas com pontuação mínima são apresentadas. A busca não usa IA generativa: é uma correspondência determinística por regras.
5. Privacidade, validação e transparência
- O assistente não solicita nome, CPF, telefone ou e-mail.
- Perguntas contendo @ ou uma sequência de 8 ou mais dígitos são recusadas antes de serem registradas.
- Perguntas vazias, opções inválidas, IDs não numéricos e consultas sem resultado são tratadas sem encerrar o programa.
- Toda orientação mostra fonte, data de verificação e aviso de não oficialidade.
- Se o JSON estiver ausente ou inválido, o programa avisa e inicia com a base vazia, em vez de encerrar por exceção não tratada.
- O histórico não guarda perguntas recusadas por conterem possíveis dados pessoais.
Limitação do filtro: a regra de 8 dígitos ou @ é uma barreira simples, não um detector perfeito de dados pessoais. Evite inserir qualquer informação pessoal.
6. Histórico, indicadores e CSV
Cada atendimento válido é gravado em data/historico.json, com data e hora, origem (pergunta ou categoria), pergunta, ID da orientação (quando encontrada), indicação de resposta encontrada, avaliação de utilidade, tentativas e tempo em segundos.

Ao encerrar, o programa solicita nota de facilidade de 1 a 5. A opção Ver indicadores calcula percentual de respostas encontradas, taxa de ajuda percebida, tempo médio, tentativas médias, média de facilidade e dúvidas sem solução.

A opção Exportar CSV gera data/atendimentos.csv com csv.DictWriter. O arquivo CSV é sobrescrito com o histórico acumulado atual.
7. Estrutura do projeto
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
    └── test_basico.py
8. Requisitos e execução
- Python 3.10 ou superior (o programa utiliza somente a biblioteca padrão).
- Não precisa de Ollama, LangChain, conexão com banco de dados ou instalação de pacotes externos.
- Abra o terminal/PowerShell na pasta do projeto.
Execute:
python main.py
Em alguns ambientes Windows, pode ser necessário:
py main.py
Para executar os testes automatizados, instale pytest se ainda não estiver disponível e rode:
python -m pip install pytest
python -m pytest -q
9. Fontes oficiais e atualização da base
As orientações iniciais foram preparadas a partir das páginas oficiais do Tribunal Superior Eleitoral (TSE). A data 2026-11-19 registra a conferência inicial desta versão do material; antes de apresentar o projeto ou utilizar uma orientação na vida real, confira se a página oficial e o calendário eleitoral continuam iguais.
- Carta de Serviços ao Eleitor — TSE
- Título Eleitoral — Perguntas frequentes — TSE
- Autoatendimento Eleitoral — Título Net — TSE
- Consulta da situação eleitoral — TSE
- e-Título — TSE
Atenção a prazos: em anos eleitorais, serviços como alistamento, transferência e revisão podem ter prazo de fechamento antes da votação. A situação pode mudar de um pleito para outro. O assistente não calcula prazos nem confirma a disponibilidade em tempo real; encaminha a pessoa à página oficial.
10. Testes e evidências a completar pela equipe
A suíte tests/test_basico.py contém verificações automatizadas para a base de conhecimento, a busca por pontuação e o bloqueio básico de dados pessoais. Na execução realizada durante a revisão desta versão, o comando python -m pytest -q concluiu com 4 testes aprovados.

Ainda é necessário realizar o teste com pelo menos 3 pessoas de fora da equipe e 10 atendimentos ou mais, conforme o enunciado de PCP. Registre no README final os indicadores reais, as dúvidas sem solução e uma melhoria feita a partir dos testes. Não invente resultados nem registre nomes ou dados pessoais dos participantes.

Para a demonstração do recorte PCP, apresente:
1. inicialização do programa e leitura da base JSON;
2. pergunta livre com resposta, fonte e data de verificação;
3. pergunta sem pontuação suficiente;
4. navegação por categorias;
5. bloqueio de entrada com possível dado pessoal;
6. registro do atendimento no histórico;
7. visualização dos indicadores e exportação CSV.
11. Limitações conhecidas
- A busca é baseada em palavras-chave e título; sinônimos não cadastrados podem não ser reconhecidos.
- Não existe integração com API do TSE/TRE nem consulta individual da situação eleitoral.
- A base é estática até que a equipe revise e atualize o JSON.
- Prazos eleitorais e procedimentos podem mudar.
- O filtro de dados pessoais é simples e não substitui controles robustos de privacidade.
- O histórico local é armazenado sem identificação de usuários; ainda assim, não se deve registrar informações pessoais nas perguntas.
12. ODS relacionados
- ODS 16 — Paz, Justiça e Instituições Eficazes: facilita o acesso a informações institucionais e serviços eleitorais.
- ODS 10 — Redução das Desigualdades: busca diminuir barreiras de compreensão e acesso a orientações públicas.
- ODS 4 — Educação de Qualidade: promove compreensão cívica por meio de informação acessível.