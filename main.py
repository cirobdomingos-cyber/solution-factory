"""Solution Factory — from ideation to execution in one pipeline.

A multi-agent system that takes a domain, idea, or problem statement
and produces a complete solution blueprint: market opportunity analysis,
product concepts, validation, architecture (with AI agent & human roles),
execution plan, and critical review.

Usage:
    py -3.12 main.py "AI-powered invoice processing for small businesses"
    py -3.12 main.py --interactive
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from rich.console import Console

from orchestrator import SolutionOrchestrator
from utils.export import export_results

console = Console()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy HTTP logs unless verbose
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("anthropic").setLevel(logging.WARNING)


def interactive_mode() -> None:
    """Run the pipeline interactively — prompt the user for input."""
    console.print(
        "\n[bold cyan]Solution Factory[/bold cyan] — Interactive Mode\n"
        "Enter a domain, idea, or problem statement.\n"
        "The pipeline will analyze it and produce a complete solution blueprint.\n"
    )

    while True:
        try:
            user_input = console.input("[bold green]> [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        orchestrator = SolutionOrchestrator()
        result = orchestrator.run(user_input)

        # Export results
        filepath = export_results(result)
        console.print(f"\n[dim]Full results exported to: {filepath}[/dim]\n")


def single_run(prompt: str, export_path: str | None = None) -> None:
    """Run the pipeline once with a given prompt."""
    orchestrator = SolutionOrchestrator()
    result = orchestrator.run(prompt)

    filepath = export_results(result, output_dir=export_path or "output")
    console.print(f"\n[dim]Full results exported to: {filepath}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Solution Factory — AI-powered ideation-to-execution pipeline",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Domain, idea, or problem statement to process",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode (prompt loop)",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory for exported results (default: output)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.interactive:
        interactive_mode()
    elif args.prompt:
        single_run(args.prompt, args.output)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
