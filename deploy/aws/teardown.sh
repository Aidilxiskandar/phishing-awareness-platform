#!/usr/bin/env bash
# Delete the demo and everything it created (stops all charges).
set -euo pipefail
REGION="${AWS_REGION:-ap-southeast-1}"
STACK="${STACK:-phishguard-demo}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${STACK}-code-${ACCOUNT}-${REGION}"
aws cloudformation delete-stack --region "$REGION" --stack-name "$STACK"
aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$STACK"
aws s3 rm "s3://$BUCKET" --recursive --region "$REGION" || true
aws s3api delete-bucket --bucket "$BUCKET" --region "$REGION" || true
echo "Removed stack $STACK and bucket $BUCKET."
