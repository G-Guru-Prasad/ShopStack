# AI Agent Use Case: Internal Documentation Q&A Bot

## Overview
This use case describes a small AI agent system that answers questions from internal company documentation such as runbooks, onboarding guides, deployment procedures, and technical policies.

The system is designed to be practical for a software engineer to build because the scope is narrow, the workflow is easy to understand, and each component has a clear responsibility.

## Problem
Teams often waste time searching across internal documentation to answer repeat questions such as:

- How do we deploy to staging?
- What is the rollback process?
- Where is the onboarding checklist?
- What is the approved way to manage secrets?

A basic chatbot can answer these questions, but it may hallucinate steps, expose unsafe information, or return incomplete responses.

## Solution
Build an AI documentation assistant with four components:

1. Guardrails
2. Task agent
3. Orchestrator
4. Verifier

This architecture improves safety, accuracy, and maintainability.

## Components

### Guardrails
The guardrails component checks the user input before it reaches the main task agent.

Responsibilities:
- Block unsafe or policy-violating questions.
- Detect sensitive requests such as passwords, secrets, API keys, or bypass instructions.
- Normalize and classify the request into a structured format.
- Enforce input and output schema rules.

Example:
A question like "How do I get the production database password?" should be rejected or redirected to a safe policy response.

### Task agent
The task agent performs the core work.

Responsibilities:
- Understand the user intent.
- Retrieve relevant documentation from internal sources.
- Summarize the retrieved content.
- Ask clarifying questions when the request is ambiguous.

Example:
For the question "How do I deploy to staging?" the task agent can search deployment runbooks, select the relevant section, and produce a short step-by-step answer.

### Orchestrator
The orchestrator controls the workflow between agents.

Responsibilities:
- Send the user input to guardrails first.
- Route approved requests to the task agent.
- Send the draft answer to the verifier.
- Retry or refine the answer when verification fails.
- Keep track of conversation state and execution limits.

The orchestrator is useful because it separates coordination logic from task logic.

### Verifier
The verifier checks whether the drafted answer is grounded in the source material and whether it is safe to return.

Responsibilities:
- Compare the answer against retrieved documentation.
- Detect unsupported claims or hallucinated steps.
- Flag dangerous instructions.
- Approve, reject, or request revision.

Example:
If the task agent says to run `./deploy.sh staging` but the documentation says the correct command is `./deploy.sh --env staging`, the verifier should reject the draft and request correction.

## Example workflow

### User question
"How do I deploy to staging?"

### Step 1: Guardrails
The input is checked for safety and converted into a structured request.

Example structured output:

```json
{
  "topic": "infrastructure",
  "intent": "get_steps",
  "question": "How do I deploy to staging?"
}
```

### Step 2: Task agent
The task agent retrieves the relevant deployment documents and generates a concise answer.

Example draft:
- Switch to the correct branch.
- Run the staging deploy command.
- Wait for CI to finish.
- Verify the service health endpoint.

### Step 3: Verifier
The verifier checks the draft against the actual runbook or scripts.

Possible outcomes:
- Pass: the answer matches the source.
- Fail: the answer contains a wrong command, missing step, or unsupported assumption.

### Step 4: Orchestrator
If verification passes, the answer is returned to the user. If verification fails, the orchestrator sends the task back for correction.

## Why this is a good starter project
This is a good starter AI agent project for a software engineer because:

- It solves a real internal productivity problem.
- It has a clear retrieval-based workflow.
- It is small enough to prototype quickly.
- Each agent has an isolated responsibility.
- The same architecture can later be reused for support bots, HR bots, incident assistants, or codebase Q&A tools.

## Minimal technical design
A simple implementation can use the following stack:

- LLM for reasoning and summarization.
- Vector database for document retrieval.
- Rule engine or policy layer for guardrails.
- Orchestration layer to chain steps.
- Verification pass using either another LLM or rule-based checks against the source snippets.

## Success criteria
A first version is useful if it can:

- Answer a narrow set of internal documentation questions.
- Refuse unsafe requests consistently.
- Cite or point to the source document section.
- Reduce hallucinations through verification.
- Produce short, reliable, operational answers.

## Extension ideas
After building the first version, the system can be extended to:

- Add source citations in every answer.
- Support Slack or Microsoft Teams.
- Handle codebase questions along with docs.
- Add approval flows for sensitive actions.
- Log verifier failures for continuous improvement.
