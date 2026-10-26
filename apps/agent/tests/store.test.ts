import { describe, expect, it } from "vitest";

import { PostgresDiscoveryStore } from "../src/store.js";

describe("durable discovery metadata", () => {
  it("survives a bridge restart and rejects changed metadata for the same job", async () => {
    const rows = new Map<string, { idempotency_key: string; session_id: string; epoch_id: string; source_ids: string[] }>();
    const pool = {
      async query(sql: string, params: unknown[] = []) {
        if (sql.includes("INSERT INTO")) {
          const [key, session, epoch, sources] = params as [string, string, string, string];
          if (!rows.has(key)) rows.set(key, { idempotency_key: key, session_id: session, epoch_id: epoch, source_ids: JSON.parse(sources) });
          return { rows: [] };
        }
        if (sql.includes("WHERE idempotency_key")) return { rows: [rows.get(params[0] as string)].filter(Boolean) };
        if (sql.includes("WHERE session_id")) return { rows: [...rows.values()].filter((row) => row.session_id === params[0]) };
        return { rows: [] };
      },
    };
    const record = { idempotencyKey: "job-1", sessionId: "session-1", epochId: "epoch-1", sourceIds: ["source-1"] };
    await new PostgresDiscoveryStore(pool).put(record);
    await expect(new PostgresDiscoveryStore(pool).get("session-1")).resolves.toEqual(record);
    await expect(new PostgresDiscoveryStore(pool).put({ ...record, epochId: "epoch-2" }))
      .rejects.toMatchObject({ code: "idempotency_conflict" });
  });
});
