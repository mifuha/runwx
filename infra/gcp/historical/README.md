# Historical warehouse resources

This Terraform root manages one results table and one dbt output dataset per
explicitly chosen full-field export. The current state covers five Lydd, three
Folkestone and 13 Battersea editions. It also holds 19 separate GNR sample
tables. It reads the existing staging dataset as a data source. It does not upload results, build views, create a project, enable APIs,
change billing or grant runtime roles.

The optional `gnr_sample_tables` map creates only explicit GNR top-1,000 staging
tables with the separate sample schema. It does not create dbt output datasets or
grant runtime roles. Add one reviewed hash-derived table name per edition.

The optional `gnr_analysis_dataset_id` creates a separate dataset for the sampled
GNR dbt summaries and comparison. It grants no new runtime access.

Run Terraform from this directory, with its own state. The parent root's state
also owns earlier cloud demonstrations and a parked revision spike. Reusing that
state with the simplified configuration could plan removal of omitted resources.
Do not copy or move parent state into this root. Preserve both state files and their
backups locally; this separation leaves existing ownership intact.

## Prepare a plan

Create an ignored `terraform.tfvars.json` with the approved project and explicit
destinations. For example, using placeholder names:

```json
{
  "project_id": "project-id",
  "snapshots": {
    "edition_a": {
      "table_id": "reviewed_export_a",
      "output_dataset_id": "runwx_dbt_export_a"
    },
    "edition_b": {
      "table_id": "reviewed_export_b",
      "output_dataset_id": "runwx_dbt_export_b"
    }
  }
}
```

From the repository root:

```bash
terraform -chdir=infra/gcp/historical init -lockfile=readonly
terraform -chdir=infra/gcp/historical fmt -check
terraform -chdir=infra/gcp/historical validate
terraform -chdir=infra/gcp/historical plan -out=historical.tfplan
```

Inspect the saved plan before approving execution. In a fresh state, the two
example snapshots above would add two tables and two datasets. Check project,
region, exact names and the packaged results schema. Existing destinations must
be inspected rather than silently adopted into this new state.

Dataset access follows the existing project-owners model; inherited project IAM
still applies. For the separately reviewed Cloud Run dbt stage, pass the dedicated
`runwx-dbt` service-account email and an explicit map from snapshot key to `READER`
or `WRITER`. The first Folkestone validation needs `WRITER` only on `folkestone_2019`
and `READER` on `folkestone_2022` and `folkestone_2023`; no Lydd dataset is included.
This root also grants table-level Data Viewer on only those three corresponding
staging tables. The parent root separately grants permission to create query jobs.
Keeping dataset access entries in this root avoids competing IAM resources against
its inline access blocks, while table-level grants avoid exposing unrelated snapshots.

Tables have deletion protection, and all managed resources prevent destruction
through this configuration. Data has no automatic expiry. dbt owns the views and
its temporary test tables, not Terraform.

Apply only a reviewed, approved saved plan. Keep the existing loader's exact export
hashes and distinct output datasets when following the
[historical input workflow](../../../docs/historical-inputs.md). Real-data upload
and dbt execution have their own bounded execution scope; no merge is implied.
