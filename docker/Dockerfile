# Runtime do noturno de estabilidade — ambiente oficial da métrica.
#
# Imagem FIXADA POR DIGEST, não por tag: uma tag pode ser reapontada para outra
# imagem sem aviso, e aí a "sequência sem flake" mediria dois ambientes
# diferentes como se fossem um. O digest abaixo corresponde a
# mcr.microsoft.com/playwright/python:v1.44.0-jammy (resolvido em 2026-07-30).
FROM mcr.microsoft.com/playwright/python@sha256:c257db7f706f31f852740b039dea4f4611418f1a6816c0ceae716dd20d4eddda

# Sem bytecode e sem buffer: log como fluxo de eventos (12-Factor).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_TERMINAL_PROMPT=0 \
    TZ=UTC

WORKDIR /app

# Dependências antes do código: muda o requirements, refaz a camada; muda um
# check, reaproveita.
COPY webqa-suite/requirements.txt /app/webqa-suite/requirements.txt
RUN pip install --no-cache-dir -r /app/webqa-suite/requirements.txt \
    # A imagem traz os navegadores da versão 1.44 e o requirements pina
    # playwright==1.56.0 — cuja revisão de Chromium NÃO é a pré-instalada. Sem
    # esta linha, toda noite falharia com "Executable doesn't exist" e viraria
    # flake permanente. O pin não dispensa a linha: torna determinística a
    # revisão que ela baixa, que antes variava com a data do build.
    && python -m playwright install chromium
# NENHUM segredo entra em camada: a deploy key é montada em /run/secrets no
# runtime. Ver .dockerignore e docker/compose.yml.
COPY . /app

# Usuário não-root já existente na imagem oficial do Playwright.
RUN chown -R pwuser:pwuser /app
USER pwuser

# O relatório vai para tmpfs: artefato de execução não persiste em volume.
ENV WEBQA_REPORT_DIR=/tmp/report

ENTRYPOINT ["/app/docker/entrypoint.sh"]
