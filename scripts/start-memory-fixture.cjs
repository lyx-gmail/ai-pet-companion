'use strict';
// Explicit integration-test service: real extraction, isolated in-memory storage.
const { loadConfig } = require('../backend/config.cjs');
const config = loadConfig();
process.env.DB_PATH = ':memory:';
const db = require('../backend/upstream.cjs').openDatabase();
const store = require('../backend/memory-store.cjs').createMemoryStore(db);
const server = require('../backend/memory-server.cjs').createApp({store,llm:config.llm,token:config.token});
server.listen(8767,'127.0.0.1',()=>console.log('Isolated in-memory fixture ready on loopback 8767'));
for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>server.close(()=>{db.close();process.exit(0);}));
