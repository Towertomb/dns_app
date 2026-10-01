FROM python:3.12-slim
WORKDIR /app
COPY server.py .
RUN mkdir -p /data
ENV DNS_RECORD_FILE=/data/records.json
VOLUME ["/data"]
EXPOSE 53533/udp
CMD ["python", "-u", "server.py"]
