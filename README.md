# Alunos: Bernardo e Otávio

# Biblioteca Penal — RAG + MCP 

Chat acadêmico em português para consultar um corpus jurídico local. O backend conversa com um **servidor MCP separado via stdio/JSON-RPC**, recupera trechos no **ChromaDB** e permite que um **LLM por API execute function calling**. As respostas incluem citações verificáveis e páginas dos PDFs.

## Executar no Windows

Requisitos: Python 3.11 a 3.13, internet na primeira instalação e aproximadamente 1 GB livre para dependências, modelo de embeddings e índice. A geração usa uma API escolhida pelo usuário; exige chave, cota e modelo compatível com tools e JSON.

```powershell
powershell -ExecutionPolicy Bypass -File .\iniciar.ps1
```

Abra **http://127.0.0.1:8000**. Na primeira execução o script cria `.venv`, instala as dependências, baixa o embedder e indexa os cinco PDFs. Pode demorar alguns minutos. O servidor escuta apenas em `127.0.0.1`. Encerre com `Ctrl+C`.

Sem chave, selecione **Buscar nos documentos**: a busca semântica via MCP funciona, mas esse modo **não é geração por LLM e não completa sozinho o RF03**.

## Configurar o modelo por API

Execute o assistente no terminal; ele solicita a chave sem exibi-la:

```powershell
powershell -ExecutionPolicy Bypass -File .\configurar_api.ps1
```

É possível escolher Google Gemini pela interface compatível com Chat Completions ou outro provedor com essa interface. Informe o **nome exato de um modelo disponível na sua conta** que suporte `tools`, `tool_choice`, `response_format: json_object`, `temperature` e `max_tokens`. A disponibilidade e os custos dependem do provedor. Não há modelo externo ou assinatura pré-configurados.

Alternativamente, copie `.env.example` para `.env` e preencha:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://endpoint-do-seu-provedor/v1
LLM_MODEL=nome-do-modelo
LLM_API_KEY=sua-chave
```

Para Gemini, o endpoint compatível é `https://generativelanguage.googleapis.com/v1beta/openai` — [documentação oficial](https://ai.google.dev/gemini-api/docs/openai). O programa acrescenta `/chat/completions`; não inclua esse sufixo no endpoint base. As alterações em `.env` são lidas automaticamente; **recarregue a página** para atualizar o indicador e selecionar o chat com IA. O arquivo está no `.gitignore`; não compartilhe a chave ou a inclua em screenshots.

Os PDFs, os vetores e o modelo de embeddings permanecem na máquina. No modo com IA, **a pergunta e os trechos retornados pelas ferramentas são enviados à API**. A ferramenta `get_document` pode enviar uma página completa para conferir o contexto. O aplicativo não envia todos os PDFs nem o banco vetorial. O histórico visual existe apenas na página; **cada pergunta é independente**, sem memória de conversa no backend.

### Falhas temporárias da API

Para erros transitórios HTTP 408/500/502/503/504 e falhas de conexão, o adaptador faz até **três tentativas**, com espera crescente (por padrão 1,5 e 3 segundos), respeitando `Retry-After` e o orçamento total de tempo da chamada. Um `Retry-After` acima de 10 segundos encerra a tentativa e preserva o tempo de espera solicitado pelo provedor, sem repetir antes dele. Erros de configuração, autenticação e cota (400/401/403/404/429) não são repetidos automaticamente.

Se uma falha temporária persistir, o chat retorna `document_fallback`: mostra **trechos literais do corpus no corpo da conversa**, com suas fontes, e informa que não houve geração de explicação por IA. Esse modo mantém a consulta documental utilizável, mas não equivale a uma resposta gerada pelo LLM nem substitui a demonstração do RF03.

Quando uma resposta gerada falha no schema ou na validação documental, há **uma tentativa de correção pelo próprio modelo**, com o motivo da rejeição. Os critérios do guardrail não são afrouxados; se a correção também falhar, a resposta continua bloqueada. O modelo é orientado a incluir o marcador de artigo na citação quando mencionar esse número na explicação. Se ele citar somente o corpo de um artigo e seu cabeçalho estiver na mesma seção do chunk, o código pode ampliar a citação literal para incluir esse cabeçalho; não acrescenta números inventados, não amplia entre artigos diferentes e não altera penas ou prazos. A citação ampliada passa novamente pelo guardrail completo. Uma resposta JSON válida recebida no fim da rodada de ferramentas é reaproveitada para evitar uma chamada extra de geração.

## Arquitetura

```mermaid
flowchart LR
  PDF[5 PDFs jurídicos] --> Extract[Extração e limpeza por página]
  Extract --> Chunk[Chunks com sobreposição]
  Chunk --> Embed[Embedder multilíngue local]
  Embed --> DB[(ChromaDB persistente)]
  Browser[Navegador] --> Guard[Guardrail de entrada]
  Guard --> Backend[FastAPI / orquestração]
  Backend <-->|stdio / JSON-RPC| MCP[Servidor MCP separado]
  MCP --> DB
  Backend <-->|tools e resultados| LLM[LLM por API]
  Backend --> Output[Guardrail de saída]
  Output --> Sources[Resposta e citações]
  Sources --> Browser
```

1. A ingestão extrai e limpa o texto dos PDFs mantendo a página física de cada trecho.
2. O embedder local `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, executado em ONNX por FastEmbed, gera vetores de **384 dimensões**. Foi escolhido pelo suporte multilíngue, incluindo português, e por executar em CPU sem PyTorch. O primeiro download é público; as consultas seguintes não exigem serviço de embeddings externo.
3. O chunking usa o tokenizer do próprio modelo: **110 tokens e 20 de sobreposição**. Esse modelo trunca em 128 tokens; a janela de 110 deixa margem para tokens especiais e pequenas diferenças ao retokenizar as bordas. A sobreposição (~18%) preserva parte das frases nas fronteiras. O limite curto é uma escolha de eficiência para este MVP; trechos podem terminar no meio de um artigo. `get_document` e o link do PDF permitem recuperar o contexto. Cada chunk pertence a uma única página.
4. ChromaDB persiste o índice HNSW com distância cosseno. A recuperação é **híbrida**: retira termos genéricos de enquadramento da pergunta, faz uma busca vetorial pelo foco e combina o ranking com BM25 local por Reciprocal Rank Fusion (constante 40; peso vetorial 1 e lexical 1,5). Se sobra apenas um termo de conteúdo, como “tentativa”, preserva o enquadramento da pergunta original para não perder seu sentido jurídico; uma consulta de uma palavra recebe o contexto “no direito penal”. Retorna `top_k=5`, retira duplicatas exatas e filtra similaridades menores que `0.45`. Quando há termos centrais, exige que pelo menos um apareça no trecho, exceto se a similaridade for ≥0,80. A similaridade exibida é o cosseno com o **foco da pergunta**, não o score híbrido. Esses limites são configurações iniciais, **não probabilidades nem prova de suficiência**; perguntas específicas podem recuperar trechos que apenas mencionam o tema. O filtro lexical pode reduzir a recuperação de paráfrases sem palavras em comum.
   Referências explícitas, como “artigo 25”, também recebem busca por marcador de artigo. Nesse caso, são retornados apenas os trechos com o marcador solicitado, identificados com `retrieval_method=article_match`; podem passar abaixo do limiar vetorial, pois o critério é a correspondência exata do artigo. Se não houver esse marcador no corpus/filtro, a busca retorna vazia. Artigos com o mesmo número em leis diferentes ainda exigem conferir o documento de origem ou selecionar uma categoria.
5. O backend abre um subprocesso MCP, faz `initialize`, descobre as ferramentas com `tools/list` e as invoca com `tools/call`. A busca inicial é obrigatória e ocorre via MCP. Em seguida, o modelo escolhe ferramentas por function calling; o código executa essas chamadas pelo mesmo cliente MCP, acrescenta os resultados e solicita JSON estruturado. Máximo de três rodadas e quatro chamadas por rodada, mais a busca inicial.
6. O retorno é validado com Pydantic. Citações precisam existir literalmente em chunks realmente recuperados, os IDs devem ser conhecidos, números precisam constar da evidência e a afirmação precisa de correspondência lexical mínima. A interface mostra as afirmações aprovadas, suas citações e todas as fontes recuperadas. Se a resposta falhar, o texto gerado é bloqueado; os trechos continuam disponíveis para consulta.

## Ferramentas MCP

| Tool | Parâmetros | Retorno |
|---|---|---|
| `search_knowledge` | `query`, `top_k` (1–10), `topic_key` opcional | Trechos, IDs, documento, tópico, página, edição, similaridade e limiar |
| `get_document` | `document_id`, `page` (a partir de 1) | Conteúdo de uma página e metadados do documento permitido |
| `list_topics` | Nenhum | Categorias e quantidades de documentos e chunks |

As tools têm descrições, schemas tipados e retornos estruturados. O filtro escolhido na interface é imposto pelo backend nas buscas do modelo. Não há ferramenta de execução de código, escrita de arquivos ou leitura de caminhos arbitrários.

Para conectar outro cliente MCP, use o Python do ambiente, com a pasta do projeto como diretório de trabalho:

```powershell
.\.venv\Scripts\python.exe -m penal.mcp_server
```

Esse processo usa stdio para o protocolo, não é uma página HTTP. O servidor FastAPI fornece a interface do navegador.

## Corpus e versões

Os 5 Arquivos de base do projeto são documentos fornecidos pelo Senado Federal e a Camara dos deputados.

| Documento | Origem / edição |
|---|---|
| Código Penal, 9ª edição | PDF do usuário; Senado; atualizado até janeiro de 2026 |
| Coletânea básica penal, 16ª edição | PDF do usuário; Senado; atualizada até janeiro de 2026 |
| Decreto-Lei 2.848/1940, texto atualizado | PDF da Câmara fornecido pelo usuário; data de atualização não verificada |
| Código de Processo Penal | [Câmara dos Deputados](https://www2.camara.leg.br/legin/fed/declei/1940-1949/decreto-lei-3689-3-outubro-1941-322206-norma-pe.html); cópia consultada em 16/11/2026 |
| Lei de Execução Penal | [Câmara dos Deputados](https://www2.camara.leg.br/legin/fed/lei/1980-1987/lei-7210-11-julho-1984-356938-norma-pl.html); cópia consultada em 16/11/2026 |

O catálogo em `data/corpus.json` preserva a procedência; os metadados do índice também guardam SHA-256 e número de páginas. As páginas exibidas são as do arquivo PDF, e podem diferir da numeração impressa.

Há sobreposição entre os códigos e a coletânea; isso não representa cinco fontes independentes de confirmação. Duplicatas exatas são retiradas do resultado da busca, mas versões com redações próximas continuam distintas. O aplicativo **não resolve conflitos entre versões e não verifica vigência ou jurisprudência em tempo real**. Serve para estudo documental, não substitui orientação profissional.

## Guardrails e limites

- **Entrada:** tamanho, caracteres de controle, escopo por vocabulário jurídico e padrões de tentativa de alterar/revelar instruções. O filtro também é aplicado na ferramenta de busca.
- **Execução:** allowlist de três ferramentas, validação de argumentos, limite de rodadas, limite de concorrência local e documentos limitados ao catálogo.
- **Saída:** schema JSON, citações literais, IDs, números e correspondência textual. Falhas bloqueiam a resposta gerada. O modelo pode declarar insuficiência mesmo quando a busca encontra resultados.
- **Navegador:** conteúdo inserido como texto, política de conteúdo, verificação de origem em POST e vínculo local do servidor.
- **Logs:** `logs/queries.jsonl` contém horário, hash da pergunta, status, guardrails e nomes/resultados das chamadas MCP; não grava chave, pergunta ou corpo das fontes.

São mecanismos básicos. Regex não detecta todas as formas de prompt injection; correspondência lexical **não comprova implicação lógica, correção jurídica ou ausência de alucinação**. Pode aceitar uma paráfrase errada com as mesmas palavras ou bloquear uma explicação correta. O system prompt trata os documentos como dados, mas essa orientação também não é uma barreira infalível. Use as citações para conferir as respostas.

## Testes e demonstração

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\verify_mcp.py
```

Os testes unitários cobrem chunking, overlap, bloqueio de entrada, citações inventadas, IDs inexistentes, números sem fonte e validação HTTP. A verificação de integração usa **MCP, ChromaDB, embeddings e PDFs reais**; registra evidências em `docs/evidencias_mcp.json`. Ela não simula nem afirma ter executado um LLM externo.


**Sem chave configurada, a geração e o function calling de um LLM real ainda precisam ser demonstrados.** A busca local e a integração MCP podem ser testadas independentemente. Os testes que usam um adaptador falso, quando presentes, verificam a orquestração e não substituem essa demonstração.

## Atualizar e desenvolver

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m penal.ingest
.\.venv\Scripts\python.exe -m uvicorn penal.web:app --host 127.0.0.1 --port 8000
```

`requirements.lock.txt` registra as versões instaladas e verificadas no Windows/Python 3.13. Para reproduzir esse ambiente use `pip install -r requirements.lock.txt`; o lock inclui dependências específicas do Windows. Em outros sistemas, use `requirements.txt`.

Para adicionar um PDF, coloque-o em `data/raw`, cadastre metadados em `data/corpus.json` e execute a ingestão novamente com o backend parado. O índice novo é construído em staging e só fica ativo ao terminar. As coleções antigas são preservadas para evitar perda em falhas; não há limpeza automática. Mudar embedder, chunk size ou overlap exige reindexação; o servidor recusa índice incompatível. PDFs digitalizados sem texto exigem OCR prévio.

### Estrutura

```text
penal/                backend, cliente/servidor MCP, RAG, guardrails e LLM
static/               interface sem dependências externas de frontend
data/raw/             os cinco PDFs do corpus
data/corpus.json      catálogo de fontes
data/processed/       páginas e manifesto do índice (gerado, fora do Git)
data/chroma/          banco vetorial persistente (fora do Git)
data/models/          cache do embedder (fora do Git)
scripts/verify_mcp.py demonstração do protocolo e recuperação real
tests/                testes automatizados
docs/                 evidências e roteiro da apresentação
```


Referências técnicas: [MCP Python SDK v1](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x), [Chroma — configuração de coleções](https://docs.trychroma.com/docs/collections/configure), [FastEmbed — modelos](https://qdrant.github.io/fastembed/examples/Supported_Models/), [Gemini — API compatível](https://ai.google.dev/gemini-api/docs/openai).
