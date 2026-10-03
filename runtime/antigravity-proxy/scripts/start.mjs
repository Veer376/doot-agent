process.env.HOST = process.env.ANTIGRAVITY_PROXY_HOST ?? "127.0.0.1";
process.env.PORT = process.env.ANTIGRAVITY_PROXY_PORT ?? "8877";

await import("../node_modules/antigravity-claude-proxy/src/index.js");
