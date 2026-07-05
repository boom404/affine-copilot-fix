FROM node:22-slim

# Tools some agents shell out to (git etc.) — keep minimal.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- ACP agents (installed globally so their bins are on PATH) --------------
# Claude Code (matches the package used by the Obsidian agent-client plugin):
RUN npm install -g @agentclientprotocol/claude-agent-acp

# Codex (ACP adapter + CLI for auth/login via ~/.codex):
RUN npm install -g @zed-industries/codex-acp @openai/codex

# Gemini — enable once you have a ~/.gemini login:
# RUN npm install -g @google/gemini-cli

WORKDIR /app
COPY server.js package.json ./

ENV NODE_ENV=production \
    PORT=5100 \
    ACP_CWD=/tmp \
    HOME=/home/node

# credential dirs are bind-mounted at runtime (~/.claude etc.)
USER node
EXPOSE 5100
CMD ["node", "server.js"]
