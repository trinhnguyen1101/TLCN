# ============================================================
# Stage 1: Get a pinned Java 11 runtime
# ============================================================
FROM eclipse-temurin:11.0.31_11-jre-jammy AS temurin11


# ============================================================
# Stage 2: Spark 3.5.4 + Scala 2.12 + Java 11
# ============================================================
FROM apache/spark:3.5.4-scala2.12-java11-ubuntu

USER root


# ============================================================
# Java 11
#
# Do not use the older Java 11 runtime bundled in the Spark
# base image. Copy the pinned Temurin Java 11 runtime into
# a separate path.
# ============================================================
COPY --from=temurin11 /opt/java/openjdk /opt/java/temurin-11

ENV JAVA_HOME=/opt/java/temurin-11
ENV PATH="${JAVA_HOME}/bin:${PATH}"


# ============================================================
# Python dependencies
# ============================================================
COPY requirements-silver.txt /tmp/requirements-silver.txt


# ============================================================
# Versions
# ============================================================
ARG ECCODES_VERSION=2.42.0
ARG ECBUILD_VERSION=3.8.5

ARG ICEBERG_VERSION=1.7.1
ARG HADOOP_AWS_VERSION=3.3.4
ARG AWS_SDK_BUNDLE_VERSION=1.12.262


# ============================================================
# Install build/runtime dependencies
#
# IMPORTANT:
# Do NOT install Ubuntu's libeccodes0 here.
# The repository available in this Spark image installs
# ecCodes 2.16.0, which is too old for eccodes-python 2.42.0.
#
# Instead, native ecCodes 2.42.0 is built from source below.
# ============================================================
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
        python3-pip \
        build-essential \
        cmake \
        pkg-config \
        libjpeg-dev \
        libpng-dev \
        libopenjp2-7-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*


# ============================================================
# Python tooling
#
# Python 3.8 is used by this Spark image.
# Keep pip below 25.1 for compatibility with Python 3.8.
# ============================================================
RUN python3 -m pip install \
        --no-cache-dir \
        --upgrade \
        "pip<25.1"


# ============================================================
# Build native ecCodes 2.42.0
#
# Download ecbuild explicitly instead of relying on ecCodes' CMake
# FetchContent fallback. CMake 3.16 cannot update ecbuild's tag clone
# reliably and fails with "invalid upstream origin/<tag>".
# ============================================================
RUN curl \
        -fL \
        --retry 5 \
        --retry-delay 3 \
        --connect-timeout 30 \
        "https://github.com/ecmwf/eccodes/archive/refs/tags/${ECCODES_VERSION}.tar.gz" \
        -o /tmp/eccodes.tar.gz \
    \
    && curl \
        -fL \
        --retry 5 \
        --retry-delay 3 \
        --connect-timeout 30 \
        "https://github.com/ecmwf/ecbuild/archive/refs/tags/${ECBUILD_VERSION}.tar.gz" \
        -o /tmp/ecbuild.tar.gz \
    \
    && mkdir -p /tmp/eccodes-src \
        /tmp/ecbuild-src \
    \
    && tar \
        -xzf /tmp/eccodes.tar.gz \
        -C /tmp/eccodes-src \
        --strip-components=1 \
    \
    && tar \
        -xzf /tmp/ecbuild.tar.gz \
        -C /tmp/ecbuild-src \
        --strip-components=1 \
    \
    && cmake \
        -S /tmp/ecbuild-src \
        -B /tmp/ecbuild-build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
    \
    && cmake \
        --build /tmp/ecbuild-build \
        --parallel 2 \
    \
    && cmake \
        --install /tmp/ecbuild-build \
    \
    && cmake \
        -S /tmp/eccodes-src \
        -B /tmp/eccodes-build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DCMAKE_INSTALL_LIBDIR=lib \
        -DENABLE_FORTRAN=OFF \
        -DENABLE_NETCDF=OFF \
        -DENABLE_AEC=OFF \
        -DENABLE_PNG=ON \
        -DENABLE_JPG=ON \
    \
    && cmake \
        --build /tmp/eccodes-build \
        --parallel 2 \
    \
    && cmake \
        --install /tmp/eccodes-build \
    \
    && ldconfig \
    \
    && rm -rf \
        /tmp/eccodes.tar.gz \
        /tmp/eccodes-src \
        /tmp/eccodes-build \
        /tmp/ecbuild.tar.gz \
        /tmp/ecbuild-src \
        /tmp/ecbuild-build


# ============================================================
# Make native ecCodes explicitly discoverable
# ============================================================
ENV LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH}"

ENV ECCODES_DEFINITION_PATH=/usr/local/share/eccodes/definitions
ENV ECCODES_SAMPLES_PATH=/usr/local/share/eccodes/samples


# ============================================================
# Install Python packages
# ============================================================
RUN python3 -m pip install \
        --no-cache-dir \
        -r /tmp/requirements-silver.txt \
    \
    && rm -f /tmp/requirements-silver.txt


# ============================================================
# Validate ecCodes during image build
#
# Build must fail here if Python cannot load native ecCodes.
# ============================================================
RUN python3 -m eccodes selfcheck \
    && python3 -c "\
import eccodes; \
print('ecCodes API version:', eccodes.codes_get_api_version()); \
print('eccodes Python module:', eccodes.__file__)\
"


# ============================================================
# Spark custom JARs
# ============================================================
RUN mkdir -p /opt/spark/custom-jars


# ============================================================
# Iceberg Spark runtime
# Spark 3.5 / Scala 2.12 / Iceberg 1.7.1
# ============================================================
RUN curl \
        -fL \
        --retry 5 \
        --retry-delay 3 \
        -o /opt/spark/custom-jars/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar \
        "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/${ICEBERG_VERSION}/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar"


# ============================================================
# Iceberg AWS bundle
# Used by Iceberg S3FileIO
# ============================================================
RUN curl \
        -fL \
        --retry 5 \
        --retry-delay 3 \
        -o /opt/spark/custom-jars/iceberg-aws-bundle-${ICEBERG_VERSION}.jar \
        "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar"


# ============================================================
# Hadoop AWS
# Used by Hadoop S3AFileSystem
# ============================================================
RUN curl \
        -fL \
        --retry 5 \
        --retry-delay 3 \
        -o /opt/spark/custom-jars/hadoop-aws-${HADOOP_AWS_VERSION}.jar \
        "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar"


# ============================================================
# AWS Java SDK v1 bundle
# Required by hadoop-aws 3.3.4
# ============================================================
RUN curl \
        -fL \
        --retry 5 \
        --retry-delay 3 \
        -o /opt/spark/custom-jars/aws-java-sdk-bundle-${AWS_SDK_BUNDLE_VERSION}.jar \
        "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_BUNDLE_VERSION}/aws-java-sdk-bundle-${AWS_SDK_BUNDLE_VERSION}.jar"


# ============================================================
# Verify Java runtime
# ============================================================
RUN java -version \
    && echo "JAVA_HOME=${JAVA_HOME}" \
    && readlink -f "$(command -v java)"


# ============================================================
# Permissions
# ============================================================
RUN chown -R spark:spark \
        /opt/spark/custom-jars \
        /usr/local/lib \
        /usr/local/share/eccodes


# ============================================================
# Run Spark as non-root
# ============================================================
USER spark
