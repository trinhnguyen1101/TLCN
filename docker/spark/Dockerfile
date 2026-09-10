# Spark 3.5.4's Java 17 image currently ships Temurin 17.0.13, which fails
# during ManagementFactory initialization under this Docker Desktop setup.
# Java 11 is supported by Spark 3.5 and avoids that JVM issue.
FROM apache/spark:3.5.4-scala2.12-java11-ubuntu

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/spark/custom-jars \
    && curl -fL --retry 3 -o /opt/spark/custom-jars/iceberg-spark-runtime-3.5_2.12-1.7.1.jar https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.7.1/iceberg-spark-runtime-3.5_2.12-1.7.1.jar \
    && curl -fL --retry 3 -o /opt/spark/custom-jars/hadoop-aws-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
    && curl -fL --retry 3 -o /opt/spark/custom-jars/aws-java-sdk-bundle-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar
USER spark
