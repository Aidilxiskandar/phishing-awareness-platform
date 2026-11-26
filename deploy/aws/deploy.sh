#!/usr/bin/env bash
# Create or update the PhishGuard public demo on AWS.
#   DEMO_PASSWORD=... [ALERT_EMAIL=you@example.com] [AWS_REGION=ap-southeast-1] deploy/aws/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

REGION="${AWS_REGION:-ap-southeast-1}"
STACK="${STACK:-phishguard-demo}"
: "${DEMO_PASSWORD:?set DEMO_PASSWORD (shown publicly on the demo sign-in page)}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${STACK}-code-${ACCOUNT}-${REGION}"

if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

# Ship exactly the committed code (no .env, databases or local files).
git archive --format=tar.gz HEAD | aws s3 cp - "s3://$BUCKET/phishguard.tar.gz" --region "$REGION"

aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/aws/phishguard-demo.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides CodeBucket="$BUCKET" DemoPassword="$DEMO_PASSWORD" \
    AlertEmail="${ALERT_EMAIL:-}" --no-fail-on-empty-changeset

aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query 'Stacks[0].Outputs' --output table
echo "First boot builds the image and seeds demo data: allow ~10 minutes before the URL answers."
