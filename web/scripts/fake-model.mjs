// A stand-in OpenAI-compatible model on this computer for the UI checks: it judges binding requests
// (src/openx_workbench/binding_judge.py) without any network. The first candidate is the same test,
// the second the same test after a change, every other one a different test.
import http from "node:http";

export async function startFakeModel({ port = 8768 } = {}) {
  let calls = 0;
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      const send = (value) => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(value));
      };
      if (req.url.endsWith("/models")) return send({ data: [{ id: "fake-judge" }] });
      calls += 1;
      const text = JSON.parse(body).messages.at(-1).content;
      const ids = [...text.matchAll(/### (C\d+)/g)].map((m) => m[1]);
      const verdict = (id) => (id === "C1" ? "同一测试" : id === "C2" ? "同一测试但要改" : "不是");
      const answer = {
        candidates: ids.map((id) => ({ id, verdict: verdict(id), reason: `${id}: authored reason`, changes: id === "C2" ? "Move the target" : "" })),
        binding: ids.slice(0, 2), preferred: ids[0] ?? null, note: "",
      };
      send({ choices: [{ finish_reason: "stop", message: { content: JSON.stringify(answer) } }], usage: { prompt_tokens: 1, completion_tokens: 1 } });
    });
  });
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  return { url: `http://127.0.0.1:${port}`, calls: () => calls, stop: () => server.close() };
}
