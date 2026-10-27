# Retained experiment resources

This root still owns the synthetic `runwx_revision_demo` dataset and its four
tables. The revision/publication application experiment is parked on its separate
branch. `revision_validation.tf` keeps the existing storage declarations and
schemas so an ordinary plan does not propose removing them.

The existing local configuration keeps `enable_revision_validation = true`.
New setups default to `false`. Do not turn the existing setting off as cleanup:
the resources retain deletion protection and `prevent_destroy` guards.

The schemas under `dbt/contracts/revisions/` describe retained tables only. They
do not enable revision selection, dbt models, jobs or additional IAM grants.

Mocked Terraform tests check the default and retained-storage boundaries without
cloud credentials. They do not prove the deployed state is unchanged. Before the
next deployment from this root, review a full saved plan against the existing
state. It must preserve all five resources and contain only the intended change.
Do not migrate state, delete resources or use targeting as the routine workflow.
