import requests
import pandas as pd
from pandas.testing import assert_frame_equal
from langgraph.graph import StateGraph, END
import argparse
import pdfplumber
import os
import subprocess
import re
import sys
import pytest


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaSyAJsAiNg0ANu12AqWraZWKGCUa8uZ3_njA"


class AgentState(dict):
    pdf_path: str
    expected_csv_path: str
    code: str
    result: str
    error: str
    counter: int


def get_pdf_preview(pdf_path: str):
    preview_lines = []
    max_lines = 10

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.splitlines():
                    preview_lines.append(line)
                    if len(preview_lines) >= max_lines:
                        return "\n".join(preview_lines)
    return "\n".join(preview_lines) if preview_lines else "[No text found]"


def send_to_llm(prompt: str):
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    headers = {
        "Content-Type": "application/json",
    }

    response = requests.post(GEMINI_ENDPOINT, json=data, headers=headers)
    response = response.json()
    if "error" in response:
        raise Exception(response["error"])
    
    output_text = response["candidates"][0]["content"]["parts"][0]["text"]
    cleaned_text = re.sub(r"^```[a-zA-Z]*\n?", "", output_text.strip())
    cleaned_text = re.sub(r"```$", "", cleaned_text.strip())
    return cleaned_text


def planner_node(state: AgentState):
    state["counter"] = state.get("counter", 0) + 1
    error = state.get("error", "")
    pdf_path = state["pdf_path"]
    print(f"PDF Path: {pdf_path}")
    print(f"Error: {error}")

    pdf_data = get_pdf_preview(pdf_path)

    output_csv_path = "custom_parser/result.csv"

    prompt = open("prompt.txt", "r").read().replace("{pdf_path}", pdf_path).replace("{pdf_data}", pdf_data).replace("{output_csv_path}", output_csv_path).replace("{error}", error)
    res = send_to_llm(prompt)
    state["code"] = res
    return state


def coder_node(state: AgentState):
    code = state.get("code", "")

    if not code.strip():
        state["error"] = "No code generated."
        return state

    try:
        path = "custom_parser/icici_parser.py"
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open("custom_parser/icici_parser.py", "w") as f:
            f.write(code)

        result = subprocess.run(
            [sys.executable, path], capture_output=True, text=True, timeout=100
        )

        print(result)

        if result.returncode != 0:
            state["error"] = f"Execution failed: {result.stderr}"
            print(f"Execution failed: {result.stderr}")
        else:
            state["result"] = result.stdout
            print(f"Execution succeeded: {result.stdout}")

    except Exception as e:
        print(e)

    return state


def tester_node(state: AgentState):
    output_csv = pd.read_csv("custom_parser/result.csv")
    expected_csv = pd.read_csv(state["expected_csv_path"])

    try:
        assert_frame_equal(output_csv, expected_csv)
        state["success"] = True
        print("Test passed")
        return state

    except Exception as e:
        state["success"] = False
        print("Test failed")
        return state


def define_workflow(pdf_path_var: str, expected_csv_path: str):
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("tester", tester_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "coder")
    workflow.add_edge("coder", "tester")

    workflow.add_conditional_edges(
        "tester",
        lambda state: "end"
        if state.get("success") or state.get("counter", 0) >= 3
        else "planner",
        {"end": END, "planner": "planner"},
    )

    app = workflow.compile()

    print(pdf_path_var)

    result = app.invoke(
        {"pdf_path": pdf_path_var, "expected_csv_path": expected_csv_path}
    )

    return result


def main():
    parser = argparse.ArgumentParser(description="Accept Bank PDF")
    parser.add_argument("--target", required=True, help="target PDF")
    args = parser.parse_args()

    target_pdf = args.target
    print(target_pdf)

    pdf_path = f"""data/icici/{target_pdf} sample.pdf"""
    expected_csv_path = "data/icici/result.csv"

    result = define_workflow(pdf_path, expected_csv_path)

    print("Expected CSV Path: ", result["expected_csv_path"])
    print("Result CSV Path: "+ "custom_parser/result.csv")
    print("Reuslt took " + str(result["counter"]) + " iterations")



if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(pytest.main(["-q"]))
    else:
        main()