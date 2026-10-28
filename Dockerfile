FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY audita/ ./audita/
COPY public/ ./public/
COPY server.py ./server.py
RUN useradd -r -u 10001 -g nogroup auditavoto && chown -R auditavoto:nogroup /app
USER auditavoto
EXPOSE 8080
CMD ["python", "server.py"]
