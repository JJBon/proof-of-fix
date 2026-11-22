output "instance_id" {
  description = "The test-chain host; empty until create_instance = true."
  value       = var.create_instance ? aws_instance.host[0].id : ""
}

output "private_ip" {
  description = "Its private address: where the chain's RPC and the seed are published for the SEV-SNP host (POF_EXT_BIND)."
  value       = var.create_instance ? aws_instance.host[0].private_ip : ""
}

output "bucket" {
  description = "The run's bucket (scripts/rc-aws.sh uploads the commit's bundle, the pinned images and solc)."
  value       = aws_s3_bucket.run.bucket
}

output "security_group_id" {
  description = "The host's group: RPC and the seed from the SEV-SNP host's group only."
  value       = aws_security_group.testchain.id
}

output "kit_security_group_id" {
  description = "The SEV-SNP host's group (the kit's), which gains egress to this host's group on the RPC port."
  value       = data.aws_security_group.kit_node.id
}

output "ami_id" {
  description = "The AMI the host runs (pinned by ami_id, or AL2023's at the first apply)."
  value       = var.create_instance ? aws_instance.host[0].ami : ""
}

output "autostop_function_name" {
  description = "The hard stop's Lambda; its log group is /aws/lambda/<name>."
  value       = var.create_instance ? aws_lambda_function.autostop[0].function_name : ""
}

output "session_command" {
  description = "A shell on the host through Session Manager (no SSH)."
  value       = var.create_instance ? "aws ssm start-session --region ${var.region} --target ${aws_instance.host[0].id}" : ""
}
