# golden-kyc-openenv image recipe (LOCAL STUB served by the Studio stub). Built by the RL Gym on this machine.
# The base is pinned by digest and must already be present locally; the build makes no network request.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GOLDEN_KYC_SEED=/app/seed/cases.jsonl
WORKDIR /app
COPY golden_kyc_env.py /app/golden_kyc_env.py
COPY cases.jsonl /app/seed/cases.jsonl
USER 10001
LABEL ai.adi-labs.rlgym.environment-contract="golden-kyc-openenv" ai.adi-labs.rlgym.synthetic="true"
ENTRYPOINT ["python", "/app/golden_kyc_env.py"]
CMD ["idle"]
