output "signing_key_secret_arn" {
  description = "Put the validator's signing key here (the plan); Terraform never sees it."
  value       = aws_secretsmanager_secret.validator_key.arn
}

output "ami_id" {
  description = "The measured disk's AMI (UEFI, NitroTPM v2.0); empty until snapshot_id is set."
  value       = var.snapshot_id != "" ? aws_ami.checker[0].id : ""
}

output "instance_id" {
  description = "The SEV-SNP instance; empty until create_instance = true."
  value       = var.create_instance ? aws_instance.node[0].id : ""
}

output "roothash" {
  description = "The disk's dm-verity root hash, from the manifest (the kernel command line names it)."
  value       = local.roothash
}

output "image_digest" {
  description = "The checker image's digest for Validators' accepted list (pof-checker-image/1), from the manifest."
  value       = local.image_digest
}

output "console_command" {
  description = "Read the boot's attestation from the serial console (no credentials on the instance)."
  value       = var.create_instance ? "aws ec2 get-console-output --region ${var.region} --instance-id ${aws_instance.node[0].id} --latest --output text | grep '^POF-ATTEST'" : ""
}

output "watcher_function_name" {
  description = "The v3 watcher's Lambda (empty until create_instance = true); its log group is /aws/lambda/<name>."
  value       = var.create_instance ? aws_lambda_function.watcher[0].function_name : ""
}

output "watcher_state_param" {
  description = "The watcher's SSM state parameter (the last block, the open seats, the day's starts)."
  value       = var.create_instance ? aws_ssm_parameter.watcher_state[0].name : ""
}
