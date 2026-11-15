from __future__ import annotations

import argparse
import base64
import csv
import json
import time
from pathlib import Path

import httpx

from experiments.plotting import configure_font, require_file, save_figure, write_json
from fire_monitoring_inference.analysis.rules import classify
from fire_monitoring_inference.vision.qwen import PromptImage, QwenVisionReasoner, VlmEvidence

LABELS = ("A", "B", "C", "D", "E", "F", "误报")
WATER_HAZARD = {"B", "D", "E", "F"}
DIRECT_PROMPT = """你是校园火情的灭火顾问。只根据这张图回答用什么灭火。
返回一个 JSON 对象，字段为 class、agents、false_alarm。
class 只能是 A、B、C、D、E、F 或 误报。
agents 是简体中文灭火剂名称数组，例如水、泡沫、干粉、二氧化碳。
false_alarm 为 true 时 class 必须是 误报。
不要输出 JSON 以外的文字。"""


def _rate(hits: int, total: int) -> float | None:
    if total == 0:
        return None
    return hits / total


def _water(agents: list[str]) -> bool:
    return any(item in {"水", "直流水"} for item in agents)


def _metrics(rows: list[dict]) -> dict:
    if not rows:
        raise SystemExit("没有评测样本")
    correct = sum(row["predicted"] == row["label"] for row in rows)
    hazard = [row for row in rows if row["label"] in WATER_HAZARD]
    unsafe = sum(row["water"] for row in hazard)
    negatives = [row for row in rows if row["label"] == "误报"]
    positives = [row for row in rows if row["label"] != "误报"]
    false_alarms = sum(row["predicted"] != "误报" for row in negatives)
    misses = sum(row["predicted"] == "误报" for row in positives)
    latencies = [row["latency_ms"] for row in rows]
    tokens = [row["prompt_tokens"] + row["completion_tokens"] for row in rows if row["priced"]]
    costs = [row["cost_cny"] for row in rows if row["cost_cny"] is not None]
    return {
        "n": len(rows),
        "class_accuracy": correct / len(rows),
        "unsafe_advice_rate": _rate(unsafe, len(hazard)),
        "unsafe_advice_n": unsafe,
        "hazard_n": len(hazard),
        "false_alarm_rate": _rate(false_alarms, len(negatives)),
        "miss_rate": _rate(misses, len(positives)),
        "latency_ms_mean": float(sum(latencies) / len(latencies)),
        "prompt_tokens": sum(row["prompt_tokens"] for row in rows),
        "completion_tokens": sum(row["completion_tokens"] for row in rows),
        "cost_cny": None if not costs else float(sum(costs)),
        "priced_calls": len(tokens),
    }


def read_manifest(path: Path) -> list[dict]:
    require_file(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "path" not in reader.fieldnames or "label" not in reader.fieldnames:
            raise SystemExit("图片清单表头必须包含 path,label")
        rows = []
        for row in reader:
            label = row["label"]
            if label not in LABELS:
                raise SystemExit(f"未知类别 {label}")
            scene = row.get("scene") or "classroom"
            rows.append({"path": row["path"], "label": label, "scene": scene})
    if not rows:
        raise SystemExit(f"{path} 没有数据行")
    return rows


def _cost(prompt_tokens: int, completion_tokens: int, price: float | None) -> float | None:
    if price is None:
        return None
    return (prompt_tokens + completion_tokens) / 1_000_000 * price


def _direct_from_payload(payload: dict, price: float | None) -> dict:
    fire_class = payload["class"]
    agents = list(payload["agents"])
    false_alarm = bool(payload["false_alarm"])
    if fire_class not in LABELS:
        raise SystemExit(f"直接回答的类别无法识别：{fire_class}")
    if false_alarm != (fire_class == "误报"):
        raise SystemExit("直接回答里的类别和误报标记不一致")
    prompt_tokens = int(payload["prompt_tokens"])
    completion_tokens = int(payload["completion_tokens"])
    return {
        "predicted": fire_class,
        "water": _water(agents),
        "agents": agents,
        "latency_ms": float(payload["latency_ms"]),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_cny": _cost(prompt_tokens, completion_tokens, price),
        "priced": True,
    }


def _evidence_decision(evidence: dict, scene: str, latency_ms: float, prompt_tokens: int, completion_tokens: int, price: float | None) -> dict:
    checked = VlmEvidence.model_validate(evidence).model_dump(by_alias=False)
    resolved = classify(checked, scene)
    predicted = resolved["classes"][0] if resolved["classes"] else "误报"
    return {
        "predicted": predicted,
        "water": _water(resolved["recommended"]),
        "agents": resolved["recommended"],
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_cny": _cost(prompt_tokens, completion_tokens, price),
        "priced": True,
    }


def score_fixtures(manifest: list[dict], fixtures: dict, price: float | None) -> dict[str, list[dict]]:
    direct = fixtures.get("direct")
    evidence = fixtures.get("evidence")
    if not isinstance(direct, dict) or not isinstance(evidence, dict):
        raise SystemExit("假响应文件需要 direct 和 evidence 两张表")
    scored = {"direct": [], "evidence": []}
    for row in manifest:
        path = row["path"]
        if path not in direct or path not in evidence:
            raise SystemExit(f"假响应缺少 {path}")
        direct_row = _direct_from_payload(direct[path], price)
        evidence_row = _evidence_decision(
            evidence[path]["evidence"],
            row["scene"],
            float(evidence[path]["latency_ms"]),
            int(evidence[path]["prompt_tokens"]),
            int(evidence[path]["completion_tokens"]),
            price,
        )
        for name, decision in (("direct", direct_row), ("evidence", evidence_row)):
            scored[name].append({"label": row["label"], "path": path, **decision})
    return scored


def _llm_config(path: Path) -> tuple[str, str, str]:
    require_file(path)
    llm = json.loads(path.read_text(encoding="utf-8"))["llm"]
    key = llm["api_key"]
    if not key:
        raise SystemExit("config.json 的 llm.api_key 是空的")
    return llm["base_url"].rstrip("/"), llm["model"], key


def _data_url(path: Path) -> str:
    require_file(path)
    encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _post(client: httpx.Client, url: str, key: str, body: dict) -> dict:
    try:
        response = client.post(url, headers={"Authorization": f"Bearer {key}"}, json=body)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise SystemExit(f"千问接口失败：{exc.__class__.__name__}") from None


def _usage(payload: dict) -> tuple[int, int]:
    usage = payload.get("usage") or {}
    if "prompt_tokens" not in usage or "completion_tokens" not in usage:
        raise SystemExit("千问响应没有 token 用量")
    return int(usage["prompt_tokens"]), int(usage["completion_tokens"])


def score_live(manifest: list[dict], config_path: Path, root: Path, price: float | None) -> dict[str, list[dict]]:
    base_url, model, key = _llm_config(config_path)
    scored = {"direct": [], "evidence": []}
    reasoner = QwenVisionReasoner(api_key=key, base_url=base_url, model=model)
    with httpx.Client(timeout=httpx.Timeout(25.0, connect=3.0)) as client:
        for row in manifest:
            image = root / row["path"]
            data_url = _data_url(image)
            started = time.perf_counter()
            body = _post(
                client,
                f"{base_url}/chat/completions",
                key,
                {
                    "model": model,
                    "temperature": 0,
                    "enable_thinking": False,
                    "messages": [
                        {"role": "system", "content": DIRECT_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "判断这张图。"},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        },
                    ],
                },
            )
            latency_ms = (time.perf_counter() - started) * 1000
            content = body["choices"][0]["message"]["content"]
            prompt_tokens, completion_tokens = _usage(body)
            decision = json.loads(content)
            direct_row = _direct_from_payload(
                {
                    **decision,
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                price,
            )
            call = reasoner.analyze(
                incident_id=None,
                images=[PromptImage(index=1, role="keyframe", data_url=data_url)],
            )
            if call.status != "SUCCEEDED" or call.evidence is None:
                raise SystemExit(f"证据接口失败：{call.error_code}")
            evidence_row = _evidence_decision(
                call.evidence,
                row["scene"],
                float(call.latency_ms or 0),
                0,
                0,
                None,
            )
            evidence_row["priced"] = False
            for name, item in (("direct", direct_row), ("evidence", evidence_row)):
                scored[name].append({"label": row["label"], "path": row["path"], **item})
    return scored


def _plot(summary: dict[str, dict], directory: Path, title: str) -> None:
    configure_font()
    import matplotlib.pyplot as plt

    names = ["直接询问", "证据加规则"]
    keys = ["direct", "evidence"]
    accuracy = [summary[key]["class_accuracy"] for key in keys]
    unsafe = [0 if summary[key]["unsafe_advice_rate"] is None else summary[key]["unsafe_advice_rate"] for key in keys]
    index = [0, 1]
    width = 0.36
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.bar([item - width / 2 for item in index], accuracy, width, label="类别准确率", color="#0072B2")
    ax.bar([item + width / 2 for item in index], unsafe, width, label="不安全建议率", color="#D55E00")
    ax.set_xticks(index, names)
    ax.set_ylim(0, 1)
    ax.set_title(title)
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, directory, "qwen-compare")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="千问直接询问与证据加规则的对比")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--price-per-million", type=float)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.manifest is None:
        raise SystemExit("需要 --manifest")
    manifest = read_manifest(args.manifest)
    root = args.manifest.parent
    if args.live and args.fixtures:
        raise SystemExit("--live 和 --fixtures 不能同时用")
    if args.live:
        scored = score_live(manifest, args.config, root, args.price_per_million)
        data = "真实调用"
        note = "本地手动运行的结果。证据接口沿用现有客户端，不另计 token。不要把这个文件提交进仓库。"
    elif args.fixtures:
        fixtures = json.loads(require_file(args.fixtures).read_text(encoding="utf-8"))
        scored = score_fixtures(manifest, fixtures, args.price_per_million)
        data = "固定假响应"
        note = "固定假响应，不是千问的真实评测结论。"
    else:
        raise SystemExit("需要 --fixtures，或在本机加上 --live")
    summary = {name: _metrics(rows) for name, rows in scored.items()}
    payload = {"data": data, "note": note, "summary": summary, "rows": scored}
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "result.json", payload)
    title = "灭火建议对比（固定假响应）" if data == "固定假响应" else "灭火建议对比"
    _plot(summary, args.out, title)


if __name__ == "__main__":
    main()
