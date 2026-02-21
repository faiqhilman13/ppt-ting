FROM node:20-bookworm-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev
RUN npx playwright install --with-deps chromium

COPY src ./src

EXPOSE 3002
CMD ["node", "src/server.js"]
