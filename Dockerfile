FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy application files
COPY . .

# Expose port (Render assigns PORT via env var)
EXPOSE 3000

CMD ["node", "server.js"]