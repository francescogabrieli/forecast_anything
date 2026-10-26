import { mistral } from "@ai-sdk/mistral";
import { defineAgent } from "eve";

// Model credentials are read by the provider from the agent service environment.
export default defineAgent({
  model: mistral(process.env.MISTRAL_MODEL_ID ?? "mistral-large-latest"),
  defaultTools: false,
  experimental: { workflow: { world: "@workflow/world-postgres" } },
});
