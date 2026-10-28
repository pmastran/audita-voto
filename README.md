# Audita Voto — GitHub Pages + Supabase + GitHub Actions

Versão de hobby **sem dependência da Lovable**. Mantém a interface visual da V1 e o mesmo parser Python; adapta a hospedagem para site estático e a auditoria para uma rotina manual, reprodutível e auditável.

## Princípio central

**Nenhum dado eleitoral fictício na interface ou nos relatórios publicados.** Todos os números são calculados a partir de arquivos oficiais do TSE. A rotina descobre o recurso pelo catálogo CKAN, faz download do domínio `cdn.tse.jus.br`, confere o SHA-512 com o arquivo publicado pelo TSE, processa os CSVs e salva um relatório com origem e parâmetros. Se faltar um dado ou ocorrer erro, a rotina falha sem apresentar relatório.

A interface pública **não dispara uma nova auditoria**. Ela consulta relatórios previamente publicados. O operador pode executar novos recortes em `GitHub → Actions → Auditar boletins oficiais do TSE → Run workflow`, definindo UF, turno e filtros. Depois pode recarregar o site e consultar o mesmo recorte.

## Arquitetura

- `public/`: site estático, compatível com GitHub Pages em subcaminho `/<repositorio>/`.
- `.github/workflows/pages.yml`: publica gratuitamente o site, usando apenas URL e chave **publishable** do Supabase.
- `.github/workflows/sincronizar-catalogo.yml`: consulta API CKAN e salva o catálogo no Supabase.
- `.github/workflows/auditar.yml`: executa o motor Python oficial do TSE e salva o relatório validado.
- `audita/`: parser e regras herdados da V1; não aceitam fonte de votos de terceiros.
- `supabase/schema.sql`: tabelas `av_catalogos` e `av_relatorios` com RLS; leitura pública, escrita restrita à chave do serviço em Actions.

## Implantação, sem mexer em outros projetos

1. Crie um **novo repositório público vazio** `audita-voto` no GitHub `pmastran`. [Criar repositório](https://github.com/new). Não marque README/license, pois o projeto já contém README.
2. Descompacte este pacote, faça `git init`, `git branch -M main`, `git add .`, `git commit -m "Audita Voto"`, `git remote add origin https://github.com/pmastran/audita-voto.git`, `git push -u origin main`. Ou peça para o assistente subir os arquivos ao repo vazio quando criado.
3. Crie **um projeto Supabase exclusivo** para o Audita Voto (Free, se houver vaga) e execute `supabase/schema.sql` no SQL Editor desse projeto. Não reutilize projetos que contêm dados de outros aplicativos.
4. No GitHub, vá em `Settings → Secrets and variables → Actions → Variables` e cadastre `AUDITA_SUPABASE_URL` (Project URL) e `AUDITA_SUPABASE_PUBLISHABLE_KEY` (chave publishable; ou anon legada). Elas são públicas por natureza, mas não devem permitir escrita nas tabelas.
5. Em `Actions → Secrets`, cadastre `AUDITA_SUPABASE_SERVICE_ROLE_KEY` (chave **service role/secret**) fornecida pelo Supabase. **Jamais** coloque essa chave em `public/`, em arquivo commitado ou no front-end.
6. No repositório, habilite GitHub Pages com fonte **GitHub Actions** em `Settings → Pages`. Na aba `Actions`, rode `Publicar Audita Voto (GitHub Pages)`.
7. Rode `Sincronizar catálogo oficial do TSE` manualmente. Depois selecione um boletim disponível e rode `Auditar boletins oficiais do TSE` com os mesmos parâmetros escolhidos no site. Para visualizar, abra `https://pmastran.github.io/audita-voto/` **após** o primeiro deploy ter sido confirmado. Esse endereço é apenas previsto; não está publicado até a implantação real.

**Atenção aos limites:** ZIP acima de 60 MiB compactados é rejeitado nesta versão; aumente apenas após testar limite de memória/tempo. Relatórios apenas após execução manual do GitHub Actions. Auditorias entre turnos, CPFs, identidade de eleitores e comparação documental com consolidados ainda não estão implementadas. O Free do Supabase pode pausar por inatividade e tem limite de espaço. A rotina Actions pode ter cotas de execução. Não há cobrança automática configurada pelo projeto.

## Testar localmente

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py
python3 -m http.server --directory _site 8080
```

Se as configurações do Supabase ainda não foram fornecidas, o site abre com estado vazio e **não inventa dados**. O código antigo `server.py` e `deploy.sh` continuam incluídos apenas para preservar a alternativa Cloud Run; o GitHub Pages não usa essas rotas.

## Fontes oficiais

- <https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna>
- <https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna>
- <https://dadosabertos.tse.jus.br/dataset/resultados-2026>

Resultados iguais não implicam irregularidade. Hash coincidente comprova correspondência de arquivo ao resumo publicado, não certifica todo o sistema eleitoral.
