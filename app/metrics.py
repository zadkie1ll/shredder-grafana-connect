from prometheus_client import Counter, Gauge, Histogram

SYNC_RUNS = Counter("node_sync_runs_total", "Total synchronization runs")
SYNC_FAILURES = Counter("node_sync_failures_total", "Failed synchronization runs")
SYNC_DURATION = Histogram("node_sync_duration_seconds", "Synchronization duration")
MANAGED_NODES = Gauge("node_sync_managed_nodes", "Managed nodes")
ACTIVE_NODES = Gauge("node_sync_nodes_active", "Active managed nodes")
ERROR_NODES = Gauge("node_sync_nodes_error", "Managed nodes in error state")
SSH_FAILURES = Counter("node_sync_ssh_failures_total", "SSH failures")
PROVISION_FAILURES = Counter("node_sync_provision_failures_total", "Provision failures")
