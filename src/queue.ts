import { Queue } from "bullmq";
import { Redis } from "ioredis";
import { cfg, SignJob } from "./config.js";

export function makeConnection() {
  // BullMQ workers require maxRetriesPerRequest = null
  return new Redis(cfg.redisUrl, { maxRetriesPerRequest: null });
}

export function makeQueue(connection = makeConnection()) {
  return new Queue<SignJob>(cfg.queueName, { connection });
}
