#!/usr/bin/env bash
# Implantacao direta, independente de Lovable. Executar no Google Cloud Shell.
set -euo pipefail
if ! command -v gcloud >/dev/null 2>&1; then
  echo "ERRO: gcloud nao encontrado. Execute no Google Cloud Shell." >&2
  exit 1
fi
PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERRO: configure o projeto: gcloud config set project SEU_PROJETO" >&2
  exit 1
fi
REGION="${REGION:-southamerica-east1}"
SERVICE="audita-voto"
echo "Projeto: $PROJECT_ID | Regiao: $REGION | Servico: $SERVICE"
read -r -p "Confirmar deploy em $PROJECT_ID, com possiveis custos Cloud Run/Cloud Build? [s/N] " response
if [[ "${response,,}" != "s" ]]; then
  echo "Implantacao cancelada sem alteracoes."
  exit 0
fi
TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
# --source usa o Dockerfile deste projeto. Publico para visualizacao; auditoria protegida por token.
gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 1Gi \
  --timeout 900 \
  --concurrency 8 \
  --max-instances 1 \
  --set-env-vars "AUDITA_RUN_KEY=$TOKEN,AUDITA_MAX_ZIP_MB=60" \
  --quiet
URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo
printf 'AUDITA VOTO - URL DIRETA:\n%s\n\n' "$URL"
printf 'CHAVE PARA EXECUTAR AUDITORIAS (GUARDE EM LOCAL SEGURO):\n%s\n' "$TOKEN"
echo "A visualizacao do site e do catalogo e publica; somente a execucao de auditorias exige essa chave."
echo "Os resultados ficam na sessao do servidor e podem ser exportados em JSON. Nao ha banco persistente nesta V1."
