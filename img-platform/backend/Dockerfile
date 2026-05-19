FROM node:22-slim AS node

FROM python:3.10-slim

WORKDIR /app

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g mmx-cli

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "if [ -n \"$MINIMAX_API_KEY\" ]; then mmx auth login --api-key \"$MINIMAX_API_KEY\" >/tmp/mmx-auth.log 2>&1 || { echo 'mmx auth login failed' >&2; exit 1; }; fi; uvicorn main:app --host 0.0.0.0 --port 8000"]
