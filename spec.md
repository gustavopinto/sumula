# projectbrief.md

Construtor de Súmula Curricular FAPESP a partir de múltiplas fontes, com saída em Markdown e envio por e mail via MailerSend.

Referência do formato e regras da súmula FAPESP. ([FAPESP][1])

## 1. Objetivo

1. Receber arquivos e links que descrevem a trajetória acadêmica de uma pessoa.
2. Extrair texto com bibliotecas, limpar e curar o conteúdo em TXT estruturado.
3. Gerar a Súmula Curricular no formato FAPESP em Markdown usando LLM apenas sobre TXT curado.
4. Enviar o Markdown por e mail via MailerSend de forma assíncrona, sem cadastro.

## 2. Não objetivos

1. Não exigir login.
2. Não delegar parsing de PDF para a LLM.
3. Não garantir extração de PDFs escaneados no MVP.
4. Não executar scraping agressivo de Google Scholar no MVP.

## 3. Regras do formato FAPESP

### 3.1 Cabeçalho obrigatório

O Markdown deve iniciar com os campos abaixo. ([FAPESP][1])

1. Nome
2. Orcid, obrigatório, com link
3. Currículo Lattes, com link
4. Web of Science, com link
5. MyCitation Google Scholar, com link

### 3.2 Seções obrigatórias

A súmula deve conter seis seções, nesta ordem, e todas devem ser preenchidas, mesmo que com “NADA A DECLARAR”. ([FAPESP][1])

1. Formação
2. Histórico Profissional Acadêmico
3. Contribuições à Ciência
4. Financiamentos à Pesquisa
5. Indicadores Quantitativos
6. Outras Informações Relevantes

### 3.3 Subitens que o template deve suportar

1. 1.1 Formação, Informações Adicionais ([FAPESP][1])
2. 6.a Informações biográficas dos últimos dez anos ([FAPESP][1])
3. 6.b Experiência internacional após doutorado ([FAPESP][1])
4. 6.c Prêmios, distinções, honrarias ([FAPESP][1])

## 4. Entradas

### 4.1 Upload de arquivos

Tipos aceitos no MVP:

1. PDF
2. XLS, XLSX
3. TXT, MD
4. PDF adicional

Limites:

1. Tamanho máximo por arquivo via env
2. Quantidade máxima de arquivos por submissão via env

### 4.2 URLs

Campos:

1. Lattes
2. ORCID
3. DBLP
4. Google Scholar
5. Web of Science
6. Site pessoal

Regra de Scholar:

1. MVP aceita BibTeX colado como entrada primária, além de URL, para reduzir falhas

### 4.3 Texto livre

Campo para:

1. Correções e preferências do usuário
2. Destaques que o usuário quer ver em Contribuições
3. Informações ausentes nas fontes

## 5. Saída

1. Markdown final da súmula, arquivo `sumula.md`
2. Envio por e mail via MailerSend com anexo `sumula.md` e corpo com texto quando couber

## 6. UX

### 6.1 Página principal

Componentes:

1. Campo e mail obrigatório
2. Upload múltiplo
3. Campos de links
4. Campo BibTeX opcional
5. Campo texto livre
6. Botão para gerar

Após submit:

1. Mostrar mensagem de processamento assíncrono e envio por e mail
2. Exibir Job ID e link de status

### 6.2 Página de status

1. Exibir estado atual do job
2. Exibir eventos por etapa
3. Não exibir conteúdo dos documentos

Estados:

1. RECEIVED
2. EXTRACTING
3. CURATING
4. ENRICHING
5. GENERATING
6. VALIDATING
7. SENDING_EMAIL
8. DONE
9. ERROR

## 7. Arquitetura

## 7.1 Componentes

1. Web app em Python com FastAPI
2. Worker assíncrono em Python
3. Redis para fila
4. Postgres para jobs, eventos e artefatos
5. Storage local no Fly volume para arquivos do job

### 7.2 Deploy Fly.io

1. Processo web
2. Processo worker
3. Redis
4. Postgres

## 8. Contratos internos

### 8.1 Input manifest

JSON persistido por job:

1. arquivos com nome, tipo, hash, path
2. urls por tipo
3. bibtex colado quando informado
4. texto livre
5. locale, default pt BR

### 8.2 TXT curado

Regra central:

1. A LLM só recebe o TXT curado, nunca recebe PDF, XLSX, HTML bruto

Formato obrigatório:

1. META

   1. job_id
   2. created_at
   3. locale
2. IDENTIFIERS

   1. nome
   2. orcid
   3. lattes_url
   4. dblp_url
   5. scholar_url
   6. wos_url
   7. site_url
3. RAW_BLOCKS

   1. FORMACAO_RAW
   2. HISTORICO_RAW
   3. CONTRIBUICOES_RAW
   4. FINANCIAMENTOS_RAW
   5. INDICADORES_RAW
   6. OUTRAS_RAW
4. EVIDENCE
   Linhas no formato:

   1. `EVID <id> | SRC=<source_id> | LOC=<page_or_row> | TEXT=<snippet>`

Regras do curador:

1. Remover duplicatas por hash de sentença
2. Normalizar datas para mês e ano quando houver
3. Preservar rastreabilidade em EVID para trechos usados

### 8.3 Markdown final

Regras do gerador:

1. Cabeçalho com os cinco links
2. Seções 1 a 6 na ordem FAPESP ([FAPESP][1])
3. Subitens 1.1 e 6.a 6.b 6.c ([FAPESP][1])
4. Seções sem dados devem conter “NADA A DECLARAR” ([FAPESP][1])
5. Markdown estrito, sem HTML

## 9. Pipeline

### 9.1 Extração

1. PDF

   1. Extrair texto com PyMuPDF ou pdfplumber
   2. Registrar origem por página
2. XLSX

   1. Ler com pandas e openpyxl
   2. Registrar origem por aba e linha
3. Site pessoal

   1. Extrair texto principal com trafilatura
4. DBLP

   1. Preferir export BibTeX quando disponível
   2. Fallback: extrair HTML e converter em texto
5. Scholar

   1. Preferir BibTeX colado
   2. Se só URL, registrar link e seguir sem falhar

### 9.2 Curadoria determinística

1. Remover cabeçalhos e rodapés repetidos por frequência
2. Remover quebras de linha artificiais
3. Normalizar espaços e bullets
4. Detectar blocos por padrões de seção
5. Gerar EVIDs com localização

### 9.3 Enriquecimento

1. Consolidar publicações duplicadas por título normalizado e ano
2. Calcular contagens para indicadores quando possível
3. Registrar evidências para itens agregados

### 9.4 Geração via LLM

Entrada:

1. Instruções fixas
2. Template alvo em Markdown no modelo FAPESP ([FAPESP][1])
3. TXT curado

Regras:

1. Não inventar dados ausentes
2. Preencher todas as seções
3. Respeitar limites do template quando houver
4. Justificar itens em Contribuições usando evidências

### 9.5 Validação e reparo

Validações:

1. Seis seções presentes e na ordem ([FAPESP][1])
2. Nenhuma seção vazia
3. Subitens 1.1 e 6.a 6.b 6.c presentes
4. Cabeçalho com ORCID e links

Reparo:

1. Se falhar, rodar etapa de correção usando apenas o Markdown gerado e a lista de erros, sem documentos brutos

## 10. API e rotas

### 10.1 Rotas web

1. GET /
2. POST /submit
3. GET /status/{job_id}

### 10.2 Rotas internas

1. GET /api/jobs/{job_id}/events
2. POST /api/jobs/{job_id}/retry

## 11. Worker

1. Executar pipeline por job
2. Persistir eventos por etapa
3. Atualizar status do job
4. Gerar artefatos e registrar no banco
5. Enviar e mail via MailerSend

Retentativas:

1. Backoff em chamadas externas
2. Limites por etapa via env

## 12. Persistência

### 12.1 Tabelas

1. jobs

   1. id
   2. email
   3. status
   4. created_at
   5. updated_at
   6. error_code
   7. error_message
   8. input_manifest_json
   9. output_manifest_json
2. artifacts

   1. id
   2. job_id
   3. kind, raw_file, extracted_txt, curated_txt, output_md
   4. path
   5. sha256
   6. size_bytes
   7. created_at
3. events

   1. id
   2. job_id
   3. step
   4. message
   5. created_at

## 13. Integração MailerSend

### 13.1 Config

Env vars:

1. MAILERSEND_API_KEY
2. MAILERSEND_FROM_EMAIL
3. MAILERSEND_FROM_NAME

### 13.2 Envio

1. Assunto: Súmula Curricular FAPESP em Markdown
2. Corpo: status final, resumo das fontes usadas, job_id
3. Anexo: `sumula.md`

## 14. Configuração

Env vars:

1. OPENAI_API_KEY
2. OPENAI_MODEL
3. OPENAI_MAX_TOKENS
4. REDIS_URL
5. DATABASE_URL
6. MAX_UPLOAD_MB
7. MAX_FILES
8. WORKDIR_PATH
9. MAILERSEND_API_KEY
10. MAILERSEND_FROM_EMAIL
11. MAILERSEND_FROM_NAME

## 15. Segurança

1. Sanitizar HTML do site pessoal
2. Validar MIME type e extensão no upload
3. Logs sem conteúdo de documentos
4. Rate limit por IP em /submit

## 16. Observabilidade

1. Logs estruturados por job_id
2. Eventos por etapa persistidos
3. Métricas básicas, contagem por status e duração por etapa

## 17. Critérios de aceite

1. Submeter URL Lattes e receber e-mail com `sumula.md` com as seis seções ([FAPESP][1])
2. Submeter Lattes XLSX e receber e mail com `sumula.md` com as seis seções ([FAPESP][1])
3. Seção vazia vira “NADA A DECLARAR” ([FAPESP][1])
4. 6.a 6.b 6.c presentes em Outras Informações Relevantes ([FAPESP][1])
5. Processamento assíncrono com status page
6. LLM opera apenas sobre TXT curado

## 18. Prompt contract

### 18.1 System prompt

1. Você gera somente Markdown.
2. Você usa somente o TXT curado fornecido.
3. Se não houver evidência, escreva “NADA A DECLARAR” na seção aplicável.
4. Preserve a estrutura FAPESP com seções 1 a 6 e subitens 1.1 e 6.a 6.b 6.c. ([FAPESP][1])

### 18.2 Output constraints

1. Não incluir HTML
2. Não incluir links não informados no TXT curado
3. Não inventar números de indicadores
4. Não criar seções fora do template

[1]: https://fapesp.br/sumula?utm_source=chatgpt.com "Roteiro para elaboração da Súmula Curricular"
