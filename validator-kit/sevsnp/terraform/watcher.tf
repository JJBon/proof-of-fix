# The v3 watcher (#251 task 4.9, #253): a Lambda run once a minute that starts the stopped SEV-SNP instance only when
# one of this validator's seats on v3's Panels needs the node (validator-kit/sevsnp/lambda/watcher.py). It exists with
# the instance (create_instance) and runs only with watcher_enabled: off by default, its schedule disabled and its kill
# switch set, so an apply never starts anything by itself.
#
# With node_config's ORACLE_MERGE_VIA = "radicle" (model (a): this validator's Radicle node is a delegate) it also
# starts the instance once each time Heads.head moves (WAKE_ON_HEAD), so the node pushes the canonical `main` even
# when it wasn't drawn for the fix (watcher.py, "The Radicle duty").
#
# Least privilege: it may start this instance and no other (ec2:StartInstances on its ARN), describe instances (no
# resource-level permission exists for that), read and write its own state parameter, write its own logs, read the
# chain's URL or key secret when one is named, and read this kit's budget when its automatic stop is on. Its RPC calls
# are reads only: it holds no key and signs nothing.

locals {
  watcher = var.create_instance ? 1 : 0
  # The chain and the race default to the node's own settings (node_config), so one value serves both.
  watcher_rpc_url       = var.watcher_rpc_url != "" ? var.watcher_rpc_url : lookup(var.node_config, "ORACLE_RPC", "")
  watcher_race          = var.race_address != "" ? var.race_address : lookup(var.node_config, "ORACLE_RACE", "")
  watcher_rpc_key       = var.rpc_api_key_secret_arn != "" ? var.rpc_api_key_secret_arn : lookup(var.node_config, "RPC_API_KEY_SECRET_ARN", "")
  watcher_secrets       = compact([var.rpc_url_secret_arn, local.watcher_rpc_key])
  watcher_budget        = local.budget_stop ? aws_budgets_budget.monthly.name : ""
  watcher_instance_arns = [for i in aws_instance.node : "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/${i.id}"]
}

data "archive_file" "watcher" {
  type        = "zip"
  source_file = "${path.module}/../lambda/watcher.py"
  output_path = "${path.module}/.build/watcher.zip"
}

data "aws_iam_policy_document" "watcher_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "watcher" {
  count              = local.watcher
  name               = "${var.name}-watcher"
  assume_role_policy = data.aws_iam_policy_document.watcher_assume.json
}

resource "aws_ssm_parameter" "watcher_state" {
  count       = local.watcher
  name        = "/${var.name}/watcher/state"
  description = "The v3 watcher's state: the last block scanned, this validator's open seats, the day's starts"
  type        = "String"
  value       = "none"

  lifecycle {
    ignore_changes = [value] # the watcher owns it
  }
}

resource "aws_cloudwatch_log_group" "watcher" {
  count             = local.watcher
  name              = "/aws/lambda/${var.name}-watcher"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "watcher" {
  count = local.watcher

  statement {
    sid       = "State"
    actions   = ["ssm:GetParameter", "ssm:PutParameter"]
    resources = [aws_ssm_parameter.watcher_state[0].arn]
  }

  statement {
    sid       = "DescribeNode"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"] # DescribeInstances has no resource-level permissions
  }

  statement {
    sid       = "StartThisInstanceOnly"
    actions   = ["ec2:StartInstances"]
    resources = local.watcher_instance_arns
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.watcher[0].arn}:*"]
  }

  dynamic "statement" {
    for_each = length(local.watcher_secrets) > 0 ? [1] : []
    content {
      sid       = "ChainUrlOrKey"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = local.watcher_secrets
    }
  }

  dynamic "statement" {
    for_each = local.watcher_budget != "" ? [1] : []
    content {
      sid       = "ReadThisBudget"
      actions   = ["budgets:ViewBudget"]
      resources = ["arn:aws:budgets::${data.aws_caller_identity.current.account_id}:budget/${local.watcher_budget}"]
    }
  }
}

resource "aws_iam_role_policy" "watcher" {
  count  = local.watcher
  name   = "watcher"
  role   = aws_iam_role.watcher[0].id
  policy = data.aws_iam_policy_document.watcher[0].json
}

resource "aws_lambda_function" "watcher" {
  count            = local.watcher
  function_name    = "${var.name}-watcher"
  role             = aws_iam_role.watcher[0].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "watcher.handler"
  filename         = data.archive_file.watcher.output_path
  source_code_hash = data.archive_file.watcher.output_base64sha256
  timeout          = 50 # under the one-minute schedule
  memory_size      = 128

  environment {
    variables = {
      RPC_URL                = var.rpc_url_secret_arn != "" ? "" : local.watcher_rpc_url
      RPC_URL_SECRET_ARN     = var.rpc_url_secret_arn
      RPC_API_KEY_SECRET_ARN = local.watcher_rpc_key
      RPC_API_KEY_HEADER     = var.rpc_api_key_header
      RACE_ADDRESS           = local.watcher_race
      VALIDATOR_ADDRESS      = var.validator_address
      INSTANCE_ID            = aws_instance.node[0].id
      STATE_PARAM            = aws_ssm_parameter.watcher_state[0].name
      ENABLED                = var.watcher_enabled ? "true" : "false"
      MAX_BLOCK_RANGE        = "2000"
      LOOKBACK_BLOCKS        = tostring(var.watcher_lookback_blocks)
      MAX_STARTS_PER_DAY     = tostring(var.max_starts_per_day)
      RETRY_MINUTES          = tostring(var.watcher_retry_minutes)
      SEAT_MAX_STARTS        = tostring(var.seat_max_starts)
      REVEAL_LEAD_SECONDS    = tostring(var.reveal_lead_seconds)
      READY_SECONDS          = tostring(var.ready_seconds)
      UNPAUSE_CHECK          = var.unpause_check
      WAKE_ON_HEAD           = lookup(var.node_config, "ORACLE_MERGE_VIA", "") == "radicle" ? "true" : "false"
      BUDGET_NAME            = local.watcher_budget
      ACCOUNT_ID             = data.aws_caller_identity.current.account_id
    }
  }

  lifecycle {
    precondition {
      condition     = !var.watcher_enabled || can(regex("^0x[0-9a-fA-F]{40}$", var.validator_address))
      error_message = "Set validator_address (the signing key's address) before watcher_enabled = true."
    }
    precondition {
      condition     = !var.watcher_enabled || ((local.watcher_rpc_url != "" || var.rpc_url_secret_arn != "") && local.watcher_race != "")
      error_message = "The watcher needs the chain (watcher_rpc_url, rpc_url_secret_arn or node_config's ORACLE_RPC) and the race (race_address or node_config's ORACLE_RACE)."
    }
  }

  depends_on = [aws_cloudwatch_log_group.watcher]
}

resource "aws_cloudwatch_event_rule" "watcher" {
  count               = local.watcher
  name                = "${var.name}-watcher"
  description         = "Run the proof-of-fix SEV-SNP validator's v3 watcher every minute"
  schedule_expression = "rate(1 minute)" # EventBridge's shortest: the watcher's polling interval
  state               = var.watcher_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "watcher" {
  count = local.watcher
  rule  = aws_cloudwatch_event_rule.watcher[0].name
  arn   = aws_lambda_function.watcher[0].arn
}

resource "aws_lambda_permission" "watcher" {
  count         = local.watcher
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.watcher[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.watcher[0].arn
}
