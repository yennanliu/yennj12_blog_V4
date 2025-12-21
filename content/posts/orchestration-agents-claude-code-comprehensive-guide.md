---
title: "Building Multi-Agent Orchestration Systems with Claude Code"
date: 2025-12-21T10:00:00Z
draft: false
authors: ["yen"]
categories: ["all", "AI", "agent-orchestration", "development-tools"]
tags: ["AI", "claude-code", "agent-orchestration", "multi-agent-systems", "automation", "python", "crewai", "langchain"]
summary: "Comprehensive guide to building multi-agent orchestration systems with Claude Code - learn to coordinate specialized AI agents for complex software development workflows, from architecture design to implementation."
readTime: "22 min"
---

## 🎯 Introduction to Agent Orchestration

### 📋 What is Agent Orchestration?

**Agent Orchestration** is the practice of coordinating multiple specialized AI agents to work together on complex tasks. Instead of relying on a single AI assistant to handle everything, orchestration divides work among specialized agents - each with distinct roles, expertise, and responsibilities.

Think of it like a software development team:
- A **Product Manager** defines requirements and acceptance criteria
- A **Designer** creates UI/UX specifications and wireframes
- A **Backend Engineer** builds APIs and database schemas
- A **Frontend Engineer** implements user interfaces and integrates with APIs

With Claude Code, you can create this entire team using multiple Claude instances, each configured with different system prompts and contexts.

### 🎯 Why Use Agent Orchestration?

**Single Agent Limitations:**
- Struggles with multi-faceted complex tasks
- Context switching between different roles
- Inconsistent expertise across domains
- Difficulty maintaining long-term task coherence

**Multi-Agent Benefits:**
- **Specialization**: Each agent excels in its specific domain
- **Parallel Execution**: Independent agents work simultaneously
- **Clear Boundaries**: Well-defined responsibilities prevent overlap
- **Scalability**: Add new agents without disrupting existing ones
- **Maintainability**: Update agent behavior through isolated prompt changes

### 🏗️ Core Architecture Patterns

#### 1. Hub-and-Spoke (Manager-Worker) Pattern

The recommended approach for most use cases. A central orchestrator manages execution flow and coordinates specialized workers.

```
┌─────────────────────────────────────┐
│     Orchestrator (Manager)          │
│  - Task planning & decomposition    │
│  - Agent coordination                │
│  - Output merging                    │
│  - Conflict resolution              │
└──────────┬─────────────┬────────────┘
           │             │
    ┌──────┴───┐    ┌────┴─────┐
    │          │    │          │
┌───▼───┐  ┌──▼───┐ ┌──▼───┐ ┌▼────┐
│  PM   │  │Design│ │  BE  │ │ FE  │
│ Agent │  │Agent │ │Agent │ │Agent│
└───┬───┘  └──┬───┘ └──┬───┘ └┬────┘
    │         │        │       │
    └─────────┴────────┴───────┘
              │
    ┌─────────▼──────────┐
    │  Shared Workspace  │
    │  (State/Memory)    │
    └────────────────────┘
```

**Key Characteristics:**
- Central controller manages all communication
- Agents never communicate directly
- Shared state serves as communication hub
- Single source of truth for task status

#### 2. Sequential/Chained Pattern

Work flows linearly through specialized agents, with each stage building on previous outputs.

```
User Request
    │
    ▼
┌───────────────┐
│  PM Agent     │ → requirements.md
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Design Agent  │ → design-spec.md
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  BE Agent     │ → api-contract.json
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  FE Agent     │ → components/
└───────┬───────┘
        │
        ▼
   Final Output
```

**Key Characteristics:**
- Linear dependency chain
- Each agent consumes prior outputs
- Clear handoff points
- Deterministic execution order

## 🚀 Building Orchestration Systems with Claude Code

### 🔧 Prerequisites & Setup

**Required Components:**
- **Claude Code CLI** (latest version)
- **Python 3.9+** for orchestration scripts
- **CrewAI or LangChain** (optional, for advanced patterns)
- **Shared workspace** (file system or database)

**Installation:**
```bash
# Create project directory
mkdir claude-orchestration
cd claude-orchestration

# Set up Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install anthropic crewai langchain python-dotenv

# Create project structure
mkdir -p agents/{pm,design,backend,frontend} shared_state logs
```

### 📦 Project Structure

```
claude-orchestration/
├── agents/
│   ├── pm/
│   │   ├── prompt.txt
│   │   └── tools.py
│   ├── design/
│   │   ├── prompt.txt
│   │   └── tools.py
│   ├── backend/
│   │   ├── prompt.txt
│   │   └── tools.py
│   └── frontend/
│       ├── prompt.txt
│       └── tools.py
├── shared_state/
│   ├── requirements.md
│   ├── design-spec.md
│   ├── api-contract.json
│   └── state.json
├── orchestrator.py
├── agent_manager.py
├── config.py
├── requirements.txt
└── .env
```

## 💻 Implementation: Basic Orchestration System

### 1. Configuration Setup

**config.py:**
```python
"""
Configuration for multi-agent orchestration system
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Configuration
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    MODEL = "claude-sonnet-4.5"  # or claude-opus-4.5 for complex tasks

    # Project paths
    PROJECT_ROOT = Path(__file__).parent
    AGENTS_DIR = PROJECT_ROOT / "agents"
    SHARED_STATE_DIR = PROJECT_ROOT / "shared_state"
    LOGS_DIR = PROJECT_ROOT / "logs"

    # Agent configuration
    AGENTS = {
        "pm": {
            "name": "Product Manager",
            "prompt_file": AGENTS_DIR / "pm" / "prompt.txt",
            "output_files": ["requirements.md", "tasks.json"],
            "priority": 1
        },
        "design": {
            "name": "Designer",
            "prompt_file": AGENTS_DIR / "design" / "prompt.txt",
            "output_files": ["design-spec.md", "wireframes.md"],
            "priority": 2,
            "depends_on": ["pm"]
        },
        "backend": {
            "name": "Backend Engineer",
            "prompt_file": AGENTS_DIR / "backend" / "prompt.txt",
            "output_files": ["api-contract.json", "schema.sql"],
            "priority": 2,
            "depends_on": ["pm"]
        },
        "frontend": {
            "name": "Frontend Engineer",
            "prompt_file": AGENTS_DIR / "frontend" / "prompt.txt",
            "output_files": ["components-plan.md", "state-management.md"],
            "priority": 3,
            "depends_on": ["design", "backend"]
        }
    }

    # Orchestration settings
    MAX_ITERATIONS = 5
    PARALLEL_EXECUTION = True
    ENABLE_VALIDATION = True

    # Shared state configuration
    STATE_FILE = SHARED_STATE_DIR / "state.json"
    COMMUNICATION_LOG = LOGS_DIR / "communication.log"

config = Config()
```

### 2. Agent System Prompts

**agents/pm/prompt.txt:**
```
You are a Product Manager Agent in a multi-agent software development system.

## Your Role
- Analyze user requirements and break them into actionable tasks
- Define clear acceptance criteria for each task
- Prioritize features and create development roadmap
- Ensure requirements are unambiguous and testable

## Input
You will receive:
- User's feature request or problem statement
- Project context and constraints

## Output Requirements
You must produce TWO files in the shared workspace:

1. requirements.md:
   - Problem statement
   - User stories with acceptance criteria
   - Functional requirements
   - Non-functional requirements (performance, security, etc.)
   - Technical constraints

2. tasks.json:
   - Structured JSON with task breakdown
   - Dependencies between tasks
   - Priority levels
   - Estimated complexity

## Guidelines
- Be specific and avoid ambiguity
- Think like a product manager, not a developer
- Focus on WHAT needs to be built, not HOW
- Consider edge cases and error scenarios
- Ensure requirements are testable

## Output Format
Write files to: /shared_state/requirements.md and /shared_state/tasks.json
Use markdown for requirements, valid JSON for tasks.
```

**agents/design/prompt.txt:**
```
You are a UI/UX Designer Agent in a multi-agent software development system.

## Your Role
- Create user interface specifications based on requirements
- Design component hierarchy and layout structure
- Define user interaction patterns
- Ensure accessibility and responsive design principles

## Input
You will receive:
- requirements.md from the Product Manager
- Project design constraints

## Output Requirements
You must produce TWO files:

1. design-spec.md:
   - UI component hierarchy
   - Layout specifications (grid, flexbox, etc.)
   - Color scheme and typography
   - Interaction patterns (hover, click, navigation)
   - Responsive breakpoints
   - Accessibility considerations (ARIA labels, keyboard nav)

2. wireframes.md:
   - ASCII art or mermaid diagrams of key screens
   - Component relationships
   - Data flow visualization
   - User journey maps

## Guidelines
- Design with frontend implementation in mind
- Specify reusable components
- Consider mobile-first design
- Include loading and error states
- Think about component composition

## Output Format
Write files to: /shared_state/design-spec.md and /shared_state/wireframes.md
Use markdown with mermaid diagrams where helpful.
```

**agents/backend/prompt.txt:**
```
You are a Backend Engineer Agent in a multi-agent software development system.

## Your Role
- Design REST API endpoints based on requirements
- Define database schemas and relationships
- Specify authentication and authorization patterns
- Plan error handling and validation logic

## Input
You will receive:
- requirements.md from Product Manager
- Project technical stack information

## Output Requirements
You must produce TWO files:

1. api-contract.json:
   - OpenAPI 3.0 specification
   - All endpoints with methods, parameters, request/response schemas
   - Authentication requirements
   - Error response formats
   - Rate limiting specifications

2. schema.sql:
   - Database table definitions
   - Relationships and foreign keys
   - Indexes for performance
   - Sample data for development

## Guidelines
- Follow RESTful design principles
- Ensure API is versioned (v1, v2, etc.)
- Include pagination for list endpoints
- Specify comprehensive error codes
- Consider security (SQL injection, XSS prevention)
- Plan for scalability (caching strategies, etc.)

## Output Format
Write files to: /shared_state/api-contract.json and /shared_state/schema.sql
Use valid OpenAPI JSON and PostgreSQL-compatible SQL.
```

**agents/frontend/prompt.txt:**
```
You are a Frontend Engineer Agent in a multi-agent software development system.

## Your Role
- Plan React component architecture based on design specs
- Define state management strategy
- Specify API integration patterns
- Plan routing and navigation structure

## Input
You will receive:
- design-spec.md from Designer
- api-contract.json from Backend Engineer
- requirements.md from Product Manager

## Output Requirements
You must produce TWO files:

1. components-plan.md:
   - Component tree structure
   - Props interface for each component
   - Component responsibilities
   - Reusable component library
   - File/folder structure

2. state-management.md:
   - State architecture (Context, Redux, Zustand, etc.)
   - Global vs local state decisions
   - API data fetching strategy
   - Caching approach
   - Error boundary implementation

## Guidelines
- Follow React best practices
- Design for component reusability
- Consider code splitting and lazy loading
- Plan for loading states and error handling
- Think about testing strategy
- Ensure accessibility implementation

## Output Format
Write files to: /shared_state/components-plan.md and /shared_state/state-management.md
Use markdown with code examples where helpful.
```

### 3. Agent Manager Implementation

**agent_manager.py:**
```python
"""
Agent Manager - Handles individual agent execution
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from anthropic import Anthropic
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Agent:
    """Represents a single specialized agent"""

    def __init__(self, agent_id: str, agent_config: Dict[str, Any]):
        self.id = agent_id
        self.name = agent_config["name"]
        self.prompt_file = agent_config["prompt_file"]
        self.output_files = agent_config["output_files"]
        self.priority = agent_config.get("priority", 10)
        self.depends_on = agent_config.get("depends_on", [])
        self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

        # Load system prompt
        with open(self.prompt_file, 'r') as f:
            self.system_prompt = f.read()

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent with given context

        Args:
            context: Dictionary containing user request and shared state

        Returns:
            Dictionary with execution results and outputs
        """
        logger.info(f"🚀 Executing {self.name} agent...")

        # Build user message with context
        user_message = self._build_user_message(context)

        # Call Claude API
        try:
            response = self.client.messages.create(
                model=config.MODEL,
                max_tokens=4096,
                system=self.system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )

            # Extract response content
            response_text = response.content[0].text

            # Parse and save outputs
            outputs = self._process_outputs(response_text)

            result = {
                "agent_id": self.id,
                "agent_name": self.name,
                "status": "success",
                "outputs": outputs,
                "timestamp": datetime.now().isoformat()
            }

            logger.info(f"✅ {self.name} completed successfully")
            return result

        except Exception as e:
            logger.error(f"❌ {self.name} failed: {str(e)}")
            return {
                "agent_id": self.id,
                "agent_name": self.name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _build_user_message(self, context: Dict[str, Any]) -> str:
        """Build user message with all relevant context"""

        message_parts = [
            "# Task Context",
            f"\n## User Request\n{context.get('user_request', 'No request provided')}",
        ]

        # Include outputs from dependent agents
        if self.depends_on:
            message_parts.append("\n## Inputs from Other Agents")
            for dep_agent in self.depends_on:
                dep_outputs = context.get('agent_outputs', {}).get(dep_agent, {})
                if dep_outputs:
                    message_parts.append(f"\n### From {dep_agent} Agent:")
                    for file_name, content in dep_outputs.items():
                        message_parts.append(f"\n#### {file_name}\n```\n{content}\n```")

        # Include shared state
        shared_state = context.get('shared_state', {})
        if shared_state:
            message_parts.append("\n## Current Shared State")
            message_parts.append(f"```json\n{json.dumps(shared_state, indent=2)}\n```")

        return "\n".join(message_parts)

    def _process_outputs(self, response_text: str) -> Dict[str, str]:
        """Extract and save outputs from agent response"""

        outputs = {}

        # Simple parsing - look for file content in response
        # In production, you'd want more sophisticated parsing
        for output_file in self.output_files:
            # Try to find content between markers
            start_marker = f"# {output_file}"
            if start_marker in response_text:
                # Extract content after marker until next file or end
                start_idx = response_text.find(start_marker)
                content = response_text[start_idx:]

                # Find end (next file marker or end of response)
                next_file = None
                for other_file in self.output_files:
                    if other_file != output_file:
                        next_marker = f"# {other_file}"
                        if next_marker in content[len(start_marker):]:
                            next_idx = content.find(next_marker, len(start_marker))
                            content = content[:next_idx]
                            break

                # Save to shared state
                output_path = config.SHARED_STATE_DIR / output_file
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w') as f:
                    f.write(content)

                outputs[output_file] = content
                logger.info(f"  📄 Saved {output_file}")

        return outputs


class AgentManager:
    """Manages multiple agents and their execution"""

    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self._initialize_agents()

    def _initialize_agents(self):
        """Initialize all agents from configuration"""
        for agent_id, agent_config in config.AGENTS.items():
            self.agents[agent_id] = Agent(agent_id, agent_config)
        logger.info(f"Initialized {len(self.agents)} agents")

    def get_execution_order(self) -> List[List[str]]:
        """
        Determine execution order based on dependencies and priority
        Returns list of lists - each inner list can execute in parallel
        """
        # Build dependency graph
        remaining = set(self.agents.keys())
        execution_order = []

        while remaining:
            # Find agents with all dependencies satisfied
            ready = []
            for agent_id in remaining:
                agent = self.agents[agent_id]
                if all(dep not in remaining for dep in agent.depends_on):
                    ready.append(agent_id)

            if not ready:
                raise ValueError("Circular dependency detected in agent configuration")

            # Sort by priority
            ready.sort(key=lambda x: self.agents[x].priority)

            # Group by priority for parallel execution
            if config.PARALLEL_EXECUTION:
                priority_groups = {}
                for agent_id in ready:
                    priority = self.agents[agent_id].priority
                    if priority not in priority_groups:
                        priority_groups[priority] = []
                    priority_groups[priority].append(agent_id)

                for priority in sorted(priority_groups.keys()):
                    execution_order.append(priority_groups[priority])
                    remaining -= set(priority_groups[priority])
            else:
                for agent_id in ready:
                    execution_order.append([agent_id])
                    remaining.remove(agent_id)

        return execution_order

    def execute_agents(self, user_request: str) -> Dict[str, Any]:
        """
        Execute all agents in proper order

        Args:
            user_request: The user's task description

        Returns:
            Dictionary with all agent results
        """
        logger.info("=" * 60)
        logger.info("🎯 Starting Multi-Agent Orchestration")
        logger.info("=" * 60)

        # Initialize context
        context = {
            "user_request": user_request,
            "agent_outputs": {},
            "shared_state": self._load_shared_state()
        }

        # Get execution order
        execution_order = self.get_execution_order()
        logger.info(f"\n📋 Execution Plan: {execution_order}\n")

        # Execute agents
        all_results = {}

        for wave_idx, agent_wave in enumerate(execution_order, 1):
            logger.info(f"\n🌊 Wave {wave_idx}: {', '.join(agent_wave)}")

            wave_results = {}

            # Execute agents in this wave (can be parallel)
            for agent_id in agent_wave:
                agent = self.agents[agent_id]
                result = agent.execute(context)
                wave_results[agent_id] = result
                all_results[agent_id] = result

                # Update context with outputs
                if result["status"] == "success":
                    context["agent_outputs"][agent_id] = result["outputs"]

            # Update shared state after each wave
            self._save_shared_state(context["shared_state"])

        logger.info("\n" + "=" * 60)
        logger.info("✨ Multi-Agent Orchestration Complete")
        logger.info("=" * 60 + "\n")

        return {
            "status": "success",
            "results": all_results,
            "final_state": context["shared_state"]
        }

    def _load_shared_state(self) -> Dict[str, Any]:
        """Load shared state from disk"""
        if config.STATE_FILE.exists():
            with open(config.STATE_FILE, 'r') as f:
                return json.load(f)
        return {}

    def _save_shared_state(self, state: Dict[str, Any]):
        """Save shared state to disk"""
        config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.STATE_FILE, 'w') as f:
            json.dump(state, indent=2, fp=f)
```

### 4. Orchestrator Implementation

**orchestrator.py:**
```python
#!/usr/bin/env python3
"""
Main Orchestrator - Coordinates multi-agent execution
"""

import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any

from agent_manager import AgentManager
from config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Orchestrator:
    """Central orchestrator for multi-agent system"""

    def __init__(self):
        self.agent_manager = AgentManager()
        self.execution_history = []

    def run(self, user_request: str) -> Dict[str, Any]:
        """
        Execute multi-agent workflow

        Args:
            user_request: User's task description

        Returns:
            Final orchestration result
        """
        logger.info("\n" + "=" * 80)
        logger.info("🚀 MULTI-AGENT ORCHESTRATION SYSTEM")
        logger.info("=" * 80)
        logger.info(f"\n📝 User Request:\n{user_request}\n")

        # Execute agents
        result = self.agent_manager.execute_agents(user_request)

        # Record execution
        self.execution_history.append({
            "request": user_request,
            "result": result
        })

        # Generate summary
        self._print_summary(result)

        return result

    def _print_summary(self, result: Dict[str, Any]):
        """Print execution summary"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 EXECUTION SUMMARY")
        logger.info("=" * 80)

        for agent_id, agent_result in result["results"].items():
            status_icon = "✅" if agent_result["status"] == "success" else "❌"
            logger.info(f"{status_icon} {agent_result['agent_name']}: {agent_result['status']}")

            if agent_result["status"] == "success":
                outputs = agent_result.get("outputs", {})
                for file_name in outputs.keys():
                    logger.info(f"   📄 {file_name}")
            else:
                logger.error(f"   ⚠️  Error: {agent_result.get('error', 'Unknown error')}")

        logger.info("\n" + "=" * 80)
        logger.info(f"📁 Outputs saved to: {config.SHARED_STATE_DIR}")
        logger.info("=" * 80 + "\n")

    def validate_outputs(self) -> bool:
        """Validate that all expected outputs were generated"""
        if not config.ENABLE_VALIDATION:
            return True

        logger.info("\n🔍 Validating outputs...")

        all_valid = True
        for agent_id, agent_config in config.AGENTS.items():
            for output_file in agent_config["output_files"]:
                output_path = config.SHARED_STATE_DIR / output_file
                if not output_path.exists():
                    logger.error(f"❌ Missing output: {output_file} from {agent_id}")
                    all_valid = False
                else:
                    logger.info(f"✅ Found: {output_file}")

        return all_valid


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Orchestration System with Claude Code"
    )
    parser.add_argument(
        "request",
        nargs="?",
        help="User request/task description"
    )
    parser.add_argument(
        "--file",
        "-f",
        help="Read request from file"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate outputs after execution"
    )

    args = parser.parse_args()

    # Get user request
    if args.file:
        with open(args.file, 'r') as f:
            user_request = f.read()
    elif args.request:
        user_request = args.request
    else:
        # Interactive mode
        print("\n🤖 Multi-Agent Orchestration System")
        print("=" * 50)
        print("Enter your task description (press Enter twice to finish):\n")

        lines = []
        empty_count = 0
        while empty_count < 2:
            line = input()
            if line:
                lines.append(line)
                empty_count = 0
            else:
                empty_count += 1

        user_request = "\n".join(lines)

    if not user_request.strip():
        print("❌ No request provided. Exiting.")
        return

    # Run orchestration
    orchestrator = Orchestrator()
    result = orchestrator.run(user_request)

    # Validate if requested
    if args.validate:
        if orchestrator.validate_outputs():
            print("\n✅ All outputs validated successfully!")
        else:
            print("\n⚠️  Some outputs are missing. Check logs for details.")

    # Save execution log
    log_file = config.LOGS_DIR / f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n📋 Execution log saved to: {log_file}")


if __name__ == "__main__":
    from datetime import datetime
    main()
```

### 5. Requirements File

**requirements.txt:**
```
anthropic>=0.18.0
python-dotenv>=1.0.0
crewai>=0.20.0
langchain>=0.1.0
```

## 🧪 Running Your First Orchestration

### Example Usage

**Create .env file:**
```bash
ANTHROPIC_API_KEY=your_api_key_here
```

**Run orchestration:**
```bash
# Interactive mode
python orchestrator.py

# Direct command
python orchestrator.py "Build a todo list application with user authentication"

# From file
python orchestrator.py --file task_description.txt --validate
```

### Example Task

Create a file `task_description.txt`:
```
Build a modern todo list web application with the following features:

Core Features:
- User authentication (email/password)
- Create, read, update, delete todos
- Mark todos as complete/incomplete
- Filter todos by status (all, active, completed)
- Search todos by title

Technical Requirements:
- React frontend with TypeScript
- Node.js/Express backend
- PostgreSQL database
- JWT authentication
- RESTful API design
- Responsive design for mobile and desktop

Non-functional Requirements:
- Fast load times (< 2s initial load)
- Secure password storage
- Input validation on frontend and backend
- Accessible UI (WCAG 2.1 AA)
```

**Execute:**
```bash
python orchestrator.py --file task_description.txt --validate
```

### Expected Outputs

After execution, check `/shared_state/`:

1. **requirements.md** - Detailed requirements from PM Agent
2. **tasks.json** - Structured task breakdown
3. **design-spec.md** - UI/UX specifications
4. **wireframes.md** - Visual layout descriptions
5. **api-contract.json** - Complete API specification
6. **schema.sql** - Database schema
7. **components-plan.md** - React component architecture
8. **state-management.md** - State management strategy

## 🎯 Advanced Patterns

### Parallel Execution with Validation

**Add a validator agent:**

```python
# agents/validator/prompt.txt
You are a Validation Agent that reviews outputs from other agents.

## Your Role
- Check requirements for completeness and clarity
- Validate API contracts against requirements
- Ensure design specs match requirements
- Verify frontend plan implements all features

## Input
All outputs from PM, Design, Backend, and Frontend agents

## Output
validation-report.md with:
- Issues found (missing requirements, inconsistencies, etc.)
- Severity (critical, major, minor)
- Recommendations for fixes

If critical issues found, flag for re-execution.
```

### Feedback Loops

**Implement iterative refinement:**

```python
class Orchestrator:
    def run_with_feedback(self, user_request: str, max_iterations: int = 3):
        """Execute with validation and feedback loops"""

        for iteration in range(max_iterations):
            logger.info(f"\n🔄 Iteration {iteration + 1}/{max_iterations}")

            # Execute agents
            result = self.agent_manager.execute_agents(user_request)

            # Validate
            validator = Validator()
            validation_result = validator.validate(result)

            if validation_result["status"] == "pass":
                logger.info("✅ Validation passed!")
                return result

            # Provide feedback for next iteration
            user_request = self._generate_feedback_request(
                user_request,
                validation_result
            )

        logger.warning("⚠️  Max iterations reached")
        return result
```

## 🔒 Best Practices

### 1. Clear Agent Boundaries

**Good:**
```python
PM_AGENT_PROMPT = """
You define WHAT to build, not HOW.
Focus on requirements, acceptance criteria, and priorities.
Do not write code or make technical decisions.
"""

BACKEND_AGENT_PROMPT = """
You design HOW to implement the backend.
Focus on API contracts, database schemas, and architecture.
Do not define UI or user stories.
"""
```

**Bad:**
```python
GENERIC_AGENT_PROMPT = """
You help with software development.
Do whatever is needed.
"""
```

### 2. Structured Outputs

**Always specify exact output format:**
```python
api-contract.json must follow OpenAPI 3.0:
{
  "openapi": "3.0.0",
  "info": { ... },
  "paths": { ... },
  "components": { ... }
}
```

### 3. Dependency Management

**Explicit dependencies in config:**
```python
AGENTS = {
    "pm": {
        "depends_on": []  # No dependencies
    },
    "frontend": {
        "depends_on": ["pm", "design", "backend"]  # Clear dependencies
    }
}
```

### 4. Error Handling

**Graceful degradation:**
```python
def execute(self, context):
    try:
        return self._execute_with_retry(context, max_retries=3)
    except Exception as e:
        return {
            "status": "partial",
            "error": str(e),
            "fallback_outputs": self._generate_fallback()
        }
```

## 📊 Monitoring and Debugging

### Execution Logs

**Enhanced logging:**
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/orchestration.log'),
        logging.StreamHandler()
    ]
)
```

### Performance Tracking

```python
class PerformanceTracker:
    def track_agent_execution(self, agent_id: str, duration: float):
        """Track agent performance metrics"""
        metrics = {
            "agent_id": agent_id,
            "duration_seconds": duration,
            "tokens_used": self._count_tokens(),
            "timestamp": datetime.now().isoformat()
        }
        self._save_metrics(metrics)
```

## 🚀 Integration with Claude Code CLI

### Using Claude Code as Orchestrator

**Leverage Claude Code's built-in capabilities:**

```bash
# Use Claude Code to run orchestration
claude-code "Orchestrate my multi-agent system to build a blog platform"
```

**With MCP Server integration:**
```python
# Create an MCP tool for orchestration
@server.call_tool()
async def orchestrate_agents(name: str, arguments: Dict):
    if name == "run_orchestration":
        orchestrator = Orchestrator()
        result = orchestrator.run(arguments["task"])
        return [TextContent(type="text", text=json.dumps(result))]
```

## 🎉 Conclusion

You've now built a complete multi-agent orchestration system with Claude Code that can:

✅ Coordinate multiple specialized AI agents
✅ Execute tasks in parallel when dependencies allow
✅ Maintain shared state across agents
✅ Handle complex software development workflows
✅ Validate outputs and provide feedback
✅ Scale to additional agents as needed

### Key Takeaways

1. **Specialization > Generalization** - Focused agents outperform single general-purpose agents
2. **Clear Boundaries** - Well-defined roles prevent overlap and confusion
3. **Structured Communication** - Shared workspace and explicit outputs enable coordination
4. **Iterative Refinement** - Validation loops improve output quality
5. **Scalability** - Easy to add new agents without disrupting existing ones

### Next Steps

**Enhance your system:**
- Add code generation agents that write actual implementation
- Integrate testing agents for automated test creation
- Build deployment agents for CI/CD pipeline generation
- Create monitoring agents for production observability

**Advanced topics:**
- Dynamic agent selection based on task type
- Learning from execution history
- Cost optimization across agent executions
- Real-time collaboration with human developers

### Resources

- **CrewAI Documentation**: https://docs.crewai.com/
- **LangChain Multi-Agent**: https://python.langchain.com/docs/use_cases/agent_simulations/
- **Claude API Docs**: https://docs.anthropic.com/
- **OpenAPI Specification**: https://swagger.io/specification/

---

## 🏷️ Tags & Categories

**Tags**: AI, claude-code, agent-orchestration, multi-agent-systems, automation, python, crewai, langchain
**Categories**: AI, agent-orchestration, development-tools
**Difficulty**: Intermediate to Advanced
**Time to Complete**: 4-6 hours
