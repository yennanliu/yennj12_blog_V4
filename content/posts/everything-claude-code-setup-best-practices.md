---
title: "Everything Claude Code: The Ultimate Production-Ready Plugin Collection Guide"
date: 2026-01-24T16:30:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "tools"]
tags: ["Claude Code", "AI", "Development Tools", "MCP", "Agents", "Automation", "Best Practices", "Productivity", "Testing", "DevOps"]
summary: "Master the everything-claude-code repository: a comprehensive collection of production-ready agents, skills, hooks, and MCP configurations evolved over 10+ months of intensive use. Learn setup, best practices, and advanced techniques to supercharge your Claude Code workflow."
description: "Deep dive into the everything-claude-code repository by an Anthropic hackathon winner. Discover how to set up, customize, and leverage production-ready agents, skills, hooks, commands, and MCP configurations for maximum productivity with Claude Code."
readTime: "22 min"
---

The [everything-claude-code](https://github.com/affaan-m/everything-claude-code) repository represents one of the most comprehensive and battle-tested collections of Claude Code configurations available today. Created by an Anthropic hackathon winner and evolved over 10+ months of intensive daily use building real products, this repository had earned its 22.3k stars (as of January 2026) by providing production-ready solutions to common development challenges.

This post provides a complete guide to setting up, customizing, and mastering this powerful plugin collection, along with best practices learned from real-world usage.

## What is Everything Claude Code?

Think of it as a professional development team in a box. The repository provides a complete ecosystem of specialized components that transform Claude Code from a general-purpose AI assistant into a sophisticated development partner with deep knowledge of your workflows, standards, and infrastructure.

### **The Core Problem It Solves**

Working with Claude Code out of the box, developers face several challenges:

- **Repetitive Instructions**: Constantly re-explaining coding standards, testing requirements, and architectural patterns
- **Context Loss**: Starting fresh each session without memory of previous decisions
- **Manual Workflow**: Repeatedly performing the same multi-step processes (testing, code review, deployment)
- **Tool Overload**: Managing dozens of MCP servers and tools without clear organization
- **Inconsistent Quality**: Varying output quality depending on how well you prompt

The everything-claude-code repository systematically addresses each of these issues through five key component types.

## Repository Architecture: Five Pillars of Productivity

```
~/.claude/
├── agents/              # Specialized subagents for delegation
│   ├── planner/
│   ├── architect/
│   ├── tdd-engineer/
│   ├── code-reviewer/
│   ├── security-auditor/
│   ├── build-fixer/
│   ├── e2e-tester/
│   ├── refactorer/
│   └── documentor/
├── skills/              # Workflow definitions and patterns
│   ├── coding-standards/
│   ├── backend-patterns/
│   ├── frontend-patterns/
│   ├── tdd-methodology/
│   ├── security-review/
│   └── verification-loops/
├── commands/            # Slash commands for quick actions
│   ├── tdd.md
│   ├── plan.md
│   ├── e2e.md
│   ├── code-review.md
│   ├── build-fix.md
│   └── refactor-clean.md
├── rules/               # Always-enforced guidelines
│   ├── security.md
│   ├── coding-style.md
│   ├── testing.md
│   ├── git-workflow.md
│   └── performance.md
├── hooks/               # Event-triggered automations
│   ├── pre-tool-use/
│   ├── post-tool-use/
│   └── on-stop/
├── scripts/             # Cross-platform utilities
│   └── package-manager-detector.js
└── mcp-configs/         # Pre-configured MCP servers
    ├── github.json
    ├── supabase.json
    ├── vercel.json
    └── railway.json
```

### **1. Agents: Your Specialized Development Team**

Agents are specialized subagents designed for specific tasks. Each agent has deep expertise in its domain and follows proven patterns:

```markdown
# TDD Engineer Agent (agents/tdd-engineer/)

**Role**: Test-Driven Development specialist
**Expertise**: Writing tests first, implementing minimal code to pass

**Process**:
1. Understand requirements thoroughly
2. Write failing test cases
3. Implement minimal code to pass tests
4. Refactor while keeping tests green
5. Document test coverage

**Best Practices**:
- Start with edge cases
- One test at a time
- Clear test descriptions
- Comprehensive assertions
- Fast execution time
```

**Key Agents Available:**
- **Planner**: Breaks down complex features into actionable tasks
- **Architect**: Designs system architecture and makes technology decisions
- **TDD Engineer**: Implements features using test-driven development
- **Code Reviewer**: Performs comprehensive code reviews with security focus
- **Security Auditor**: Identifies vulnerabilities and suggests fixes
- **Build Fixer**: Diagnoses and resolves build failures
- **E2E Tester**: Creates and maintains end-to-end test suites
- **Refactorer**: Improves code quality while preserving functionality
- **Documentor**: Generates comprehensive technical documentation

### **2. Skills: Reusable Workflow Definitions**

Skills define standardized workflows that Claude Code follows automatically. They encode institutional knowledge and best practices:

```markdown
# Backend API Development Skill

## Workflow

### 1. Planning Phase
- Define API endpoints and methods
- Specify request/response schemas
- Identify authentication requirements
- Plan database schema changes

### 2. Implementation Phase
- Write integration tests first
- Implement route handlers
- Add input validation
- Implement business logic
- Add error handling

### 3. Testing Phase
- Unit tests for business logic
- Integration tests for endpoints
- Load testing for performance
- Security testing for vulnerabilities

### 4. Documentation Phase
- OpenAPI/Swagger specs
- Example requests/responses
- Error code documentation
- Authentication flow diagrams

## Quality Gates
- ✅ All tests passing
- ✅ 80%+ code coverage
- ✅ No security vulnerabilities
- ✅ API docs generated
- ✅ Performance benchmarks met
```

### **3. Commands: Quick Workflow Triggers**

Commands provide slash-command interfaces to common workflows:

```bash
# Available Commands
/tdd           # Start test-driven development workflow
/plan          # Create implementation plan
/e2e           # Generate end-to-end tests
/code-review   # Perform comprehensive code review
/build-fix     # Diagnose and fix build errors
/refactor-clean # Improve code quality
/setup-pm      # Configure package manager
/security      # Run security audit
/docs          # Generate documentation
```

Each command delegates to the appropriate agent with predefined parameters and workflows.

### **4. Rules: Always-Enforced Guidelines**

Rules are automatically applied to every Claude Code interaction, ensuring consistency:

```markdown
# Security Rules (Always Applied)

## Input Validation
- ALWAYS validate and sanitize all user input
- Use parameterized queries for database operations
- Never trust client-side validation alone

## Authentication & Authorization
- Verify authentication on every protected endpoint
- Implement least-privilege access control
- Use secure session management

## Data Protection
- Encrypt sensitive data at rest and in transit
- Never log passwords or tokens
- Use environment variables for secrets

## Dependencies
- Keep all dependencies up to date
- Review security advisories regularly
- Use lock files for deterministic builds

## Code Review Checklist
- [ ] No hardcoded secrets
- [ ] Input validation present
- [ ] Error messages don't leak info
- [ ] Authentication verified
- [ ] Authorization checked
```

### **5. Hooks: Event-Triggered Automation**

Hooks execute automatically in response to events, enabling powerful automations:

Hooks are configured under the `"hooks"` key of `settings.json` (`~/.claude/settings.json` for user scope, `.claude/settings.json` for a project); a plugin ships the same structure in its `hooks/hooks.json`. Each event takes a list of matchers, and each matcher runs one or more shell commands:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "node scripts/save-context.js" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "node scripts/run-tests.js" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "node scripts/session-summary.js" }]
      }
    ]
  }
}
```

## Installation: Two Approaches

### **Option 1: Plugin Marketplace (Recommended)**

The fastest and easiest method:

```bash
# In Claude Code: register the repository as a plugin marketplace
/plugin marketplace add affaan-m/everything-claude-code

# Install the plugin from that marketplace (check the repo README for the exact name)
/plugin install <plugin-name>@<marketplace-name>

# Review what is installed
/plugin
```

This method handles all file copying and configuration automatically, with built-in update support.

### **Option 2: Manual Installation**

For customization or offline environments:

```bash
# 1. Clone the repository
git clone https://github.com/affaan-m/everything-claude-code.git
cd everything-claude-code

# 2. Copy components to Claude Code directory
# On macOS/Linux:
cp -r agents ~/.claude/agents
cp -r skills ~/.claude/skills
cp -r commands ~/.claude/commands
cp -r rules ~/.claude/rules
cp -r hooks ~/.claude/hooks
cp -r scripts ~/.claude/scripts
cp -r mcp-configs ~/.claude/mcp-configs

# On Windows (PowerShell):
Copy-Item -Recurse -Force agents $env:USERPROFILE\.claude\agents
Copy-Item -Recurse -Force skills $env:USERPROFILE\.claude\skills
Copy-Item -Recurse -Force commands $env:USERPROFILE\.claude\commands
Copy-Item -Recurse -Force rules $env:USERPROFILE\.claude\rules
Copy-Item -Recurse -Force hooks $env:USERPROFILE\.claude\hooks
Copy-Item -Recurse -Force scripts $env:USERPROFILE\.claude\scripts
Copy-Item -Recurse -Force mcp-configs $env:USERPROFILE\.claude\mcp-configs

# 3. Install script dependencies
cd ~/.claude/scripts
npm install

# 4. Restart Claude Code
```

### **Post-Installation Configuration**

After installation, customize for your environment:

```bash
# 1. Keep only what you use: subagents are active if their file is in
#    ~/.claude/agents/ (or .claude/agents/), and hooks are the ones listed
#    under "hooks" in ~/.claude/settings.json
ls ~/.claude/agents/

# 2. Set up MCP servers
# Edit ~/.claude/mcp-configs/github.json
{
  "github": {
    "token": "${GITHUB_TOKEN}",
    "repo": "your-org/your-repo"
  }
}

# 3. Customize rules for your stack
# Edit ~/.claude/rules/coding-style.md to match your team's standards
```

## Critical Best Practice: Context Window Management

**This is the most important lesson from the repository's documentation.**

Claude Code has a 200k token context window, but poor configuration can shrink effective capacity to 70k tokens. The culprit? Too many MCP servers and tools active simultaneously.

### **The Problem**

```
# ❌ BAD: Too many active tools
~/.claude/mcp-configs/
├── github.json          # 15 tools
├── gitlab.json          # 12 tools
├── supabase.json        # 20 tools
├── firebase.json        # 18 tools
├── vercel.json          # 8 tools
├── railway.json         # 6 tools
├── aws.json             # 30 tools
├── docker.json          # 25 tools
└── kubernetes.json      # 35 tools

Total: 169 tools loaded into every conversation!
Context consumed: ~130k tokens just for tool definitions
Remaining for code: ~70k tokens
```

### **The Solution: Project-Specific MCP Configurations**

```bash
# ✅ GOOD: Project-specific configuration
~/projects/web-app/.mcp.json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"]
    },
    "supabase": {
      "command": "npx",
      "args": ["-y", "@supabase/mcp-server-supabase@latest"]
    }
  }
}

# Result: ~40 tools total
# Context consumed: ~30k tokens
# Remaining for code: ~170k tokens
```

### **Context Optimization Guidelines**

From the repository's best practices:

1. **Fewer than 10 MCP servers per project** - More than this significantly degrades performance
2. **Under 80 total active tools** - Each tool definition consumes ~200 tokens
3. **Project-specific configurations** - Different MCP servers for different projects
4. **Disable unused tools** - Even within enabled MCPs, disable tools you don't need
5. **Monitor token usage** - Use `/context` to see current consumption

### **Practical Example: E-commerce Project**

```json
// ~/projects/ecommerce/.mcp.json (JSON itself does not allow comments)
{
  "mcpServers": {
    "github":   { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"] },
    "supabase": { "command": "npx", "args": ["-y", "@supabase/mcp-server-supabase@latest"] },
    "vercel":   { "command": "npx", "args": ["-y", "<vercel-mcp-package>"] }
  }
}
// Payment processing (Stripe) is left out; add it only for the sessions that need it:
//   claude mcp add stripe -- <command>
```

## Workflow Patterns: Real-World Usage

### **Pattern 1: Feature Development with TDD**

```bash
# 1. Start with planning
/plan implement user authentication with JWT

# Claude delegates to Planner agent, creates task breakdown

# 2. Begin TDD workflow
/tdd

# TDD Engineer agent activated:
# - Writes failing tests
# - Implements minimal code
# - Refactors
# - Documents

# 3. Code review before committing
/code-review

# Code Reviewer agent checks:
# - Code quality
# - Security issues
# - Test coverage
# - Documentation

# 4. Fix any issues found
# Claude automatically fixes issues based on review

# 5. Commit with generated message
git add .
git commit -m "feat: implement JWT authentication

- Add JWT token generation and validation
- Implement secure password hashing
- Add authentication middleware
- Test coverage: 95%

Co-authored-by: Claude Code <noreply@anthropic.com>"
```

### **Pattern 2: Build Error Resolution**

```bash
# You see build errors
npm run build
# Error: Module not found: 'react-router-dom'

# Quick fix with specialized agent
/build-fix

# Build Fixer agent:
# 1. Analyzes error output
# 2. Identifies root cause (missing dependency)
# 3. Proposes solution
# 4. Executes fix (npm install react-router-dom)
# 5. Verifies build succeeds
# 6. Commits fix if needed
```

### **Pattern 3: Security Audit**

```bash
# Before production deployment
/security

# Security Auditor agent:
# 1. Scans for common vulnerabilities
# 2. Checks dependency security
# 3. Reviews authentication/authorization
# 4. Validates input sanitization
# 5. Checks for secret leaks
# 6. Generates security report

# Output:
# ✅ No hardcoded secrets found
# ❌ SQL injection risk in user search endpoint
# ❌ Missing rate limiting on login endpoint
# ⚠️  3 dependencies with known vulnerabilities

# Claude automatically creates issues for each finding
# and can fix them immediately with your approval
```

### **Pattern 4: Comprehensive Refactoring**

```bash
# Legacy code needs improvement
/refactor-clean src/components/UserProfile.jsx

# Refactorer agent:
# 1. Analyzes code structure
# 2. Identifies improvement opportunities:
#    - Extract reusable hooks
#    - Reduce component complexity
#    - Improve naming
#    - Add TypeScript types
#    - Optimize renders
# 3. Refactors incrementally
# 4. Runs tests after each change
# 5. Ensures no functionality breaks
```

## Advanced Techniques

### **1. Custom Agent Creation**

Create specialized agents for your domain:

```markdown
# ~/.claude/agents/api-integration-specialist/

**Role**: Third-party API integration expert
**Expertise**: REST APIs, GraphQL, webhooks, rate limiting, retries

**Process**:
1. Review API documentation
2. Design client wrapper with error handling
3. Implement rate limiting and retries
4. Write integration tests with mocks
5. Create usage examples

**Tech Stack Familiarity**:
- axios/fetch for HTTP requests
- graphql-request for GraphQL
- node-cache for response caching
- p-retry for retry logic

**Quality Standards**:
- Comprehensive error handling
- Request/response logging
- API key management via env vars
- Automatic token refresh
- Circuit breaker pattern
```

**Usage:**
```bash
/agent api-integration-specialist "integrate Stripe payment API"
```

### **2. Custom Skills for Your Stack**

Define workflows specific to your technology:

```markdown
# ~/.claude/skills/nextjs-fullstack/

## Next.js Full-Stack Feature Development

### 1. Component Development
- Create React Server Component
- Add client interactivity with 'use client' where needed
- Implement loading and error states
- Add Suspense boundaries

### 2. API Route Development
- Create route handler in app/api/
- Implement request validation with Zod
- Add authentication middleware
- Return proper status codes

### 3. Database Integration
- Define Prisma schema
- Generate migrations
- Implement CRUD operations
- Add database indexes

### 4. Testing Strategy
- Component tests with React Testing Library
- API tests with supertest
- E2E tests with Playwright
- Visual regression tests

### 5. Performance Optimization
- Implement React Server Components
- Add proper caching headers
- Optimize images with next/image
- Use dynamic imports for code splitting
```

### **3. Hook Chains for Advanced Automation**

Chain multiple hooks for complex workflows:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{ "type": "command", "command": "node scripts/backup-files.js" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command", "command": "node scripts/format-code.js" },
          { "type": "command", "command": "node scripts/run-tests.js" }
        ]
      }
    ]
  }
}
```

There is no built-in "only if all tests passed" condition: put that logic inside the script itself (e.g. have `run-tests.js` call `update-docs.js` only on success). A hook command signals failure through its exit code, which Claude Code reports back.

### **4. Verification Loops for Quality Assurance**

Implement continuous validation:

````markdown
# ~/.claude/skills/verification-loop/

## Continuous Verification Pattern

### Checkpoint Model
After each significant change:
1. Run affected tests
2. Check type errors
3. Verify build succeeds
4. Update documentation

### Continuous Evaluation Model
Before marking task complete:
1. Full test suite passes
2. No TypeScript errors
3. No linting errors
4. Code coverage > 80%
5. Security scan passes
6. Performance benchmarks met

### Grader Configuration
```yaml
graders:
  - type: test
    command: npm test
    threshold: 100%

  - type: coverage
    command: npm run coverage
    threshold: 80%

  - type: security
    command: npm audit
    severity: high

  - type: performance
    command: npm run benchmark
    threshold: 95  # 95th percentile < 100ms
```
````

## Common Pitfalls and Solutions

### **Pitfall 1: Agent Overload**

**Problem**: Enabling all agents makes Claude Code slow and confused.

**Solution**: Enable only agents you actively use:

```bash
# Subagents are enabled by their presence in ~/.claude/agents/ (or .claude/agents/).
# Park the ones you only need occasionally:
mkdir -p ~/.claude/agents-parked
mv ~/.claude/agents/architect.md ~/.claude/agents/security-auditor.md ~/.claude/agents-parked/
# Keep tdd-engineer, code-reviewer, build-fixer for daily work
```

**Pro tip**: Run `/agents` inside Claude Code to see and manage the available subagents.

### **Pitfall 2: Conflicting Rules**

**Problem**: Multiple rule files with contradicting guidelines confuse Claude.

**Solution**: Consolidate and prioritize rules:

```markdown
# ~/.claude/rules/consolidated.md

## Rule Priority System

### P0: Security (Never Compromise)
- Input validation
- Authentication/authorization
- Secret management

### P1: Correctness (Rarely Compromise)
- Type safety
- Error handling
- Test coverage

### P2: Style (Compromise for readability)
- Naming conventions
- Code formatting
- Comment style

### P3: Performance (Compromise for clarity)
- Optimization techniques
- Caching strategies
- Algorithm choices

When rules conflict, higher priority wins.
```

### **Pitfall 3: Hook Cascades**

**Problem**: Hooks triggering other hooks creates infinite loops.

**Solution**: Implement circuit breakers:

```javascript
// scripts/run-tests-with-circuit-breaker.js
let executionCount = 0;
const MAX_EXECUTIONS = 3;

export async function hook({ event, context }) {
  executionCount++;

  if (executionCount > MAX_EXECUTIONS) {
    console.log('Circuit breaker activated - too many hook executions');
    return { skip: true };
  }

  // Run tests
  const result = await runTests();

  // Reset counter on success
  if (result.success) {
    executionCount = 0;
  }

  return result;
}
```

### **Pitfall 4: Stale Context Accumulation**

**Problem**: Session context grows unbounded, degrading performance.

**Solution**: Hooks cannot rewrite the conversation history, so prune with the built-in commands instead: check usage with `/context`, run `/compact [focus instructions]` to summarise the session so far, and `/clear` when you switch to an unrelated task. Durable decisions belong in `CLAUDE.md`, not in the running session.

## Customization Strategies

### **Strategy 1: Start Minimal, Add Incrementally**

Don't enable everything at once. Follow this adoption path:

**Week 1: Core Workflow**
```bash
# Enable only:
- commands/tdd.md
- rules/security.md
- rules/testing.md
```

**Week 2: Add Code Quality**
```bash
# Add:
- commands/code-review.md
- agents/code-reviewer/
- rules/coding-style.md
```

**Week 3: Add Automation**
```bash
# Add:
- hooks/post-tool-use/run-tests
- hooks/on-stop/session-summary
```

**Month 2: Advanced Features**
```bash
# Add:
- agents/architect/
- skills/backend-patterns/
- verification-loops
```

### **Strategy 2: Team-Specific Customization**

Create team variations:

```bash
# Backend team configuration
~/.claude/profiles/backend/
├── agents/
│   ├── api-designer/
│   └── database-optimizer/
├── skills/
│   ├── microservices-patterns/
│   └── database-design/
└── mcp-configs/
    ├── supabase.json
    └── railway.json

# Frontend team configuration
~/.claude/profiles/frontend/
├── agents/
│   ├── component-builder/
│   └── accessibility-auditor/
├── skills/
│   ├── react-patterns/
│   └── design-system/
└── mcp-configs/
    ├── vercel.json
    └── figma.json
```

**Switch profiles**: Claude Code has no built-in profile switch; copy (or symlink) the relevant profile's `agents/` and `skills/` into the project's `.claude/` directory and its MCP servers into the project's `.mcp.json`.

### **Strategy 3: Project Templates**

Create starter templates for different project types:

```bash
# Create template
~/.claude/templates/fullstack-nextjs/
├── .claude/
│   ├── agents/         # Relevant agents
│   ├── skills/         # Stack-specific skills
│   ├── rules/          # Project conventions
│   └── settings.json   # Permissions and hooks
├── .mcp.json           # Required MCPs
├── .gitignore
├── package.json
└── README.md

# Use template: copy it into the new project
cp -r ~/.claude/templates/fullstack-nextjs/.claude ~/.claude/templates/fullstack-nextjs/.mcp.json ./
```

## Performance Monitoring

Track your productivity gains:

The simplest signals are the ones Claude Code already exposes: `/context` for context usage in the current session and `/cost` for token spend. For longer-term trends, compare your own before/after numbers (PR cycle time, review turnaround) rather than relying on estimated "time saved".

## Contributing Back to the Repository

The repository welcomes contributions. Here's how to add value:

### **1. Share Your Custom Agents**

```bash
# 1. Create your agent
~/.claude/agents/my-custom-agent/

# 2. Test thoroughly: place it in a test project's .claude/agents/
#    and ask Claude to delegate a task to it

# 3. Document clearly
# Add comprehensive README with examples

# 4. Submit PR
git clone https://github.com/affaan-m/everything-claude-code.git
cd everything-claude-code
git checkout -b agent/my-custom-agent
# Add your agent to agents/
git push origin agent/my-custom-agent
# Create PR with detailed description
```

### **2. Report Issues with Context**

When reporting bugs:
````markdown
**Issue**: Hook infinite loop with TypeScript watch mode

**Environment**:
- OS: macOS 14.2
- Claude Code version: 1.5.0
- Node.js: 20.10.0
- Package manager: pnpm 8.15.0

**Configuration**:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "node run-tests.js" }]
      }
    ]
  }
}
```

**Steps to Reproduce**:
1. Edit TypeScript file
2. Hook triggers tsc --watch
3. Watcher detects changes
4. Hook triggers again
5. Infinite loop

**Expected**: Hook should detect watcher and skip
**Actual**: Infinite loop until manual intervention
````

### **3. Improve Documentation**

The repository values clear documentation:
- Add more usage examples
- Create video tutorials
- Write troubleshooting guides
- Translate to other languages

## Integration with CI/CD

Extend the patterns to your CI pipeline:

```yaml
# .github/workflows/claude-code-review.yml
name: Claude Code Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Claude Code
        run: |
          npm install -g @anthropic/claude-code
          # Copy repository agents/skills
          cp -r .claude-config/* ~/.claude/

      - name: Run Code Review
        run: |
          claude code /code-review --pr ${{ github.event.pull_request.number }}

      - name: Post Review Comments
        uses: actions/github-script@v7
        with:
          script: |
            // Post Claude's findings as PR comments
            const review = require('./claude-review.json');
            github.rest.pulls.createReview({
              owner: context.repo.owner,
              repo: context.repo.repo,
              pull_number: context.issue.number,
              body: review.summary,
              event: 'COMMENT',
              comments: review.findings
            });
```

## Troubleshooting Guide

### **Problem: "Agent not found" error**

```bash
# Subagents are Markdown files with YAML front matter
ls ~/.claude/agents/ .claude/agents/

# Check the front matter has a name and description
head -n 10 .claude/agents/tdd-engineer.md

# Inside Claude Code: list and manage subagents
/agents
```

### **Problem: Hooks not triggering**

```bash
# Start Claude Code with debug output to see hook execution
claude --debug

# Inside Claude Code: review the registered hooks
/hooks

# Verify hook script exists and runs on its own
ls -la ~/.claude/scripts/run-tests.js
node ~/.claude/scripts/run-tests.js
```

### **Problem: Context window exceeded**

```bash
# Inside Claude Code: see what is using the context
/context

# Summarise the session, or start fresh for a new task
/compact
/clear

# Remove MCP servers you are not using
claude mcp list
claude mcp remove docker

# Prefer a project-scoped .mcp.json with only the servers this repo needs
```

### **Problem: Slow response times**

```text
Common causes:
1. Too many active MCP tools: check `claude mcp list` and remove unused servers
2. Large context history: check `/context`, then `/compact` or `/clear`
3. Expensive hooks: review them with `/hooks` and temporarily remove slow ones
4. Slow MCP servers: `/mcp` shows each server's connection status
```

## Conclusion: From Good to Great

The everything-claude-code repository represents the evolution of Claude Code from a helpful assistant to an indispensable development partner. By encoding workflows, standards, and institutional knowledge into agents, skills, and rules, you create a system that improves with every interaction.

### **Key Takeaways**

1. **Start Minimal**: Don't enable everything at once. Add components as you identify needs.

2. **Context is King**: Manage your context window carefully. Fewer than 10 MCPs per project, under 80 total tools.

3. **Customize Relentlessly**: The provided agents and skills are starting points. Adapt them to your stack, team, and domain.

4. **Automate Incrementally**: Use hooks to automate repetitive tasks, but add circuit breakers to prevent cascades.

5. **Measure Impact**: Track time saved and quality improvements to justify continued investment.

6. **Contribute Back**: Share your improvements with the community. Your custom agents might solve others' problems.

### **Next Steps**

1. **Install the repository** using your preferred method
2. **Enable TDD workflow** for your next feature
3. **Add code review automation** to your PR process
4. **Create your first custom agent** for domain-specific work
5. **Optimize your MCP configuration** for better performance
6. **Share your experience** in the repository discussions

The repository is MIT licensed and actively maintained. Whether you're a solo developer or part of a large engineering organization, these battle-tested patterns can transform your development workflow.

Start with what resonates. Modify for your stack. Remove what you don't use. Add your own patterns. The goal isn't to use every feature—it's to use the right features for your context.

**Repository**: [github.com/affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code)
**Stars**: 22.3k | **Forks**: 2.7k | **License**: MIT

---

*Have you customized Claude Code with your own agents or skills? Share your patterns in the comments below or contribute to the repository!*
