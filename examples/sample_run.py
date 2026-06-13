"""Quick demo: run a single scenario, evaluate it, and print results.

Usage:
    python examples/sample_run.py

Requires ANTHROPIC_API_KEY to be set.
"""

import asyncio
import json

from dotenv import load_dotenv

load_dotenv()

from agent_evaluator.judge import AnthropicJudge
from agent_evaluator.runner import AgentRunner
from scenarios.registry import load_scenario


async def main():
    # Pick a simple scenario
    scenario = load_scenario("weather_lookup")
    print(f"Scenario: {scenario.name}")
    print(f"Query: {scenario.user_query}\n")

    # Run the agent
    runner = AgentRunner()
    print("Running agent...")
    trajectory = await runner.run_scenario(scenario)

    print(f"Steps taken: {len(trajectory.steps)}")
    for step in trajectory.steps:
        status = "ERROR" if step.tool_response.error else "OK"
        print(f"  [{step.step_index}] {step.tool_call.tool_name}({json.dumps(step.tool_call.parameters)}) → {status}")
    print(f"Final answer: {trajectory.final_answer[:200] if trajectory.final_answer else 'None'}...\n")

    # Evaluate the trajectory
    judge = AnthropicJudge()
    print("Evaluating trajectory...")
    result = await judge.evaluate_trajectory(trajectory, scenario)

    print(f"\nOverall score: {result.overall_score:.2f}")
    for score in result.dimension_scores:
        print(f"  {score.dimension:<20} {score.score:.2f}  {score.reasoning}")

    # Save outputs
    runner.save_trajectory(trajectory, "results/demo_trajectory.json")
    with open("results/demo_eval.json", "w") as f:
        f.write(result.model_dump_json(indent=2))
    print("\nSaved to results/demo_trajectory.json and results/demo_eval.json")


if __name__ == "__main__":
    asyncio.run(main())
