# Prompt for storing and improving conversational state.

## The problem:
Currently, the MCP server tools (create and update form) alongside their /gpt/* equivalents do not use the conversation history while creating the form. This creates a suboptimal conversational experience with the MCP server by causing many back and forth conversations with the user. On many occasions, the user gives up because they are not able to create the signup forms.

## The goal:
We want to utilize the user and the system's conversation history while creating forms. Considering we use LLMs, we want to pass this conversation history so that have all the information to create forms with quicker back and forth.

## The task:
1. Create a plan to build this future (research third party libraries if necessary).
2. Document this plan in the docs/ directory and split the plan into set of incremental tasks.
3. For each task, create a description of each task (its input, output and the business logic).
4. Optimize of reusability, if a third party library can help preserve and pass conversational history to LLMs use that instead of trying to implement the own.

## Constraints:
1. Forms properties are held in in-memory until they are ready to be published. We don't want to store the temporary form properties in DB.
2. We want a single tool (`create_or_update_form`) instead of 2 separate tools to create or update the form.
3. A published form can not be updated.
4. Once we are happy with the `create_or_update` form tool (or /gpt endpoint), we will deprecate `create_form` and `update_form` tools.
