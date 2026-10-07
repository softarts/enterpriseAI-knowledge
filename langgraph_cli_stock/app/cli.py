"""Command-line interface for the LangGraph stock assistant."""

import json
import logging
import sys
from pathlib import Path

from .config import get_llm_config, get_log_dir, get_user_id
from .graph import get_graph, run_agent
from .logging_config import setup_logging
from .memory import create_memory_manager
from .trace import generate_trace_id
from .tools import get_tool_names


class CLI:
    """CLI application for stock assistant."""
    
    def __init__(self, user_id: str):
        """Initialize CLI with user ID."""
        self.user_id = user_id
        self.memory = create_memory_manager(user_id)
        self.conversation_history = []
        self.logger = None
        
    def print_welcome(self):
        """Print welcome message with configuration info."""
        # Get config
        config = get_llm_config()
        log_dir = get_log_dir()
        
        print("\n" + "=" * 50)
        print("LangGraph CLI Stock Assistant")
        print("=" * 50)
        print(f"User ID:      {self.user_id}")
        print(f"LLM Model:    {config['model']}")
        print(f"LLM URL:      {config['base_url']}")
        print(f"Tools:        {', '.join(get_tool_names())}")
        print(f"Log Dir:      {log_dir}")
        print("=" * 50)
        print("\nType /help for available commands\n")
    
    def print_help(self):
        """Print help message."""
        print("""
Available commands:
  /help     - Show this help message
  /history  - Show conversation history
  /clear    - Clear conversation history
  /exit     - Exit the application
  /quit     - Exit the application
        """)
    
    def print_history(self):
        """Print conversation history."""
        if not self.conversation_history:
            print("No conversation history.")
            return
        
        print("\nConversation History:")
        print("-" * 40)
        for i, msg in enumerate(self.conversation_history, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:100]
            print(f"{i}. {role}: {content}...")
        print("-" * 40 + "\n")
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        print("Conversation history cleared.")
    
    def handle_command(self, user_input: str) -> bool:
        """
        Handle built-in CLI commands.
        
        Returns:
            True if command was handled, False otherwise
        """
        cmd = user_input.strip().lower()
        
        if cmd == "/help":
            self.print_help()
            return True
        elif cmd in ["/exit", "/quit"]:
            print("Goodbye!")
            sys.exit(0)
        elif cmd == "/history":
            self.print_history()
            return True
        elif cmd == "/clear":
            self.clear_history()
            return True
        
        return False
    
    def run(self):
        """Run the CLI application."""
        self.print_welcome()
        
        while True:
            try:
                user_input = input("\n> ").strip()
                
                if not user_input:
                    continue
                
                # Check for commands
                if user_input.startswith("/"):
                    if self.handle_command(user_input):
                        continue
                    else:
                        print(f"Unknown command: {user_input}")
                        print("Type /help for available commands.")
                        continue
                
                # Generate trace_id for this turn
                trace_id = generate_trace_id()
                
                # Set up logging for this trace
                self.logger = setup_logging(trace_id)
                
                # Log user input
                self.logger.info(
                    f"User input received",
                    extra={
                        "trace_id": trace_id,
                        "event_type": "user_input",
                        "component": "cli",
                        "payload": {
                            "user_id": self.user_id,
                            "input": user_input
                        }
                    }
                )
                
                # Run the agent
                try:
                    response = run_agent(
                        user_input=user_input,
                        user_id=self.user_id,
                        trace_id=trace_id,
                        thread_id=self.user_id  # Use user_id as thread_id
                    )
                    
                    print(f"\n{response}\n")
                    
                    # Add to history
                    self.conversation_history.append(
                        {"role": "user", "content": user_input}
                    )
                    self.conversation_history.append(
                        {"role": "assistant", "content": response}
                    )
                    
                except Exception as e:
                    print(f"\nError: {e}\n")
                    self.logger.error(
                        f"Error processing request: {e}",
                        extra={
                            "trace_id": trace_id,
                            "event_type": "error",
                            "component": "cli",
                            "payload": {"error": str(e)}
                        }
                    )
                    
            except KeyboardInterrupt:
                print("\n\nInterrupted. Type /exit to quit.")
                continue
            except EOFError:
                print("\nGoodbye!")
                sys.exit(0)


def main():
    """Main entry point for CLI."""
    # Get user ID from command line
    user_id = get_user_id()
    
    # Create and run CLI
    cli = CLI(user_id)
    cli.run()


if __name__ == "__main__":
    main()