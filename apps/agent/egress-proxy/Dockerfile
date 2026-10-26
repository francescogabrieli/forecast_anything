FROM python:3.12-alpine

WORKDIR /app
COPY proxy.py ./proxy.py
USER 65532:65532
EXPOSE 3128
ENTRYPOINT ["python", "-u", "/app/proxy.py"]
