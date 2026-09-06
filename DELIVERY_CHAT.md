# Entrega dos scanners — regra vigente do operador (2026-09-06)

Esta regra substitui instruções anteriores de entrega, publicação de resultados
e reutilização de preços. Vale para todos os jogos e perfis deste scanner.

- Rodar uma coleta nova quando o operador solicitar um scan. Não criar execução
  recorrente. Uma análise de código ou formatação não autoriza uma coleta de mercado.
- Entregar a tabela Markdown do gerador canônico diretamente no painel de conversa,
  no padrão MYP Cards: carta com número (ou produto/SKU), compra, referência assumida,
  diferença, métricas econômicas e flags pertinentes, com links da oferta e referência.
- O próprio preço de referência deve ser clicável e apontar à fonte que sustenta
  aquele valor. Mediana e projeção devem ser identificadas, com suas evidências.
  Não substituir fonte ausente por uma busca genérica ou por outra carta.
- Preservar todas as linhas disponíveis e os avisos de revisão/rejeição. Não
  remontar tabelas à mão nem transformar uma ausência de referência em preço zero.
- Não publicar resultados, preços, relatórios ou logs de coleta no GitHub, inclusive
  commits, Pages, releases, issues, comentários, Actions artifacts ou job summaries.
  GitHub pode guardar código e documentação; a entrega dos resultados é só no chat.
- Arquivos locais temporários são apoio de processamento, não a entrega padrão.
  Só anexar arquivos se solicitado. Não usar resultados antigos como preços atuais.
- Em cada nova solicitação, renovar ofertas, referências de preço e câmbio.
  Cache apenas da coleta em andamento ou de metadados estáveis; nunca reutilizar
  preços de outro scan, mesmo no mesmo dia. Um dump atualizado do provedor deve
  ter sua data informada; não prometer cotação em tempo real se a fonte é diária.
- Falha da coleta atual: declarar indisponibilidade/resultado parcial. Nunca
  apresentar um snapshot anterior como se tivesse sido coletado agora.
- Não mudar regras de margem, taxas, moedas ou equivalências para padronizar a tabela.

## Procedimento antes de entregar

1. Fazer a nova coleta solicitada, com saída e caches voláteis próprios desta execução.
2. Gerar a tabela com a ferramenta do repositório, a partir somente dessa execução.
3. Conferir identificação, horário da coleta, preço clicável, fonte e flags.
4. Colar a tabela no chat; se longa, dividir em mensagens preservando todas as linhas.

Para CardTrader usar coleta sem cache de preços; para Liga desativar cache de preços
entre execuções; para MYP não retomar checkpoints de solicitações anteriores.
COMC/eBay devem usar diretório de cache novo por coleta. Selados devem reconstruir
as referências de classificação e coletar novamente as ofertas antes do relatório.
O integrado deve chamar as fontes nesta execução, sem carregar arquivos antigos.
