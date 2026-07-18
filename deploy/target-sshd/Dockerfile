# Host de prueba DESCARTABLE para la validación end-to-end del vector SSH (Fase 6).
# Debian + sshd + agente Wazuh. El usuario de prueba tiene un password débil A PROPÓSITO
# (es el blanco del brute-force controlado). NO usar fuera de un lab descartable.
#
# Build (contexto = raíz del repo):
#   docker build -f deploy/target-sshd/Dockerfile -t argos-target-sshd .
# Run (enrola al manager de ARGOS; 2222 del host -> 22 del contenedor):
#   docker run -d --name target-sshd -p 2222:22 -e WAZUH_MANAGER=<ip-del-host-docker> argos-target-sshd
FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server curl gnupg ca-certificates procps iproute2 lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Repo + agente Wazuh (la dirección del manager se fija en runtime, en el entrypoint).
RUN curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH \
      | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import \
    && chmod 644 /usr/share/keyrings/wazuh.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
      > /etc/apt/sources.list.d/wazuh.list \
    && apt-get update && apt-get install -y wazuh-agent \
    && rm -rf /var/lib/apt/lists/*

# Usuario de prueba con password débil (blanco del brute-force de lab).
RUN useradd -m -s /bin/bash labuser \
    && echo 'labuser:password123' | chpasswd \
    && mkdir -p /run/sshd

# Scripts de active-response de ARGOS: la contención real (argos-isolate/kill/...) corre acá,
# invocada por el manager. Se instalan sin extensión (el <executable> del ossec.conf).
COPY active-response/linux/ /tmp/argos-ar/
RUN mkdir -p /var/ossec/active-response/bin \
    && for f in /tmp/argos-ar/argos-*.sh; do \
         base="$(basename "$f" .sh)"; \
         install -m 0750 "$f" "/var/ossec/active-response/bin/${base}"; \
       done \
    && rm -rf /tmp/argos-ar

COPY deploy/target-sshd/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
