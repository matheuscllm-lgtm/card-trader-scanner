# Checklist manual — tornar o repositório público (discreto)

> Tudo que o Claude **não** consegue fazer por você (mudanças de configuração no
> site do GitHub). Faça **nesta ordem**. O objetivo é reduzir descoberta casual —
> **não** é segurança real: qualquer pessoa com o link verá tudo.
>
> ⚠️ **Antes de virar público:** confirme que o PR de preparação já foi mergeado
> no `main` (ele tira os dados de deal do repositório e neutraliza o README).

## 0. Pré-checagem (1 min)

- [ ] O PR `chore/prepare-public-release` está **mergeado** no `main`.
- [ ] Os branches `scan-live` e `claude/keen-faraday-*` **não existem mais**
      (o Claude tentou apagá-los; se sobraram, rode no seu terminal):
      ```bash
      git push origin --delete scan-live
      git push origin --delete claude/keen-faraday-w3bq9j
      ```

## 1. Renomear o repositório (nome menos óbvio)

- [ ] `Settings → General → Repository name` → trocar `Card-trader-scanner`
      por algo neutro, ex.: `price-compare-tool` ou `pc-utils`.
- [ ] (O GitHub cria redirect do nome antigo; se quiser cortar isso, evite usar
      o nome antigo em links públicos.)
- [ ] Atualizar o `git remote` local depois:
      ```bash
      git remote set-url origin https://github.com/matheuscllm-lgtm/<novo-nome>.git
      ```

## 2. Remover description e topics

- [ ] Na página inicial do repo → engrenagem ⚙️ ao lado de "About".
- [ ] Apagar a **Description**.
- [ ] Apagar todos os **Topics** (tags).
- [ ] Desmarcar "Use your GitHub Pages website" e "Releases/Packages" se marcados.

## 3. Desligar features que criam superfície pública

- [ ] `Settings → General → Features`:
  - [ ] **Issues** → desligar.
  - [ ] **Wikis** → desligar.
  - [ ] **Discussions** → desligar.
  - [ ] **Projects** → desligar.
- [ ] `Settings → Pages` → Source = **None** (confirmar que Pages está desligado).

## 4. Conferir secrets de CI (antes de publicar)

- [ ] `Settings → Secrets and variables → Actions` → confirmar que existem
      `CT_JWT` e `POKEMONTCG_API_KEY` (necessários só para os workflows de scan;
      o workflow de testes **não** usa secret).
- [ ] Lembre: em repo **público**, os **logs e artifacts** de cada run dos
      workflows de scan ficam baixáveis por qualquer um que achar o repo. Para
      resultados realmente privados, rode o scan **local** (venv + .env), não no
      Actions.

## 5. Tornar público

- [ ] `Settings → General → Danger Zone → Change repository visibility`
      → **Make public** → confirmar digitando o nome.

## 6. Validar que o Actions roda de graça

- [ ] Aba **Actions** → workflow **tests** deve rodar sozinho no próximo push/PR
      (ou rode via "Run workflow") e ficar **verde**, em runner `ubuntu-latest`.
- [ ] `Settings → Billing` → confirmar que minutos de Actions de repo público
      **não** consomem cota paga (são gratuitos).

## 7. Pós-publicação (higiene)

- [ ] Rotacionar o `CT_JWT` se houver qualquer dúvida sobre exposição passada
      (gerar novo token em CardTrader → Settings → API Access; atualizar o
      secret e o `.env` local).
- [ ] Conferir a aba **Actions → artifacts** e apagar artifacts antigos de scan
      que tenham ficado de runs anteriores (eles contêm deals).
