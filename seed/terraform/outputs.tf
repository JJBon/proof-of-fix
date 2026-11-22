output "instance_id" {
  description = "The seed's instance; empty until create_instance = true."
  value       = var.create_instance ? aws_instance.seed[0].id : ""
}

output "public_ip" {
  description = "The seed's Elastic IP; empty until create_instance = true."
  value       = var.create_instance ? aws_eip.seed[0].public_ip : ""
}

output "external_address" {
  description = "The address in the node's config (externalAddresses): host:8776."
  value       = local.external_address
}

output "rid" {
  description = "The one repository the seed serves, from the publication record."
  value       = local.rid
}

output "session_command" {
  description = "A shell on the seed through Session Manager (ssm_access), then: sudo -u radicle RAD_HOME=/var/lib/radicle/home rad self --nid"
  value       = var.create_instance && var.ssm_access ? "aws ssm start-session --region ${var.region} --target ${aws_instance.seed[0].id}" : ""
}
