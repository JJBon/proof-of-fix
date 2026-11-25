# Spec Delta

## ADDED Requirements

### Requirement: The result's caller is repaid about its gas
The caller who counts a verdict's result SHALL be repaid from the check's deposit about the gas it spent, up to a published allowance and gas price, and the deposit's gas line SHALL stay the allowance times the published price ceiling. At the launch's smallest panel (one judge) the repayment SHALL cover at least the measured gas of the call.

#### Scenario: A lone judge's result
- **WHEN** a keeper counts a lone judge's result, measured at about 0.7 million gas
- **THEN** it is repaid for about the whole of it, within the 1 million gas allowance

#### Scenario: The deposit doesn't grow
- **WHEN** the repayment's fixed overhead is raised to cover the call's tail
- **THEN** a fix's deposit is unchanged, because the allowance and the price ceiling are unchanged

### Requirement: A participant's tool shows its standing without the key
The participants' tool SHALL show a participant's standing (its cap, open claims, coin balance, credit, allowance and its ETH balance for gas) without unlocking its key, from the address it is configured with. It SHALL ask for the key only for a command that signs.

#### Scenario: A newcomer checks whether its gas arrived
- **WHEN** a newcomer with a keystore and its address in the tool's configuration runs the status command with no terminal
- **THEN** the status shows its ETH and coin balances, and no password is asked for

#### Scenario: A signing command
- **WHEN** the same newcomer registers an issue
- **THEN** the tool asks for the keystore's password once, as before

### Requirement: A reporter's tool gives the registered issue's id and can draw its check
When a reporter registers an issue, the tool SHALL print the Radicle issue's whole id on a line of its own and in its machine-readable output, so no reader has to scrape another tool's display. It SHALL be able to open the Radicle issue itself and register it in one step. It SHALL tell the reporter how to draw the registration check if no validator draws it, and draw it on request.

#### Scenario: Register and open in one step
- **WHEN** a reporter registers with a title and a description instead of an existing issue's id
- **THEN** the tool opens the Radicle issue, checks the id it got back, registers it, and prints that id and the claim lines

#### Scenario: The check isn't drawn
- **WHEN** the registration check is still undrawn some minutes after its seed block
- **THEN** the reporter can draw it with the tool, which sends the draw and its fee-meter signal and refuses, sending nothing, if the check isn't due

### Requirement: The newcomer's ceiling is published
The guides SHALL state the largest bounty a solver with no reputation can claim under its cap at the deployment's opening share, how a later pledge raises the claim past the cap even after the share is locked, and the advice to record an attempt as soon as work starts, which locks the share at that day's level.

#### Scenario: A newcomer picks a bounty
- **WHEN** a solver with no reputation reads the fix guide before choosing a bounty
- **THEN** it learns that a bounty whose funds, less the registration fee, are over about 117.6 coins (the Sepolia record's opening share and finder's fee, against a 50-coin cap) can't be claimed by it at the opening share, that pledges after its attempt can still push the claim over, and to record its attempt first

### Requirement: A participant's tool waits for its own approval
When the participants' tool approves the race to take its coin before a send, it SHALL wait until the chain it reads shows the allowance, so the send can't be refused for an allowance the participant just granted.

#### Scenario: A lagging provider
- **WHEN** a reporter registers an issue, the tool approves the race, and the provider's next answer comes from a node that hasn't seen the approval
- **THEN** the tool waits until the allowance reads at least what is needed, then registers, and the registration succeeds

### Requirement: Every transaction a participant sends is reported
The participants' tool SHALL print the hash and block of every transaction it sends, approvals included, in its text and machine-readable output.

#### Scenario: Claiming test coin
- **WHEN** a newcomer claims from the faucet with machine-readable output
- **THEN** the output holds the claim's transaction hash and block

### Requirement: A reporter can follow its registration
The participants' tool SHALL show a registration's check: its status, panel size and panel, its deadlines, its counted result, its hold or window and final time, and its deposit's spending and refund. Its status command SHALL list the address's registrations.

#### Scenario: A registration held after a pass
- **WHEN** a reporter asks for its registration whose check passed at k = 1 and is held
- **THEN** the tool shows the pass, that it is held and why, the deadlines that apply, and that the deposit's rest is refunded once the verdict is final and its reports are in
