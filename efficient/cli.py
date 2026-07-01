"""CLI entry point for Efficient AI.

Commands:
    efficient setup      — Run auto-detection wizard
    efficient status     — Show current configuration
    efficient report     — Show impact report (queries avoided, savings)
    efficient chat       — Interactive chat REPL
    efficient pull       — Pull recommended models via Ollama
    efficient clear      — Clear cache and/or telemetry
    efficient bench      — Run quick benchmark comparing local vs cloud
    efficient serve      — Start x402-enabled OpenAI-compatible proxy server
"""

from __future__ import annotations

import argparse
import sys
import time

from efficient.cache import SemanticCache
from efficient.client import Client
from efficient.config import Config
from efficient.telemetry import Telemetry


def main():
    parser = argparse.ArgumentParser(
        prog="efficient",
        description="Efficient AI — drop-in OpenAI replacement with stacked optimizations",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup
    subparsers.add_parser("setup", help="Run auto-detection wizard")

    # Status
    subparsers.add_parser("status", help="Show current configuration and backend status")

    # Report
    report_parser = subparsers.add_parser("report", help="Show impact report")
    report_parser.add_argument(
        "--hours", type=float, default=24.0, help="Hours to report on (default: 24)"
    )

    # Chat
    chat_parser = subparsers.add_parser("chat", help="Interactive chat REPL")
    chat_parser.add_argument("--model", default="auto", help="Model to use (default: auto)")

    # Pull
    pull_parser = subparsers.add_parser("pull", help="Pull recommended models via Ollama")
    pull_parser.add_argument(
        "--model", default="", help="Specific model to pull (default: recommended)"
    )

    # Clear
    clear_parser = subparsers.add_parser("clear", help="Clear cache and/or telemetry")
    clear_parser.add_argument("--cache", action="store_true", help="Clear cache only")
    clear_parser.add_argument("--telemetry", action="store_true", help="Clear telemetry only")
    clear_parser.add_argument("--all", action="store_true", help="Clear everything (default)")

    # Bench
    bench_parser = subparsers.add_parser(
        "bench", help="Benchmark engine vs Ollama vs cloud on real tasks"
    )
    bench_parser.add_argument(
        "--queries", type=int, default=0, help="(unused, kept for compatibility)"
    )

    # Serve
    serve_parser = subparsers.add_parser(
        "serve", help="Start x402-enabled OpenAI-compatible proxy server"
    )
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    serve_parser.add_argument(
        "--wallet",
        default=os.environ.get("EFFICIENT_WALLET", ""),
        help="EVM wallet address for receiving x402 payments (default: $EFFICIENT_WALLET)",
    )
    serve_parser.add_argument(
        "--network", default="eip155:8453", help="CAIP-2 network (default: Base mainnet)"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "setup":
        cmd_setup()
    elif args.command == "status":
        cmd_status()
    elif args.command == "report":
        cmd_report(args.hours)
    elif args.command == "chat":
        cmd_chat(args.model)
    elif args.command == "pull":
        cmd_pull(args.model)
    elif args.command == "clear":
        cmd_clear(args.cache, args.telemetry, args.all)
    elif args.command == "bench":
        cmd_bench(args.queries)
    elif args.command == "serve":
        cmd_serve(args.host, args.port, args.wallet, args.network)


def cmd_setup():
    """Run auto-detection wizard."""
    print("\nEfficient AI — Setup Wizard")
    print("=" * 50)

    print("\nDetecting hardware...")
    config = Config.autodetect()
    config._init_paths()

    print(f"\nGPU: {config.gpu.name} ({config.gpu.vendor})")
    if config.gpu.vram_mb > 0:
        print(f"  VRAM: {config.gpu.vram_mb / 1024:.1f} GB")
    else:
        print("  VRAM: not detected (will use CPU if local)")

    print(f"\nOllama: {'installed' if config.ollama.installed else 'NOT installed'}")
    if config.ollama.installed:
        print(f"  Running: {'yes' if config.ollama.running else 'no'}")
        if config.ollama.running:
            print(f"  Version: {config.ollama.version}")
            print(
                f"  Models: {', '.join(config.ollama.models) if config.ollama.models else 'none'}"
            )

    print(
        f"\nCloud providers detected: {', '.join(config.cloud.available_providers()) if config.cloud.any_available else 'none'}"
    )

    print(f"\nRecommended local model: {config.preferred_local_model or 'none'}")

    # Save config
    config.save()
    print(f"\nConfiguration saved to {config._config_path}")

    if not config.ollama.installed:
        print("\n⚠ Ollama is not installed.")
        print("  Install from https://ollama.com to enable local inference.")
        print("  Without Ollama, Efficient AI will use cloud APIs only.")

    if not config.cloud.any_available and not config.ollama.running:
        print("\n⚠ No inference backends available!")
        print("  Install Ollama or set an API key (e.g. OPENAI_API_KEY).")

    print("\n✓ Setup complete. Run 'efficient status' to verify.")
    print("  Run 'efficient chat' to start chatting.")


def cmd_status():
    """Show current configuration."""
    client = Client()
    print(client.status())


def cmd_report(hours: float):
    """Show impact report."""
    client = Client()
    print(client.report(since_hours=hours))


def cmd_chat(model: str):
    """Interactive chat REPL."""
    client = Client()
    print("\nEfficient AI Chat (type 'exit' to quit, 'report' for impact report)")
    print("=" * 50)
    print(f"Model: {model}")
    print()

    messages: list[dict] = []

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            break
        if user_input.lower() == "report":
            print(client.report())
            continue
        if user_input.lower() == "clear":
            messages = []
            print("Conversation cleared.\n")
            continue
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        print("ai> ", end="", flush=True)
        try:
            if model == "auto" and client.config.ollama.running:
                # Stream for local
                for chunk in client.chat_stream(messages=messages, model=model):
                    print(chunk, end="", flush=True)
                print()
            else:
                response = client.chat(messages=messages, model=model)
                print(response.content)

            # Show routing info
            if model == "auto":
                # Re-route to show decision (the actual call already routed)
                decision = client.router.route(messages)
                provider_tag = "LOCAL" if decision.model.is_local else "CLOUD"
                cost_tag = (
                    f"${0:.4f}"
                    if decision.model.is_local
                    else f"${decision.model.avg_price_per_m:.2f}/M"
                )
                print(
                    f"  [{provider_tag}] {decision.model.name} | {decision.intent} | {decision.complexity} | {cost_tag}"
                )
            print()
        except Exception as e:
            print(f"\nError: {e}\n")


def cmd_pull(model: str):
    """Pull recommended models via Ollama."""
    import subprocess

    config = Config.load()

    if not config.ollama.installed:
        print("Ollama is not installed. Install from https://ollama.com")
        return

    if model:
        models_to_pull = [model]
    else:
        models_to_pull = [config.preferred_local_model]
        # Also pull a small embedding model for semantic cache
        models_to_pull.append("nomic-embed-text")

    for m in models_to_pull:
        if not m:
            continue
        print(f"\nPulling {m}...")
        try:
            result = subprocess.run(
                ["ollama", "pull", m],
                timeout=600,
            )
            if result.returncode == 0:
                print(f"✓ {m} pulled successfully")
            else:
                print(f"✗ Failed to pull {m}")
        except subprocess.TimeoutExpired:
            print(f"✗ Timeout pulling {m}")
        except FileNotFoundError:
            print("Ollama binary not found. Is it in your PATH?")

    # Refresh config
    config.refresh()
    config.save()
    print(f"\nConfig updated. Available models: {', '.join(config.ollama.models)}")


def cmd_clear(cache: bool, telemetry: bool, all_flag: bool):
    """Clear cache and/or telemetry."""
    config = Config.load()

    if all_flag or (not cache and not telemetry):
        cache = True
        telemetry = True

    if cache:
        c = SemanticCache(db_path=config.cache_db_path)
        c.clear()
        print("✓ Cache cleared")

    if telemetry:
        t = Telemetry(db_path=config.telemetry_db_path)
        t.clear()
        print("✓ Telemetry cleared")


# ─── Benchmark ─────────────────────────────────────────────────────────────────

_BENCH_CATEGORIES = [
    {
        "name": "Arithmetic",
        "queries": [
            {"role": "user", "content": "What is 15 * 12?"},
            {"role": "user", "content": "What is 100 / 7?"},
            {"role": "user", "content": "What is 2 + 2?"},
            {"role": "user", "content": "What is 50 - 23?"},
        ],
    },
    {
        "name": "Summarization",
        "queries": [
            {
                "role": "user",
                "content": "Summarize: The weather today is sunny with a high of 75 degrees and light winds from the west. Tomorrow will bring rain showers in the afternoon with cooler temperatures around 60 degrees. The weekend looks clear and pleasant.",
            },
            {
                "role": "user",
                "content": "Summarize: Artificial intelligence has transformed how we interact with technology. From voice assistants to recommendation systems, AI is everywhere. However, the computational cost of running large models is enormous, requiring massive data centers that consume vast amounts of energy and water.",
            },
        ],
    },
    {
        "name": "Classification",
        "queries": [
            {
                "role": "user",
                "content": "Classify the sentiment of: 'I love this product, it works great!' as positive, negative, or neutral.",
            },
            {
                "role": "user",
                "content": "Classify the sentiment of: 'This is the worst experience ever, terrible service.' as positive, negative, or neutral.",
            },
        ],
    },
    {
        "name": "Extraction",
        "queries": [
            {
                "role": "user",
                "content": "Extract emails from: Contact john@test.com or jane@example.org for details.",
            },
            {
                "role": "user",
                "content": "Extract phone numbers from: Call 555-1234 or (123) 456-7890 for support.",
            },
        ],
    },
    {
        "name": "Code Gen",
        "queries": [
            {"role": "user", "content": "Write a Python function that returns the factorial of n."},
            {
                "role": "user",
                "content": "Write a Python function to check if a string is a palindrome.",
            },
            {
                "role": "user",
                "content": "Write a Python function to sort a list using bubble sort.",
            },
        ],
    },
    {
        "name": "Knowledge Q&A",
        "queries": [
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "user", "content": "Who invented Python?"},
            {"role": "user", "content": "What is the speed of light?"},
            {"role": "user", "content": "What is machine learning?"},
        ],
    },
    {
        "name": "Algebra",
        "queries": [
            {"role": "user", "content": "Solve 2x + 3 = 7"},
            {"role": "user", "content": "Solve 3x - 5 = 16"},
            {"role": "user", "content": "Solve x^2 - 5x + 6 = 0"},
        ],
    },
    {
        "name": "Translation",
        "queries": [
            {"role": "user", "content": "Translate to Spanish: hello and goodbye"},
            {"role": "user", "content": "Translate to French: thank you and yes"},
        ],
    },
    {
        "name": "Unit Conversion",
        "queries": [
            {"role": "user", "content": "Convert 100 feet to meters"},
            {"role": "user", "content": "Convert 25 Celsius to Fahrenheit"},
        ],
    },
]


def cmd_bench(n_queries: int):
    """Run a comprehensive benchmark: engine-only vs full pipeline."""
    from efficient.local_engine import LocalEngine

    client = Client()
    engine = LocalEngine()

    print("\nEfficient AI — Benchmark")
    print("=" * 70)

    # ── Part 1: Engine-only (always available, zero cost) ──
    print("\n  ENGINE-ONLY (deterministic, no network, no model)")
    print("  " + "-" * 66)
    print(
        f"  {'Category':<18} {'#':<3} {'Intent':<16} {'Latency':<10} {'OK':<4} {'Response (truncated)'}"
    )
    print("  " + "-" * 100)

    engine_times = []
    engine_handled = 0
    engine_total = 0

    for category in _BENCH_CATEGORIES:
        for i, query in enumerate(category["queries"]):
            engine_total += 1
            try:
                decision = client.router.route([{"role": "user", "content": query}])
                intent = decision.intent
                complexity = decision.complexity
            except Exception:
                intent, complexity = "unknown", "unknown"

            start = time.time()
            engine_resp = engine.generate(
                messages=[{"role": "user", "content": query}], intent=intent, complexity=complexity
            )
            elapsed_ms = (time.time() - start) * 1000
            engine_times.append(elapsed_ms)

            ok = "✓" if engine_resp.handled else "✗"
            if engine_resp.handled:
                engine_handled += 1
                preview = engine_resp.content[:55].replace("\n", " ")
            else:
                preview = "(would escalate)"

            print(
                f"  {category['name']:<18} {i + 1:<3} {intent:<16} {elapsed_ms:<8.2f}ms {ok:<4} {preview}"
            )

    print("\n  " + "─" * 66)
    avg_e = sum(engine_times) / len(engine_times) if engine_times else 0
    min_e = min(engine_times) if engine_times else 0
    max_e = max(engine_times) if engine_times else 0
    rate = engine_handled / engine_total * 100 if engine_total else 0

    print("  Engine Summary:")
    print(f"    Queries:     {engine_total}")
    print(f"    Handled:     {engine_handled}/{engine_total} ({rate:.0f}%)")
    print(f"    Avg latency: {avg_e:.3f}ms")
    print(f"    Min latency: {min_e:.3f}ms")
    print(f"    Max latency: {max_e:.3f}ms")
    print(f"    Total time:  {sum(engine_times):.2f}ms")
    print("    Cost:        $0.0000")

    # ── Part 2: Full pipeline (engine → Ollama → cloud) ──
    print("\n\n  FULL PIPELINE (engine → Ollama → cloud)")
    print("  " + "-" * 66)
    print(
        f"  {'Category':<18} {'#':<3} {'Provider':<10} {'Model':<22} {'Latency':<10} {'Cost':<10} {'Cached'}"
    )
    print("  " + "-" * 95)

    pipeline_times = []
    pipeline_costs = []
    providers = {"engine": 0, "ollama": 0, "cloud": 0, "cache": 0}
    pipeline_total = 0

    # Clear cache for fair benchmark
    try:
        if client.cache:
            client.cache.clear()
    except Exception:
        pass

    for category in _BENCH_CATEGORIES:
        for i, query in enumerate(category["queries"]):
            pipeline_total += 1
            try:
                start = time.time()
                resp = client.chat(messages=[{"role": "user", "content": query}])
                elapsed_ms = (time.time() - start) * 1000
                pipeline_times.append(elapsed_ms)
                pipeline_costs.append(resp.cost)
                providers[resp.provider] += 1
                if resp.cache_hit:
                    providers["cache"] += 1

                cached = "yes" if resp.cache_hit else "no"
                print(
                    f"  {category['name']:<18} {i + 1:<3} {resp.provider:<10} "
                    f"{resp.model[:22]:<22} {elapsed_ms:<8.0f}ms ${resp.cost:<9.6f} {cached}",
                )
            except Exception as e:
                print(f"  {category['name']:<18} {i + 1:<3} ERROR: {str(e)[:60]}")

    print("\n  " + "─" * 66)
    avg_p = sum(pipeline_times) / len(pipeline_times) if pipeline_times else 0
    total_cost = sum(pipeline_costs)

    print("  Pipeline Summary:")
    print(f"    Queries:     {pipeline_total}")
    print(f"    Avg latency: {avg_p:.1f}ms")
    print(f"    Total cost:  ${total_cost:.4f}")
    print(f"    By provider: {', '.join(f'{k}={v}' for k, v in providers.items() if v > 0)}")

    # ── Part 3: Comparison ──
    print("\n\n  COMPARISON")
    print("  " + "-" * 66)
    print(f"  {'Metric':<30} {'Engine-only':<20} {'Full pipeline'}")
    print("  " + "-" * 66)
    print(f"  {'Total queries':<30} {engine_total:<20} {pipeline_total}")
    print(f"  {'Avg latency (ms)':<30} {avg_e:<20.3f} {avg_p:.1f}")
    print(f"  {'Total cost':<30} {'$0.0000':<20} ${total_cost:.4f}")
    print(f"  {'Engine handle rate':<30} {f'{rate:.0f}%':<20} {'—'}")
    print(f"  {'Data center queries':<30} {'0':<20} {providers.get('cloud', 0)}")
    print()

    if rate >= 80:
        print(f"  ✓ Engine handles {rate:.0f}% of queries — target met!")
    else:
        print(f"  → Engine handles {rate:.0f}% of queries — room to expand engine capabilities.")

    if total_cost == 0:
        print("  ✓ Zero cost — all queries handled locally.")
    else:
        print(f"  → ${total_cost:.4f} spent on cloud fallback.")

    print("\n" + "=" * 70)


def cmd_serve(host: str, port: int, wallet: str, network: str):
    """Start the x402-enabled OpenAI-compatible proxy server."""
    from efficient.proxy import run_server

    run_server(host=host, port=port, wallet_address=wallet, network=network)


if __name__ == "__main__":
    main()
