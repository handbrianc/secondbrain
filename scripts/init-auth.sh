#!/bin/bash
set -e

# Wait for MongoDB to be ready
echo "Waiting for MongoDB to be ready..."
until mongosh --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
  sleep 1
done

# Create admin user if it doesn't exist
echo "Creating admin user..."
mongosh --eval "
  db = db.getSiblingDB('admin');
  try {
    db.createUser({
      user: 'admin',
      pwd: 'supersecretpassword123',
      roles: [{ role: 'root', db: 'admin' }]
    });
    print('User admin created successfully');
  } catch(e) {
    if (e.codeName === 'DuplicateKey') {
      print('User admin already exists');
    } else {
      print('Error: ' + e.message);
    }
  }
"

echo "MongoDB initialization complete"
