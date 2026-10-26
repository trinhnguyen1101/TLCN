```
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

```
ingestion_date=$(date -u +%F)
batch_id="raw-$(date -u +%Y%m%dT%H%M%SZ)"

printf 'Ngày: %s\nBatch: %s\n' "$ingestion_date" "$batch_id"
```

Landing -> bronze
```
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset waqi/historical --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset CAMS/EAC4 --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset climate_trace/climate_trace_vietnam --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset reference/vietnam_administrative_divisions --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset reference/vietnamese-provinces-database --batch-id "$batch_id" --ingestion-date "$ingestion_date"
```