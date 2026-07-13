FROM openroad/orfs:latest

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:${PATH}"

RUN pip3 install --no-cache-dir volare && \
    volare enable --pdk sky130 --pdk-root /pdk 0fe599b2afb6708d281543108caf8310912f54af

RUN pip3 install --no-cache-dir fastapi uvicorn jinja2

WORKDIR /work
COPY api.py /app/api.py
COPY pd_verification.py /app/pd_verification.py
COPY verification_policy.json /app/verification_policy.json
COPY export_preview.py /app/export_preview.py

EXPOSE 7070
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7070", "--app-dir", "/app"]