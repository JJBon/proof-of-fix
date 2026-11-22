# The hard stop (task 7.0's cost cap): a Lambda run every 10 minutes that stops any running instance carrying the SEV-SNP
# kit's tag (pof:kit = validator-kit/sevsnp: this host and the kit's SEV-SNP host) once it has run autostop_hours since
# its last start (EC2's LaunchTime is the last start). It exists with the instance and goes with `tofu destroy`.
# The second layer is on the host itself: pof-autostop.service schedules its shutdown at each boot (user data), and
# scripts/rc-aws.sh stops both machines at the end of a run, on a failure and on an interrupt.
#
# Least privilege: describe instances (no resource-level permission exists for that) and stop only instances with the
# kit's tag; its own logs.

locals {
  autostop = var.create_instance ? 1 : 0
}

data "archive_file" "autostop" {
  type        = "zip"
  source_file = "${path.module}/lambda/autostop.py"
  output_path = "${path.module}/.build/autostop.zip"
}

data "aws_iam_policy_document" "autostop_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "autostop" {
  count              = local.autostop
  name               = "${var.name}-autostop"
  assume_role_policy = data.aws_iam_policy_document.autostop_assume.json
}

resource "aws_cloudwatch_log_group" "autostop" {
  count             = local.autostop
  name              = "/aws/lambda/${var.name}-autostop"
  retention_in_days = 14
}

data "aws_iam_policy_document" "autostop" {
  count = local.autostop

  statement {
    sid       = "Describe"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"] # DescribeInstances has no resource-level permissions
  }

  statement {
    sid       = "StopTheKitsInstancesOnly"
    actions   = ["ec2:StopInstances"]
    resources = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/pof:kit"
      values   = ["validator-kit/sevsnp"]
    }
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.autostop[0].arn}:*"]
  }
}

resource "aws_iam_role_policy" "autostop" {
  count  = local.autostop
  name   = "autostop"
  role   = aws_iam_role.autostop[0].id
  policy = data.aws_iam_policy_document.autostop[0].json
}

resource "aws_lambda_function" "autostop" {
  count            = local.autostop
  function_name    = "${var.name}-autostop"
  role             = aws_iam_role.autostop[0].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "autostop.handler"
  filename         = data.archive_file.autostop.output_path
  source_code_hash = data.archive_file.autostop.output_base64sha256
  timeout          = 60
  memory_size      = 128

  environment {
    variables = {
      MAX_HOURS = tostring(var.autostop_hours)
      TAG_KEY   = "pof:kit"
      TAG_VALUE = "validator-kit/sevsnp"
    }
  }

  depends_on = [aws_cloudwatch_log_group.autostop]
}

resource "aws_cloudwatch_event_rule" "autostop" {
  count               = local.autostop
  name                = "${var.name}-autostop"
  description         = "Stop the SEV-SNP kit's instances after autostop_hours of running (proof-of-fix task 7.0)"
  schedule_expression = "rate(10 minutes)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "autostop" {
  count = local.autostop
  rule  = aws_cloudwatch_event_rule.autostop[0].name
  arn   = aws_lambda_function.autostop[0].arn
}

resource "aws_lambda_permission" "autostop" {
  count         = local.autostop
  statement_id  = "events"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.autostop[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.autostop[0].arn
}
