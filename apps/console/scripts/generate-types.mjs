import { readFile, writeFile } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";

const apiDirectory = new URL("../src/api/", import.meta.url);
const schemaFile = new URL("schemas.json", apiDirectory);
const target = new URL("schema.generated.ts", apiDirectory);
const schemas = JSON.parse(await readFile(schemaFile, "utf8"));
const names = [
  "ForecastSelection",
  "BacktestSettings",
  "BacktestReport",
  "OriginOutcome",
  "OriginPage",
  "PartitionScore",
  "SourceField",
  "SourceProfile",
  "SourceSpec",
  "SourceView",
  "SourceRegistration",
  "ForecastResult",
  "RunRecord",
  "Candidate",
  "Watch",
  "WatchView",
  "EventRecord",
  "EvaluationRecord",
  "Node",
  "GraphSpec",
  "Snapshot",
  "ScenarioRequest",
  "ScenarioView",
  "JobView",
  "QuestionForecastSelection",
  "QuestionCreateRequest",
  "QuestionRevisionRequest",
  "QuestionTitlePatch",
  "QuestionRevision",
  "QuestionView",
  "QuestionReferenceRequest",
  "QuestionReference",
  "QuestionPage",
  "QuestionRevisionPage",
  "QuestionReferencePage",
  "OperationCreateRequest",
  "OperationUpdateRequest",
  "OperationSubmitRequest",
  "OperationView",
  "OperationPage",
  "SnapshotSummary",
  "SnapshotSeriesSummary",
  "SnapshotSeriesPage",
  "ForecastPresentation",
  "ForecastPresentationPoint",
  "ForecastProviderUse",
  "BacktestPresentation",
  "BacktestSummary",
  "QuestionPresentation",
  "QuestionPresentationReference",
];
let output = "// Generated from src/api/schemas.json. Run npm run generate:types.\n\n";
for (const name of names) {
  const schema = schemas[name];
  if (!schema) throw new Error(`Missing core contract: ${name}`);
  const definition = await compile(schema, name, {
    bannerComment: "",
    style: { singleQuote: false },
  });
  const body = definition
    .trimEnd()
    .split("\n")
    .map((line) => (line.trim() ? `  ${line.trimEnd()}` : ""))
    .join("\n");
  output += `export namespace ${name}Generated {\n${body}\n}\n`;
  output += `export type ${name} = ${name}Generated.${name};\n\n`;
}
output = `${output.trimEnd()}\n`;
if (process.argv.includes("--check")) {
  const actual = await readFile(target, "utf8").catch(() => "");
  if (actual !== output) {
    process.stderr.write("Generated console contracts are stale. Run npm run generate:types.\n");
    process.exitCode = 1;
  }
} else {
  await writeFile(target, output);
}
