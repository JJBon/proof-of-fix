# The money: a monthly budget with alerts, and at 100 % actual an automatic stop of both instances (this host and the
# SEV-SNP host, found by their Name tags), as the kit's own budget does for its host. The run's own cap is the auto-stop
# (autostop.tf) and scripts/rc-aws.sh's stop; this is the last line.

locals {
  budget_alerts = length(var.budget_emails) > 0
  budget_stop   = local.budget_alerts && var.create_instance
}

data "aws_instances" "kit_node" {
  filter {
    name   = "tag:Name"
    values = ["${var.kit_name}-node"]
  }
  instance_state_names = ["pending", "running", "stopping", "stopped"]
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = local.budget_alerts ? [["ACTUAL", 50], ["ACTUAL", 80], ["FORECASTED", 100]] : []
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

data "aws_iam_policy_document" "budget_action" {
  count = local.budget_stop ? 1 : 0

  statement {
    sid       = "RunTheStopAutomation"
    actions   = ["ssm:StartAutomationExecution"]
    resources = ["arn:aws:ssm:${var.region}::automation-definition/AWS-StopEC2Instance:*"]
  }

  statement {
    sid       = "StopTheKitsInstancesOnly"
    actions   = ["ec2:StopInstances", "ec2:DescribeInstanceStatus", "ec2:DescribeInstances"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/pof:kit"
      values   = ["validator-kit/sevsnp"]
    }
  }
}

resource "aws_iam_role_policy" "budget_action" {
  count  = local.budget_stop ? 1 : 0
  name   = "stop-the-instances"
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
      instance_ids    = concat([aws_instance.host[0].id], data.aws_instances.kit_node.ids)
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
