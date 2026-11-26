#!/usr/bin/env bash
# Ship the current commit to the running demo (no instance replacement).
set -euo pipefail
cd "$(dirname "$0")/../.."
REGION="${AWS_REGION:-ap-southeast-1}"
STACK="${STACK:-phishguard-demo}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${STACK}-code-${ACCOUNT}-${REGION}"
INSTANCE="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"

git archive --format=tar.gz HEAD | aws s3 cp - "s3://$BUCKET/phishguard.tar.gz" --region "$REGION"
CMD="$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript --comment "phishguard redeploy" \
  --parameters 'commands=["/usr/local/bin/phishguard-redeploy"]' \
  --query Command.CommandId --output text)"
aws ssm wait command-executed --region "$REGION" --command-id "$CMD" --instance-id "$INSTANCE" || true
aws ssm get-command-invocation --region "$REGION" --command-id "$CMD" --instance-id "$INSTANCE" \
  --query '{status:Status,output:StandardOutputContent}' --output json
