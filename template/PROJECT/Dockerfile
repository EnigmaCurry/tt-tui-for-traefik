# ---- Builder -------------------------------------------------
FROM rust:1.91-slim-trixie AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git pkg-config libssl-dev && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo fetch
COPY . .
RUN cargo build --release --locked

# ---- Runtime -------------------------------------------------
FROM debian:trixie-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/${GIT_USERNAME}/${APP}"
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*
ARG USER=appuser UID=1001 GID=1001
RUN groupadd --gid "$GID" "$USER" \
 && useradd  --uid "$UID" \
             --gid "$GID" \
             --create-home \
             --shell /usr/sbin/nologin \
             "$USER"

COPY --from=builder /app/target/release/${APP} /usr/local/bin/${APP}
USER $USER
ENTRYPOINT ["${APP}"]
