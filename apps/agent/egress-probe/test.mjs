import assert from "node:assert/strict";
import net from "node:net";

const openai = await fetch("https://api.openai.com/v1/models", {
  signal: AbortSignal.timeout(10_000),
});
assert.ok(openai.status >= 200 && openai.status < 500, "OpenAI HTTPS tunnel should reach the provider");
console.log(`allowed OpenAI endpoint reached (HTTP ${openai.status})`);

await assert.rejects(
  fetch("https://api.mistral.ai/v1/models", { signal: AbortSignal.timeout(10_000) }),
  "Mistral chat endpoint must not be reachable from the agent service",
);
console.log("Mistral API endpoint denied by the proxy");

await assert.rejects(
  fetch("https://example.com/", { signal: AbortSignal.timeout(10_000) }),
  "unlisted HTTPS origins must be denied by the proxy",
);
console.log("unlisted HTTPS origin denied by the proxy");

const directSocketBlocked = await new Promise((resolve) => {
  const socket = net.connect({ host: "1.1.1.1", port: 443 });
  const timer = setTimeout(() => { socket.destroy(); resolve(true); }, 3_000);
  socket.once("connect", () => { clearTimeout(timer); socket.destroy(); resolve(false); });
  socket.once("error", () => { clearTimeout(timer); resolve(true); });
});
assert.equal(directSocketBlocked, true, "the isolated process must not open direct Internet sockets");
console.log("direct Internet socket denied by the isolated network");
