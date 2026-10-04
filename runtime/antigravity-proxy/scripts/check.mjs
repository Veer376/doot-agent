const baseUrl = process.env.ANTIGRAVITY_BASE_URL ?? "http://127.0.0.1:8877";

async function getJson(path) {
  const response = await fetch(`${baseUrl}${path}`);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

async function postJson(path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": "doot-local-check",
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}: ${JSON.stringify(result)}`);
  }
  return result;
}

const health = await getJson("/health");
const models = await getJson("/v1/models");

if (health.status !== "ok") {
  throw new Error(`Proxy health is not ok: ${JSON.stringify(health)}`);
}
if (!Array.isArray(models.data) || models.data.length === 0) {
  throw new Error("Proxy returned no models");
}

const model = models.data.some((item) => item?.id === "gemini-3.8-flash-low")
  ? "gemini-3.8-flash-low"
  : models.data[0].id;

const toolResponse = await postJson("/v1/messages", {
  model,
  max_tokens: 128,
  messages: [
    {
      role: "user",
      content: "Call proxy_check with value DOOT_PROXY_TOOL_OK. Do not answer directly.",
    },
  ],
  tools: [
    {
      name: "proxy_check",
      description: "Return the supplied value unchanged.",
      input_schema: {
        type: "object",
        properties: { value: { type: "string" } },
        required: ["value"],
      },
    },
  ],
  tool_choice: { type: "any" },
});

const toolUse = toolResponse.content?.find(
  (item) => item?.type === "tool_use" && item?.name === "proxy_check",
);
if (!toolUse || toolUse.input?.value !== "DOOT_PROXY_TOOL_OK") {
  throw new Error(`Proxy did not preserve tool calling: ${JSON.stringify(toolResponse)}`);
}

console.log(
  JSON.stringify(
    {
      status: health.status,
      accounts: health.counts?.total ?? null,
      available: health.counts?.available ?? null,
      modelCount: models.data.length,
      toolCalling: "ok",
      model,
    },
    null,
    2,
  ),
);
