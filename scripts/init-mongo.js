// This script runs after MongoDB initialization
db = db.getSiblingDB('admin');
try {
  db.createUser({
    user: 'admin',
    pwd: 'supersecretpassword123',
    roles: [{ role: 'root', db: 'admin' }]
  });
  print('User admin created successfully');
} catch(e) {
  print('Warning: ' + e.message);
}
