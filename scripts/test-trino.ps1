# Lists Trino catalogs and validates that the Nessie-backed Iceberg catalog loads.
docker compose exec trino trino --server http://localhost:8080 --execute "SHOW CATALOGS"
