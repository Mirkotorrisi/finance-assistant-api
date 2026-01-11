import datetime
import json
import sys
from enum import Enum
from typing import Dict, List, Optional, TypedDict, Union
import speech_recognition as sr
from dotenv import load_dotenv
from openai import OpenAI
import os

from pydantic import BaseModel
from langgraph.graph import StateGraph, END

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# Global Debug Flag
DEBUG_MODE = "--debug" in sys.argv

# --- BUSINESS LOGIC (MCP SIMULATION) ---

class FinanceMCP:
    """
    Simulates a Model Context Protocol (MCP) server for Personal Finance.
    Provides APIs for the LLM to interact with the financial data.
    """
    def __init__(self, initial_transactions: List[dict]):
        self.transactions = initial_transactions
        self._set_next_id()

    def _set_next_id(self):
        if not self.transactions:
            self.next_id = 1
        else:
            self.next_id = max(t.get("id", 0) for t in self.transactions) + 1

    def list_transactions(self, category: str = None, start_date: str = None, end_date: str = None) -> List[dict]:
        results = self.transactions
        if category:
            results = [t for t in results if t["category"].lower() == category.lower()]
        if start_date:
            results = [t for t in results if t["date"] >= start_date]
        if end_date:
            results = [t for t in results if t["date"] <= end_date]
        return results

    def add_transaction(self, amount: float, category: str, description: str, date: str = None) -> dict:
        if not date:
            date = datetime.date.today().isoformat()
        new_entry = {
            "id": self.next_id,
            "date": date,
            "amount": amount,
            "category": category,
            "description": description
        }
        self.transactions.append(new_entry)
        self.next_id += 1
        return new_entry

    def delete_transaction(self, transaction_id: int) -> bool:
        original_count = len(self.transactions)
        self.transactions = [t for t in self.transactions if t.get("id") != transaction_id]
        return len(self.transactions) < original_count

    def get_balance(self) -> float:
        return sum(t["amount"] for t in self.transactions)

# --- DATA INITIALIZATION ---

def get_initial_data():
    today = datetime.date.today()
    return [
        {"id": 1, "date": (today - datetime.timedelta(days=6)).isoformat(), "amount": -50.0, "category": "food", "description": "Grocery shopping"},
        {"id": 2, "date": (today - datetime.timedelta(days=5)).isoformat(), "amount": -15.0, "category": "transport", "description": "Bus ticket"},
        {"id": 3, "date": (today - datetime.timedelta(days=4)).isoformat(), "amount": -1200.0, "category": "rent", "description": "Monthly rent"},
        {"id": 4, "date": (today - datetime.timedelta(days=3)).isoformat(), "amount": -30.0, "category": "food", "description": "Dinner out"},
        {"id": 5, "date": (today - datetime.timedelta(days=2)).isoformat(), "amount": 2000.0, "category": "income", "description": "Salary"},
        {"id": 6, "date": (today - datetime.timedelta(days=1)).isoformat(), "amount": -45.0, "category": "food", "description": "Lunch with friends"},
        {"id": 7, "date": today.isoformat(), "amount": -10.0, "category": "transport", "description": "Parking"},
    ]

# Global MCP instance
mcp_server = FinanceMCP(get_initial_data())

# --- DOMAIN MODELS ---

class Action(str, Enum):
    LIST = "list"
    ADD = "add"
    DELETE = "delete"
    BALANCE = "balance"
    UNKNOWN = "unknown"

class FinancialParameters(BaseModel):
    category: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    transaction_id: Optional[int] = None

class UserInput(BaseModel):
    text: str
    is_audio: bool = False

# --- LANGGRAPH STATE DEFINITION ---

class FinanceState(TypedDict):
    input: UserInput
    transcription: Optional[str]
    action: Action
    parameters: FinancialParameters
    query_results: Optional[Union[List[dict], dict, float, bool]]
    response: Optional[str]
    history: List[str]

class LLMNLUResponse(BaseModel):
    action: Action
    parameters: FinancialParameters

# --- CORE COMPONENTS (NODES) ---

def asr_node(state: FinanceState) -> Dict:
    user_input = state["input"]
    if user_input.is_audio:
        recognizer = sr.Recognizer()
        try:
            # Note: user_input.text contains path to wav file when is_audio is True
            with sr.AudioFile(user_input.text) as source:
                audio = recognizer.record(source)
            transcription = recognizer.recognize_google(audio)
        except Exception as e:
            print(f"--- ASR Error: {e} ---")
            transcription = ""
    else:
        transcription = user_input.text
    return {"transcription": transcription}

def nlu_node(state: FinanceState) -> Dict:
    text = state["transcription"]
    if not text:
        return {"action": Action.UNKNOWN, "parameters": FinancialParameters()}

    today = datetime.date.today().isoformat()
    monday = (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())).isoformat()

    system_prompt = f"""
You are an NLU engine for a personal finance assistant.
Today's date is {today}. The current week started on Monday {monday}.
Extract the user's intended action and parameters.

Actions:
- list: For querying transactions (by category, date range, or all).
- add: For adding a new transaction. (Requires amount, category, description). 
       Note: Spending should be negative amounts, income positive.
- delete: For removing a transaction (requires an ID).
- balance: For checking the current total balance.

Parameters:
- category: Any string (e.g., 'food', 'salary', 'fun').
- start_date / end_date: ISO 8601 format (YYYY-MM-DD). Resolve relative terms like 'this week', 'last 3 days', 'yesterday' based on {today}.
- amount: Float.
- description: String.
- transaction_id: Integer if specified.

Respond ONLY in valid JSON matching the schema.
"""
    user_prompt = f"User input: {text}"

    if DEBUG_MODE:
        print("\n[DEBUG] NLU - System Prompt:", system_prompt)
        print("[DEBUG] NLU - User Prompt:", user_prompt)

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        raw_response = completion.choices[0].message.content
        if DEBUG_MODE:
            print("[DEBUG] NLU - Raw Response:", raw_response)
            
        parsed = LLMNLUResponse.model_validate_json(raw_response)
        action = parsed.action
        params = parsed.parameters
    except Exception as e:
        print(f"--- NLU Error: {e} ---")
        action = Action.UNKNOWN
        params = FinancialParameters()

    print(f"--- LLM NLU: Action={action.value}, Params={params.model_dump(exclude_none=True)} ---")
    return {"action": action, "parameters": params}

def query_node(state: FinanceState) -> Dict:
    action = state["action"]
    params = state["parameters"]
    results = None

    if action == Action.LIST:
        results = mcp_server.list_transactions(params.category, params.start_date, params.end_date)
    elif action == Action.ADD:
        if params.amount is not None and params.category and params.description:
            results = mcp_server.add_transaction(params.amount, params.category, params.description)
        else:
            results = {"error": "Missing parameters (amount, category, or description) for adding transaction"}
    elif action == Action.DELETE:
        if params.transaction_id:
            results = mcp_server.delete_transaction(params.transaction_id)
        else:
            results = {"error": "Transaction ID required for deletion"}
    elif action == Action.BALANCE:
        results = mcp_server.get_balance()
    
    return {"query_results": results}

def generator_node(state: FinanceState) -> Dict:
    results = state["query_results"]
    action = state["action"]
    
    current_context = {
        "action": action,
        "parameters": state["parameters"].model_dump(exclude_none=True),
        "results": results,
        "current_balance": mcp_server.get_balance(),
        "today": datetime.date.today().isoformat()
    }

    system_instr = "You are a professional personal finance assistant. Generate a clear, friendly, and professional response based on the provided data. If an entry was added or deleted, confirm the action and show the new balance. If querying, summarize the findings naturally."
    user_instr = f"User request: {state['transcription']}\nContext Data: {json.dumps(current_context)}"

    if DEBUG_MODE:
        print("\n[DEBUG] Generator - System Instruction:", system_instr)
        print("[DEBUG] Generator - User Instruction:", user_instr)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instr},
            {"role": "user", "content": user_instr},
        ],
        temperature=0.3
    )

    response = completion.choices[0].message.content
    if DEBUG_MODE:
        print("[DEBUG] Generator - Raw Response:", response)
    new_history = state["history"] + [f"User: {state['transcription']}", f"Assistant: {response}"]
    
    print(f"--- Generator: Developed response ---")
    return {"response": response, "history": new_history}

# --- GRAPH DEFINITION ---

def create_assistant_graph():
    workflow = StateGraph(FinanceState)
    workflow.add_node("asr", asr_node)
    workflow.add_node("nlu", nlu_node)
    workflow.add_node("query", query_node)
    workflow.add_node("generator", generator_node)

    workflow.set_entry_point("asr")
    workflow.add_edge("asr", "nlu")
    workflow.add_edge("nlu", "query")
    workflow.add_edge("query", "generator")
    workflow.add_edge("generator", END)
    return workflow.compile()



# --- INTERACTIVE CLI ---
def main():
    print("====================================================")
    print("   Professional MCP Finance Assistant (LLM-Powered)  ")
    print("====================================================")
    print("Capabilities:")
    print(" - List: 'Show my spending on food this week'")
    print(" - Add: 'I spent 45.50 on gadgets today'")
    print(" - Balance: 'What is my total balance right now?'")
    print(" - Delete: 'Delete transaction 4'")
    print(" - Hybrid: 'How much did I spend in the last 48 hours?'")
    print("\nSimulation Tips:")
    print(" - Prefix with 'audio:' for file-based transcription (requires .wav)")
    print(" - Standard text input works directly.")
    print("----------------------------------------------------\n")

    assistant_graph = create_assistant_graph()
    current_history = []

    while True:
        try:
            u_input = input("You: ").strip()
        except EOFError:
            break
        
        if u_input.lower() in ["exit", "quit", "bye"]:
            print("\nAssistant: Goodbye! Tracking your finances is the first step to wealth.")
            break
        
        if not u_input:
            continue
        
        is_audio = False
        text_to_process = u_input
        if u_input.lower().startswith("audio:"):
            is_audio = True
            text_to_process = u_input[6:].strip()
        
        state: FinanceState = {
            "input": UserInput(text=text_to_process, is_audio=is_audio),
            "transcription": None,
            "action": Action.UNKNOWN,
            "parameters": FinancialParameters(),
            "query_results": None,
            "response": None,
            "history": current_history
        }
        
        try:
            result = assistant_graph.invoke(state)
            current_history = result["history"]
            print(f"\nAssistant: {result['response']}\n")
        except Exception as e:
            print(f"\nAssistant: Oops, I ran into a technical issue: {e}\n")

if __name__ == "__main__":
    main()
