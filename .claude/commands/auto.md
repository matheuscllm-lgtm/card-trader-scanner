---
description: Modo autônomo — executa a tarefa ponta a ponta (corrige, integra, testa, commita, abre PR draft, mergeia só quando trivialmente seguro) sem pedir confirmação, salvo risco alto. Checkpoints frequentes.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, Task, TaskCreate, TaskUpdate, TaskList, WebFetch, WebSearch, mcp__github__push_files, mcp__github__create_pull_request, mcp__github__list_branches, mcp__github__create_branch, mcp__github__get_file_contents, mcp__github__list_commits, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__update_pull_request, mcp__github__actions_list, mcp__github__actions_get, mcp__github__subscribe_pr_activity, mcp__github__add_issue_comment
---

Você foi acionado pelo comando **`/auto`** (modo autônomo) do operador.

**Argumento recebido (objetivo da rodada, se houver):** `$ARGUMENTS`

A partir de agora, opere em **modo autônomo** sobre a tarefa em foco (o que vier
em `$ARGUMENTS`, ou, se vazio, a tarefa que já está na mesa). Este arquivo é o
contrato. Adote-o até a entrega estar completa.

---

## 0. Pré-voo (obrigatório — antes de qualquer ação)

Execute estes passos na ordem, em paralelo onde possível:

1. **Identifica o repo atual**: leia o `CLAUDE.md` do repo para invariantes e o
   comando de teste correto (cada scanner tem o seu — não assuma `pytest` cegamente).
2. **Verifica handoff**: se existir `SESSION-HANDOFF.md` na raiz, leia antes de
   agir — é a continuação canônica. Ausência em clone limpo é esperada, não é erro.
3. **Confirma a branch de trabalho**: a sessão já define a branch (`claude/…` no
   system prompt). Nunca assuma `main`. Se a branch não existir localmente,
   crie com `git checkout -b <branch>` e `git push -u origin <branch>`.
4. **Ambiente (nuvem)**: `gh` CLI **NÃO está disponível** neste container — use as
   ferramentas `mcp__github__*` para todas as operações GitHub (criar PR, listar
   branches, verificar CI). `git push -u origin <branch>` via Bash ainda funciona
   para o push em si.

---

## 1. O que o modo autônomo faz

- **Executa ponta a ponta até entregar completo**: pode corrigir, limpar,
  integrar, aprimorar, implementar, testar, commitar, abrir PR (draft) e
  **mergear quando trivialmente seguro**.
- **Trabalha por checkpoints**: faça commits atômicos com frequência (a cada
  unidade lógica concluída, ~a cada 10 min de progresso). Nunca acumule horas de
  trabalho sem commitar — checkpoint é o que garante que nada se perde.
- **Usa as ferramentas úteis sem pedir licença pra cada uma**: GitHub (via
  `mcp__github__*`), APIs de preço, web (WebFetch/WebSearch), subagentes (Agent).
- **Tarefa multi-repo**: se a mudança toca mais de um scanner, cria commit + PR
  em CADA repo afetado e lista todos no resumo final.

## 2. Quando agir sozinho (NÃO pedir confirmação)

Mudanças de **baixo risco**: código, testes, documentação, refactor, rodar um
scan de leitura, abrir PR draft. Apenas faça, e relate no resumo final.

## 3. Quando PARAR e perguntar (risco alto — exceções duras)

Pare e confirme com o operador (via `AskUserQuestion`) **antes** de qualquer:

- **Perda de dados** — apagar/sobrescrever arquivo que você não criou,
  `git reset --hard`, `push --force`, deletar branch/repo, `rm` largo.
- **Segredo/credencial** — expor, commitar, logar ou rotacionar uma chave.
- **Custo relevante** — chamadas pagas em volume (LLM/API) que pesem.
- **Decisão irreversível** — merge que apaga trabalho, release público,
  mudança que muda comportamento de produção de forma difícil de desfazer.

Na dúvida entre "baixo" e "alto" risco, trate como alto.

## 4. Política de merge (ambiente de nuvem)

- O **padrão deste ambiente é PR como DRAFT**. Ao terminar e dar push, **sempre
  crie um PR draft** via `mcp__github__create_pull_request` se ainda não existir.
- **Mergear sozinho só mudança trivialmente segura** (doc, teste verde isolado).
  Qualquer coisa com peso: deixe o PR pronto, com resumo, e **aponte pro
  operador decidir** — não mergeie.
- Antes de mergear/abrir PR: **revise o diff**, **rode os checks possíveis** e
  **varra por segredos**.

## 5. Validação por segundo agente (honestidade)

Em decisão **ambígua ou arriscada**, spawne um subagente (Agent) pra revisar
antes de seguir. **Seja honesto sobre o limite**: um subagente seu **não é um
revisor independente de verdade** — serve pra pegar erro óbvio, não vale como
carimbo. Em **risco alto**, prefira **esperar o operador** a confiar no
subagente.

## 6. Contexto longo / compactação (honestidade)

**Você NÃO consegue disparar `/compact` sozinho** — é comando do operador. O que
você **garante** é manter tudo **commitado/checkpointado**, de modo que uma
compactação automática **nunca perca trabalho**. Se notar o contexto apertando,
**avise o operador** pra rodar `/compact`; depois retome o objetivo original sem
pedir confirmação.

## 7. Invariantes que o modo autônomo NUNCA quebra

- **Respeite o `CLAUDE.md` do repo**: margem **BRUTA 30%**, **NM-only** (match
  exato `== "NM"`), **nunca inventar preço** (fonte falhou → fallback rotulado),
  **entrega = tabela markdown no chat** gerada pela ferramenta do repo (nunca
  arquivo por padrão).
- **Outputs de scan são gitignored de propósito** (`results/*.xlsx`,
  `results/*.md`, `outputs/`): NUNCA commite dados de scan — só código e doc.
- **Desenvolva na branch designada** da sessão; **nunca** dê push direto na
  `main`.
- **Nunca** commite segredo/chave.
- **Comando de teste varia por scanner**: sempre leia o `CLAUDE.md` do repo —
  não assuma `pytest` sem verificar.

## 8. Encerramento (obrigatório)

Termine **sempre** com um resumo curto e honesto:

- o que foi feito;
- **repos e branches** afetados;
- commits/PRs criados (com links);
- testes rodados e **resultado real** (se algo falhou ou foi pulado, diga);
- merges feitos;
- riscos e pendências em aberto.
