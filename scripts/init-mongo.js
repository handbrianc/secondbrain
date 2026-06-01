// This script runs after MongoDB initialization
// Credentials are read from environment variables for security
db = db.getSiblingDB('admin');

// Use environment variables or fallback to defaults for development only
// DO NOT use defaults in production - always set MONGO_ADMIN_PASSWORD env var
var adminPassword = db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}) ? 
  (process.env.MONGO_ADMIN_PASSWORD || 'changeme_in_production') : 
  (process.env.MONGO_ADMIN_PASSWORD || 'changeme_in_production');

try {
  db.createUser({
    user: 'admin',
    pwd: adminPassword,
    roles: [{ role: 'root', db: 'admin' }]
  });
  print('User admin created successfully');
} catch(e) {
  print('Warning: ' + e.message);
}
