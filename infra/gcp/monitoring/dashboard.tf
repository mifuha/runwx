resource "google_monitoring_dashboard" "api" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "runwx API"
    gridLayout = {
      columns = "2"
      widgets = [
        {
          title = "Requests by status class / 5 minutes"
          xyChart = {
            dataSets = [{
              plotType   = "LINE"
              targetAxis = "Y1"
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "${local.api_filter} AND metric.type = \"run.googleapis.com/request_count\""
                  aggregation = {
                    alignmentPeriod    = "300s"
                    perSeriesAligner   = "ALIGN_SUM"
                    crossSeriesReducer = "REDUCE_SUM"
                    groupByFields      = ["metric.label.response_code_class"]
                  }
                }
              }
            }]
            yAxis = { label = "Requests", scale = "LINEAR" }
          }
        },
        {
          title = "Server errors (5xx) / 5 minutes"
          xyChart = {
            dataSets = [{
              plotType   = "LINE"
              targetAxis = "Y1"
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "${local.api_filter} AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
                  aggregation = {
                    alignmentPeriod    = "300s"
                    perSeriesAligner   = "ALIGN_SUM"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }]
            yAxis = { label = "Errors", scale = "LINEAR" }
          }
        },
        {
          title = "Request latency p95 per series / 5 minutes"
          xyChart = {
            dataSets = [{
              plotType   = "LINE"
              targetAxis = "Y1"
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "${local.api_filter} AND metric.type = \"run.googleapis.com/request_latencies\""
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = "ALIGN_PERCENTILE_95"
                  }
                }
              }
            }]
            yAxis = { label = "Latency (ms)", scale = "LINEAR" }
          }
        },
        {
          title = "How to read this"
          text = {
            format = "MARKDOWN"
            style  = {}
            content = join("\n\n", [
              "[API error logs](${local.error_logs_url}) · [Uptime results](https://console.cloud.google.com/monitoring/uptime?project=${var.project_id})",
              "Traffic is low. Health probes count as requests and can keep the instance warm. Latency is p95 for each metric series, not a service-wide percentile. Empty charts can mean no samples; they do not prove zero errors.",
              "The uptime check calls /health without BigQuery. It does not check comparison values or pipeline runs. Use the retained [pipeline evidence](https://github.com/mifuha/runwx/blob/master/docs/dbt-models.md) for those checks.",
            ])
          }
        },
      ]
    }
  })
}
