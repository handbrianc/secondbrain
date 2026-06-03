# MongoDB Authentication Setup

This guide explains how to configure MongoDB authentication for SecondBrain, both for new installations and existing setups.

## Why Authentication?

Enabling MongoDB authentication:
- **Security**: Prevents unauthorized access to your data
- **Production-ready**: Required for production deployments
- **Multi-tenant support**: Isolate different users/organizations
- **Compliance**: Meets security requirements for sensitive data

## Quick Setup (Recommended for New Installations)

### Step 1: Stop MongoDB

```bash
# Stop the running container
docker-compose stop mongodb

# Remove the container (keeps data)
docker-compose rm -f mongodb
```

### Step 2: Set Credentials in `.env`

Create or update your `.env` file:

```bash
# MongoDB credentials
MONGODB_INITDB_ROOT_USERNAME=your_username
MONGODB_INITDB_ROOT_PASSWORD=your_strong_password

# SecondBrain connection string (must match credentials)
SECONDBRAIN_MONGO_URI=mongodb://your_username:your_strong_password@localhost:27017
```

**Security Tips:**
- Use strong passwords (16+ characters, mixed case, numbers, symbols)
- Never commit `.env` to version control (add to `.gitignore`)
- Use different credentials for development and production

### Step 3: Update `docker-compose.yml`

The `docker-compose.yml` already includes authentication configuration:

```yaml
services:
  mongodb:
    image: mongodb/mongodb-community-server:7.0
    environment:
      - MONGODB_INITDB_ROOT_USERNAME=${MONGODB_INITDB_ROOT_USERNAME:-admin}
      - MONGODB_INITDB_ROOT_PASSWORD=${MONGODB_INITDB_ROOT_PASSWORD:-password}
```

No changes needed if you're using environment variables from `.env`.

### Step 4: Start MongoDB with Fresh Authentication

```bash
# Start MongoDB (will create admin user with your credentials)
docker-compose up -d mongodb

# Wait for MongoDB to be ready
sleep 10

# Verify authentication works
docker exec secondbrain-mongodb mongosh \
  -u your_username \
  -p your_strong_password \
  --eval "db.adminCommand('listDatabases')"

# Test SecondBrain connection
secondbrain health
```

### Step 5: Verify Connection

```bash
# Should show database stats instead of connection error
secondbrain status

# Should show all services healthy
secondbrain health
```

## Migrate Existing MongoDB to Authentication

If you already have data in MongoDB without authentication:

### Option 1: Fresh Start (Simplest)

```bash
# Backup existing data (optional)
docker exec secondbrain-mongodb mongodump \
  --out /backup \
  --authenticationDatabase admin

# Copy backup to host
docker cp secondbrain-mongodb:/backup ./mongodb-backup

# Remove container and data
docker-compose down -v

# Set new credentials in .env
cat > .env << EOF
MONGODB_INITDB_ROOT_USERNAME=your_username
MONGODB_INITDB_ROOT_PASSWORD=your_strong_password
SECONDBRAIN_MONGO_URI=mongodb://your_username:your_strong_password@localhost:27017
EOF

# Start fresh with authentication
docker-compose up -d mongodb

# Re-ingest your documents
secondbrain ingest /path/to/documents/
```

### Option 2: Enable Authentication Without Data Loss

⚠️ **Warning**: This is complex and error-prone. Consider Option 1 for most cases.

```bash
# Step 1: Create admin user in current MongoDB
docker exec -it secondbrain-mongodb mongosh << EOF
use admin
db.createUser({
  user: "admin",
  pwd: "your_strong_password",
  roles: ["root"]
})
EOF

# Step 2: Stop MongoDB
docker-compose stop mongodb

# Step 3: Update docker-compose.yml to enable auth
# Add or uncomment this line in the mongodb service:
# command: mongod --auth

# Step 4: Restart with authentication
docker-compose up -d mongodb

# Step 5: Update .env with credentials
cat >> .env << EOF
SECONDBRAIN_MONGO_URI=mongodb://admin:your_strong_password@localhost:27017
EOF

# Step 6: Verify
secondbrain health
```

## Docker Compose Configuration Reference

Full `docker-compose.yml` with authentication:

```yaml
services:
  mongodb:
    image: mongodb/mongodb-community-server:7.0
    container_name: secondbrain-mongodb
    hostname: mongodb
    ports:
      - "27017:27017"
    environment:
      - MONGODB_INITDB_ROOT_USERNAME=${MONGODB_INITDB_ROOT_USERNAME:-admin}
      - MONGODB_INITDB_ROOT_PASSWORD=${MONGODB_INITDB_ROOT_PASSWORD:-password}
    volumes:
      - mongodb-data:/data/db
      - mongodb-configdb:/data/configdb
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - secondbrain-network

volumes:
  mongodb-data:
  mongodb-configdb:

networks:
  secondbrain-network:
    driver: bridge
```

## Configuration in SecondBrain

### `.env` File Example

```bash
# MongoDB Authentication
MONGODB_INITDB_ROOT_USERNAME=secondbrain_user
MONGODB_INITDB_ROOT_PASSWORD=SuperSecureP@ssw0rd123!

# Connection string (must match credentials above)
SECONDBRAIN_MONGO_URI=mongodb://secondbrain_user:SuperSecureP@ssw0rd123!@localhost:27017
SECONDBRAIN_MONGO_DB=secondbrain
SECONDBRAIN_MONGO_COLLECTION=embeddings
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MONGODB_INITDB_ROOT_USERNAME` | MongoDB admin username | Yes (for new installs) |
| `MONGODB_INITDB_ROOT_PASSWORD` | MongoDB admin password | Yes (for new installs) |
| `SECONDBRAIN_MONGO_URI` | Full connection string with credentials | Yes |
| `SECONDBRAIN_MONGO_DB` | Database name | No (default: secondbrain) |
| `SECONDBRAIN_MONGO_COLLECTION` | Collection name | No (default: embeddings) |

## Troubleshooting

### Authentication Failed

**Error**: `Authentication failed.`

**Solutions:**
1. Verify credentials match in `.env` and `docker-compose.yml`
2. Check for special characters in password (escape them)
3. Ensure MongoDB container was started with auth enabled

```bash
# Check what MongoDB is configured with
docker exec secondbrain-mongodb mongosh \
  --eval "db.adminCommand('getParameter', {'authentication': 1})"

# Test connection manually
mongosh "mongodb://your_username:your_password@localhost:27017/secondbrain"
```

### Connection Refused After Enabling Auth

**Error**: `Cannot connect to MongoDB`

**Solutions:**
1. Restart MongoDB container: `docker-compose restart mongodb`
2. Check container logs: `docker-compose logs mongodb`
3. Verify port is listening: `lsof -i :27017`

### Password with Special Characters

If your password contains special characters (`@`, `:`, `/`, etc.), URL-encode them:

```bash
# Replace these characters:
@ → %40
: → %3A
/ → %2F
# → %23
? → %3F
& → %26

# Example:
# Password: my@pass:word#123
# URI: mongodb://user:my%40pass%3Aword%23123@localhost:27017
```

Or use a `.env` file to avoid shell escaping issues.

### Lost Password Recovery

If you lose your MongoDB password:

```bash
# Step 1: Stop MongoDB
docker-compose stop mongodb

# Step 2: Start without auth
docker run -d --name secondbrain-mongodb-nopass -p 27017:27017 mongodb/mongodb-community-server:7.0

# Step 3: Reset password
docker exec -it secondbrain-mongodb-nopass mongosh << EOF
use admin
db.changeUserPassword("admin", "new_password")
EOF

# Step 4: Stop and restart with proper config
docker stop secondbrain-mongodb-nopass
docker rm secondbrain-mongodb-nopass
docker-compose up -d mongodb
```

## Security Best Practices

### Password Requirements

- Minimum 16 characters
- Mix of uppercase, lowercase, numbers, symbols
- No dictionary words or personal information
- Use a password manager to generate and store

### Environment Variables

```bash
# ✅ Good: .env file with proper permissions
cat > .env << EOF
MONGODB_INITDB_ROOT_PASSWORD=$(openssl rand -base64 24)
EOF
chmod 600 .env

# ❌ Bad: Hardcoded in docker-compose.yml
# ❌ Bad: Committed to Git
# ❌ Bad: Shared via email/chat
```

### Production Deployment

For production environments:

1. **Use MongoDB Atlas** (managed service) or deploy with TLS/SSL
2. **Network isolation**: Don't expose MongoDB port to public internet
3. **Regular backups**: Automate with `mongodump`
4. **Monitor access**: Enable audit logging
5. **Rotate credentials**: Change passwords periodically

```bash
# Example: Production docker-compose with network isolation
services:
  mongodb:
    image: mongodb/mongodb-community-server:7.0
    ports: []  # No public port exposure
    environment:
      - MONGODB_INITDB_ROOT_USERNAME=${MONGODB_INITDB_ROOT_USERNAME}
      - MONGODB_INITDB_ROOT_PASSWORD=${MONGODB_INITDB_ROOT_PASSWORD}
    # ... rest of config
```

## Next Steps

- [Quick Start Guide](quick-start.md) - Get started with SecondBrain
- [Configuration Reference](configuration.md) - Complete configuration options
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [Docker Setup](../developer-guide/docker.md) - Advanced Docker configuration
