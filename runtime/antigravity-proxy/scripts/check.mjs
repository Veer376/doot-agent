const baseUrl = process.env.ANTIGRAVITY_BASE_URL ?? "http://127.0.0.1:8877";

async function getJson(path) {
  const response = await fetch(`${baseUrl}${path}`);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

const health = await getJson("/health");
const models = await getJson("/v1/models");

if (health.status !== "ok") {
  throw new Error(`Proxy health is not ok: ${JSON.stringify(health)}`);
}
if (!Array.isArray(models.data) || models.data.length === 0) {
  throw new Error("Proxy returned no models");
}

console.log(
  JSON.stringify(
    {
      status: health.status,
      accounts: health.counts?.total ?? null,
      available: health.counts?.available ?? null,
      modelCount: models.data.length,
    },
    null,
    2,
  ),
);
