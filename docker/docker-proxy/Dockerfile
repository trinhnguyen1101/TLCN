FROM tecnativa/docker-socket-proxy:v0.5.0

# DockerOperator waits on POST /containers/{id}/wait for the whole Spark job.
# The upstream 10-minute idle timeouts cut that valid long-lived response and
# make Airflow report a false failure while the container keeps running.
RUN sed -i \
      -e 's/timeout client 10m/timeout client 12h/' \
      -e 's/timeout server 10m/timeout server 12h/' \
      /usr/local/etc/haproxy/haproxy.cfg.template
