#!/usr/bin/env bash
# Despliegue simple en AWS Academy (Learner Lab): API (Lambda + API Gateway + DynamoDB + S3) y front en un bucket S3.
# Idempotente: se puede volver a correr para actualizar la API, los datos o el front.
#
# Requisitos: AWS CLI v2 con las credenciales del Learner Lab (aws sts get-caller-identity), Python 3, Node 20+.
# Uso (desde la raíz del repo):  bash scripts/desplegar_lab.sh
# Variables opcionales: STACK (default ambulatorio-hlf), REGION (default us-east-1), DATA_DIR (default data), MODEL_ID.
set -euo pipefail

STACK="${STACK:-ambulatorio-hlf}"
REGION="${REGION:-us-east-1}"
DATA_DIR="${DATA_DIR:-data}"
MODEL_ID="${MODEL_ID:-}"
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

CUENTA="$(aws sts get-caller-identity --query Account --output text)"
ROL="arn:aws:iam::${CUENTA}:role/LabRole"
ARTEFACTOS="ambulatorio-hlf-artefactos-${CUENTA}"
echo "▶ Cuenta ${CUENTA} · región ${REGION} · stack ${STACK}"

for f in perfiles.json agenda_box.csv citaciones.csv; do
  [ -f "${DATA_DIR}/${f}" ] || { echo "Falta ${DATA_DIR}/${f} (copie el dataset del HLF en ${DATA_DIR}/)"; exit 1; }
done

echo "▶ 1/5 Bucket de artefactos"
aws s3api head-bucket --bucket "$ARTEFACTOS" 2>/dev/null || aws s3 mb "s3://${ARTEFACTOS}" --region "$REGION"

echo "▶ 2/5 API (CloudFormation con la transformación SAM, rol LabRole)"
rm -rf lambda/__pycache__
aws cloudformation package --template-file template-lab.yaml --s3-bucket "$ARTEFACTOS" \
  --output-template-file /tmp/ambulatorio-hlf-empaquetado.yaml --region "$REGION" >/dev/null
aws cloudformation deploy --template-file /tmp/ambulatorio-hlf-empaquetado.yaml --stack-name "$STACK" --region "$REGION" \
  --capabilities CAPABILITY_AUTO_EXPAND --no-fail-on-empty-changeset \
  --parameter-overrides "RoleArn=${ROL}" "ModelId=${MODEL_ID}"

salida() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
API_URL="$(salida ApiUrl)"; DATA_BUCKET="$(salida DataBucket)"; WEB_BUCKET="$(salida WebBucket)"; WEB_URL="$(salida WebUrl)"

echo "▶ 3/5 Datos del HLF → s3://${DATA_BUCKET} (privado)"
python3 scripts/generar_box.py "$DATA_DIR" >/dev/null
aws s3 cp "${DATA_DIR}/perfiles.json" "s3://${DATA_BUCKET}/perfiles.json" --region "$REGION" --only-show-errors
aws s3 cp "${DATA_DIR}/box.json" "s3://${DATA_BUCKET}/box.json" --region "$REGION" --only-show-errors

echo "▶ 4/5 Front → s3://${WEB_BUCKET}"
( cd front && npm ci --silent && VITE_API_URL="$API_URL" npm run build --silent )
aws s3 sync front/dist "s3://${WEB_BUCKET}" --delete --region "$REGION" --only-show-errors \
  --cache-control "public,max-age=31536000,immutable" --exclude index.html
aws s3 cp front/dist/index.html "s3://${WEB_BUCKET}/index.html" --region "$REGION" --only-show-errors --cache-control "no-cache"

echo "▶ 5/5 Verificación"
curl -fsS "${API_URL}/health" && echo
echo
echo "API:   ${API_URL}"
echo "Front: ${WEB_URL}"
