# Spec Delta

## ADDED Requirements

### Requirement: Model quality: scenarios and criteria
The market simulation SHALL offer models by provider and tier, each with an accuracy and a cost per verdict, let operators run the model that pays them best, and provide an operator declaring a reputable model while running a cheap one. With tiered fees, a more accurate model SHALL pay its operator more than a cheaper one, net of cost; good fixes SHALL be rejected less often than in checking v5; and every earlier criterion SHALL hold or be named.

#### Scenario: Quality pays
- **WHEN** operators run models of different tiers under tiered fees
- **THEN** the more accurate tier's net return per verdict is significantly higher

#### Scenario: Flat fees, as a comparison
- **WHEN** the same seeds run with one flat fee
- **THEN** the report gives the operators' returns by tier, the share of good fixes rejected, and honest solvers' returns under both

#### Scenario: The cheat is caught
- **WHEN** an operator declares a reputable model and runs a cheap one
- **THEN** it is suspended, and its return is significantly lower than running the model it declared
