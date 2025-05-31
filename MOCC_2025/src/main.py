import os
from typing import Dict, Tuple
import time

from src.agents import LLM_Agent, Reasoning_Agent
from src.lean_runner import execute_lean_code

LeanCode = Dict[str, str]

def main_workflow(problem_description: str, task_lean_code: str = "") -> LeanCode:
    """
    A 3‐round generate→verify→refine loop using LLM_Agent and Reasoning_Agent.
    Returns {"code": <implementation>, "proof": <proof>} for the task.
    """
    # Initialize agents
    llm = LLM_Agent(model="gpt-4o")
    reasoner = Reasoning_Agent(model="o3-mini")

    code_snippet = ""
    proof_snippet = ""
    last_error = ""

    for round_idx in range(3):
        # Build messages
        if round_idx == 0:
            system_msg = {
                "role": "system",
                "content": "You are a Lean 4 expert. Fill the implementation and proof placeholders."
            }
            user_msg = {
                "role": "user",
                "content": (
                    f"Problem Description:\n{problem_description}\n\n"
                    f"Lean Template (with {{code}} and {{proof}}):\n{task_lean_code}"
                )
            }
            messages = [system_msg, user_msg]

            # Call LLM with basic retry on exception
            try:
                response = llm.get_response(messages)
            except Exception as e:
                last_error = str(e)
                time.sleep(5)
                response = llm.get_response(messages)
        else:
            # Provide the last error for refinement
            system_msg = {
                "role": "system",
                "content": (
                    "You are a Lean 4 expert. The previous code failed with an error. "
                    "Please fix the implementation or proof accordingly."
                )
            }
            user_msg = {
                "role": "user",
                "content": (
                    f"Problem Description:\n{problem_description}\n\n"
                    f"Lean Template:\n{task_lean_code}\n\n"
                    f"Last implementation:\n{code_snippet}\n\n"
                    f"Last proof:\n{proof_snippet}\n\n"
                    f"Lean Error Message:\n{last_error}"
                )
            }
            messages = [system_msg, user_msg]

            try:
                response = reasoner.get_response(messages)
            except Exception as e:
                last_error = str(e)
                time.sleep(5)
                response = reasoner.get_response(messages)

        # Extract code and proof from markers
        try:
            code_snippet = response.split("-- << CODE START >>")[1] \
                                     .split("-- << CODE END >>")[0].strip()
            proof_snippet = response.split("-- << PROOF START >>")[1] \
                                      .split("-- << PROOF END >>")[0].strip()
        except Exception:
            # Fallback extraction
            parts = response.split("{{code}}")
            if len(parts) > 1:
                code_snippet = parts[1].split("{{proof}}\n")[0].strip()
                proof_snippet = parts[1].split("{{proof}}\n")[1].strip()

        # Inject into template
        filled = (
            task_lean_code
            .replace("{{code}}", code_snippet)
            .replace("{{proof}}", proof_snippet)
        )

        # Verify with Lean
        success, stderr = execute_lean_code(filled)
        if success:
            return {"code": code_snippet, "proof": proof_snippet}
        else:
            last_error = stderr

    # After 3 attempts, return last try (or sorry)
    return {"code": code_snippet or "sorry", "proof": proof_snippet or "sorry"}


def get_problem_and_code_from_taskpath(task_path: str) -> Tuple[str, str]:
    """Reads description.txt and task.lean from a task directory."""
    with open(os.path.join(task_path, "description.txt"), "r") as f:
        desc = f.read()
    with open(os.path.join(task_path, "task.lean"), "r") as f:
        tmpl = f.read()
    return desc, tmpl


def get_unit_tests_from_taskpath(task_path: str) -> str:
    """Reads tests.lean from a task directory."""
    with open(os.path.join(task_path, "tests.lean"), "r") as f:
        return f.read()


def get_task_lean_template_from_taskpath(task_path: str) -> str:
    """Reads task.lean template from a task directory."""
    with open(os.path.join(task_path, "task.lean"), "r") as f:
        return f.read()


if __name__ == "__main__":
    # Quick debug: python src/main.py tasks/task_id_0
    import sys
    if len(sys.argv) != 2:
        print("Usage: python src/main.py <task_directory>")
        sys.exit(1)
    task_dir = sys.argv[1]
    desc, tmpl = get_problem_and_code_from_taskpath(task_dir)
    result = main_workflow(desc, tmpl)
    print("\n=== Generated CODE ===\n", result["code"])
    print("\n=== Generated PROOF ===\n", result["proof"])
