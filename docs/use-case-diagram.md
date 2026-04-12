# Use Case Diagram

This project uses a single diagram in the documentation: the Use Case Diagram.

## Actors

- Admin
- Security Analyst
- FinOps Analyst
- Governance/Admin
- User

## Use Cases

- Login / Register
- Manage Resources
- Forecast Cost
- Detect Threats
- Run Attack Scenarios
- Evaluate Policies
- View Reports
- Manage Membership
- Use AI Chat

## Diagram

```text
Admin ------------> (Manage Resources)
Admin ------------> (Evaluate Policies)
Admin ------------> (View Reports)
Admin ------------> (Manage Membership)

Security Analyst --> (Detect Threats)
Security Analyst --> (Run Attack Scenarios)
Security Analyst --> (View Reports)

FinOps Analyst ---> (Forecast Cost)
FinOps Analyst ---> (Manage Resources)
FinOps Analyst ---> (View Reports)

Governance/Admin --> (Evaluate Policies)
Governance/Admin --> (View Reports)

User -------------> (Login / Register)
User -------------> (Use AI Chat)
User -------------> (View Reports)
```

## Scope

No other diagram types are used in the final documentation.
