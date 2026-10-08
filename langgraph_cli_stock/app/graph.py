"""LangGraph agent implementation."""

import json
import logging
from typing import Any, Dict, List, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .llm_client import get_llm_client
from .tools import AVAILABLE_TOOLS, execute_tool, get_tool_names
from .state import AgentState, ToolCall


def _parse_tool_arguments(arguments: Any) -> Dict[str, Any]:
    """Parse tool arguments supplied as a JSON string or dictionary."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise ValueError("Tool-call arguments must contain valid JSON") from error

    if not isinstance(arguments, dict):
        raise TypeError("Tool-call arguments must be a JSON object")

    return arguments


# Define the graph nodes
def model_node(state: AgentState) -> AgentState:
    """Call the LLM to generate a response."""
    logger = logging.getLogger(f"trace_{state.trace_id}")
    
    extra = {
        "trace_id": state.trace_id,
        "event_type": "graph_node",
        "component": "graph",
        "payload": {
            "node": "model_node",
            "input_messages_count": len(state.messages)
        }
    }
    logger.info("Entering model_node", extra=extra)
    
    # Get LLM client
    client = get_llm_client()
    client.set_trace_context(state.trace_id, logger)
    
    # Prepare messages for API
    messages = []
    for msg in state.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Handle tool calls
        if msg.get("tool_calls"):
            messages.append({
                "role": role,
                "content": content,
                "tool_calls": msg.get("tool_calls")
            })
        elif msg.get("tool_call_id"):
            messages.append({
                "role": role,
                "content": content,
                "tool_call_id": msg.get("tool_call_id")
            })
        else:
            messages.append({"role": role, "content": content})
    
    # Add system message
    system_message = {
        "role": "system",
        "content": "You are a helpful AI assistant. When users ask about stock prices, use the stock_price tool to get the data."
    }
    
    # Call LLM
    try:
        response = client.chat(
            messages=[system_message] + messages,
            tools=AVAILABLE_TOOLS if get_tool_names() else None
        )
        
        # Extract response
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            
            # Handle tool calls
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                state.tool_calls = [
                    ToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("function", {}).get("name", ""),
                        arguments=_parse_tool_arguments(
                            tc.get("function", {}).get("arguments", {})
                        )
                    )
                    for tc in tool_calls
                ]
                
                extra["payload"]["tool_calls"] = [tc.name for tc in state.tool_calls]
                logger.info(f"Model requested tools: {extra['payload']['tool_calls']}", extra=extra)
            else:
                # No tool calls, this is the final answer
                state.tool_calls = []
                state.final_answer = message.get("content", "")
                logger.info("Model provided final answer", extra=extra)
        
        return state
        
    except Exception as e:
        logger.error(f"Error in model_node: {e}", extra={
            "trace_id": state.trace_id,
            "event_type": "error",
            "component": "graph",
            "payload": {"node": "model_node", "error": str(e)}
        })
        raise


def tool_node(state: AgentState) -> AgentState:
    """Execute tools and return results."""
    logger = logging.getLogger(f"trace_{state.trace_id}")
    
    extra = {
        "trace_id": state.trace_id,
        "event_type": "graph_node",
        "component": "graph",
        "payload": {
            "node": "tool_node",
            "tool_calls_count": len(state.tool_calls)
        }
    }
    logger.info("Entering tool_node", extra=extra)
    
    tool_results = []
    
    for tool_call in state.tool_calls:
        tool_name = tool_call.name
        tool_args = tool_call.arguments
        
        logger.info(f"Executing tool: {tool_name}", extra={
            "trace_id": state.trace_id,
            "event_type": "tool_execution",
            "component": "graph",
            "payload": {"tool": tool_name, "arguments": tool_args}
        })
        
        # Execute the tool
        result = execute_tool(tool_name, tool_args, logger)
        
        tool_results.append({
            "tool_call_id": tool_call.id,
            "tool_name": tool_name,
            "result": result
        })
    
    state.tool_results = tool_results
    
    # Add tool results as messages
    for tool_result in tool_results:
        state.messages.append({
            "role": "tool",
            "tool_call_id": tool_result["tool_call_id"],
            "content": str(tool_result["result"])
        })
    
    return state


def should_continue(state: AgentState) -> Literal["tools", "END"]:
    """Determine whether to continue or end the graph."""
    logger = logging.getLogger(f"trace_{state.trace_id}")
    
    if state.tool_calls:
        logger.info("Continuing to tools", extra={
            "trace_id": state.trace_id,
            "event_type": "graph_decision",
            "component": "graph",
            "payload": {"decision": "continue_to_tools"}
        })
        return "tools"
    
    logger.info("Ending graph", extra={
        "trace_id": state.trace_id,
        "event_type": "graph_decision",
        "component": "graph",
        "payload": {"decision": "end"}
    })
    return END


def create_graph():
    """Create and compile the LangGraph."""
    
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", model_node)
    workflow.add_node("tools", tool_node)
    
    # Set entry point
    workflow.set_entry_point("agent")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    
    # Add edge from tools back to agent
    workflow.add_edge("tools", "agent")
    
    # Create checkpointer
    checkpointer = MemorySaver()
    
    # Compile the graph
    return workflow.compile(checkpointer=checkpointer)


# Global graph instance
_graph = None


def get_graph() -> StateGraph:
    """Get the compiled LangGraph instance."""
    global _graph
    if _graph is None:
        _graph = create_graph()
    return _graph


def run_agent(user_input: str, user_id: str, trace_id: str, thread_id: str = None) -> str:
    """
    Run the agent with user input.
    
    Args:
        user_input: User's input message
        user_id: User ID for memory isolation
        trace_id: Trace ID for this conversation turn
        thread_id: Thread ID for conversation continuity
        
    Returns:
        The final answer from the agent
    """
    logger = logging.getLogger(f"trace_{trace_id}")
    
    # Log user input
    extra = {
        "trace_id": trace_id,
        "event_type": "user_input",
        "component": "graph",
        "payload": {
            "user_id": user_id,
            "input": user_input,
            "thread_id": thread_id
        }
    }
    logger.info(f"User input: {user_input[:100]}...", extra=extra)
    
    # Prepare initial state
    initial_state = AgentState(
        messages=[{"role": "user", "content": user_input}],
        user_id=user_id,
        trace_id=trace_id
    )
    
    # Use thread_id for checkpointing
    config = {"configurable": {"thread_id": thread_id or trace_id}}
    
    # Run the graph
    try:
        result = get_graph().invoke(initial_state, config)
        final_answer = result.get("final_answer")
        tool_calls = result.get("tool_calls", [])
        tool_results = result.get("tool_results", [])
        
        # Log final response
        logger.info("Agent completed", extra={
            "trace_id": trace_id,
            "event_type": "final_response",
            "component": "graph",
            "payload": {
                "final_answer": final_answer,
                "has_tool_calls": bool(tool_calls),
                "tool_results_count": len(tool_results)
            }
        })
        
        return final_answer or "No response generated"
        
    except Exception as e:
        logger.error(f"Agent error: {e}", extra={
            "trace_id": trace_id,
            "event_type": "error",
            "component": "graph",
            "payload": {"error": str(e)}
        })
        raise