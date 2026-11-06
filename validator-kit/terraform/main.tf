# A proof-of-fix validator in your own AWS account (proof-of-fix#104).
#
# Idle, it costs almost nothing: a stopped Graviton instance (you pay for its disk), a watcher Lambda that runs once a
# minute, and an SSM parameter. When a sealed submission appears on the chain the watcher starts the instance; the node
# fetches the fix, runs its tests in a sandbox with no network (Docker), asks your model, signs its verdict, and the
# instance powers itself off when there's no work left.
#
# Why an EC2 instance and not Fargate: the sandbox runs each fix's tests in a container with no network (rule 4), which
# needs a Docker daemon; Fargate has none, and containers in one Fargate task share a network. Nitro Enclaves (the
# attested node, later) also run on EC2 only.

locals {
  tags = merge({ "pof:component" = "validator", "pof:validator" = var.validator_address }, var.tags)

  secret_arns = compact([
    aws_secretsmanager_secret.validator_key.arn,
    var.rpc_api_key_secret_arn,
    var.repo_token_secret_arn,
    var.model_provider == "api" ? var.model_api_key_secret_arn : "",
  ])
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ---------- The validator's signing key ----------

# Created empty: you generate the key yourself and put it here (runbook), so it never passes through Terraform or its
# state. The node reads it at start-up, in memory only. KMS signing (secp256k1 keys that never leave KMS) is a follow-up.
resource "aws_secretsmanager_secret" "validator_key" {
  name                    = "${var.name}/signing-key"
  description             = "proof-of-fix validator signing key (hex secp256k1); written by the operator, never by Terraform"
  recovery_window_in_days = 7
  tags                    = local.tags
}

# ---------- The watcher's state ----------

resource "aws_ssm_parameter" "last_block" {
  name        = "/${var.name}/last-block"
  description = "The watcher's scan: the last block, and the won bounties awaiting their merge"
  type        = "String"
  value       = "none"
  tags        = local.tags

  lifecycle {
    ignore_changes = [value] # the watcher owns it
  }
}

# ---------- Logs ----------

resource "aws_cloudwatch_log_group" "watcher" {
  name              = "/aws/lambda/${var.name}-watcher"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

resource "aws_cloudwatch_log_group" "node" {
  name              = "/${var.name}/node"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

# ---------- Money ----------

resource "aws_budgets_budget" "monthly" {
  count        = var.budget_limit_usd > 0 ? 1 : 0
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = length(var.budget_emails) > 0 ? [["ACTUAL", 80], ["FORECASTED", 100]] : []
    content {
      comparison_operator        = "GREATER_THAN"
      notification_type          = notification.value[0]
      threshold                  = notification.value[1]
      threshold_type             = "PERCENTAGE"
      subscriber_email_addresses = var.budget_emails
    }
  }
}

# The budget's stop (budget_stop): an alert doesn't stop a bill. At 100 % actual, AWS Budgets attaches this policy to the
# node's and the watcher's roles: no model call on Bedrock, and no new start (which also stops a model reached by API key,
# since the node runs only when started). Attaching it is all this does: reverse it with the runbook's command.
locals {
  budget_stop = var.budget_stop && var.budget_limit_usd > 0 && length(var.budget_emails) > 0
}

data "aws_iam_policy_document" "budget_stop" {
  count = local.budget_stop ? 1 : 0

  statement {
    sid       = "NoSpending"
    effect    = "Deny"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream", "ec2:StartInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "budget_stop" {
  count       = local.budget_stop ? 1 : 0
  name        = "${var.name}-budget-stop"
  description = "Attached by the budget's action at 100 %: stops the validator's spending"
  policy      = data.aws_iam_policy_document.budget_stop[0].json
  tags        = local.tags
}

data "aws_iam_policy_document" "budget_action_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "budget_action" {
  count              = local.budget_stop ? 1 : 0
  name               = "${var.name}-budget-action"
  assume_role_policy = data.aws_iam_policy_document.budget_action_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "budget_action" {
  count = local.budget_stop ? 1 : 0

  statement {
    sid       = "AttachTheStopToTheseRolesOnly"
    actions   = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
    resources = [aws_iam_role.node.arn, aws_iam_role.watcher.arn]
    condition {
      test     = "ArnEquals"
      variable = "iam:PolicyARN"
      values   = [aws_iam_policy.budget_stop[0].arn]
    }
  }
}

resource "aws_iam_role_policy" "budget_action" {
  count  = local.budget_stop ? 1 : 0
  name   = "attach-the-stop"
  role   = aws_iam_role.budget_action[0].id
  policy = data.aws_iam_policy_document.budget_action[0].json
}

resource "aws_budgets_budget_action" "stop" {
  count              = local.budget_stop ? 1 : 0
  budget_name        = aws_budgets_budget.monthly[0].name
  action_type        = "APPLY_IAM_POLICY"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budget_action[0].arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    iam_action_definition {
      policy_arn = aws_iam_policy.budget_stop[0].arn
      roles      = [aws_iam_role.node.name, aws_iam_role.watcher.name]
    }
  }

  dynamic "subscriber" {
    for_each = toset(var.budget_emails)
    content {
      address           = subscriber.value
      subscription_type = "EMAIL"
    }
  }
}
