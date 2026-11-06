# The watcher: a Lambda run once a minute that starts the node instance only when a sealed submission appears.

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
  name               = "${var.name}-watcher"
  assume_role_policy = data.aws_iam_policy_document.watcher_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "watcher" {
  statement {
    sid       = "State"
    actions   = ["ssm:GetParameter", "ssm:PutParameter"]
    resources = [aws_ssm_parameter.last_block.arn]
  }

  statement {
    sid       = "DescribeNode"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"] # DescribeInstances has no resource-level permissions
  }

  statement {
    sid       = "StartNodeOnly"
    actions   = ["ec2:StartInstances"]
    resources = ["arn:aws:ec2:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:instance/${aws_instance.node.id}"]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.watcher.arn}:*"]
  }

  dynamic "statement" {
    for_each = var.rpc_api_key_secret_arn != "" ? [1] : []
    content {
      sid       = "ChainApiKey"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.rpc_api_key_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "watcher" {
  name   = "watcher"
  role   = aws_iam_role.watcher.id
  policy = data.aws_iam_policy_document.watcher.json
}

resource "aws_lambda_function" "watcher" {
  function_name    = "${var.name}-watcher"
  role             = aws_iam_role.watcher.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "watcher.handler"
  filename         = data.archive_file.watcher.output_path
  source_code_hash = data.archive_file.watcher.output_base64sha256
  timeout          = 50 # under the one-minute schedule
  memory_size      = 128
  tags             = local.tags

  environment {
    variables = {
      RPC_URL                = var.rpc_url
      RPC_API_KEY_SECRET_ARN = var.rpc_api_key_secret_arn
      RPC_API_KEY_HEADER     = var.rpc_api_key_header
      RACE_ADDRESS           = var.race_address
      SEAT_ADDRESS           = var.validator_address
      INSTANCE_ID            = aws_instance.node.id
      STATE_PARAM            = aws_ssm_parameter.last_block.name
      ENABLED                = var.enabled ? "true" : "false"
      MAX_BLOCK_RANGE        = "2000"
      MERGE_POLL_MINUTES     = tostring(var.merge_poll_minutes)
      PENDING_POLL_MINUTES   = tostring(var.pending_poll_minutes)
      PENDING_MAX_STARTS     = tostring(var.pending_max_starts)
      MAX_STARTS_PER_DAY     = tostring(var.max_starts_per_day)
    }
  }

  depends_on = [aws_cloudwatch_log_group.watcher]
}

resource "aws_cloudwatch_event_rule" "watcher" {
  name                = "${var.name}-watcher"
  description         = "Run the proof-of-fix validator's watcher every minute"
  schedule_expression = "rate(1 minute)"
  state               = var.enabled ? "ENABLED" : "DISABLED"
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "watcher" {
  rule = aws_cloudwatch_event_rule.watcher.name
  arn  = aws_lambda_function.watcher.arn
}

resource "aws_lambda_permission" "watcher" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.watcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.watcher.arn
}
