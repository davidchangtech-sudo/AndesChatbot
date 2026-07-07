#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BUCKET="${S3_BUCKET:-andes-ai-demo-978022759900}"
REGION="${AWS_REGION:-us-east-1}"
STACK="${STACK_NAME:-andes-chatbot-s3-demo}"

python3 scripts/build_s3_demo.py
aws sts get-caller-identity
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file infra/s3-static-demo.yaml \
  --parameter-overrides "BucketName=${BUCKET}" \
  --region "$REGION" \
  --no-fail-on-empty-changeset
aws s3 sync s3-demo/ "s3://${BUCKET}/" --delete --region "$REGION"
URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='WebsiteURL'].OutputValue" --output text)
echo "$URL" | tee S3_DEMO_URL.txt
echo "Live: $URL"
