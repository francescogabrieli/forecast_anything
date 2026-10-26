import pg from "pg";

import { BridgeError, type DiscoveryRecord } from "./bridge.js";

interface PgPoolLike {
  query(sql: string, params?: unknown[]): Promise<{ rows: any[] }>;
}

const { Pool } = pg;

function configuredPool(): PgPoolLike {
  const connectionString = process.env.FORECAST_AGENT_DATABASE_URL ?? process.env.WORKFLOW_POSTGRES_URL;
  if (!connectionString) throw new BridgeError("missing_agent_database_url");
  return new Pool({ connectionString });
}

export class PostgresDiscoveryStore {
  private readonly pool: PgPoolLike;
  private setupPromise?: Promise<void>;

  constructor(pool?: PgPoolLike) { this.pool = pool ?? configuredPool(); }

  private async setup(): Promise<void> {
    this.setupPromise ??= (async () => {
      await this.pool.query("CREATE SCHEMA IF NOT EXISTS forecast_agent");
      await this.pool.query("CREATE TABLE IF NOT EXISTS forecast_agent.discovery_sessions (idempotency_key text PRIMARY KEY, session_id text NOT NULL UNIQUE, epoch_id text NOT NULL, source_ids jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now())");
    })().catch((error) => { this.setupPromise = undefined; throw error; });
    await this.setupPromise;
  }

  async put(record: DiscoveryRecord): Promise<void> {
    await this.setup();
    await this.pool.query(
      "INSERT INTO forecast_agent.discovery_sessions (idempotency_key, session_id, epoch_id, source_ids) VALUES ($1, $2, $3, $4::jsonb) ON CONFLICT (idempotency_key) DO NOTHING",
      [record.idempotencyKey, record.sessionId, record.epochId, JSON.stringify(record.sourceIds)],
    );
    const row = (await this.pool.query(
      "SELECT idempotency_key, session_id, epoch_id, source_ids FROM forecast_agent.discovery_sessions WHERE idempotency_key = $1",
      [record.idempotencyKey],
    )).rows[0];
    if (!row || row.session_id !== record.sessionId || row.epoch_id !== record.epochId ||
        JSON.stringify(row.source_ids) !== JSON.stringify(record.sourceIds)) {
      throw new BridgeError("idempotency_conflict");
    }
  }

  async get(sessionId: string): Promise<DiscoveryRecord | undefined> {
    await this.setup();
    const row = (await this.pool.query(
      "SELECT idempotency_key, session_id, epoch_id, source_ids FROM forecast_agent.discovery_sessions WHERE session_id = $1",
      [sessionId],
    )).rows[0];
    if (!row) return undefined;
    return { idempotencyKey: row.idempotency_key, sessionId: row.session_id, epochId: row.epoch_id, sourceIds: row.source_ids };
  }
}
