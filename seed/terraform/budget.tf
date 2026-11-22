# The money: a monthly budget with alerts, and no automatic stop.
#
# Why no stop (unlike the SEV-SNP kit's): the seed's cost is fixed by design (one t4g instance with standard CPU
# credits, two small volumes, one public IPv4: seed/README.md), so a budget overrun means something else in the account
# or an unexpected data-transfer bill, not the seed running away. Stopping it would take proof-of-fix offline for
# everyone who fetches through it, while the budget, like the SEV-SNP kit's, sees the whole account. The alerts reach
# the owner, who decides; `create_instance = false` removes the seed's billed resources.

resource "aws_budgets_budget" "monthly" {
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
