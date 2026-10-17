// Runs as root in mongo-init. Idempotent: safe on every `docker compose up`.
//
// 1. Initiate the single-node replica set rs0 (transactions need one).
// 2. One database and one user per service (CLAUDE.md rule 1, TRD §15). platform has two.
// 3. The audit user cannot update or delete audit_events (rule 10, TP "Audit insert-only").

function initiate() {
  try {
    rs.status();
    return;
  } catch (e) {
    if (e.codeName !== "NotYetInitialized") throw e;
  }
  rs.initiate({ _id: "rs0", members: [{ _id: 0, host: "mongo:27017" }] });
  for (let i = 0; i < 60; i++) {
    if (db.hello().isWritablePrimary) return;
    sleep(1000);
  }
  throw new Error("rs0 did not elect a primary in 60 s");
}

function upsertRole(dbName, role, privileges) {
  const target = db.getSiblingDB(dbName);
  if (target.getRole(role)) {
    target.updateRole(role, { privileges, roles: [] });
  } else {
    target.createRole({ role, privileges, roles: [] });
  }
}

function upsertUser(dbName, user, password, roles) {
  const target = db.getSiblingDB(dbName);
  if (target.getUser(user)) {
    target.updateUser(user, { pwd: password, roles });
  } else {
    target.createUser({ user, pwd: password, roles });
  }
  print(`user ${user} on ${dbName}`);
}

initiate();

const env = process.env;
upsertUser("auth", "auth", env.AUTH_DB_PASSWORD, [{ role: "readWrite", db: "auth" }]);
upsertUser("operations", "operations", env.OPS_DB_PASSWORD, [{ role: "readWrite", db: "operations" }]);
upsertUser("media", "media", env.MEDIA_DB_PASSWORD, [{ role: "readWrite", db: "media" }]);
upsertUser("report", "report", env.REPORT_DB_PASSWORD, [{ role: "readWrite", db: "report" }]);
upsertUser("notification", "notification", env.PLATFORM_NOTIFICATION_DB_PASSWORD, [
  { role: "readWrite", db: "notification" },
]);

// Audit: insert and read audit_events, never update or remove them. Its other collections
// (audit_state, processed_events, _migrations) are ordinary read-write.
const auditIndexes = ["createIndex", "listIndexes", "createCollection"];
upsertRole("audit", "auditWriter", [
  { resource: { db: "audit", collection: "audit_events" }, actions: ["find", "insert", ...auditIndexes] },
  {
    resource: { db: "audit", collection: "audit_state" },
    actions: ["find", "insert", "update", ...auditIndexes],
  },
  {
    resource: { db: "audit", collection: "processed_events" },
    actions: ["find", "insert", "update", "remove", ...auditIndexes],
  },
  {
    resource: { db: "audit", collection: "_migrations" },
    actions: ["find", "insert", "update", "remove", ...auditIndexes],
  },
  { resource: { db: "audit", collection: "" }, actions: ["listCollections"] },
]);
upsertUser("audit", "audit", env.PLATFORM_AUDIT_DB_PASSWORD, [{ role: "auditWriter", db: "audit" }]);

print("mongo-init done");
