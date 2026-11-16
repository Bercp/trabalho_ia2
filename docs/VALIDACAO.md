# Validação realizada em 16/11/2026

Ambiente: Windows, Python 3.13, CPU, dependências registradas em `requirements.lock.txt`.

| Verificação | Resultado |
|---|---|
| Testes automatizados | 30 aprovados; um aviso de depreciação da biblioteca de teste HTTP |
| Corpus local | 5 PDFs, 734 páginas físicas, 5.487 chunks |
| Protocolo MCP | `initialize`, descoberta e execução real das 3 ferramentas por stdio |
| Consulta de legítima defesa | 5 trechos recuperados, incluindo o artigo pertinente |
| Consulta explícita ao artigo 25 com filtro de Direito Penal | 3 trechos do artigo solicitado |
| Consulta ao artigo 99999 | Nenhum trecho |
| Consulta fictícia de crime intergaláctico | Nenhum trecho |
| Prompt injection | Bloqueado na entrada e também pela ferramenta de busca |
| `get_document` | Página recuperada contém literalmente o chunk retornado |
| Acesso ao PDF no navegador | HTTP 200 com conteúdo PDF |
| Chat sem chave | Informa `llm_unavailable` e preserva as fontes recuperadas |
| Assistente de configuração | Endpoint, modelo e chave fictícia salvos corretamente em diretório de teste isolado |

O arquivo [`evidencias_mcp.json`](evidencias_mcp.json) foi produzido pela integração real entre o cliente MCP, o servidor MCP, os embeddings e o ChromaDB. Os testes de orquestração e do adaptador HTTP usam doubles explícitos; **não são evidência de inferência com LLM externo**.

Atualização da auditoria: o Gemini foi configurado e o fluxo real foi testado. A consulta válida executou uma ferramenta solicitada pelo modelo, mas a resposta foi bloqueada na validação de números/artigos. Os cenários de informação ausente, prompt injection e pergunta fora do domínio passaram. Veja [`evidencias_gemini.json`](evidencias_gemini.json) e a [`auditoria de requisitos`](REVISAO_REQUISITOS.md). Ainda falta uma demonstração atual aprovada de resposta válida com o LLM, além do fortalecimento dos guardrails descrito na auditoria.

Registros da interface, em modo de busca documental sem LLM:

![Consulta válida com trecho e página](consulta-documental.jpg)

![Retorno sem evidência suficiente](consulta-sem-evidencia.jpg)

![Bloqueio da entrada de manipulação](entrada-bloqueada.jpg)

Para reproduzir:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\verify_mcp.py
```
