import { readFile, writeFile } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";

const source = new URL("../../../contracts/v1/schemas.json", import.meta.url);
const openapiSource = new URL("../../../contracts/v1/openapi.json", import.meta.url);
const target = new URL("../src/schema.generated.ts", import.meta.url);
const all = JSON.parse(await readFile(source, "utf8"));
const openapi = JSON.parse(await readFile(openapiSource, "utf8"));
const names = ["ForecastSelection", "BacktestSettings", "BacktestReport", "OriginPage", "CandidateRequest", "Candidate", "SourceProfile", "RunRecord", "AgentOperationRequest", "AgentOperationResponse"];
let output = "// Generated from contracts/v1/schemas.json and openapi.json. Run npm run contracts:generate.\n\n";
for (const name of names) {
  const schema = name.startsWith("AgentOperation")
    ? { ...openapi.components.schemas[name], $defs: { JsonValue: openapi.components.schemas.JsonValue } }
    : all[name];
  if (!schema) throw new Error(`Missing core schema: ${name}`);
  const normalized = JSON.parse(JSON.stringify(schema).replaceAll("#/components/schemas/JsonValue", "#/$defs/JsonValue"));
  const id = name.charAt(0).toLowerCase() + name.slice(1);
  output += `export const ${id}Schema = ${JSON.stringify(normalized, null, 2)} as const;\n\n`;
  const types = await compile(normalized, name, { bannerComment: "", style: { singleQuote: false } });
  output += `export namespace ${name}Generated {\n${types.trimEnd().split("\n").map((line) => line.trim() ? `  ${line}` : "").join("\n")}\n}\n`;
  output += `export type ${name} = ${name}Generated.${name};\n\n`;
}
if (process.argv.includes("--check")) {
  const actual = await readFile(target, "utf8").catch(() => "");
  if (actual !== output) {
    process.stderr.write("Generated agent schemas are stale. Run npm run contracts:generate.\n");
    process.exitCode = 1;
  }
} else {
  await writeFile(target, output);
}
