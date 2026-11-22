# The money: a monthly budget with alerts, and at 100 % actual an automatic stop of the instance. The model's spending
# is capped by the node itself (oracle/spend.py: ORACLE_SPEND_DAILY_USD, ORACLE_SPEND_MONTHLY_USD, and the on-chain
# pause), since a model reached by API key isn't on this bill.

locals {
  budget_alerts = length(var.budget_emails) > 0
  budget_stop   = var.budget_stop && local.budget_alerts && var.create_instance
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = local.budget_alerts ? [["ACTUAL", 80], ["FORECASTED", 100]] : []
    content {
      comparison_operator        = "GREATER_THAN"
      notification_type          = notification.value[0]
      threshold                  = notification.value[1]
      threshold_type             = "PERCENTAGE"
      subscriber_email_addresses = var.budget_emails
    }
  }
}

data "aws_iam_policy_document" "budget_assume" {
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
  assume_role_policy = data.aws_iam_policy_document.budget_assume.json
}

# AWS Budgets runs the SSM automation that stops the listed instances; this instance only.
data "aws_iam_policy_document" "budget_action" {
  count = local.budget_stop ? 1 : 0

  statement {
    sid       = "RunTheStopAutomation"
    actions   = ["ssm:StartAutomationExecution"]
    resources = ["arn:aws:ssm:${var.region}::automation-definition/AWS-StopEC2Instance:*"]
  }

  statement {
    sid       = "StopThisInstanceOnly"
    actions   = ["ec2:StopInstances", "ec2:DescribeInstanceStatus", "ec2:DescribeInstances"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Name"
      values   = ["${var.name}-node"]
    }
  }
}

resource "aws_iam_role_policy" "budget_action" {
  count  = local.budget_stop ? 1 : 0
  name   = "stop-the-instance"
  role   = aws_iam_role.budget_action[0].id
  policy = data.aws_iam_policy_document.budget_action[0].json
}

resource "aws_budgets_budget_action" "stop" {
  count              = local.budget_stop ? 1 : 0
  budget_name        = aws_budgets_budget.monthly.name
  action_type        = "RUN_SSM_DOCUMENTS"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budget_action[0].arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    ssm_action_definition {
      action_sub_type = "STOP_EC2_INSTANCES"
      region          = var.region
      instance_ids    = [aws_instance.node[0].id]
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
