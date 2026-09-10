# Verifies Spark can resolve MinIO and Nessie service names from its Docker network.
docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /opt/spark/work-dir/jobs/smoke_test.py
