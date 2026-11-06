output "validator_address" {
  description = "Your validator's public address, as you set it (it comes from the key in the signing-key secret)."
  value       = var.validator_address
}

output "signing_key_secret_arn" {
  description = "Put your validator's signing key here (runbook); Terraform never sees it."
  value       = aws_secretsmanager_secret.validator_key.arn
}

output "node_instance_id" {
  description = "The node instance: stopped while idle, started by the watcher."
  value       = aws_instance.node.id
}

output "node_log_group" {
  description = "The node's runs."
  value       = aws_cloudwatch_log_group.node.name
}

output "watcher_log_group" {
  description = "The watcher's minute-by-minute decisions (idle, started, disabled)."
  value       = aws_cloudwatch_log_group.watcher.name
}

output "watcher_state_parameter" {
  description = "The last block the watcher scanned; delete its value (set it to none) to rescan the last 100 blocks."
  value       = aws_ssm_parameter.last_block.name
}

output "budget_action_id" {
  description = "The budget stop's action, to reverse it (the runbook's \"Spending guards\"); empty without one."
  value       = local.budget_stop ? aws_budgets_budget_action.stop[0].action_id : ""
}
