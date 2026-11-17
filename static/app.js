const $ = (selector) => document.querySelector(selector);
let mode = 'search';
let busy = false;
let lastSources = [];
let state = null;
const statusLabels = {answered:'Resposta com fontes', search_only:'Busca documental · sem LLM', document_fallback:'Consulta local · IA temporariamente indisponível', blocked:'Entrada bloqueada', insufficient_evidence:'Evidência insuficiente', output_blocked:'Resposta bloqueada pela validação', llm_unavailable:'API não disponível'};

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}
function setMode(next) {
  mode = next;
  for (const name of ['chat', 'search']) {
    $(`#mode-${name}`).classList.toggle('selected', next === name);
    $(`#mode-${name}`).setAttribute('aria-pressed', String(next === name));
  }
}
function renderSources(sources) {
  lastSources = sources;
  $('#source-count').textContent = sources.length;
  $('#sources').replaceChildren();
  if (!sources.length) {
    $('#sources').append(element('p', 'muted', 'Nenhum trecho recuperado nesta consulta.'));
    return;
  }
  sources.forEach((source, index) => {
    const card = $('#source-template').content.firstElementChild.cloneNode(true);
    card.id = `source-${index + 1}`;
    card.querySelector('.source-number').textContent = `FONTE ${index + 1}`;
    card.querySelector('.source-page').textContent = `PÁGINA ${source.page}`;
    card.querySelector('h3').textContent = source.title;
    card.querySelector('.source-edition').textContent = source.edition;
    card.querySelector('.source-text').textContent = source.text;
    card.querySelector('.source-score').textContent = source.retrieval_method === 'article_match' ? 'Artigo solicitado localizado' : `Similaridade: ${source.similarity.toFixed(2)}`;
    card.querySelector('.source-link').href = `/documents/${encodeURIComponent(source.document_id)}/pdf#page=${source.page}`;
    $('#sources').append(card);
  });
}
function appendEvidence(container, citations, sources) {
  for (const citation of citations) {
    const index = sources.findIndex(s => s.chunk_id === citation.chunk_id);
    const quote = element('blockquote','');
    const button = element('button','citation-link',`[${index + 1}]`);
    button.title = 'Ver fonte e página';
    button.addEventListener('click', () => {
      renderSources(sources);
      const target = $(`#source-${index + 1}`);
      if (target) { target.querySelector('details').open = true; target.scrollIntoView({behavior:'smooth', block:'center'}); }
    });
    quote.append(button,document.createTextNode(citation.quote));
    container.append(quote);
  }
}
function appendMessage(role, text, data) {
  const article = element('article', `message ${role}`);
  if (data && !['answered','search_only'].includes(data.status)) article.classList.add('warning');
  const header = element('div','message-header');
  header.append(element('span','message-role',role === 'user' ? 'Você' : '§ Biblioteca Penal'));
  if (data?.elapsed_ms) header.append(element('span','',`${(data.elapsed_ms / 1000).toFixed(1)} s`));
  article.append(header);
  const body = element('div','message-content');
  if (data) body.append(element('span','result-status',statusLabels[data.status] || data.status));
  if (data?.claims?.length) {
    data.claims.forEach(claim => {
      const section = element('section','claim');
      section.append(element('p','',claim.text));
      appendEvidence(section, claim.evidence, data.sources);
      body.append(section);
    });
  } else body.append(element('p','',text));
  if (data?.excerpts?.length) {
    const section = element('section','claim fallback-excerpts');
    appendEvidence(section, data.excerpts, data.sources);
    body.append(section);
  }
  article.append(body);
  if (data?.tools?.length) {
    const details = element('details','diagnostics');
    details.append(element('summary','',`Como a consulta foi feita · ${data.tools.length} chamada(s) MCP`));
    const list = element('ul','');
    for (const tool of data.tools) list.append(element('li','',`${tool.ok ? '✓' : '×'} ${tool.name} · ${tool.initiated_by === 'llm' ? 'solicitada pelo modelo' : 'solicitada pelo backend'}${tool.chunks ? ` · ${tool.chunks} trechos` : ''}`));
    const guardrailNames = {input:'entrada',output:'saída',availability:'disponibilidade da IA'};
    for (const [name,result] of Object.entries(data.guardrails || {})) list.append(element('li','',`${result.passed ? '✓' : '×'} Validação de ${guardrailNames[name] || name}: ${result.detail}`));
    details.append(list); article.append(details);
  }
  $('#conversation').append(article);
  article.scrollIntoView({block:'nearest',behavior:'smooth'});
}
async function submit(event) {
  event?.preventDefault();
  const message = $('#message').value.trim();
  if (!message || busy) return;
  busy = true;
  $('#welcome')?.remove();
  appendMessage('user',message);
  $('#message').value = '';
  $('#send').disabled = true;
  $('#new-chat').disabled = true;
  const pending = element('div','pending');
  pending.append(element('span','spinner'),document.createTextNode(mode === 'chat' ? 'Consultando documentos e preparando a resposta…' : 'Buscando trechos no acervo…'));
  $('#conversation').append(pending);
  pending.scrollIntoView({block:'nearest'});
  try {
    const response = await fetch('/api/chat', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,mode,topic_key:$('#topic').value || null})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Confira o tamanho e o formato da pergunta.');
    renderSources(data.sources || []);
    appendMessage('assistant', data.answer, data);
  } catch (error) {
    appendMessage('assistant', error.message || 'Não foi possível conectar ao servidor local.');
  } finally {
    pending.remove(); busy = false; $('#send').disabled = false; $('#new-chat').disabled = false; $('#message').focus();
  }
}
async function initialize() {
  try {
    const response = await fetch('/api/status');
    if (!response.ok) throw new Error('status');
    state = await response.json();
    $('#doc-count').textContent = state.documents.length;
    $('#chunk-count').textContent = state.chunks.toLocaleString('pt-BR');
    $('#connection-status').textContent = !state.indexed ? 'Base não indexada' : state.llm_configured ? 'API configurada' : 'Busca local disponível';
    if (state.llm_configured) setMode('chat');
    $('#document-list').replaceChildren();
    for (const doc of state.documents) {
      const anchor = element('a','document-item');
      anchor.href = `/documents/${encodeURIComponent(doc.document_id)}/pdf`;
      anchor.target = '_blank'; anchor.rel = 'noopener noreferrer';
      anchor.append(element('span','doc-icon','▤'));
      const label = element('div','');
      label.append(element('strong','',doc.title), element('small','',`${doc.total_pages} páginas · PDF`));
      anchor.append(label); $('#document-list').append(anchor);
    }
  } catch (_) { $('#connection-status').textContent = 'Servidor indisponível'; }
}
$('#chat-form').addEventListener('submit',submit);
$('#message').addEventListener('keydown',event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); submit();} });
$('#new-chat').addEventListener('click',() => { if (!busy) location.reload(); });
for (const button of document.querySelectorAll('[data-question]')) button.addEventListener('click',()=> {$('#message').value = button.dataset.question; submit();});
$('#mode-chat').addEventListener('click',()=>setMode('chat'));
$('#mode-search').addEventListener('click',()=>setMode('search'));
$('#config-button').addEventListener('click',()=>$('#config-dialog').showModal());
$('#close-dialog').addEventListener('click',()=>$('#config-dialog').close());
$('#dialog-ok').addEventListener('click',()=>$('#config-dialog').close());
initialize();
