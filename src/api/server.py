import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.tools.registry import create_default_registry
from src.providers.base import MockLlmProvider, MultiProviderGateway
from src.agents.orchestrator import AgentRunner

app = FastAPI(
    title="Agentic AI Runtime",
    version="1.0.0",
    description="Autonomous Tool-Calling Loop with Multi-Provider Fallback and Token/Cost Telemetry",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = create_default_registry()
gateway = MultiProviderGateway([MockLlmProvider(model_name="mock-llm")])
runner = AgentRunner(provider=gateway, registry=registry)


class PromptRequest(BaseModel):
    prompt: str
    max_budget_usd: float = 0.50


@app.get("/api/v1/tools")
def get_registered_tools():
    return {"tools": registry.list_tools()}


@app.post("/api/v1/agent/run")
async def run_agent(request: PromptRequest):
    try:
        runner.max_budget_usd = request.max_budget_usd
        result = await runner.run(request.prompt)
        return result.to_dict()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.post("/api/v1/agent/stream")
async def stream_agent(request: PromptRequest):
    async def sse_generator():
        async for event in runner.stream_events(request.prompt):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
def get_playground():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Agentic AI Runtime Playground</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card: rgba(18, 24, 38, 0.8);
      --border: rgba(255, 255, 255, 0.08);
      --primary: #6366f1;
      --text: #f8fafc;
      --muted: #94a3b8;
      --success: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Plus Jakarta Sans', sans-serif; background: var(--bg); color: var(--text); padding: 2rem; }
    .container { max-width: 900px; margin: 0 auto; }
    .header { margin-bottom: 2rem; display: flex; align-items: center; justify-content: space-between; }
    .brand { font-size: 1.5rem; font-weight: 800; }
    .badge { background: rgba(99, 102, 241, 0.2); color: #818cf8; padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; }
    .input-box { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
    textarea { width: 100%; height: 90px; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border); border-radius: 8px; color: #fff; padding: 12px; font-family: inherit; font-size: 0.95rem; outline: none; margin-bottom: 1rem; resize: none; }
    .btn-row { display: flex; justify-content: space-between; align-items: center; }
    .btn { background: var(--primary); color: #fff; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 700; cursor: pointer; }
    .presets { display: flex; gap: 8px; }
    .preset-btn { background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: var(--muted); padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; cursor: pointer; }
    .timeline { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; min-height: 250px; }
    .event-item { margin-bottom: 1rem; padding: 12px; border-radius: 8px; border-left: 3px solid var(--primary); background: rgba(255,255,255,0.02); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }
    .event-tool { border-left-color: #f59e0b; }
    .event-result { border-left-color: var(--success); }
    .event-final { border-left-color: #a855f7; font-family: inherit; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">🤖 Agentic AI Runtime</div>
      <div class="badge">Tool-Calling Loop • Fallback Gateway</div>
    </div>

    <div class="input-box">
      <textarea id="promptInput" placeholder="Ask the agent to analyze growth metrics or query warehouse cohorts...">Analyze our ARR trajectory over 3 years starting from $100k to $550k with estimated 25% EBITDA margin.</textarea>
      <div class="btn-row">
        <div class="presets">
          <button class="preset-btn" onclick="setPrompt('financial')">Financial CAGR</button>
          <button class="preset-btn" onclick="setPrompt('warehouse')">Analytical Query</button>
        </div>
        <button class="btn" id="runBtn" onclick="runAgentStream()">Execute Agent Loop ⚡</button>
      </div>
    </div>

    <div class="timeline" id="timeline">
      <div style="color: var(--muted); text-align: center; padding: 2rem;">Ready to execute autonomous agent loop...</div>
    </div>
  </div>

  <script>
    function setPrompt(type) {
      const input = document.getElementById('promptInput');
      if (type === 'financial') {
        input.value = "Analyze our ARR trajectory over 3 years starting from $100k to $550k with estimated 25% EBITDA margin.";
      } else {
        input.value = "Query the analytical warehouse for our top enterprise tenants with retention over 95%.";
      }
    }

    async function runAgentStream() {
      const prompt = document.getElementById('promptInput').value;
      const timeline = document.getElementById('timeline');
      const runBtn = document.getElementById('runBtn');

      timeline.innerHTML = '';
      runBtn.disabled = true;
      runBtn.innerText = 'Running Loop...';

      const response = await fetch('/api/v1/agent/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        const lines = text.split('\\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.replace('data: ', ''));
            renderEvent(data);
          }
        }
      }

      runBtn.disabled = false;
      runBtn.innerText = 'Execute Agent Loop ⚡';
    }

    function renderEvent(event) {
      const timeline = document.getElementById('timeline');
      const div = document.createElement('div');
      div.className = 'event-item';

      if (event.event === 'tool_calling') {
        div.className += ' event-tool';
        div.innerHTML = `<strong>⚡ Tool Invocation:</strong> <code>${event.data.tool}</code><pre style="margin-top:6px; color:#fcd34d;">${JSON.stringify(event.data.arguments, null, 2)}</pre>`;
      } else if (event.event === 'tool_result') {
        div.className += ' event-result';
        div.innerHTML = `<strong>✅ Tool Execution Result:</strong> <code>${event.data.tool}</code><pre style="margin-top:6px; color:#6ee7b7;">${JSON.stringify(event.data.result, null, 2)}</pre>`;
      } else if (event.event === 'final_answer') {
        div.className += ' event-final';
        div.innerHTML = `<strong>🎯 Terminal Strategic Synthesis:</strong><div style="margin-top:8px; line-height:1.6; white-space:pre-wrap;">${event.data.content}</div><div style="margin-top:12px; font-size:0.75rem; color:#818cf8;">Telemetry: ${event.data.telemetry.total_tokens} tokens • Est. Cost: $${event.data.telemetry.cost_usd} USD</div>`;
      } else if (event.event === 'iteration_start') {
        div.style.borderColor = '#6366f1';
        div.innerHTML = `🔄 <strong>Agent Loop Iteration:</strong> ${event.data.iteration}`;
      } else {
        div.innerHTML = `ℹ️ Event: ${event.event}`;
      }
      timeline.appendChild(div);
      timeline.scrollTop = timeline.scrollHeight;
    }
  </script>
</body>
</html>
    """
